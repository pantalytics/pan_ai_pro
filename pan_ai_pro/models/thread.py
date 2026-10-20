# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""`pan_ai.thread`: one conversation with one agent, for one person.

`conversation` is Pydantic AI's message history as JSON
(`ModelMessagesTypeAdapter`), carried across runs and slices, plus the tool
calls waiting for the person's approval. A chat thread shows in a
`discuss.channel` of type `ai`; a scheduled, triggered or continuous thread
has no channel: its answer stays on the run and, when the action asks, lands
as a note or an activity on the record.
"""

import json
import logging
from ast import literal_eval
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain

from ..compat import params
from ..defaults import RETENTION_DAYS
from ..tools import commit
from .run import LIVE, StillAnswering

_logger = logging.getLogger(__name__)

# Changes one tick of a watch names at most; the rest waits for the next.
TICK_BATCH = 50

KINDS = [
    ("chat", "Chat"),
    ("scheduled", "Scheduled"),
    ("triggered", "Triggered"),
    ("continuous", "Continuous"),
]


class Thread(models.Model):
    _name = "pan_ai.thread"
    _description = "AI thread"
    _order = "last_activity desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("New thread"))
    kind = fields.Selection(KINDS, default="chat", required=True, index=True)
    user_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete="cascade",
        help="Whose thread it is: who asked, or who owns the schedule.",
    )
    agent_id = fields.Many2one("pan_ai.agent", required=True, ondelete="restrict", index=True)
    channel_id = fields.Many2one("discuss.channel", ondelete="set null", index=True)
    res_model = fields.Char(help="The record the thread is about, when there is one.")
    res_id = fields.Integer()
    conversation = fields.Text(default="[]", help="Pydantic AI message history, JSON.")
    pending_tool_calls = fields.Text(
        default="[]", help="Tool calls waiting for the person's approval, JSON."
    )
    usage_requests = fields.Integer(string="Requests", default=0)
    usage_input_tokens = fields.Integer(string="Input tokens", default=0)
    usage_output_tokens = fields.Integer(string="Output tokens", default=0)
    cost = fields.Float(
        digits=(16, 6), default=0.0, help="Across all runs, as OpenRouter reports it."
    )
    last_activity = fields.Datetime(default=fields.Datetime.now, index=True)
    run_ids = fields.One2many("pan_ai.run", "thread_id", string="Runs")
    run_count = fields.Integer(compute="_compute_run_count")
    live_run_id = fields.Many2one("pan_ai.run", compute="_compute_live_run")

    # Scheduled and triggered threads: what to do with the answer
    post_answer = fields.Boolean(help="Post the answer in the record's chatter.")
    activity = fields.Boolean(help="Create an activity on the record with the answer.")

    # Continuous threads (PR E): the watch
    paused = fields.Boolean()
    watch_model_id = fields.Many2one("ir.model", string="Model", ondelete="cascade")
    # The model's name, for the domain widget (it takes a name, not a row).
    watch_model = fields.Char(related="watch_model_id.model")
    watch_domain = fields.Char(string="Records", default="[]")
    watch_interval = fields.Integer(
        string="Every (minutes)", default=15, help="Minutes between looks, at least 1."
    )
    watch_cursor = fields.Datetime(
        string="Last look", help="Records changed after this were not seen yet."
    )
    # One transaction gives every record it touches the same write_date, so
    # the cursor is a pair: the last change seen, and the last id at that time.
    watch_cursor_id = fields.Integer(default=0)
    next_tick_at = fields.Datetime(string="Next look", index=True)

    @api.depends("run_ids")
    def _compute_run_count(self):
        for thread in self:
            thread.run_count = len(thread.run_ids)

    @api.depends("run_ids.status")
    def _compute_live_run(self):
        # One query, not every run the thread ever had (a watch makes hundreds).
        live = {}
        for run in self.env["pan_ai.run"].search(
            [("thread_id", "in", self.ids), ("status", "in", LIVE)], order="id desc"
        ):
            live.setdefault(run.thread_id.id, run)
        for thread in self:
            thread.live_run_id = live.get(thread.id, False)

    def messages(self):
        self.ensure_one()
        return json.loads(self.conversation or "[]")

    def pending(self):
        self.ensure_one()
        return json.loads(self.pending_tool_calls or "[]")

    def _close_open_calls(self, note):
        """Answer the tool calls the conversation ends with (a stopped
        approval) with `note`, so the next message does not meet them."""
        from pydantic_ai.messages import ModelMessagesTypeAdapter
        from pydantic_core import to_jsonable_python

        from ..runtime.slices import close_open_calls

        self.ensure_one()
        messages = ModelMessagesTypeAdapter.validate_python(self.messages())
        closed = close_open_calls(messages, note)
        if closed is not messages:
            self.write({"conversation": json.dumps(to_jsonable_python(closed))})
        self.write({"pending_tool_calls": "[]"})

    def record(self):
        """The record the thread is about, as the thread's user sees it, or None."""
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return None
        rec = self.env[self.res_model].browse(self.res_id).exists()
        return rec if rec and rec.has_access("read") else None

    @api.model
    def _cron_retention(self):
        days = params(self.env).get_int("pan_ai.retention_days", RETENTION_DAYS)
        if days <= 0:
            return
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        old = self.sudo().search([("kind", "=", "chat"), ("last_activity", "<", cutoff)])
        old._unlink_with_channels()
        # The other kinds keep their thread (its memory); their finished runs go.
        self.env["pan_ai.run"].sudo().search(
            [
                ("thread_id.kind", "!=", "chat"),
                ("status", "not in", LIVE),
                ("started_at", "<", cutoff),
            ]
        ).unlink()
        # A triggered or scheduled thread (an AI field's value, a rule's run,
        # one cron execution) is one per run: nothing to keep once it is gone.
        self.sudo().search(
            [
                ("kind", "in", ("triggered", "scheduled")),
                ("channel_id", "=", False),
                ("run_ids", "=", False),
                ("create_date", "<", cutoff),
            ]
        ).unlink()

    def _unlink_with_channels(self):
        self.channel_id.sudo().unlink()
        self.unlink()

    # ---- continuous threads: the ticks ------------------------------------

    @api.model
    def _start_due_ticks(self):
        """Every continuous thread whose tick is due and that has no live run
        gets a run, with what changed since its cursor as the prompt; the
        worker loop that called this runs it inside its budget. A tick that
        finds nothing makes no model call: it only moves the clock."""
        now = fields.Datetime.now()
        due = self.sudo().search(
            [
                ("kind", "=", "continuous"),
                ("paused", "=", False),
                ("next_tick_at", "<=", now),
                ("watch_model_id", "!=", False),
            ]
        )
        for thread in due:
            if thread.live_run_id or not thread.user_id.active:
                if not thread.user_id.active:
                    thread.write({"paused": True})
                continue
            try:
                prompt, seen_until = thread._tick_prompt(now)
            except Exception as error:  # noqa: BLE001 - a bad watch pauses, never loops
                _logger.warning("[AI Pro] thread %s watch failed: %s", thread.id, error)
                thread.write({"paused": True})
                continue
            interval = timedelta(minutes=max(1, thread.watch_interval))
            thread.write({"next_tick_at": now + interval})
            if prompt is None:
                thread.write({"watch_cursor": seen_until[0], "watch_cursor_id": seen_until[1]})
                continue
            try:
                run = self.env["pan_ai.run"].start(
                    thread, prompt, kind="continuous", caller=thread.user_id
                )
            except StillAnswering:
                # The other worker cron got this tick first: not a pause.
                continue
            except UserError as error:
                # The cursor stays: the changes are seen again after Resume.
                _logger.warning("[AI Pro] thread %s tick refused: %s", thread.id, error)
                thread.write({"paused": True})
                continue
            thread.write({"watch_cursor": seen_until[0], "watch_cursor_id": seen_until[1]})
            commit(self.env)
            run._wake_worker()

    def _tick_prompt(self, now):
        """What changed since the cursor, as the thread's user sees it, and
        where the cursor moves to: (now, 0), or the last change named when
        more than TICK_BATCH changed (the rest waits for the next tick).
        (None, cursor) when nothing changed. A new watch starts from now: it
        does not walk the model's history."""
        self.ensure_one()
        if not self.watch_cursor:
            return None, (now, 0)
        env = api.Environment(self.env.cr, self.user_id.id, {})
        Model = env[self.watch_model_id.model]
        domain = Domain(literal_eval(self.watch_domain or "[]")) & (
            Domain("write_date", ">", self.watch_cursor)
            | (
                Domain("write_date", "=", self.watch_cursor)
                & Domain("id", ">", self.watch_cursor_id)
            )
        )
        records = Model.search(domain, limit=TICK_BATCH + 1, order="write_date asc, id asc")
        if not records:
            return None, (now, 0)
        seen_until = (now, 0)
        more = ""
        if len(records) > TICK_BATCH:
            records = records[:TICK_BATCH]
            seen_until = (records[-1].write_date, records[-1].id)
            more = " More changed after these; they come next time."
        lines = [f"- {r._name} {r.id}: {r.display_name}" for r in records]
        return (
            f"Since your last look at {fields.Datetime.to_string(self.watch_cursor)} UTC, "
            f"{len(records)} {Model._description} record(s) changed:\n"
            + "\n".join(lines)
            + "\nDo what your instructions say about them. Remember what you did in your answer; it is your memory for the next look."
            + more
        ), seen_until

    def _own_or_manager(self):
        """The thread's owner and a manager may flip it; the rows themselves
        are the runtime's to write."""
        self.check_access("read")
        if not self.env.user.has_group("pan_ai_pro.group_manager") and any(
            thread.user_id != self.env.user for thread in self
        ):
            raise AccessError(_("This thread is not yours."))
        return self.sudo()

    def action_pause(self):
        self._own_or_manager().write({"paused": True})

    def action_resume(self):
        self._own_or_manager().write({"paused": False, "next_tick_at": fields.Datetime.now()})
        self.env["pan_ai.run"]._wake_worker()

    def action_open_chat(self):
        self.ensure_one()
        if not self.channel_id:
            return False
        return {
            "type": "ir.actions.client",
            "tag": "pan_ai_pro.open_chat",
            "params": {"channel_id": self.channel_id.id},
        }
