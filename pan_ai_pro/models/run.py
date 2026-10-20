# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
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
from odoo.tools.sql import table_exists

from ..compat import params
from ..defaults import RUNS_PER_USER_PER_HOUR
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
# A failure's kind. The heartbeat counts these; the free-text `error` (which
# can quote a record) never leaves this Odoo.
ERROR_CODES = [
    ("limit", "Limit"),
    ("model", "Model error"),
    ("timeout", "Timeout"),
    ("build", "Agent could not be built"),
    ("unresolved", "Could not resolve"),
    ("stuck", "Nobody picked it up"),
    ("other", "Other"),
]
# A claim whose heartbeat is older than this belongs to a dead worker. The
# worker beats every HEARTBEAT_SECONDS (runtime/slices.py) and around every
# Odoo tool; one tool call may not be silent longer than this.
STALE_SECONDS = 90
# Nobody holds the run.
NO_CLAIM = {"claimed_at": False, "worker": False, "claim_token": False}
WORKER_CRONS = ("pan_ai_pro.cron_worker_1", "pan_ai_pro.cron_worker_2")
# The worker name of an AI-field fill: the fill holds it from birth to end,
# and the slice loop never takes it, dead or alive (the stuck cron does).
FILL_WORKER = "fill"
# The tool log of a run: the last calls, their arguments clipped.
TOOL_LOG_ENTRIES = 200
TOOL_LOG_ARGS = 2000


def worker_name():
    return f"{os.getpid()}:{threading.get_ident()}"


class StillAnswering(UserError):
    """The thread has a live run: a second start waits, it is not an error
    of the watch or the person."""


class Run(models.Model):
    _name = "pan_ai.run"
    _description = "AI run"
    _order = "id desc"

    thread_id = fields.Many2one(
        "pan_ai.thread", string="Conversation", required=True, ondelete="cascade", index=True
    )
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
    text_html = fields.Html(compute="_compute_text_html", sanitize=False)
    slices = fields.Integer(default=0)
    requests = fields.Integer(default=0)
    input_tokens = fields.Integer(default=0)
    output_tokens = fields.Integer(default=0)
    cost = fields.Float(digits=(16, 6), default=0.0)
    started_at = fields.Datetime(default=fields.Datetime.now)
    worked_seconds = fields.Float(
        default=0.0, help="Time spent in slices; waiting in the queue or for approval is not."
    )
    finished_at = fields.Datetime()
    duration = fields.Float(compute="_compute_duration", help="Seconds.")
    error = fields.Char(help="What went wrong, for the person.")
    error_code = fields.Selection(
        ERROR_CODES,
        help="Why a run failed, as one word: the only thing about a failure the heartbeat reports.",
    )
    cancel_requested = fields.Boolean()
    tool_log = fields.Text(
        default="[]",
        help="JSON: the last 200 tool calls with their outcome, arguments clipped, for the Runs view.",
    )
    deferred_results = fields.Text(help="JSON: the person's approvals for the next slice.")

    # The claim
    claimed_at = fields.Datetime(index=True)
    heartbeat_at = fields.Datetime()
    worker = fields.Char()
    claim_token = fields.Char()

    # Two requests on one thread (a double send, two tabs, both worker crons
    # on one due tick) cannot both pass the live_run_id check; the index can.
    _one_live_per_thread = models.UniqueIndex(
        "(thread_id) WHERE status IN ('running', 'interrupted')",
        "The agent is still answering. Stop it first, or wait.",
    )

    def _auto_init(self):
        """Before the unique live-run index lands on a database that ran
        the race it closes: the older of two live runs on one thread is
        failed, so the index is created and not skipped."""
        result = super()._auto_init()
        if table_exists(self.env.cr, "pan_ai_run"):
            self.env.cr.execute(
                """
                UPDATE pan_ai_run
                   SET status = 'failed', error_code = 'stuck', error = %s,
                       claimed_at = NULL, worker = NULL, claim_token = NULL
                 WHERE id IN (
                    SELECT id FROM (
                        SELECT id, row_number() OVER (PARTITION BY thread_id ORDER BY id DESC) AS rn
                          FROM pan_ai_run WHERE status IN ('running', 'interrupted')
                    ) live WHERE rn > 1
                 )
                """,
                ("Stopped: two runs were live on one thread.",),
            )
        return result

    @api.depends("text")
    def _compute_text_html(self):
        from ..runtime.stream import render_markdown

        for run in self:
            run.text_html = render_markdown(run.text) if run.text else False

    @api.depends("agent_id.name")
    def _compute_display_name(self):
        for run in self:
            run.display_name = _("Run %(id)s, %(agent)s", id=run.id, agent=run.agent_id.name or "")

    @api.depends("started_at", "finished_at")
    def _compute_duration(self):
        for run in self:
            end = run.finished_at or fields.Datetime.now()
            run.duration = (end - run.started_at).total_seconds() if run.started_at else 0.0

    # ---- starting ------------------------------------------------------

    @api.model
    def _check_may_start(self, agent, caller, kind="chat", by_hand=None):
        """Every refusal a run start can meet, one shape: a UserError. The
        hourly cap refuses what a person starts by hand (a chat, a Fill
        button); it counts their chats and the runs their records
        triggered. A watch's ticks, a schedule and the nightly fills are
        the administrator's settings, not the person's doing, and never
        refused here: a rule must not fail somebody's save."""
        self.env["pan_ai.license"].require_entitled()
        if not params(self.env).get_str("pan_ai.openrouter_key"):
            raise UserError(_("No OpenRouter key. Add one in Settings > AI Pro."))
        if not agent.may_use(caller):
            raise UserError(_("You may not use the agent %s.", agent.name))
        if not (kind == "chat" if by_hand is None else by_hand):
            return
        per_hour = params(self.env).get_int("pan_ai.runs_per_user_per_hour", RUNS_PER_USER_PER_HOUR)
        since = fields.Datetime.now() - timedelta(hours=1)
        recent = self.sudo().search_count(
            [
                ("caller_id", "=", caller.id),
                ("kind", "in", ("chat", "triggered")),
                ("started_at", ">=", since),
            ]
        )
        if per_hour and recent >= per_hour:
            raise UserError(_("You reached the hourly limit of %s. Try again later.", per_hour))

    @api.model
    def start(self, thread, prompt, kind="chat", message=None, caller=None, by_hand=None):
        """Create the run for a prompt on a thread; the caller decides where
        the first slice runs (inline or on a worker). `by_hand`: the person
        pressed something, so their hourly cap applies (a chat always)."""
        caller = caller or self.env.user
        agent = thread.agent_id
        self._check_may_start(agent, caller, kind, by_hand=by_hand)
        if thread.live_run_id:
            raise StillAnswering(_("The agent is still answering. Stop it first, or wait."))
        run_user = agent.run_user(caller)
        try:
            with self.env.cr.savepoint():
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
        except psycopg2.errors.UniqueViolation as error:
            raise StillAnswering(
                _("The agent is still answering. Stop it first, or wait.")
            ) from error
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
                       SET claimed_at = %(now)s, heartbeat_at = %(now)s,
                           worker = %(worker)s, claim_token = %(token)s
                     WHERE id = %(id)s AND status = 'running'
                       AND (claimed_at IS NULL OR heartbeat_at < %(stale)s)
                 RETURNING id
                    """,
                    {
                        # Python's clock, in UTC like every Datetime column; the
                        # database's now() would land in the session's time zone.
                        "now": fields.Datetime.now(),
                        "stale": fields.Datetime.now() - timedelta(seconds=STALE_SECONDS),
                        "worker": worker_name(),
                        "token": token,
                        "id": self.id,
                    },
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
        self.sudo().write(NO_CLAIM)

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

        started = fields.Datetime.now()
        self.env["pan_ai.thread"]._start_due_ticks()
        # A slice started now may take slice_budget("cron") more; both must
        # end inside the cron's limit, or the master kills the worker.
        limit = slices.server_limit("limit_time_real_cron")
        budget = max(1.0, limit - slices.slice_budget("cron") - limit * 0.1)

        def in_budget():
            return (fields.Datetime.now() - started).total_seconds() < budget

        while in_budget():
            ran = False
            # Round robin: every claimable run gets one slice before the
            # list is read again, so one long run never starves the rest.
            # Least recently served first: a paused run keeps its heartbeat,
            # a run nobody touched has none.
            for run in self.sudo().search(
                self._claimable_domain() + [("worker", "!=", FILL_WORKER)],
                order="heartbeat_at asc nulls first, id",
            ):
                if not in_budget():
                    break
                ran = run._run_now("cron") or ran
            if not ran:
                return
        self._wake_worker()

    def _run_now(self, where):
        """Claim this run and give it one slice here. False when another
        worker holds it."""
        from ..runtime import slices

        self.ensure_one()
        token = self._claim()
        if token:
            slices.run_slice(self, token, where=where)
        return bool(token)

    @api.model
    def _cron_mark_stuck(self):
        """A run nobody has touched for twice its agent's time limit (its last
        heartbeat, or its start when no worker ever served it) and that
        nobody holds is failed, so it is visible as such and the thread is
        free again. Waiting for an approval does not count: that run is
        `interrupted`, not claimable."""
        from ..runtime import stream

        for run in self.sudo().search(self._claimable_domain()):
            limit = run.agent_id.time_limit
            last = run.heartbeat_at or run.started_at
            if last < fields.Datetime.now() - timedelta(seconds=limit * 2):
                error = _("Stopped: nobody picked the run up in time.")
                run._finish("failed", error=error, code="stuck")
                stream.finish_outside(run, "failed", error=error)

    # ---- the person's buttons ----------------------------------------

    def action_stop(self):
        from ..runtime import stream

        for run in self:
            if run.status in LIVE:
                run.sudo().write({"cancel_requested": True})
                if run.status == "interrupted":
                    run.thread_id.sudo()._close_open_calls(_("Stopped by the user."))
                    run._finish("cancelled")
                    stream.finish_outside(run, "cancelled")
        return True

    def action_decide(self, approvals):
        """The person approved or skipped the pending tool calls. Only the
        ids the thread is waiting for count; the rest is ignored, never
        trusted from the client."""

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
        self._run_now("inline")
        return True

    def _finish(self, status, error=None, code=None):
        self.ensure_one()
        self.sudo().write(
            {
                "status": status,
                "error": error or False,
                "error_code": (code or "other") if status == "failed" else False,
                "finished_at": fields.Datetime.now(),
                **NO_CLAIM,
            }
        )

    def log_tool(self, entry):
        """Bounded by shape (the last TOOL_LOG_ENTRIES calls, args clipped),
        so the log stays JSON however long the run."""
        self.ensure_one()
        entry = dict(entry, args=json.dumps(entry.get("args"), default=str)[:TOOL_LOG_ARGS])
        entries = (json.loads(self.tool_log or "[]") + [entry])[-TOOL_LOG_ENTRIES:]
        self.sudo().write({"tool_log": json.dumps(entries)})
