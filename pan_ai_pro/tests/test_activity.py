# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An activity assigned to the agent's user is its to-do, worked on in the
assigner's direct chat with it (docs/plans/ai-colleague.md, section 3)."""

from .common import AiProCase


class TestActivity(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user")
        contacts = cls.env.ref("base.group_partner_manager")
        cls.ava = cls.env["res.users"].create(
            {"name": "Ava", "login": "ava_agent", "group_ids": [(6, 0, [internal.id, contacts.id])]}
        )
        cls.user.group_ids = [(4, contacts.id)]
        cls.agent.write({"run_as": "user", "user_id": cls.ava.id, "in_channels": True})
        cls.acme = cls.env["res.partner"].create({"name": "Acme", "phone": "111"})

    def assign(self, summary="Call back", user=None):
        return (
            self.env["mail.activity"]
            .with_user(user or self.user)
            .create(
                {
                    "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                    "res_id": self.acme.id,
                    "user_id": self.ava.id,
                    "summary": summary,
                    "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                }
            )
        )

    def pick_up(self):
        self.env["mail.activity"]._cron_pan_ai_activities()

    def notes_by_ava(self):
        return self.acme.message_ids.filtered(lambda m: m.author_id == self.ava.partner_id)

    def is_open(self, activity):
        return bool(activity.exists() and activity.active)

    def test_a_todo_is_worked_on_in_the_chat_and_marked_done(self):
        self.fake(["Called Acme, they want a quote."])
        activity = self.assign()
        self.assertEqual(activity.pan_ai_assigned_by, self.user)
        self.pick_up()
        run = activity.pan_ai_run_id
        self.assertEqual((run.caller_id, run.user_id), (self.user, self.ava))
        chat = run.thread_id.channel_id
        self.assertEqual(chat.channel_type, "chat")
        self.assertIn(
            "To-do from Sam: Call back, on Acme", chat.sudo().message_ids.mapped("body")[-1]
        )
        self.assertIn('Record: Contact "Acme"', run.prompt)
        run._run_now("cron")
        self.assertEqual(run.status, "ok")
        self.assertFalse(self.is_open(activity), "done means the activity is marked done")
        self.assertIn("they want a quote", " ".join(self.notes_by_ava().mapped("body")))

    def test_one_todo_at_a_time_per_chat(self):
        self.fake(["first done"])
        first = self.assign("First")
        second = self.assign("Second")
        self.pick_up()
        self.assertTrue(first.pan_ai_run_id)
        self.assertFalse(second.pan_ai_run_id, "the second waits for the first")
        first.pan_ai_run_id._run_now("cron")
        self.fake(["second done"])
        self.pick_up()
        self.assertTrue(second.pan_ai_run_id)

    def test_odoobot_cannot_give_the_agent_work(self):
        activity = self.assign(user=self.env.ref("base.user_root"))
        self.assertFalse(activity.pan_ai_assigned_by)
        self.assertIn("A person has to give me this to-do", self.notes_by_ava().body)

    def test_a_change_waits_for_the_assigner_and_is_named_in_the_feedback(self):
        self.fake(
            [
                [
                    (
                        "write_record",
                        {"model": "res.partner", "id": self.acme.id, "values": {"phone": "222"}},
                    )
                ],
                "Phone updated.",
            ]
        )
        activity = self.assign("Fix the phone")
        self.pick_up()
        run = activity.pan_ai_run_id
        run._run_now("cron")
        self.assertEqual(run.status, "interrupted")
        self.assertTrue(self.is_open(activity))
        chat = run.thread_id.channel_id.with_user(self.user)
        call = chat.pan_ai_state()["pending"][0]
        self.assertIn('Change Contact "Acme"', call["effect"])
        chat.pan_ai_decide(run.id, {call["id"]: True})
        self.assertEqual(self.acme.phone, "222")
        self.assertFalse(self.is_open(activity))
        self.assertIn("Changes allowed by Sam", " ".join(self.notes_by_ava().mapped("body")))

    def test_an_approval_nobody_decides_on_stops_after_a_day(self):
        self.fake(
            [
                [
                    (
                        "write_record",
                        {"model": "res.partner", "id": self.acme.id, "values": {"phone": "222"}},
                    )
                ],
                "never",
            ]
        )
        activity = self.assign("Fix the phone")
        self.pick_up()
        run = activity.pan_ai_run_id
        run._run_now("cron")
        self.env.cr.execute(
            "UPDATE pan_ai_run SET write_date = now() - interval '25 hours' WHERE id = %s",
            [run.id],
        )
        run.invalidate_recordset(["write_date"])
        self.env["pan_ai.run"]._cron_expire_approvals()
        self.assertEqual(run.status, "cancelled")
        self.assertEqual(self.acme.phone, "111")
        self.assertTrue(self.is_open(activity), "a to-do that was not done stays open")
