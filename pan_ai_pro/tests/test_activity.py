# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Pick an agent on an activity and it does the to-do for the person it is
assigned to, in their AI chat with it; no Odoo user per agent
(docs/plans/ai-colleague.md, section 3)."""

from .common import AiProCase

WRITE_PHONE = "write_record"


class TestActivity(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user.group_ids = [(4, cls.env.ref("base.group_partner_manager").id)]
        cls.acme = cls.env["res.partner"].create({"name": "Acme", "phone": "111"})

    def todo(self, summary="Call back", creator=None, **values):
        return (
            self.env["mail.activity"]
            .with_user(creator or self.user)
            .create(
                {
                    "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                    "res_id": self.acme.id,
                    "user_id": self.user.id,
                    "summary": summary,
                    "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                    "pan_ai_agent_id": self.agent.id,
                    **values,
                }
            )
        )

    def pick_up(self):
        self.env["mail.activity"]._cron_pan_ai_activities()

    def notes_by_agent(self):
        return self.acme.message_ids.filtered(lambda m: m.author_id == self.agent.partner_id)

    def is_open(self, activity):
        return bool(activity.exists() and activity.active)

    def write_phone(self):
        return [
            (WRITE_PHONE, {"model": "res.partner", "id": self.acme.id, "values": {"phone": "222"}})
        ]

    def test_the_agent_does_the_todo_in_the_persons_chat_and_marks_it_done(self):
        self.fake(["Called Acme, they want a quote."])
        activity = self.todo()
        self.pick_up()
        run = activity.pan_ai_run_id
        self.assertEqual((run.caller_id, run.user_id), (self.user, self.user), "their rights")
        chat = run.thread_id.channel_id
        self.assertEqual(chat.channel_type, "ai", "the person's own chat with the agent")
        self.assertIn("To-do: Call back, on Acme", " ".join(chat.sudo().message_ids.mapped("body")))
        self.assertIn('Record: Contact "Acme"', run.prompt)
        run._run_now("cron")
        self.assertEqual(run.status, "ok")
        self.assertFalse(self.is_open(activity), "done means the activity is marked done")
        self.assertIn("they want a quote", " ".join(self.notes_by_agent().mapped("body")))

    def test_no_agent_no_work(self):
        self.fake(["never"])
        activity = self.todo(pan_ai_agent_id=False)
        self.pick_up()
        self.assertFalse(activity.pan_ai_run_id)

    def test_one_todo_at_a_time_per_chat(self):
        self.fake(["first done"])
        first = self.todo("First")
        second = self.todo("Second")
        self.pick_up()
        self.assertTrue(first.pan_ai_run_id)
        self.assertFalse(second.pan_ai_run_id, "the second waits for the first")
        first.pan_ai_run_id._run_now("cron")
        self.fake(["second done"])
        self.pick_up()
        self.assertTrue(second.pan_ai_run_id)

    def test_a_todo_an_automation_made_waits_for_its_person(self):
        self.fake([self.write_phone(), "Phone updated."])
        activity = self.todo("Fix the phone", creator=self.env.ref("base.user_root"))
        self.pick_up()
        run = activity.pan_ai_run_id
        self.assertEqual(run.caller_id, self.user, "the person the to-do is assigned to decides")
        run._run_now("cron")
        self.assertEqual(run.status, "interrupted")
        self.assertTrue(self.is_open(activity))
        chat = run.thread_id.channel_id.with_user(self.user)
        call = chat.pan_ai_state()["pending"][0]
        self.assertIn('Change Contact "Acme"', call["effect"])
        chat.pan_ai_decide(run.id, {call["id"]: True})
        self.assertEqual(self.acme.phone, "222")
        self.assertFalse(self.is_open(activity))
        self.assertIn("Changes allowed by Sam", " ".join(self.notes_by_agent().mapped("body")))

    def test_an_approval_nobody_decides_on_stops_after_a_day(self):
        self.fake([self.write_phone(), "never"])
        activity = self.todo("Fix the phone")
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

    def test_a_person_who_may_not_use_the_agent_gets_nothing_done(self):
        self.agent.group_ids = [(6, 0, [self.env.ref("base.group_system").id])]
        activity = self.todo()
        self.pick_up()
        self.assertFalse(activity.pan_ai_run_id)
        self.assertFalse(activity.pan_ai_agent_id)
