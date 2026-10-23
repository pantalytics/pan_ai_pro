# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The chat: a `discuss.channel` of type `ai`, one per (person, agent, thread).

The person types in Odoo's own chat window; `message_post` starts a run on
the thread behind the channel and the agent's answer streams into its own
message over the bus (runtime/stream.py). The window's buttons (Stop,
approve, new chat, pick an agent) are the RPCs at the bottom.

In a team channel or a group, mentioning the dedicated user of an agent
that answers in channels does the same in a thread (Odoo's sub-channel)
under the message, as that user, for everybody in the channel to read
(docs/plans/agent-in-discuss.md).
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
        Thread.sudo().create(
            {
                "name": agent.name,
                "agent_id": agent.id,
                "channel_id": channel.id,
                "user_id": self.env.uid,
            }
        )
        return channel.with_env(self.env)

    @api.model
    def pan_ai_open(self, agent_id=None, new=False, channel_id=None):
        """RPC for the window: the channel id to open. The agent comes from
        the call, else from the channel the person is in, else the first
        agent open to them."""
        if not agent_id and channel_id:
            channel = self.browse(channel_id)
            channel.check_access("read")
            thread = channel._pan_ai_thread()
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
        if message_type == "comment" and not self.env.context.get("pan_ai_agent_post"):
            if self.channel_type == "ai":
                self._pan_ai_on_user_message(message)
            elif self.channel_type in ("channel", "group") and partner_ids:
                self._pan_ai_on_mention(message, partner_ids)
        return message

    def _pan_ai_on_user_message(self, message):

        if self.env.user.share:
            raise AccessError(_("Only internal users can chat with an agent."))
        thread = self._pan_ai_thread()
        if not thread or thread.user_id != self.env.user:
            raise AccessError(_("This chat is not yours."))
        prompt = html2plaintext(message.body or "").strip()[:PROMPT_MAX]
        if not prompt:
            return
        if not thread.run_ids:
            # The first prompt names the thread in the Conversations list.
            thread.sudo().write({"name": prompt[:60] + ("..." if len(prompt) > 60 else "")})
        self._pan_ai_answer(thread, prompt)

    def _pan_ai_on_mention(self, message, partner_ids):
        """A mention of an agent's dedicated user in a channel or a group: the
        agent answers in the thread under the message, or in the thread the
        mention was made in. One agent per thread; a second one says so.
        Only a mention by name counts: @everyone is for the people."""
        named = message.partner_ids.filtered(lambda p: p.id in partner_ids)
        agent = self.env["pan_ai.agent"]._mentioned(named)
        if not agent or agent.user_id == self.env.user or self.env.user.share:
            return
        channel = self if self.parent_channel_id else self._pan_ai_sub_channel(message)
        thread = channel._pan_ai_thread()
        if thread and thread.agent_id != agent:
            channel._pan_ai_agent_message(
                agent,
                html_escape(
                    _(
                        "%s answers in this thread. Ask me in a new one.",
                        thread.agent_id.name,
                    )
                ),
            )
            return
        if not thread:
            thread = (
                self.env["pan_ai.thread"]
                .sudo()
                .create(
                    {
                        "name": channel.name,
                        "agent_id": agent.id,
                        "channel_id": channel.id,
                        "user_id": self.env.uid,
                    }
                )
            )
        channel._pan_ai_answer(thread, channel._pan_ai_mention_prompt(thread, agent))

    def _pan_ai_sub_channel(self, message):
        """The thread under `message`: Odoo's own, made as the person who
        asked, so the parent shows "Sam started a thread" like any other."""
        existing = self.sudo().sub_channel_ids.filtered(lambda c: c.from_message_id == message)
        return existing[:1].with_env(self.env) or self._create_sub_channel(
            from_message_id=message.id
        )

    def _pan_ai_mention_prompt(self, thread, agent):
        """What the people said since the agent last spoke here, one line per
        message, oldest first; on a new thread the message it hangs under."""
        Message = self.env["mail.message"].sudo()
        domain = [
            ("model", "=", "discuss.channel"),
            ("res_id", "=", self.id),
            ("message_type", "=", "comment"),
        ]
        me = agent.user_id.partner_id
        last = Message.search(domain + [("author_id", "=", me.id)], order="id desc", limit=1)
        if last:
            domain.append(("id", ">", last.id))
        messages = Message.search(domain, order="id desc", limit=50)
        if not thread.run_ids and self.from_message_id:
            messages |= self.from_message_id.sudo()
        lines = []
        for m in messages.sorted("id"):
            # Without the link footnotes a mention adds ("[1] /odoo/res.partner/7").
            text = html2plaintext(m.body or "", include_references=False).strip()
            if text:
                lines.append(f"{m.author_id.name or _('Someone')}: {text}")
        head = _(
            "You were mentioned in the Discuss channel %(channel)s. "
            "What was said since your last answer, oldest first:",
            channel=(self.parent_channel_id or self).display_name,
        )
        # Over the cap, the newest lines stay: the question is the last one.
        return head + "\n" + "\n".join(lines)[-PROMPT_MAX:]

    def _pan_ai_answer(self, thread, prompt):
        """The agent's bubble, then the run, its first slice inline."""
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
        run._run_now("inline")

    def _pan_ai_agent_message(self, agent, body):
        # In a team channel the agent speaks as its dedicated user, the one
        # people mention; in its own chat as its chat identity.
        author = agent.partner_id if self.channel_type == "ai" else agent.user_id.partner_id
        return (
            self.sudo()
            .with_context(pan_ai_agent_post=True)
            .message_post(
                author_id=author.id,
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        )

    # ---- the window's buttons ----------------------------------------

    def _pan_ai_may_see(self, thread):
        """An AI chat is its owner's; a thread in a team channel is everybody's
        who may read the channel, as its messages are."""
        # sudo: a person outside the chat may not read the channel's type either
        if self.sudo().channel_type == "ai":
            return thread.user_id == self.env.user
        return self.has_access("read")

    @staticmethod
    def _pan_ai_asker(run):
        """Who may stop a run and decide on its calls: the person who asked."""
        return run.caller_id or run.thread_id.user_id

    def pan_ai_stop(self):
        self.ensure_one()
        run = self._pan_ai_thread().live_run_id
        if run and self._pan_ai_asker(run) == self.env.user:
            run.action_stop()
        return True

    def pan_ai_decide(self, run_id, approvals):
        """The approval card: {tool_call_id: true|false} for the pending calls."""
        self.ensure_one()
        thread = self._pan_ai_thread()
        run = self.env["pan_ai.run"].sudo().browse(run_id)
        if not thread or run.thread_id != thread:
            raise AccessError(_("This run is not on this chat."))
        if self._pan_ai_asker(run) != self.env.user:
            raise AccessError(_("Only the person who asked can decide."))
        run.action_decide(approvals)
        return True

    def pan_ai_state(self):
        """What the window needs on open: the live run and its pending calls,
        for whoever may read the chat (an AI chat: its owner only)."""
        self.ensure_one()
        thread = self._pan_ai_thread()
        if thread and not self._pan_ai_may_see(thread):
            # Not theirs: the window gets nothing to show, and no error dialog.
            thread = None
        run = thread and thread.live_run_id
        asker = run and self._pan_ai_asker(run)
        return {
            "thread_id": thread.id if thread else False,
            "agent_id": thread.agent_id.id if thread else False,
            "agent_name": thread.agent_id.name if thread else "",
            "run_id": run.id if run else False,
            "run_status": run.status if run else "",
            "text": run.text if run else "",
            "message_id": run.message_id.id if run and run.message_id else False,
            "pending": thread.pending() if thread else [],
            "asker_uid": asker.id if asker else False,
            "asker_name": asker.name if asker else "",
        }
