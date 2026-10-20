# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Spike S4: a run in slices. `agent.iter()` stopped at a budget, the
messages persisted, the next slice on a worker cron woken with
`ir.cron._trigger()`. Chat runs start inline in the request; everything
past the first budget, and every continuous tick, runs on a cron.

Throwaway. What it must show is in the spike README.
"""

import asyncio
import json
import psycopg2
import logging
import os
import random
import threading
import time
from datetime import datetime, timedelta

from markdown2 import markdown
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessagesTypeAdapter,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_core import to_jsonable_python

from odoo import api, fields, models
from odoo.tools import config
from odoo.addons.mail.tools.discuss import Store
from odoo.tools import html_sanitize

_logger = logging.getLogger(__name__)

BATCH_SECONDS = 0.1
STALE_SECONDS = 20  # a claim whose heartbeat is older than this is a dead worker's


def _worker():
    return f"{os.getpid()}:{threading.get_ident()}"


def _fake_model(steps, step_seconds, before_step=None):
    """A model that asks for `steps` tool calls after the last user prompt,
    then streams a short answer. Tick prompts get a one-line answer."""

    async def stream_fn(messages, info):
        last_prompt = ""
        done = 0
        for m in messages:
            for p in getattr(m, "parts", []):
                if isinstance(p, UserPromptPart):
                    last_prompt = str(p.content)
                    done = 0
                elif isinstance(p, ToolReturnPart):
                    done += 1
        await asyncio.sleep(0.1)
        if last_prompt.startswith("tick"):
            for tok in ["Noted ", last_prompt, ". Memory holds ", str(sum(1 for m in messages for p in getattr(m, 'parts', []) if isinstance(p, UserPromptPart))), " prompts."]:
                yield tok
            return
        if done < steps:
            yield {0: DeltaToolCall(name="step", json_args=json.dumps({"n": done + 1}), tool_call_id=f"c{done + 1}")}
            return
        for tok in ["All ", str(steps), " steps ", "done."]:
            await asyncio.sleep(0.02)
            yield tok

    agent = Agent(FunctionModel(stream_function=stream_fn))

    @agent.tool_plain
    def step(n: int) -> str:
        """One step of the long task."""
        seconds = before_step() if before_step else step_seconds
        time.sleep(seconds)
        return f"step {n} ok"

    return agent


class Thread(models.Model):
    _name = "pan_ai_s4.thread"
    _description = "AI Pro S4 thread"

    channel_id = fields.Many2one("discuss.channel", required=True, ondelete="cascade")
    message_id = fields.Integer(help="The agent's placeholder mail.message")
    kind = fields.Selection([("chat", "Chat"), ("continuous", "Continuous")], default="chat", required=True)
    state = fields.Selection([("running", "Running"), ("done", "Done"), ("failed", "Failed")], default="running", required=True, index=True)
    messages = fields.Text(default="[]")
    prompt = fields.Text(help="The user prompt the next slice starts with; empty means continue")
    budget_rounds = fields.Integer(default=3)
    budget_seconds = fields.Float(default=2.5)
    steps = fields.Integer(default=12)
    step_seconds = fields.Float(default=0.4)
    slices = fields.Integer(default=0)
    rounds = fields.Integer(default=0)
    claimed_at = fields.Datetime(index=True)
    heartbeat_at = fields.Datetime()
    worker = fields.Char()
    triggered_at = fields.Datetime(help="When the last cron trigger was placed")
    log = fields.Text(default="[]", help="JSON: one entry per slice start and per tick")
    ticks = fields.Integer(default=0)
    max_ticks = fields.Integer(default=0)
    tick_seconds = fields.Integer(default=3)
    text = fields.Text(default="")
    crash_once = fields.Boolean(default=False, help="The next tool call takes step_seconds (long enough to be killed) once; after that, tools are fast")

    # ---- entry points -------------------------------------------------

    @api.model
    def pan_ai_s4_new_chat(self):
        agent = self.env.ref("pan_ai_s2.partner_agent")
        channel = self.env["discuss.channel"].create(
            {
                "name": "AI Pro S4",
                "channel_type": "ai",
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.env.user.partner_id.id}),
                    (0, 0, {"partner_id": agent.id}),
                ],
            }
        )
        return channel.id

    @api.model
    def pan_ai_s4_start_cron_thread(self, vals):
        """A thread that starts on a cron, never inline (crash and continuous tests)."""
        channel_id = self.pan_ai_s4_new_chat()
        channel = self.env["discuss.channel"].browse(channel_id)
        placeholder = self._placeholder(channel)
        thread = self.create({"channel_id": channel_id, "message_id": placeholder.id, **vals})
        thread._wake_worker()
        self.env.cr.commit()
        return thread.id

    @api.model
    def pan_ai_s4_read(self, thread_id):
        t = self.browse(thread_id)
        return {
            "state": t.state, "slices": t.slices, "rounds": t.rounds, "ticks": t.ticks, "worker": t.worker,
            "log": json.loads(t.log or "[]"), "text": t.text, "messages": len(json.loads(t.messages or "[]")),
        }

    def _placeholder(self, channel):
        agent = self.env.ref("pan_ai_s2.partner_agent")
        return channel.sudo().message_post(author_id=agent.id, body="Thinking", message_type="comment", subtype_xmlid="mail.mt_comment")

    def start_chat(self, channel, user_message):
        """Called from the channel's message_post: one slice inline, the rest on a cron."""
        placeholder = self._placeholder(channel)
        thread = self.create({"channel_id": channel.id, "message_id": placeholder.id, "prompt": user_message.body and "do the steps" or "do the steps"})
        self.env.cr.commit()
        if thread._claim():
            thread._run_slice(where="inline")

    # ---- workers ------------------------------------------------------

    def _claim(self):
        """Atomically claim this thread for one slice. False when another
        worker holds it with a fresh heartbeat."""
        # Odoo runs REPEATABLE READ: two workers updating the same row is a
        # serialization failure, not a wait. That failure means "the other
        # one has it", nothing more.
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    """
                    UPDATE pan_ai_s4_thread SET claimed_at = now(), heartbeat_at = now(), worker = %s
                    WHERE id = %s AND state = 'running'
                      AND (claimed_at IS NULL OR heartbeat_at < now() - make_interval(secs => %s))
                    RETURNING id
                    """,
                    (_worker(), self.id, STALE_SECONDS),
                )
                got = bool(self.env.cr.fetchone())
        except psycopg2.errors.SerializationFailure:
            self.env.cr.rollback()
            return False
        self.env.cr.commit()
        self.invalidate_recordset()
        return got

    def _release(self):
        self.write({"claimed_at": False, "worker": False})
        self.env.cr.commit()

    @api.model
    def _wake_worker_any(self):
        random.choice([self.env.ref("pan_ai_s4.cron_worker_1"), self.env.ref("pan_ai_s4.cron_worker_2")]).sudo()._trigger()

    def _wake_worker(self, at=None):
        cron = random.choice([self.env.ref("pan_ai_s4.cron_worker_1"), self.env.ref("pan_ai_s4.cron_worker_2")])
        self.write({"triggered_at": fields.Datetime.now()})
        cron.sudo()._trigger(at=at)

    @api.model
    def _cron_run_slices(self):
        """Every claimable thread gets a slice in this wake, while the job
        stays well inside the cron worker's time limit. One wake can carry
        several triggers (Odoo consumes all due triggers of a cron in one
        run), so stopping after one slice would leave the others for the
        next scheduled run, a minute away (measured: 66 s)."""
        started = time.monotonic()
        budget = max(10, int(config["limit_time_real_cron"] or 120) * 0.6)
        while time.monotonic() - started < budget:
            candidates = self.search(
                ["|", ("claimed_at", "=", False), ("heartbeat_at", "<", fields.Datetime.now() - timedelta(seconds=STALE_SECONDS)), ("state", "=", "running")],
                order="id",
            )
            ran = False
            for thread in candidates:
                if thread._claim():
                    thread._run_slice(where="cron")
                    ran = True
                    break
            if not ran:
                return
        # Out of time with work left: hand the rest to the next wake.
        self._wake_worker_any()

    # ---- the slice ----------------------------------------------------

    def _log(self, **entry):
        entries = json.loads(self.log or "[]")
        entries.append({"t": time.time(), **entry})
        self.write({"log": json.dumps(entries)})

    def _run_slice(self, where):
        self.ensure_one()
        started = time.time()
        triggered = self.triggered_at and self.triggered_at.replace(tzinfo=None)
        wake_ms = int((datetime.utcnow() - triggered).total_seconds() * 1000) if (triggered and where == "cron") else None
        self._log(event="slice_start", where=where, worker=_worker(), slice=self.slices + 1, wake_ms=wake_ms)
        self.env.cr.commit()
        channel = self.channel_id.sudo()
        msg_id = self.message_id
        history = ModelMessagesTypeAdapter.validate_python(json.loads(self.messages or "[]")) or None
        prompt = self.prompt or None
        def before_step():
            # The crash scenario: one slow call, committed as spent before it
            # starts, so the worker that dies in it is not followed by
            # another that dies the same way.
            if self.crash_once:
                self.write({"crash_once": False})
                self.env.cr.commit()
                return self.step_seconds
            return 0.2 if self.crash_once is False and self.step_seconds >= 30 else self.step_seconds

        agent = _fake_model(self.steps, self.step_seconds, before_step)
        budget_rounds, budget_seconds = self.budget_rounds, self.budget_seconds
        text = [self.text or ""]
        batch, last_flush = [], time.monotonic()

        def flush(final=False):
            if not batch and not final:
                return
            channel._bus_send("pan_ai.run_event", {"message_id": msg_id, "events": list(batch), "sent_at": time.time(), "final": final})
            batch.clear()
            self.write({"heartbeat_at": fields.Datetime.now()})
            self.env.cr.commit()

        def on_event(ev):
            nonlocal last_flush
            batch.append(ev)
            if ev["type"] == "delta":
                text[0] += ev["text"]
            now = time.monotonic()
            if ev["type"] != "delta" or now - last_flush >= BATCH_SECONDS:
                flush()
                last_flush = now

        async def run():
            rounds = 0
            async with agent.iter(prompt, message_history=history) as run:
                async for node in run:
                    if Agent.is_model_request_node(node):
                        over = rounds >= budget_rounds or (time.time() - started) >= budget_seconds
                        if over and rounds > 0:
                            # Clean boundary: this node's request (the tool
                            # returns) is not in the history yet; carry it.
                            return list(run.all_messages()) + [node.request], False, rounds
                        async with node.stream(run.ctx) as s:
                            async for ev in s:
                                if isinstance(ev, PartStartEvent) and isinstance(ev.part, TextPart) and ev.part.content:
                                    on_event({"type": "delta", "text": ev.part.content})
                                elif isinstance(ev, PartDeltaEvent) and isinstance(ev.delta, TextPartDelta):
                                    on_event({"type": "delta", "text": ev.delta.content_delta})
                    elif Agent.is_call_tools_node(node):
                        async with node.stream(run.ctx) as s:
                            async for ev in s:
                                if isinstance(ev, FunctionToolCallEvent):
                                    on_event({"type": "tool_call", "id": ev.part.tool_call_id, "name": ev.part.tool_name, "args": ev.part.args_as_json_str()})
                                elif isinstance(ev, FunctionToolResultEvent):
                                    on_event({"type": "tool_result", "id": ev.part.tool_call_id, "summary": str(ev.part.content)[:200]})
                        rounds += 1
                    elif Agent.is_end_node(node):
                        return list(run.all_messages()), True, rounds
            return list(run.all_messages()), True, rounds

        messages, done, rounds = asyncio.run(run())
        self.write({
            "messages": json.dumps(to_jsonable_python(messages)),
            "prompt": False,
            "slices": self.slices + 1,
            "rounds": self.rounds + rounds,
            "text": text[0],
        })
        if done:
            placeholder = self.env["mail.message"].sudo().browse(msg_id)
            placeholder.write({"body": html_sanitize(markdown(text[0]))})
            Store(bus_channel=channel).add(placeholder, ["body"])
            batch.append({"type": "run_finished", "stats": {"slices": self.slices, "rounds": self.rounds}})
            flush(final=True)
            if self.kind == "continuous" and self.ticks < self.max_ticks:
                self.write({"ticks": self.ticks + 1, "prompt": f"tick {self.ticks + 1}", "text": text[0] + "\n\n"})
                self._log(event="tick_armed", tick=self.ticks, in_seconds=self.tick_seconds)
                self._release()
                self._wake_worker(at=datetime.utcnow() + timedelta(seconds=self.tick_seconds))
                self.env.cr.commit()
                return
            self.write({"state": "done"})
            self._release()
            _logger.warning("[pan_ai_s4] thread %s done after %s slices, %s rounds", self.id, self.slices, self.rounds)
            return
        flush()
        self._release()
        self._wake_worker()
        self.env.cr.commit()


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _pan_ai_s2_respond(self, user_message, agent_partner):
        if self.name == "AI Pro S4":
            return self.env["pan_ai_s4.thread"].start_chat(self, user_message)
        return super()._pan_ai_s2_respond(user_message, agent_partner)
