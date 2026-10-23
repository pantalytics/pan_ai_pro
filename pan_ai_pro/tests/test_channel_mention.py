# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An agent mentioned in a team channel answers in a thread under the message
(docs/plans/agent-in-discuss.md)."""

import psycopg2

from odoo.exceptions import AccessError, ValidationError
from odoo.tools import mute_logger

from ..compat import params
from .common import AiProCase


class TestChannelMention(AiProCase):
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
        cls.sales = cls.env["discuss.channel"].create({"name": "sales", "channel_type": "channel"})
        cls.sales._add_members(users=cls.user | cls.ava | cls.bob, post_joined_message=False)

    def post(self, channel, text, partners=(), user=None, **kwargs):
        return channel.with_user(user or self.user).message_post(
            body=text,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            partner_ids=[p.id for p in partners],
            **kwargs,
        )

    def thread_under(self, message):
        sub = self.sales.sudo().sub_channel_ids.filtered(lambda c: c.from_message_id == message)
        return sub, sub.pan_ai_thread_ids[:1]

    def agent_messages(self, channel):
        return channel.sudo().message_ids.filtered(
            lambda m: m.author_id == self.ava.partner_id and m.message_type == "comment"
        )

    def test_a_mention_answers_in_a_thread_as_the_dedicated_user(self):
        self.fake(["Three quotes are open."])
        message = self.post(self.sales, "@Ava open quotes for Acme?", [self.ava.partner_id])
        sub, thread = self.thread_under(message)
        self.assertTrue(sub, "the answer goes in a thread under the message")
        run = thread.run_ids
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.user_id, self.ava, "the channel's answer carries the agent's reach")
        self.assertEqual(run.caller_id, self.user)
        self.assertIn("Sam: @Ava open quotes for Acme?", run.prompt or thread.conversation)
        self.assertIn("Three quotes", self.agent_messages(sub).body)
        self.assertFalse(self.agent_messages(self.sales), "nothing from the agent in the channel")

    def test_only_a_mention_starts_a_run_and_the_prompt_is_what_came_since(self):
        self.fake(["first"])
        message = self.post(self.sales, "@Ava hi", [self.ava.partner_id])
        sub, thread = self.thread_under(message)
        self.post(sub, "Bob, do you know?", user=self.user)
        self.post(sub, "No idea", user=self.bob)
        self.assertEqual(len(thread.run_ids), 1, "people talk in the thread without the agent")
        self.fake(["second"])
        self.post(sub, "@Ava and now?", [self.ava.partner_id], user=self.bob)
        second = thread.run_ids.sorted("id")[-1]
        self.assertEqual(len(thread.run_ids), 2)
        self.assertEqual(second.caller_id, self.bob)
        conversation = thread.conversation
        self.assertIn("Bob: No idea", conversation)
        self.assertIn("Bob: @Ava and now?", conversation)
        self.assertEqual(conversation.count("Sam: @Ava hi"), 1, "the old lines are not sent again")

    def test_everyone_is_for_the_people(self):
        self.fake(["never"])
        message = self.post(self.sales, "Office closed Friday", special_mentions=["everyone"])
        sub, thread = self.thread_under(message)
        self.assertFalse(sub)
        self.assertFalse(
            self.env["pan_ai.thread"].sudo().search([("agent_id", "=", self.agent.id)])
        )

    def test_a_person_who_may_not_use_the_agent_gets_told(self):
        self.fake(["never"])
        self.agent.group_ids = [(6, 0, [self.env.ref("base.group_system").id])]
        message = self.post(self.sales, "@Ava hi", [self.ava.partner_id])
        sub, thread = self.thread_under(message)
        self.assertFalse(thread.run_ids)
        self.assertIn("You may not use", self.agent_messages(sub).body)

    def test_the_asker_decides_and_the_channel_sees_who_it_waits_for(self):
        self.fake([[("create_record", {"model": "res.partner", "values": {"name": "Acme"}})], "ok"])
        message = self.post(self.sales, "@Ava create Acme", [self.ava.partner_id])
        sub, thread = self.thread_under(message)
        run = thread.run_ids
        self.assertEqual(run.status, "interrupted")
        sub = sub.with_user(self.bob)
        state = sub.pan_ai_state()
        self.assertEqual(state["run_id"], run.id, "a member sees the run the channel reads")
        self.assertEqual(state["asker_uid"], self.user.id)
        self.assertEqual(state["asker_name"], "Sam")
        call = state["pending"][0]["id"]
        with self.assertRaises(AccessError):
            sub.pan_ai_decide(run.id, {call: True})
        sub.pan_ai_stop()
        self.assertEqual(run.status, "interrupted", "only the asker stops it")
        sub.with_user(self.user).pan_ai_decide(run.id, {call: False})
        self.assertEqual(run.status, "ok")

    def test_one_agent_per_thread(self):
        self.fake(["first"])
        message = self.post(self.sales, "@Ava hi", [self.ava.partner_id])
        sub, thread = self.thread_under(message)
        max_user = self.env["res.users"].create(
            {
                "name": "Max",
                "login": "max_agent",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        other = self.agent.copy(
            {"name": "Other", "user_id": max_user.id, "in_channels": True, "partner_id": False}
        )
        self.sales._add_members(users=max_user, post_joined_message=False)
        self.post(sub, "@Max you too?", [max_user.partner_id])
        self.assertFalse(
            self.env["pan_ai.thread"].sudo().search([("agent_id", "=", other.id)]),
            "a second agent does not join a thread",
        )
        said = sub.sudo().message_ids.filtered(lambda m: m.author_id == max_user.partner_id)
        self.assertIn("answers in this thread", said.body)

    def test_retention_keeps_the_peoples_thread(self):
        self.fake(["ok"])
        message = self.post(self.sales, "@Ava hi", [self.ava.partner_id])
        sub, thread = self.thread_under(message)
        params(self.env).set_str("pan_ai.retention_days", "1")
        thread.write({"last_activity": "2020-01-01 00:00:00"})
        self.env["pan_ai.thread"]._cron_retention()
        self.assertFalse(thread.exists())
        self.assertTrue(sub.exists(), "the channel's thread is the people's")

    def test_only_an_agent_with_a_dedicated_user_answers_in_channels(self):
        with (
            mute_logger("odoo.sql_db"),
            self.assertRaises(psycopg2.errors.CheckViolation),
            self.env.cr.savepoint(),
        ):
            self.agent.write({"run_as": "caller"})
            self.env.cr.flush()
        with self.assertRaises(ValidationError):
            self.agent.copy({"name": "Twin", "in_channels": True, "partner_id": False})
