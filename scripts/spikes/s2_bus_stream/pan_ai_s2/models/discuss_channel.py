"""Spike S2: a `discuss.channel` of type `ai`, a fake Pydantic AI model that
streams, and the run's events batched over the bus into the agent's message.

Measured, not designed: the module is throwaway. What it must show is in
README.md of the spike directory.
"""

import asyncio
import json
import logging
import time

from markdown2 import markdown
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolReturnPart,
)
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.tools import html_sanitize

_logger = logging.getLogger(__name__)

BATCH_SECONDS = 0.1
TOKEN_SECONDS = 0.02  # a plausible model: ~50 tokens a second

ANSWER = (
    "There are **twelve** open sales orders. The three largest:\n\n"
    "| Order | Customer | Amount |\n|---|---|---|\n"
    "| S00042 | Azure Interior | 4,200.00 |\n"
    "| S00039 | Deco Addict | 3,150.00 |\n"
    "| S00037 | Gemini Furniture | 2,980.00 |\n\n"
    "Want me to open the list?"
)


def _tokens(text):
    # Word-ish chunks, the way a model streams.
    out, cur = [], ""
    for ch in text:
        cur += ch
        if ch in " \n|":
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


async def _stream_function(messages, info):
    """First round: one tool call. Second round: the answer, token by token."""
    seen_tool_return = any(
        isinstance(p, ToolReturnPart) for m in messages for p in getattr(m, "parts", [])
    )
    if not seen_tool_return:
        await asyncio.sleep(0.15)
        yield {0: DeltaToolCall(name="search_sales_orders", json_args='{"state": "sale"}', tool_call_id="c1")}
        return
    await asyncio.sleep(0.15)
    for tok in _tokens(ANSWER):
        await asyncio.sleep(TOKEN_SECONDS)
        yield tok


def _build_agent():
    agent = Agent(FunctionModel(stream_function=_stream_function))

    @agent.tool_plain
    def search_sales_orders(state: str) -> str:
        """Count the sales orders in a state."""
        time.sleep(0.05)
        return "12 found"

    return agent


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    channel_type = fields.Selection(selection_add=[("ai", "AI")], ondelete={"ai": "cascade"})

    @api.model
    def pan_ai_s2_new_chat(self):
        agent = self.env.ref("pan_ai_s2.partner_agent")
        channel = self.create(
            {
                "name": "AI Pro",
                "channel_type": "ai",
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.env.user.partner_id.id}),
                    (0, 0, {"partner_id": agent.id}),
                ],
            }
        )
        return channel.id

    @api.model
    def pan_ai_s2_report(self, data):
        self.env["ir.config_parameter"].sudo().set_str("pan_ai_s2.report", json.dumps(data))
        return True

    @api.model
    def pan_ai_s2_stop(self, message_id):
        self.env["ir.config_parameter"].sudo().set_str(f"pan_ai_s2.stop.{message_id}", "1")
        return True

    def _pan_ai_s2_stopped(self, message_id):
        with self.pool.cursor() as cr:
            cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (f"pan_ai_s2.stop.{message_id}",))
            return bool(cr.fetchone())

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        agent = self.env.ref("pan_ai_s2.partner_agent")
        if self.channel_type == "ai" and message.author_id != agent:
            self._pan_ai_s2_respond(message, agent)
        return message

    def _pan_ai_s2_respond(self, user_message, agent_partner):
        channel = self.sudo()
        placeholder = channel.message_post(
            author_id=agent_partner.id,
            body="Thinking",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        msg_id = placeholder.id
        # The user's message and the placeholder reach the browser now, not
        # at the end of the run.
        self.env.cr.commit()

        batch = []
        last_flush = time.monotonic()
        text = []
        stats = {"batches": 0, "events": 0, "first_delta_sent_at": None, "stopped": False, "t0": time.time()}

        def flush(final=False):
            if not batch and not final:
                return
            sent_at = time.time()
            if stats["first_delta_sent_at"] is None and any(e["type"] == "delta" for e in batch):
                stats["first_delta_sent_at"] = sent_at
            channel._bus_send(
                "pan_ai.run_event",
                {"message_id": msg_id, "events": list(batch), "sent_at": sent_at, "final": final},
            )
            batch.clear()
            stats["batches"] += 1
            self.env.cr.commit()

        def on_event(ev):
            stats["events"] += 1
            batch.append(ev)
            if ev["type"] == "delta":
                text.append(ev["text"])
            nonlocal last_flush
            now = time.monotonic()
            if ev["type"] != "delta" or now - last_flush >= BATCH_SECONDS:
                flush()
                last_flush = now

        async def run():
            agent = _build_agent()
            async with agent.run_stream_events("How many open sales orders are there?") as events:
              async for event in events:
                  if self._pan_ai_s2_stopped(msg_id):
                      stats["stopped"] = True
                      return
                  if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                      if event.part.content:
                          on_event({"type": "delta", "text": event.part.content})
                  elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                      on_event({"type": "delta", "text": event.delta.content_delta})
                  elif isinstance(event, FunctionToolCallEvent):
                      on_event({"type": "tool_call", "id": event.part.tool_call_id, "name": event.part.tool_name, "args": event.part.args_as_json_str()})
                  elif isinstance(event, FunctionToolResultEvent):
                      on_event({"type": "tool_result", "id": event.part.tool_call_id, "summary": str(event.part.content)[:200]})
                  elif isinstance(event, FinalResultEvent):
                      on_event({"type": "final_result"})

        asyncio.run(run())
        final_text = "".join(text)
        if stats["stopped"]:
            final_text = final_text + "\n\n*Stopped.*"
        placeholder.write({"body": html_sanitize(markdown(final_text, extras=["tables", "fenced-code-blocks"]))})
        Store(bus_channel=channel).add(placeholder, ["body"])
        batch.append({"type": "run_finished", "stats": {k: v for k, v in stats.items() if k != "t0"}})
        flush(final=True)
        _logger.warning("[pan_ai_s2] run done in %.2fs: %s", time.time() - stats["t0"], stats)
