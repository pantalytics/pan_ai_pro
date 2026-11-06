# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An activity can be done by an agent (docs/plans/ai-colleague.md,
section 3): pick the agent on the activity, and it does the to-do.

The activity stays assigned to its person: the to-do is theirs, the agent
does it for them. That person is the caller (their limit, their Allow and
Skip) and the work happens in their AI chat with the agent, one to-do at a
time per chat: the open activities are the queue, picked up by a cron that
every assignment and every finished to-do wakes. No Odoo user per agent, so
no seat: five agents cost nothing extra. Done means the agent's answer is a
note on the record from the agent, and the activity is marked done. A
failure or a Stop leaves it open.
"""

from markupsafe import escape as html_escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

from ..compat import send_fields
from ..runtime.stream import render_markdown
from ..tools import commit

QUEUE_BATCH = 20


class MailActivity(models.Model):
    _inherit = "mail.activity"

    pan_ai_agent_id = fields.Many2one(
        "pan_ai.agent",
        string="Done by agent",
        ondelete="set null",
        index="btree_not_null",
        help="The agent does this to-do for the person it is assigned to, with their "
        "rights and their approval.",
    )
    pan_ai_run_id = fields.Many2one("pan_ai.run", readonly=True, copy=False, ondelete="set null")

    @api.model_create_multi
    def create(self, vals_list):
        activities = super().create(vals_list)
        activities.filtered("pan_ai_agent_id")._pan_ai_queue()
        return activities

    def write(self, vals):
        result = super().write(vals)
        if {"pan_ai_agent_id", "user_id"} & set(vals):
            self.filtered("pan_ai_run_id").sudo().write({"pan_ai_run_id": False})
            self.filtered("pan_ai_agent_id")._pan_ai_queue()
        return result

    def _pan_ai_queue(self):
        """Start them after this transaction, never inside somebody's save."""
        self.env.ref("pan_ai_pro.cron_activities").sudo()._trigger()

    # ---- the queue -------------------------------------------------------

    @api.model
    def _cron_pan_ai_activities(self):
        queue = self.sudo().search(
            [("pan_ai_agent_id", "!=", False), ("pan_ai_run_id", "=", False)],
            order="id",
            limit=QUEUE_BATCH,
        )
        seen = set()
        for activity in queue:
            person, agent = activity.user_id, activity.pan_ai_agent_id
            if (person.id, agent.id) in seen:
                continue
            if not activity.res_model:
                activity.pan_ai_agent_id = False  # a to-do needs a record to work on
                continue
            seen.add((person.id, agent.id))
            if not person or person.share:
                activity.pan_ai_agent_id = False
                continue
            try:
                chat = self.env["discuss.channel"].with_user(person).pan_ai_chat(agent.id)
            except AccessError:
                activity.pan_ai_agent_id = False  # this person may not use the agent
                continue
            thread = chat._pan_ai_thread()
            if thread and not thread.live_run_id:
                activity._pan_ai_start(agent, chat, thread)
                commit(self.env)

    def _pan_ai_start(self, agent, chat, thread):
        person = self.user_id
        chat._pan_ai_agent_message(
            agent,
            html_escape(
                _(
                    "To-do: %(what)s, on %(record)s",
                    what=self.summary or self.activity_type_id.name or _("an activity"),
                    record=self.res_name or "",
                )
            ),
        )
        placeholder = chat._pan_ai_agent_message(agent, _("Thinking"))
        try:
            run = (
                self.env["pan_ai.run"]
                .with_user(person)
                .start(
                    thread,
                    self._pan_ai_prompt(),
                    kind="chat",
                    message=placeholder,
                    caller=person,
                    by_hand=True,
                )
            )
        except UserError as error:
            placeholder.sudo().write({"body": html_escape(str(error))})
            send_fields(chat.sudo(), placeholder, ["body"])
            self.pan_ai_agent_id = False
            return
        self.pan_ai_run_id = run.id
        run.sudo().todo = True
        commit(self.env)
        run._wake_worker()

    def _pan_ai_prompt(self):
        record = self.env[self.res_model].sudo().browse(self.res_id)
        return "\n".join(
            [
                _("A to-do in Odoo that %s asked you to do.", self.user_id.name),
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
                    "they are posted on the record when the to-do is marked done."
                ),
            ]
        )

    @api.model
    def _pan_ai_finish(self, run):
        """A run that ended Done: the agent's answer on the record, from the
        agent, and the activity marked done by its person."""
        activity = self.sudo().search([("pan_ai_run_id", "=", run.id)], limit=1)
        if not activity:
            return
        agent = activity.pan_ai_agent_id
        text = (run.text or "").strip()
        if run.allowed_calls:
            text += "\n\n" + _("Changes allowed by %s.", run.caller_id.name)
        record = self.env[activity.res_model].browse(activity.res_id).exists()
        if record and hasattr(record, "message_post"):
            record.sudo().message_post(
                author_id=agent.partner_id.id,
                body=render_markdown(text),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        activity.with_user(activity.user_id).sudo().action_feedback(
            feedback=_("Done by %s.", agent.name)
        )
        self.env.ref("pan_ai_pro.cron_activities").sudo()._trigger()


class MailActivitySchedule(models.TransientModel):
    """Odoo's own "Schedule Activity" dialog (the chatter's Activity button)
    is this wizard, not the activity's form: it gets the same field and
    hands it to the activities it makes."""

    _inherit = "mail.activity.schedule"

    pan_ai_agent_id = fields.Many2one(
        "pan_ai.agent",
        string="Done by agent",
        help="The agent does this to-do for the person it is assigned to, with their "
        "rights and their approval.",
    )

    def _action_schedule_activities(self):
        activities = super()._action_schedule_activities()
        if self.pan_ai_agent_id and activities:
            activities.filtered("res_model").write({"pan_ai_agent_id": self.pan_ai_agent_id.id})
        return activities
