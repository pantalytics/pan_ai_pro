"""`pan_ai.thread`: one conversation with one agent, for one person.

`conversation` is Pydantic AI's message history as JSON
(`ModelMessagesTypeAdapter`), carried across runs and slices, plus the tool
calls waiting for the person's approval. A chat thread shows in a
`discuss.channel` of type `ai`; a scheduled, triggered or continuous thread
has no channel unless the action asked to post somewhere.
"""

import json
import logging
from ast import literal_eval
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from ..tools import commit

_logger = logging.getLogger(__name__)

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
    usage_requests = fields.Integer(default=0)
    usage_input_tokens = fields.Integer(default=0)
    usage_output_tokens = fields.Integer(default=0)
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
    watch_model_id = fields.Many2one("ir.model", ondelete="cascade")
    watch_domain = fields.Char(default="[]")
    watch_interval = fields.Integer(default=15, help="Minutes between ticks, at least 1.")
    watch_cursor = fields.Datetime(help="Records changed after this were not seen yet.")
    next_tick_at = fields.Datetime(index=True)

    @api.depends("run_ids")
    def _compute_run_count(self):
        for thread in self:
            thread.run_count = len(thread.run_ids)

    @api.depends("run_ids.status")
    def _compute_live_run(self):
        for thread in self:
            thread.live_run_id = thread.run_ids.filtered(
                lambda r: r.status in ("running", "interrupted")
            )[:1]

    def messages(self):
        self.ensure_one()
        return json.loads(self.conversation or "[]")

    def pending(self):
        self.ensure_one()
        return json.loads(self.pending_tool_calls or "[]")

    def record(self):
        """The record the thread is about, as the thread's user sees it, or None."""
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return None
        rec = self.env[self.res_model].browse(self.res_id).exists()
        return rec if rec and rec.has_access("read") else None

    @api.model
    def _cron_retention(self):
        days = self.env["ir.config_parameter"].sudo().get_int("pan_ai.retention_days", 90)
        if days <= 0:
            return
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        old = self.sudo().search([("kind", "=", "chat"), ("last_activity", "<", cutoff)])
        old.channel_id.sudo().unlink()
        old.unlink()

    # ---- continuous threads: the ticks ------------------------------------

    @api.model
    def _start_due_ticks(self):
        """Every continuous thread whose tick is due and that has no live run
        gets a run now, with what changed since its cursor as the prompt. A
        tick that finds nothing makes no model call: it only moves the clock."""
        from ..runtime import slices

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
                prompt = thread._tick_prompt(now)
            except Exception as error:  # noqa: BLE001 - a bad watch pauses, never loops
                _logger.warning("[AI Pro] thread %s watch failed: %s", thread.id, error)
                thread.write({"paused": True})
                continue
            interval = timedelta(minutes=max(1, thread.watch_interval))
            if prompt is None:
                thread.write({"watch_cursor": now, "next_tick_at": now + interval})
                continue
            thread.write({"watch_cursor": now, "next_tick_at": now + interval})
            try:
                run = self.env["pan_ai.run"].start(
                    thread, prompt, kind="continuous", caller=thread.user_id
                )
            except UserError as error:
                _logger.warning("[AI Pro] thread %s tick refused: %s", thread.id, error)
                thread.write({"paused": True})
                continue
            commit(self.env)
            token = run._claim()
            if token:
                slices.run_slice(run, token, where="cron")

    def _tick_prompt(self, now):
        """What changed since the cursor, as the thread's user sees it, or
        None when nothing did."""
        self.ensure_one()
        env = api.Environment(self.env.cr, self.user_id.id, {})
        Model = env[self.watch_model_id.model]
        domain = Domain(literal_eval(self.watch_domain or "[]"))
        if self.watch_cursor:
            domain &= Domain("write_date", ">", self.watch_cursor)
        records = Model.search(domain, limit=50, order="write_date desc")
        if not records:
            return None
        lines = [f"- {r._name} {r.id}: {r.display_name}" for r in records]
        return (
            f"Since your last look at {fields.Datetime.to_string(self.watch_cursor or now)} UTC, "
            f"{len(records)} {Model._description} record(s) changed:\n"
            + "\n".join(lines)
            + "\nDo what your instructions say about them. Remember what you did in your answer; it is your memory for the next look."
        )

    def action_pause(self):
        self.write({"paused": True})

    def action_resume(self):
        self.write({"paused": False, "next_tick_at": fields.Datetime.now()})
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
