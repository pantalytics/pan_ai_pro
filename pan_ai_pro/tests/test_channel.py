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
