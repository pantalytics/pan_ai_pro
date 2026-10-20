# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
from odoo.exceptions import AccessError

from ..compat import params
from .common import AiProCase


class TestChannel(AiProCase):
    def test_one_chat_per_person_and_agent_until_new(self):
        Channel = self.env["discuss.channel"].with_user(self.user)
        a = Channel.pan_ai_chat(self.agent.id)
        b = Channel.pan_ai_chat(self.agent.id)
        self.assertEqual(a, b)
        self.assertEqual(a.channel_type, "ai")
        c = Channel.pan_ai_chat(self.agent.id, new=True)
        self.assertNotEqual(a, c)
        self.assertEqual(len(a.sudo().channel_member_ids), 2)

    def test_a_portal_user_cannot_chat(self):
        portal = self.env["res.users"].create(
            {
                "name": "P",
                "login": "p",
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        with self.assertRaises(AccessError):
            self.env["discuss.channel"].with_user(portal).pan_ai_chat(self.agent.id)

    def test_an_agent_closed_to_the_user_is_refused(self):
        self.agent.group_ids = [(6, 0, [self.env.ref("base.group_system").id])]
        with self.assertRaises(AccessError):
            self.env["discuss.channel"].with_user(self.user).pan_ai_chat(self.agent.id)
        self.assertEqual(self.env["discuss.channel"].with_user(self.user).pan_ai_agents(), [])

    def test_not_connected_answers_in_the_chat(self):
        self.license.sudo().write({"status": "not_connected", "key": False})
        self.fake(["never"])
        self.assertFalse(self.env["pan_ai.license"].current().is_entitled())
        channel, thread = self.chat(text="hi")
        self.assertFalse(thread.run_ids)
        self.assertIn("Connect to Pantalytics", channel.sudo().message_ids[:1].body)

    def test_retention_deletes_old_chats_and_keeps_runs(self):
        self.fake(["ok"])
        channel, thread = self.chat(text="hi")
        run = thread.run_ids[:1]
        params(self.env).set_str("pan_ai.retention_days", "1")
        thread.sudo().write({"last_activity": "2020-01-01 00:00:00"})
        self.env["pan_ai.thread"]._cron_retention()
        self.assertFalse(thread.exists())
        self.assertFalse(channel.exists())
        self.assertFalse(run.exists())

    def test_the_window_state_is_the_owners_only(self):
        from odoo.exceptions import AccessError

        self.fake([[("create_record", {"model": "res.partner", "values": {"name": "Mine"}})], "ok"])
        channel, thread = self.chat(text="create")
        run = thread.run_ids[:1]
        self.assertEqual(run.status, "interrupted")
        state = channel.with_user(self.user).pan_ai_state()
        self.assertEqual(state["run_id"], run.id)
        self.assertEqual(state["run_status"], "interrupted")
        self.assertEqual(state["message_id"], run.message_id.id)
        self.assertEqual(state["agent_id"], self.agent.id)
        self.assertEqual(state["pending"], thread.pending())
        self.assertEqual(state["pending"][0]["name"], "create_record")
        eve = self.env["res.users"].create(
            {
                "name": "Eve",
                "login": "eve_state",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        eves = channel.with_user(eve).pan_ai_state()
        self.assertFalse(eves["run_id"])
        self.assertEqual(eves["pending"], [])
        self.assertEqual(eves["text"], "")
        with self.assertRaises(AccessError):
            channel.with_user(eve).pan_ai_decide(run.id, {state["pending"][0]["id"]: True})
        channel.with_user(eve).pan_ai_stop()
        self.assertEqual(run.status, "interrupted")
        channel.with_user(self.user).pan_ai_decide(run.id, {state["pending"][0]["id"]: False})
        after = channel.with_user(self.user).pan_ai_state()
        self.assertFalse(after["run_id"])
        self.assertEqual(after["pending"], [])

    def test_retention_keeps_the_memory_of_other_kinds_and_drops_their_old_runs(self):
        from datetime import timedelta

        from odoo import fields

        from ..compat import params

        params(self.env).set_str("pan_ai.retention_days", "30")
        old = fields.Datetime.now() - timedelta(days=40)
        Thread = self.env["pan_ai.thread"].sudo()
        watch = Thread.create(
            {"name": "w", "kind": "continuous", "agent_id": self.agent.id, "user_id": self.user.id}
        )
        Run = self.env["pan_ai.run"].sudo()
        gone = Run.create(
            {"thread_id": watch.id, "user_id": self.user.id, "status": "ok", "started_at": old}
        )
        kept = Run.create({"thread_id": watch.id, "user_id": self.user.id, "status": "ok"})
        field_thread = Thread.create(
            {"name": "f", "kind": "triggered", "agent_id": self.agent.id, "user_id": self.user.id}
        )
        self.env.cr.execute(
            "UPDATE pan_ai_thread SET create_date = %s WHERE id = %s", (old, field_thread.id)
        )
        field_thread.invalidate_recordset()
        Thread._cron_retention()
        self.assertTrue(watch.exists())
        self.assertFalse(gone.exists())
        self.assertTrue(kept.exists())
        self.assertFalse(field_thread.exists())

    def test_two_starts_on_one_thread_cannot_both_run(self):
        from odoo.exceptions import UserError

        self.fake(["one"])
        thread = (
            self.env["pan_ai.thread"]
            .sudo()
            .create({"name": "t", "agent_id": self.agent.id, "user_id": self.user.id})
        )
        Run = self.env["pan_ai.run"]
        first = Run.start(thread, "a", caller=self.user)
        self.assertEqual(first.status, "running")
        with self.assertRaises(UserError):
            Run.start(thread, "b", caller=self.user)
        # the index itself, past the compute: a second live row is refused
        import psycopg2

        with self.assertRaises(psycopg2.errors.UniqueViolation), self.env.cr.savepoint():
            Run.sudo().create({"thread_id": thread.id, "user_id": self.user.id, "prompt": "c"})
        self.assertEqual(len(thread.run_ids), 1)
