# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""A run with nobody behind it (an automation, a schedule, a watch) asks the
agent's sponsor to allow its changes, in the sponsor's AI chat with the
agent (docs/plans/agent-identity.md, section 4; #58)."""

from odoo.exceptions import AccessError

from .common import AiProCase


class TestSponsor(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        contacts = cls.env.ref("base.group_partner_manager")
        cls.user.group_ids = [(4, contacts.id)]
        cls.bob = cls.env["res.users"].create(
            {
                "name": "Bob",
                "login": "bob",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, contacts.id])],
            }
        )
        cls.acme = cls.env["res.partner"].create({"name": "Acme", "phone": "111"})

    def background_run(self):
        """A rule Bob's save triggered: it wants to change Acme's phone."""
        self.fake(
            [
                [
                    (
                        "write_record",
                        {"model": "res.partner", "id": self.acme.id, "values": {"phone": "222"}},
                    )
                ],
                "Phone fixed.",
            ]
        )
        thread = (
            self.env["pan_ai.thread"]
            .sudo()
            .create(
                {
                    "name": "Fix phones",
                    "kind": "triggered",
                    "agent_id": self.agent.id,
                    "user_id": self.bob.id,
                    "res_model": "res.partner",
                    "res_id": self.acme.id,
                }
            )
        )
        run = self.env["pan_ai.run"].start(thread, "fix it", kind="triggered", caller=self.bob)
        run._run_now("cron")
        return run

    def test_the_sponsor_is_asked_in_their_chat_and_decides(self):
        self.agent.sponsor_id = self.user
        run = self.background_run()
        self.assertEqual(run.status, "interrupted")
        chat = self.env["discuss.channel"].with_user(self.user).pan_ai_chat(self.agent.id)
        self.assertEqual(run.message_id.res_id, chat.id, "the question waits in Sam's chat")
        self.assertIn("Waiting for your OK", run.message_id.body)
        state = chat.pan_ai_state()
        self.assertEqual((state["run_id"], state["asker_uid"]), (run.id, self.user.id))
        call = state["pending"][0]
        self.assertIn('Change Contact "Acme"', call["effect"])
        bob_chat = self.env["discuss.channel"].with_user(self.bob).pan_ai_chat(self.agent.id)
        with self.assertRaises(AccessError):
            bob_chat.pan_ai_decide(run.id, {call["id"]: True})
        chat.pan_ai_decide(run.id, {call["id"]: True})
        self.assertEqual(run.status, "ok")
        self.assertEqual(self.acme.phone, "222")

    def test_without_a_sponsor_it_waits_in_the_activity_list(self):
        self.agent.sponsor_id = False
        run = self.background_run()
        self.assertEqual(run.status, "interrupted")
        self.assertFalse(run.message_id)

    def test_a_new_agent_is_sponsored_by_who_made_it(self):
        Agent = self.env["pan_ai.agent"].with_user(self.env.ref("base.user_admin"))
        agent = Agent.sudo(False).create({"name": "Mila"})
        self.assertEqual(agent.sponsor_id, self.env.ref("base.user_admin"))
