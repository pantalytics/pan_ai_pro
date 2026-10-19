"""One slice of a run: `agent.iter()` up to a time budget, the messages
persisted, the rest handed to a worker cron. The shape S4 measured.

The boundary is before the next model request: the tool returns of the
round that just finished are not in the history yet, so the slice carries
`node.request` along (S4 finding 4). The budget is read from the server's
own limits at runtime and kept well under them (S4 findings 1 to 3).
"""

import asyncio
import json
import logging
import time
from datetime import timedelta

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessagesTypeAdapter,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from pydantic_core import to_jsonable_python

from odoo import _, api, fields
from odoo.exceptions import UserError
from odoo.tools import config

from ..tools import commit
from .agent import build_agent, usage_limits
from .deps import OdooDeps
from .stream import LostClaim, Streamer

_logger = logging.getLogger(__name__)


def slice_budget(where):
    """Seconds this slice may take. Under the request limit inline, under
    the cron limit on a worker, with the margin S4 showed a slice needs."""
    if where == "inline":
        limit = int(config["limit_time_real"] or 0) or 120
        return max(2.0, min(limit * 0.5, 40.0))
    limit = int(config["limit_time_real_cron"] or 0) or 120
    return max(10.0, limit * 0.6)


def _cancelled(run):
    """Stop was pressed: read the flag fresh, past the cache."""
    run.invalidate_recordset(["cancel_requested"])
    return bool(run.cancel_requested)


def run_slice(run, token, where):
    """Run one slice of `run` under `token`. Never raises: every outcome
    lands on the run and the thread."""
    run = run.sudo()
    thread = run.thread_id
    started = time.monotonic()
    budget = slice_budget(where)
    stream = Streamer(run, token)
    run_env = api.Environment(
        run.env.cr,
        run.user_id.id,
        {"lang": run.user_id.lang or "en_US", "tz": run.user_id.tz or "UTC"},
    )
    deps = OdooDeps(
        env=run_env,
        user=run.user_id.with_env(run_env),
        run=run,
        thread=thread,
        record=thread.with_env(run_env).record(),
    )
    try:
        agent = build_agent(thread.agent_id.with_env(run_env), run_env)
    except UserError as error:
        _fail(run, stream, str(error))
        return
    except Exception as error:  # noqa: BLE001 - a bad agent row or a bad dependency lands on the run
        _logger.exception("[AI Pro] run %s: could not build the agent", run.id)
        _fail(run, stream, _("The agent could not be built: %s", type(error).__name__))
        return
    history = ModelMessagesTypeAdapter.validate_python(thread.messages()) or None
    prompt = run.prompt or None
    deferred = None
    if run.deferred_results:
        decided = json.loads(run.deferred_results)
        deferred = DeferredToolResults(
            approvals={cid: bool(ok) for cid, ok in decided.get("approvals", {}).items()}
        )
    if history is None and prompt is None:
        _fail(run, stream, _("Nothing to run."))
        return

    async def go():
        rounds = 0
        async with agent.iter(
            prompt,
            message_history=history,
            deferred_tool_results=deferred,
            deps=deps,
            usage_limits=usage_limits(thread.agent_id),
        ) as agent_run:
            async for node in agent_run:
                if _cancelled(run):
                    return list(agent_run.all_messages()), "cancelled", None, agent_run.usage
                if Agent.is_model_request_node(node):
                    if rounds > 0 and time.monotonic() - started >= budget:
                        return (
                            list(agent_run.all_messages()) + [node.request],
                            "paused",
                            None,
                            agent_run.usage,
                        )
                    async with node.stream(agent_run.ctx) as s:
                        async for ev in s:
                            if (
                                isinstance(ev, PartStartEvent)
                                and isinstance(ev.part, TextPart)
                                and ev.part.content
                            ):
                                stream.event("delta", text=ev.part.content)
                            elif isinstance(ev, PartDeltaEvent) and isinstance(
                                ev.delta, TextPartDelta
                            ):
                                stream.event("delta", text=ev.delta.content_delta)
                elif Agent.is_call_tools_node(node):
                    async with node.stream(agent_run.ctx) as s:
                        async for ev in s:
                            if isinstance(ev, FunctionToolCallEvent):
                                stream.event(
                                    "tool_call",
                                    id=ev.part.tool_call_id,
                                    name=ev.part.tool_name,
                                    args=ev.part.args_as_json_str()[:2000],
                                )
                            elif isinstance(ev, FunctionToolResultEvent):
                                summary = _summary(ev.part.content)
                                stream.event(
                                    "tool_result", id=ev.part.tool_call_id, summary=summary
                                )
                                for action in deps.ui_actions:
                                    stream.event("open", **action)
                                deps.ui_actions.clear()
                    rounds += 1
                elif Agent.is_end_node(node):
                    output = node.data.output
                    if isinstance(output, DeferredToolRequests):
                        pending = [
                            {
                                "id": c.tool_call_id,
                                "name": c.tool_name,
                                "args": c.args_as_json_str()[:2000],
                            }
                            for c in output.approvals
                        ]
                        return (
                            list(agent_run.all_messages()),
                            "interrupted",
                            pending,
                            agent_run.usage,
                        )
                    if not isinstance(output, str):
                        stream.event(
                            "delta",
                            text="\n```json\n"
                            + json.dumps(output, ensure_ascii=False, indent=1)
                            + "\n```\n",
                        )
                    return list(agent_run.all_messages()), "ok", None, agent_run.usage
        return list(agent_run.all_messages()), "ok", None, agent_run.usage

    try:
        messages, outcome, pending, usage = asyncio.run(go())
    except LostClaim:
        _logger.info("[AI Pro] run %s: claim lost, slice dropped", run.id)
        return
    except UsageLimitExceeded as error:
        _fail(run, stream, _("The agent hit its limit: %s", str(error)[:200]))
        return
    except ModelHTTPError as error:
        _fail(
            run,
            stream,
            _(
                "The model answered with an error (HTTP %s). Try again in a minute.",
                error.status_code,
            ),
        )
        return
    except Exception as error:  # noqa: BLE001 - every outcome lands on the run
        _logger.exception("[AI Pro] run %s failed", run.id)
        _fail(run, stream, _("Something went wrong: %s", type(error).__name__))
        return

    if not run._holds(token):
        return
    before = len(thread.messages())
    cost = sum(
        (m.provider_details or {}).get("cost") or 0.0
        for m in messages[before:]
        if isinstance(m, ModelResponse)
    )
    thread.write(
        {
            "conversation": json.dumps(to_jsonable_python(messages)),
            "pending_tool_calls": json.dumps(pending or []),
            "usage_requests": thread.usage_requests + usage.requests,
            "usage_input_tokens": thread.usage_input_tokens + usage.input_tokens,
            "usage_output_tokens": thread.usage_output_tokens + usage.output_tokens,
            "cost": thread.cost + cost,
            "last_activity": fields.Datetime.now(),
        }
    )
    run.write(
        {
            "prompt": False,
            "deferred_results": False,
            "slices": run.slices + 1,
            "requests": run.requests + usage.requests,
            "input_tokens": run.input_tokens + usage.input_tokens,
            "output_tokens": run.output_tokens + usage.output_tokens,
            "cost": run.cost + cost,
            "text": stream.text[0],
        }
    )
    if outcome == "paused":
        stream.flush()
        run._release()
        commit(run.env)
        run._wake_worker()
        commit(run.env)
        return
    if outcome == "interrupted":
        run.write(
            {"status": "interrupted", "claimed_at": False, "worker": False, "claim_token": False}
        )
        stream.finish("interrupted", pending=pending)
        return
    run._finish(outcome)
    stream.finish(outcome)
    _after(run, thread)


def _fail(run, stream, message):
    try:
        run._finish("failed", error=message[:250])
        stream.finish("failed", error=message)
    except LostClaim:
        pass


def _summary(content):
    if isinstance(content, dict):
        if "error" in content:
            return f"error: {content['error']}"[:200]
        if "count" in content:
            return f"{content['count']} records"
        if "groups" in content:
            return f"{len(content['groups'])} groups"
        if "opened" in content:
            return "opened"
        if "display_name" in content:
            return str(content["display_name"])[:200]
    return str(content)[:200]


def _after(run, thread):
    """A finished run that is not a chat: post the answer, make the activity,
    arm the next tick."""
    if run.status != "ok":
        return
    record = thread.record()
    if record is not None and (thread.post_answer or thread.activity):
        from .stream import render_markdown

        if thread.post_answer and hasattr(record, "message_post"):
            record.with_user(run.user_id).message_post(
                body=render_markdown(run.text), message_type="comment", subtype_xmlid="mail.mt_note"
            )
        if thread.activity and hasattr(record, "activity_schedule"):
            record.with_user(run.user_id).activity_schedule(
                summary=thread.agent_id.name,
                note=render_markdown(run.text),
                user_id=thread.user_id.id,
            )
    if thread.kind == "continuous" and not thread.paused:
        thread.write(
            {
                "next_tick_at": fields.Datetime.now()
                + timedelta(minutes=max(1, thread.watch_interval))
            }
        )
        run._wake_worker(at=thread.next_tick_at)
    commit(run.env)
