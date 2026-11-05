# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An activity assigned to an agent's dedicated user is its to-do
(docs/plans/ai-colleague.md, section 3).

Whoever assigns it is the caller: their hourly limit, their Allow and Skip.
The work happens in the direct chat between that person and the agent, so
the approval card and Stop have a place, and one to-do at a time per chat:
the open activities are the queue, picked up by a cron that every
assignment and every finished to-do wakes. Done means the activity is
marked done by the agent, with its answer as the feedback. A failure or a
Stop leaves it open. An activity OdooBot assigns (a scheduled action) is
refused: nobody could approve its changes.
"""

from markupsafe import escape as html_escape

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from ..compat import send_fields
from ..tools import commit

QUEUE_BATCH = 20


class MailActivity(models.Model):
    _inherit = "mail.activity"

    pan_ai_assigned_by = fields.Many2one(
        "res.users", readonly=True, copy=False, index="btree_not_null"
    )
    pan_ai_run_id = fields.Many2one("pan_ai.run", readonly=True, copy=False, ondelete="set null")

    @api.model_create_multi
    def create(self, vals_list):
        activities = super().create(vals_list)
        activities._pan_ai_assign()
        return activities

    def write(self, vals):
        result = super().write(vals)
        if "user_id" in vals:
            self._pan_ai_assign()
        return result

    def _pan_ai_assign(self):
        """Queue the activities given to an agent; the cron starts them after
        this transaction, never inside somebody's save."""
        Agent = self.env["pan_ai.agent"]
        assigner = self.env.user
        queued = False
        for activity in self.sudo():
            agent = Agent._mentioned(activity.user_id.partner_id)
            if not agent or assigner == agent.user_id:
                continue
            if self.env.uid == SUPERUSER_ID or assigner.share:
                activity._pan_ai_tell(agent, _("A person has to give me this to-do."))
                continue
            activity.write({"pan_ai_assigned_by": assigner.id, "pan_ai_run_id": False})
            queued = True
        if queued:
            self.env.ref("pan_ai_pro.cron_activities").sudo()._trigger()

    def _pan_ai_tell(self, agent, text):
        record = self.env[self.res_model].browse(self.res_id).exists()
        if record and hasattr(record, "message_post"):
            record.with_user(agent.user_id).sudo().message_post(
                body=html_escape(text), message_type="comment", subtype_xmlid="mail.mt_note"
            )

    # ---- the queue -------------------------------------------------------

    @api.model
    def _cron_pan_ai_activities(self):
        Agent = self.env["pan_ai.agent"]
        queue = self.sudo().search(
            [("pan_ai_assigned_by", "!=", False), ("pan_ai_run_id", "=", False)],
            order="id",
            limit=QUEUE_BATCH,
        )
        seen = set()
        for activity in queue:
            agent = Agent._mentioned(activity.user_id.partner_id)
            if not agent:
                activity.pan_ai_assigned_by = False
                continue
            assigner = activity.pan_ai_assigned_by
            if (assigner.id, agent.id) in seen:
                continue
            seen.add((assigner.id, agent.id))
            chat, thread = self.env["discuss.channel"]._pan_ai_direct(agent, assigner)
            if not thread.live_run_id:
                activity._pan_ai_start(agent, chat, thread)
                commit(self.env)

    def _pan_ai_start(self, agent, chat, thread):
        assigner = self.pan_ai_assigned_by
        chat = chat.with_user(assigner)
        chat._pan_ai_agent_message(
            agent,
            html_escape(
                _(
                    "To-do from %(person)s: %(what)s, on %(record)s",
                    person=assigner.name,
                    what=self.summary or self.activity_type_id.name or _("an activity"),
                    record=self.res_name or "",
                )
            ),
        )
        placeholder = chat._pan_ai_agent_message(agent, _("Thinking"))
        try:
            run = (
                self.env["pan_ai.run"]
                .with_user(assigner)
                .start(
                    thread,
                    self._pan_ai_prompt(assigner),
                    kind="chat",
                    message=placeholder,
                    caller=assigner,
                    by_hand=True,
                )
            )
        except UserError as error:
            placeholder.sudo().write({"body": html_escape(str(error))})
            send_fields(chat.sudo(), placeholder, ["body"])
            self.pan_ai_assigned_by = False
            return
        self.pan_ai_run_id = run.id
        commit(self.env)
        run._wake_worker()

    def _pan_ai_prompt(self, assigner):
        record = self.env[self.res_model].sudo().browse(self.res_id)
        return "\n".join(
            [
                _("%s gave you a to-do in Odoo.", assigner.name),
                _("Activity: %s", self.activity_type_id.name or "-"),
                _("Summary: %s", self.summary or "-"),
                _("Due: %s", self.date_deadline or "-"),
                _("Note: %s", html2plaintext(self.note or "") or "-"),
                _(
                    'Record: %(what)s "%(name)s" (model %(model)s, id %(id)s)',
                    what=record._description,
                    name=self.res_name or "",
                    model=self.res_model,
                    id=self.res_id,
                ),
                _(
                    "Do it with your tools. End with one or two sentences on what you did: "
                    "they are logged on the record when the to-do is marked done."
                ),
            ]
        )

    @api.model
    def _pan_ai_finish(self, run):
        """A run that ended Done: its activity is marked done by the agent,
        the answer as feedback, and the next to-do may start."""
        activity = self.sudo().search([("pan_ai_run_id", "=", run.id)], limit=1)
        if not activity:
            return
        agent = run.thread_id.agent_id
        feedback = (run.text or "").strip()
        if run.allowed_calls:
            feedback += "\n\n" + _("Changes allowed by %s.", run.caller_id.name)
        activity.with_user(agent.user_id).sudo().action_feedback(feedback=feedback)
        self.env.ref("pan_ai_pro.cron_activities").sudo()._trigger()
