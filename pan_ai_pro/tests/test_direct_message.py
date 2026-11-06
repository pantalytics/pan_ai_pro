# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""A direct message to an agent's dedicated user is answered there, like a
colleague's (docs/plans/ai-colleague.md, slice 1)."""

from odoo.exceptions import AccessError

from .common import AiProCase


class TestDirectMessage(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = [(6, 0, [cls.env.ref("base.group_user").id])]
        cls.ava = cls.env["res.users"].create(
            {"name": "Ava", "login": "ava_agent", "group_ids": internal}
        )
        cls.bob = cls.env["res.users"].create(
            {"name": "Bob", "login": "bob", "group_ids": internal}
        )
        cls.agent.write({"run_as": "user", "user_id": cls.ava.id, "in_channels": True})

    def chat(self, user, partner):
        return self.env["discuss.channel"].with_user(user)._get_or_create_chat([partner.id])

    def post(self, channel, text, user=None):
        return channel.with_user(user or self.user).message_post(
            body=text, message_type="comment", subtype_xmlid="mail.mt_comment"
        )

    def said_by(self, channel, user):
        return channel.sudo().message_ids.filtered(
            lambda m: m.author_id == user.partner_id and m.message_type == "comment"
        )

    def test_a_direct_message_is_answered_there_as_the_dedicated_user(self):
        self.fake(["Three quotes are open."])
        dm = self.chat(self.user, self.ava.partner_id)
        self.post(dm, "Which quotes for Acme are open?")
        thread = dm.sudo().pan_ai_thread_ids
        self.assertEqual(len(thread), 1)
        run = thread.run_ids
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.user_id, self.ava, "it works with its own reach")
        self.assertEqual(run.caller_id, self.user)
        self.assertIn("Sam sent you a direct message", thread.conversation)
        self.assertIn("Sam: Which quotes for Acme are open?", thread.conversation)
        self.assertIn("Three quotes", self.said_by(dm, self.ava).body)

    def test_every_message_continues_the_same_conversation(self):
        self.fake(["first"])
        dm = self.chat(self.user, self.ava.partner_id)
        self.post(dm, "hi")
        self.fake(["second"])
        self.post(dm, "and now?")
        thread = dm.sudo().pan_ai_thread_ids
        self.assertEqual(len(thread), 1)
        self.assertEqual(len(thread.run_ids), 2)
        self.assertEqual(thread.conversation.count("Sam: hi"), 1, "old lines are not sent again")

    def test_a_chat_between_people_is_left_alone(self):
        self.fake(["never"])
        dm = self.chat(self.user, self.bob.partner_id)
        self.post(dm, "lunch?")
        self.assertFalse(dm.sudo().pan_ai_thread_ids)

    def test_an_agent_that_does_not_answer_in_discuss_stays_quiet(self):
        self.fake(["never"])
        self.agent.in_channels = False
        dm = self.chat(self.user, self.ava.partner_id)
        self.post(dm, "hi")
        self.assertFalse(dm.sudo().pan_ai_thread_ids)

    def test_a_person_who_may_not_use_the_agent_gets_told(self):
        self.fake(["never"])
        self.agent.group_ids = [(6, 0, [self.env.ref("base.group_system").id])]
        dm = self.chat(self.user, self.ava.partner_id)
        self.post(dm, "hi")
        self.assertFalse(dm.sudo().pan_ai_thread_ids.run_ids)
        self.assertIn("You may not use", self.said_by(dm, self.ava).body)

    def test_the_asker_decides_and_nobody_else_reads_the_chat(self):
        self.fake([[("create_record", {"model": "res.partner", "values": {"name": "Acme"}})], "ok"])
        dm = self.chat(self.user, self.ava.partner_id)
        self.post(dm, "create Acme")
        run = dm.sudo().pan_ai_thread_ids.run_ids
        self.assertEqual(run.status, "interrupted")
        state = dm.pan_ai_state()
        self.assertEqual(state["asker_uid"], self.user.id)
        with self.assertRaises(AccessError):
            dm.with_user(self.bob).pan_ai_decide(run.id, {state["pending"][0]["id"]: True})
        dm.pan_ai_decide(run.id, {state["pending"][0]["id"]: False})
        self.assertEqual(run.status, "ok")
