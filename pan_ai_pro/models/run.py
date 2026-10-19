"""`pan_ai.run`: one `agent.run`, in slices on Odoo's workers.

A run starts from a chat message, a scheduled action, an automation rule or
a continuous thread's tick. The first slice of a chat runs inline in the
request; everything past the slice budget runs on one of two worker crons
woken with `ir.cron._trigger()`. The claim (an atomic row update with a
heartbeat and a token) is what keeps two workers off one run; the loop
itself is runtime/slices.py.
"""

import json
import logging
import os
import random
import threading
from datetime import timedelta

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

from ..tools import commit

_logger = logging.getLogger(__name__)

STATUSES = [
    ("running", "Running"),
    ("interrupted", "Waiting for approval"),
    ("ok", "Done"),
    ("cancelled", "Stopped"),
    ("failed", "Failed"),
]
LIVE = ("running", "interrupted")
# A claim whose heartbeat is older than this belongs to a dead worker.
STALE_SECONDS = 30
WORKER_CRONS = ("pan_ai_pro.cron_worker_1", "pan_ai_pro.cron_worker_2")


def worker_name():
    return f"{os.getpid()}:{threading.get_ident()}"


class Run(models.Model):
    _name = "pan_ai.run"
    _description = "AI run"
    _order = "id desc"

    thread_id = fields.Many2one("pan_ai.thread", required=True, ondelete="cascade", index=True)
    agent_id = fields.Many2one(related="thread_id.agent_id", store=True)
    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="cascade",
        index=True,
        help="Whose rights the run carries: the caller, or the agent's dedicated user.",
    )
    caller_id = fields.Many2one("res.users", help="Who asked, when that is someone else.")
    kind = fields.Selection(
        [
            ("chat", "Chat"),
            ("scheduled", "Scheduled"),
            ("triggered", "Triggered"),
            ("continuous", "Continuous"),
        ],
        required=True,
        default="chat",
        index=True,
    )
    status = fields.Selection(STATUSES, default="running", required=True, index=True)
    prompt = fields.Text(help="The user prompt the next slice starts with; empty means continue.")
    message_id = fields.Many2one(
        "mail.message", ondelete="set null", help="The agent's message in the chat."
    )
    text = fields.Text(default="", help="The answer so far, markdown.")
    slices = fields.Integer(default=0)
    requests = fields.Integer(default=0)
    input_tokens = fields.Integer(default=0)
    output_tokens = fields.Integer(default=0)
    cost = fields.Float(digits=(16, 6), default=0.0)
    started_at = fields.Datetime(default=fields.Datetime.now)
    finished_at = fields.Datetime()
    duration = fields.Float(compute="_compute_duration", help="Seconds.")
    error = fields.Char()
    cancel_requested = fields.Boolean()
    tool_log = fields.Text(
        default="[]", help="JSON: every tool call with its outcome, for the Runs view."
    )
    deferred_results = fields.Text(help="JSON: the person's approvals for the next slice.")

    # The claim
    claimed_at = fields.Datetime(index=True)
    heartbeat_at = fields.Datetime()
    worker = fields.Char()
    claim_token = fields.Char()

    @api.depends("started_at", "finished_at")
    def _compute_duration(self):
        for run in self:
            end = run.finished_at or fields.Datetime.now()
            run.duration = (end - run.started_at).total_seconds() if run.started_at else 0.0

    # ---- starting ------------------------------------------------------

    @api.model
    def _check_may_start(self, agent, caller):
        """Every refusal a run start can meet, one shape: a UserError."""
        self.env["pan_ai.license"].require_entitled()
        if not self.env["ir.config_parameter"].sudo().get_str("pan_ai.openrouter_key"):
            raise UserError(_("No OpenRouter key. Add one in Settings > AI Pro."))
        if not agent.may_use(caller):
            raise UserError(_("You may not use the agent %s.", agent.name))
        per_hour = (
            self.env["ir.config_parameter"].sudo().get_int("pan_ai.runs_per_user_per_hour", 30)
        )
        since = fields.Datetime.now() - timedelta(hours=1)
        recent = self.sudo().search_count(
            [("caller_id", "=", caller.id), ("started_at", ">=", since)]
        )
        if per_hour and recent >= per_hour:
            raise UserError(_("You started %s runs in the last hour. Try again later.", recent))

    @api.model
    def start(self, thread, prompt, kind="chat", message=None, caller=None):
        """Create the run for a prompt on a thread; the caller decides where
        the first slice runs (inline or on a worker)."""
        caller = caller or self.env.user
        agent = thread.agent_id
        self._check_may_start(agent, caller)
        if thread.live_run_id:
            raise UserError(_("The agent is still answering. Stop it first, or wait."))
        run_user = agent.run_user(caller)
        run = self.sudo().create(
            {
                "thread_id": thread.id,
                "user_id": run_user.id,
                "caller_id": caller.id,
                "kind": kind,
                "prompt": prompt,
                "message_id": message.id if message else False,
            }
        )
        thread.sudo().write({"last_activity": fields.Datetime.now()})
        return run

    # ---- the claim -----------------------------------------------------

    def _claim(self):
        """Atomically claim this run for one slice. Returns the claim token,
        or None when another worker holds it with a fresh heartbeat."""
        self.ensure_one()
        token = f"{worker_name()}:{random.randrange(1 << 48):x}"
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    """
                    UPDATE pan_ai_run
                       SET claimed_at = now(), heartbeat_at = now(), worker = %s, claim_token = %s
                     WHERE id = %s AND status = 'running'
                       AND (claimed_at IS NULL OR heartbeat_at < now() - make_interval(secs => %s))
                 RETURNING id
                    """,
                    (worker_name(), token, self.id, STALE_SECONDS),
                )
                got = bool(self.env.cr.fetchone())
        except psycopg2.errors.SerializationFailure:
            return None
        commit(self.env)
        self.invalidate_recordset()
        return token if got else None

    def _holds(self, token):
        """The fence: before every write, is this still our claim?"""
        self.env.cr.execute("SELECT claim_token FROM pan_ai_run WHERE id = %s", (self.id,))
        row = self.env.cr.fetchone()
        return bool(row) and row[0] == token

    def _release(self):
        self.sudo().write({"claimed_at": False, "worker": False, "claim_token": False})

    @api.model
    def _wake_worker(self, at=None):
        cron = self.env.ref(random.choice(WORKER_CRONS), raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger(at=at)

    @api.model
    def _claimable_domain(self):
        stale = fields.Datetime.now() - timedelta(seconds=STALE_SECONDS)
        return [
            ("status", "=", "running"),
            "|",
            ("claimed_at", "=", False),
            ("heartbeat_at", "<", stale),
        ]

    @api.model
    def _cron_run_slices(self):
        """Every claimable run gets a slice in this wake, inside the cron
        worker's time limit; what is left is handed to the next wake.
        Continuous threads whose tick is due start a run first."""
        from ..runtime import slices

        self.env["pan_ai.thread"]._start_due_ticks()
        started = fields.Datetime.now()
        budget = max(10, int(config["limit_time_real_cron"] or 120) * 0.6)
        while (fields.Datetime.now() - started).total_seconds() < budget:
            ran = False
            for run in self.sudo().search(self._claimable_domain(), order="id"):
                token = run._claim()
                if token:
                    slices.run_slice(run, token, where="cron")
                    ran = True
                    break
            if not ran:
                return
        self._wake_worker()

    @api.model
    def _cron_mark_stuck(self):
        """A run past its agent's time limit and nobody's claim is failed,
        so it is visible as such and the thread is free again."""
        for run in self.sudo().search(self._claimable_domain()):
            limit = run.agent_id.time_limit or 300
            if run.started_at < fields.Datetime.now() - timedelta(seconds=limit * 2):
                run._finish("failed", error=_("Stopped: nobody picked the run up in time."))

    # ---- the person's buttons ----------------------------------------

    def action_stop(self):
        for run in self:
            if run.status in LIVE:
                run.sudo().write({"cancel_requested": True})
                if run.status == "interrupted":
                    run._finish("cancelled")
        return True

    def action_decide(self, approvals):
        """The person approved or skipped the pending tool calls. Only the
        ids the thread is waiting for count; the rest is ignored, never
        trusted from the client."""
        from ..runtime import slices

        self.ensure_one()
        if self.status != "interrupted":
            raise UserError(_("Nothing is waiting for approval."))
        pending = {call["id"] for call in self.thread_id.pending()}
        decided = {cid: bool(ok) for cid, ok in (approvals or {}).items() if cid in pending}
        if decided.keys() != pending:
            raise UserError(_("Decide on every pending call."))
        self.sudo().write(
            {
                "deferred_results": json.dumps({"approvals": decided}),
                "status": "running",
                "prompt": False,
            }
        )
        self.thread_id.sudo().write({"pending_tool_calls": "[]"})
        commit(self.env)
        token = self._claim()
        if token:
            slices.run_slice(self, token, where="inline")
        return True

    def _finish(self, status, error=None):
        self.ensure_one()
        self.sudo().write(
            {
                "status": status,
                "error": error or False,
                "finished_at": fields.Datetime.now(),
                "claimed_at": False,
                "worker": False,
                "claim_token": False,
            }
        )

    def log_tool(self, entry):
        self.ensure_one()
        entries = json.loads(self.tool_log or "[]")
        entries.append(entry)
        self.sudo().write({"tool_log": json.dumps(entries)[:200000]})
