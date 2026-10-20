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

import psycopg2.extensions
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_core import to_jsonable_python

from odoo import _, api, fields
from odoo.exceptions import AccessError, UserError
from odoo.tools import config

from ..tools import commit
from .agent import build_agent, usage_limits
from .deps import OdooDeps
from .stream import LostClaim, Streamer, render_markdown

_logger = logging.getLogger(__name__)

# The worker writes the run's heartbeat on this clock while the model or an
# MCP tool is awaited (an Odoo tool runs on the slice's thread and blocks
# it), so a thinking model never makes a live run look dead to the crons
# (STALE_SECONDS on the run, several times this).
HEARTBEAT_SECONDS = 10
# A thread keeps this many messages (requests and responses); older rounds
# are dropped at a user prompt, so every slice sends a bounded history.
KEEP_MESSAGES = 60
# When the server has no limit (-1 or 0), budget as if it had this one.
DEFAULT_LIMIT = 120


def server_limit(key):
    """`limit_time_real` or `limit_time_real_cron` as a positive number of
    seconds: the server's value; a cron limit of -1 means the request limit
    (Odoo's own rule); 0 means no limit, budgeted as DEFAULT_LIMIT."""
    try:
        limit = int(config[key] or 0)
    except (TypeError, ValueError):
        limit = 0
    if key == "limit_time_real_cron" and limit == -1:
        return server_limit("limit_time_real")
    return limit if limit > 0 else DEFAULT_LIMIT


def slice_budget(where):
    """Seconds this slice may take. Under the request limit inline, under
    the cron limit on a worker, with the margin S4 showed a slice needs."""
    if where == "inline":
        return max(2.0, min(server_limit("limit_time_real") * 0.5, 40.0))
    return max(10.0, server_limit("limit_time_real_cron") * 0.6)


def beat(run):
    """The heartbeat: this worker is alive on this run. Written by the
    slice's clock task while the model is awaited and by every Odoo tool
    before and after its work, which runs on the slice's thread and keeps
    the clock task from firing."""
    run.sudo().write({"heartbeat_at": fields.Datetime.now()})
    commit(run.env)


def _cancelled(run):
    """Stop was pressed: read the flag fresh, past the cache."""
    run.invalidate_recordset(["cancel_requested"])
    return bool(run.cancel_requested)


class TimeLimit(Exception):
    """The agent's `time_limit` (seconds per run, across slices) is spent."""


def close_open_calls(messages, note):
    """A history that ends in tool calls nobody answered (Stop between the
    call and its result, Stop on a waiting approval) breaks the next model
    request. Answer each open call with `note` so the thread goes on."""
    if not messages or not isinstance(messages[-1], ModelResponse):
        return messages
    calls = [p for p in messages[-1].parts if isinstance(p, ToolCallPart)]
    if not calls:
        return messages
    return messages + [
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name=c.tool_name, content=note, tool_call_id=c.tool_call_id)
                for c in calls
            ]
        )
    ]


def trim_history(messages, keep=KEEP_MESSAGES):
    """The last `keep` messages, cut at a user prompt so no tool call loses
    its return. Returns `messages` itself when it is short enough."""
    if len(messages) <= keep:
        return messages
    for i in range(len(messages) - keep, len(messages)):
        m = messages[i]
        if isinstance(m, ModelRequest) and any(isinstance(p, UserPromptPart) for p in m.parts):
            return messages[i:]
    return messages


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
        _fail(run, stream, str(error), code="build")
        return
    except Exception:  # noqa: BLE001 - a bad agent row or a bad dependency lands on the run
        _logger.exception("[AI Pro] run %s: could not build the agent", run.id)
        _fail(
            run,
            stream,
            _("The agent could not be built. The server log for run %s has the details.", run.id),
            code="build",
        )
        return
    raw = thread.messages()
    history = ModelMessagesTypeAdapter.validate_python(raw) or None
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

    time_limit = thread.agent_id.time_limit

    async def heartbeat():
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            if not run._holds(token):
                return
            beat(run)

    async def go():
        pulse = asyncio.ensure_future(heartbeat())
        try:
            async with agent.iter(
                prompt,
                message_history=history,
                deferred_tool_results=deferred,
                deps=deps,
                usage_limits=usage_limits(thread.agent_id),
            ) as agent_run:
                rounds = 0
                async for node in agent_run:
                    if _cancelled(run):
                        messages = close_open_calls(
                            list(agent_run.all_messages()), _("Stopped by the user.")
                        )
                        return messages, "cancelled", None, agent_run.usage
                    if Agent.is_model_request_node(node):
                        if run.worked_seconds + time.monotonic() - started > time_limit:
                            raise TimeLimit()
                        if rounds > 0 and time.monotonic() - started >= budget:
                            messages = list(agent_run.all_messages()) + [node.request]
                            return messages, "paused", None, agent_run.usage
                        await _stream_text(node, agent_run, stream)
                    elif Agent.is_call_tools_node(node):
                        await _stream_tools(node, agent_run, stream, deps)
                        rounds += 1
                    elif Agent.is_end_node(node):
                        return _end(node, agent_run, stream)
            return list(agent_run.all_messages()), "ok", None, agent_run.usage
        finally:
            pulse.cancel()

    try:
        messages, outcome, pending, usage = asyncio.run(go())
    except LostClaim:
        _logger.info("[AI Pro] run %s: claim lost, slice dropped", run.id)
        _drop(run)
        return
    except TimeLimit:
        if run._holds(token):
            run.write({"worked_seconds": run.worked_seconds + time.monotonic() - started})
        _fail(
            run, stream, _("The agent hit its time limit of %s seconds.", time_limit), code="limit"
        )
        return
    except UsageLimitExceeded as error:
        _fail(run, stream, _("The agent hit its limit: %s", str(error)[:200]), code="limit")
        return
    except ModelHTTPError as error:
        _fail(
            run,
            stream,
            _(
                "The model answered with an error (HTTP %s). Try again in a minute.",
                error.status_code,
            ),
            code="model",
        )
        return
    except Exception:  # noqa: BLE001 - every outcome lands on the run
        _logger.exception("[AI Pro] run %s failed", run.id)
        _fail(
            run,
            stream,
            _("Something went wrong. The server log for run %s has the details.", run.id),
        )
        return

    if not run._holds(token):
        return
    before = len(raw)
    cost = sum(
        (m.provider_details or {}).get("cost") or 0.0
        for m in messages[before:]
        if isinstance(m, ModelResponse)
    )
    if outcome != "paused":
        messages = trim_history(messages)
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
            "worked_seconds": run.worked_seconds + time.monotonic() - started,
            "requests": run.requests + usage.requests,
            "input_tokens": run.input_tokens + usage.input_tokens,
            "output_tokens": run.output_tokens + usage.output_tokens,
            "cost": run.cost + cost,
            "text": stream.text,
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
        run.write({"status": "interrupted"})
        run._release()
        stream.finish("interrupted", pending=pending)
        return
    run._finish(outcome)
    stream.finish(outcome)
    _after(run, thread)


async def _stream_text(node, agent_run, stream):
    """The model's answer, token by token, to the window."""
    async with node.stream(agent_run.ctx) as events:
        async for ev in events:
            if isinstance(ev, PartStartEvent) and isinstance(ev.part, TextPart) and ev.part.content:
                stream.event("delta", text=ev.part.content)
            elif isinstance(ev, PartDeltaEvent) and isinstance(ev.delta, TextPartDelta):
                stream.event("delta", text=ev.delta.content_delta)


async def _stream_tools(node, agent_run, stream, deps):
    """Every tool call and its result as a row in the window; what a tool
    asked to open follows its result."""
    async with node.stream(agent_run.ctx) as events:
        async for ev in events:
            if isinstance(ev, FunctionToolCallEvent):
                stream.event(
                    "tool_call",
                    id=ev.part.tool_call_id,
                    name=ev.part.tool_name,
                    args=ev.part.args_as_json_str()[:2000],
                )
            elif isinstance(ev, FunctionToolResultEvent):
                stream.event(
                    "tool_result", id=ev.part.tool_call_id, summary=_summary(ev.part.content)
                )
                for action in deps.ui_actions:
                    stream.event("open", **action)
                deps.ui_actions.clear()


def _end(node, agent_run, stream):
    """The run's end: an approval to wait for, or the answer (a structured
    one shown as JSON)."""
    output = node.data.output
    if isinstance(output, DeferredToolRequests):
        pending = [
            {"id": c.tool_call_id, "name": c.tool_name, "args": c.args_as_json_str()[:2000]}
            for c in output.approvals
        ]
        return list(agent_run.all_messages()), "interrupted", pending, agent_run.usage
    if not isinstance(output, str):
        stream.event(
            "delta",
            text="\n```json\n" + json.dumps(output, ensure_ascii=False, indent=1) + "\n```\n",
        )
    return list(agent_run.all_messages()), "ok", None, agent_run.usage


def _fail(run, stream, message, code="other"):
    """A run that died on a limit (time, requests, tokens) would meet it
    again on the next tick of a continuous thread, so that thread pauses."""
    if _aborted(run.env.cr):
        run.env.cr.rollback()
    if stream.token is not None and not run._holds(stream.token):
        # Another worker took the run over; its outcome is theirs to write.
        _logger.info("[AI Pro] run %s: claim lost, failure dropped", run.id)
        _drop(run)
        return
    try:
        run._finish("failed", error=message[:250], code=code)
        if code == "limit" and run.thread_id.kind == "continuous":
            run.thread_id.write({"paused": True})
        stream.finish("failed", error=message)
    except LostClaim:
        pass


def _drop(run):
    """A slice that lost its claim: whatever it still holds uncommitted (a
    tool's writes, a log entry) must not land beside the live worker's."""
    if not config["test_enable"]:
        run.env.cr.rollback()


def _aborted(cr):
    """The transaction is in error: nothing can be written until a rollback."""
    status = cr._cnx.get_transaction_status()
    return status == psycopg2.extensions.TRANSACTION_STATUS_INERROR


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
        try:
            with run.env.cr.savepoint():
                if thread.post_answer and hasattr(record, "message_post"):
                    record.with_user(run.user_id).message_post(
                        body=render_markdown(run.text),
                        message_type="comment",
                        subtype_xmlid="mail.mt_note",
                    )
                if thread.activity and hasattr(record, "activity_schedule"):
                    record.with_user(run.user_id).activity_schedule(
                        summary=thread.agent_id.name,
                        note=render_markdown(run.text),
                        user_id=thread.user_id.id,
                    )
        except (AccessError, UserError) as error:
            # The answer is on the run; the record refused it. Say so there.
            _logger.warning("[AI Pro] run %s: could not post on the record: %s", run.id, error)
            run.write({"error": _("The answer could not be posted on the record: %s", error)[:250]})
    if thread.kind == "continuous" and not thread.paused:
        thread.write(
            {
                "next_tick_at": fields.Datetime.now()
                + timedelta(minutes=max(1, thread.watch_interval))
            }
        )
        run._wake_worker(at=thread.next_tick_at)
    commit(run.env)
