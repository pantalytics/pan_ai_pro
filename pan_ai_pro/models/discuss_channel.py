"""The chat: a `discuss.channel` of type `ai`, one per (person, agent, thread).

The person types in Odoo's own chat window; `message_post` starts a run on
the thread behind the channel and the agent's answer streams into its own
message over the bus (runtime/stream.py). The window's buttons (Stop,
approve, new chat, pick an agent) are the RPCs at the bottom.
"""

import logging

from markupsafe import escape as html_escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

from ..compat import send_fields
from ..tools import commit

_logger = logging.getLogger(__name__)

PROMPT_MAX = 16000


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    channel_type = fields.Selection(selection_add=[("ai", "AI")], ondelete={"ai": "cascade"})
    pan_ai_thread_ids = fields.One2many("pan_ai.thread", "channel_id")

    # ---- opening a chat ------------------------------------------------

    @api.model
    def pan_ai_chat(self, agent_id, new=False):
        """This person's chat with the agent: the latest one, or a new one."""
        agent = self.env["pan_ai.agent"].browse(agent_id).exists()
        if not agent or not agent.may_use():
            raise AccessError(_("You may not use this agent."))
        Thread = self.env["pan_ai.thread"]
        if not new:
            thread = Thread.search(
                [
                    ("user_id", "=", self.env.uid),
                    ("agent_id", "=", agent.id),
                    ("kind", "=", "chat"),
                    ("channel_id", "!=", False),
                ],
                limit=1,
            )
            if thread:
                return thread.channel_id
        channel = self.sudo().create(
            {
                "name": agent.name,
                "channel_type": "ai",
                "channel_member_ids": [
                    (0, 0, {"partner_id": self.env.user.partner_id.id}),
                    (0, 0, {"partner_id": agent.partner_id.id}),
                ],
            }
        )
        Thread.create({"name": agent.name, "agent_id": agent.id, "channel_id": channel.id})
        return channel.with_env(self.env)

    @api.model
    def pan_ai_open(self, agent_id=None, new=False, channel_id=None):
        """RPC for the window: the channel id to open. The agent comes from
        the call, else from the channel the person is in, else the first
        agent open to them."""
        if not agent_id and channel_id:
            thread = self.browse(channel_id)._pan_ai_thread()
            agent_id = thread.agent_id.id if thread else None
        if not agent_id:
            agents = self.env["pan_ai.agent"].search([], limit=50).filtered(lambda a: a.may_use())
            if not agents:
                raise UserError(_("No agent is open to you. Ask an administrator."))
            agent_id = agents[0].id
        return self.pan_ai_chat(agent_id, new=new).id

    @api.model
    def pan_ai_agents(self):
        """The agents this person may chat with, for the picker."""
        return [
            {"id": a.id, "name": a.name, "description": a.description or ""}
            for a in self.env["pan_ai.agent"].search([]).filtered(lambda a: a.may_use())
        ]

    def _pan_ai_thread(self):
        self.ensure_one()
        return self.sudo().pan_ai_thread_ids[:1]

    # ---- the person typed ----------------------------------------------

    def message_post(self, *, message_type="notification", partner_ids=None, **kwargs):
        message = super().message_post(message_type=message_type, partner_ids=partner_ids, **kwargs)
        if (
            self.channel_type == "ai"
            and message_type == "comment"
            and not self.env.context.get("pan_ai_agent_post")
        ):
            self._pan_ai_on_user_message(message)
        return message

    def _pan_ai_on_user_message(self, message):
        from ..runtime import slices

        if self.env.user.share:
            raise AccessError(_("Only internal users can chat with an agent."))
        thread = self._pan_ai_thread()
        if not thread or thread.user_id != self.env.user:
            raise AccessError(_("This chat is not yours."))
        prompt = html2plaintext(message.body or "").strip()[:PROMPT_MAX]
        if not prompt:
            return
        Run = self.env["pan_ai.run"]
        placeholder = self._pan_ai_agent_message(thread.agent_id, _("Thinking"))
        try:
            run = Run.start(thread, prompt, kind="chat", message=placeholder)
        except UserError as error:
            # The refusal is the agent's answer: in the same bubble, no second one.
            placeholder.sudo().write({"body": html_escape(str(error))})
            send_fields(self.sudo(), placeholder, ["body"])
            return
        # The person's message and the placeholder reach the browser now, not
        # at the end of the slice.
        commit(self.env)
        token = run._claim()
        if token:
            slices.run_slice(run, token, where="inline")

    def _pan_ai_agent_message(self, agent, body):
        return (
            self.sudo()
            .with_context(pan_ai_agent_post=True)
            .message_post(
                author_id=agent.partner_id.id,
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        )

    # ---- the window's buttons ----------------------------------------

    def pan_ai_stop(self):
        self.ensure_one()
        thread = self._pan_ai_thread()
        if thread and thread.user_id == self.env.user and thread.live_run_id:
            thread.live_run_id.action_stop()
        return True

    def pan_ai_decide(self, run_id, approvals):
        """The approval card: {tool_call_id: true|false} for the pending calls."""
        self.ensure_one()
        thread = self._pan_ai_thread()
        if not thread or thread.user_id != self.env.user:
            raise AccessError(_("This chat is not yours."))
        run = self.env["pan_ai.run"].sudo().browse(run_id)
        if run.thread_id != thread:
            raise AccessError(_("This run is not on this chat."))
        run.action_decide(approvals)
        return True

    def pan_ai_state(self):
        """What the window needs on open: the live run and its pending calls."""
        self.ensure_one()
        thread = self._pan_ai_thread()
        run = thread and thread.live_run_id
        return {
            "thread_id": thread.id if thread else False,
            "agent_id": thread.agent_id.id if thread else False,
            "agent_name": thread.agent_id.name if thread else "",
            "run_id": run.id if run else False,
            "run_status": run.status if run else "",
            "message_id": run.message_id.id if run and run.message_id else False,
            "pending": thread.pending() if thread else [],
        }
