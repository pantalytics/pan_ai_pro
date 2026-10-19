"""Scheduled, triggered and continuous runs: the server action "Run AI
agent", the ticks of a continuous thread, and who they run as."""

from odoo.exceptions import UserError

from .common import AiProCase


class TestRuns(AiProCase):
    def _action(self, **vals):
        return self.env["ir.actions.server"].create(
            {
                "name": "Summarise",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "pan_ai_run",
                "pan_ai_agent_id": self.agent.id,
                "pan_ai_prompt": "Summarise {{ object.name }}",
                **vals,
            }
        )

    def test_a_triggered_run_gets_the_record_and_posts_the_answer(self):
        self.fake(["A fine contact."])
        action = self._action(pan_ai_post=True)
        partner = self.user.partner_id
        action.with_user(self.user).with_context(
            active_model="res.partner", active_ids=partner.ids, active_id=partner.id
        ).run()
        thread = self.env["pan_ai.thread"].search(
            [("res_model", "=", "res.partner"), ("res_id", "=", partner.id)]
        )
        self.assertEqual(thread.kind, "triggered")
        self.assertEqual(thread.user_id, self.user)
        run = thread.run_ids[:1]
        self.assertEqual(run.status, "ok", run.error)
        self.assertEqual(run.kind, "triggered")
        self.assertIn("fine contact", run.text)
        # the prompt was rendered from the record
        self.assertIn("Sam", thread.messages()[0]["parts"][0]["content"])
        # and the answer landed in the chatter, as the run's user
        note = partner.message_ids.filtered(lambda m: "fine contact" in (m.body or ""))
        self.assertTrue(note)
        self.assertEqual(note.author_id, self.user.partner_id)

    def test_a_scheduled_run_has_no_record(self):
        self.fake(["Nothing to report."])
        action = self._action(model_id=self.env["ir.model"]._get_id("res.users"))
        action.with_user(self.user).run()
        thread = self.env["pan_ai.thread"].search([("kind", "=", "scheduled")], limit=1)
        self.assertTrue(thread)
        self.assertFalse(thread.res_model)
        self.assertEqual(thread.run_ids[:1].status, "ok")

    def test_odoobot_may_not_run_an_agent(self):
        self.fake(["never"])
        action = self._action()
        with self.assertRaises(UserError):
            action.with_user(self.env.ref("base.user_root")).run()

    def test_a_dedicated_user_carries_the_run(self):
        self.fake(["As the bot."])
        bot = self.env["res.users"].create(
            {
                "name": "Agent bot",
                "login": "agentbot",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.agent.write({"run_as": "user", "user_id": bot.id})
        channel, thread = self.chat(text="hi")
        run = thread.run_ids[:1]
        self.assertEqual(run.user_id, bot)
        self.assertEqual(run.caller_id, self.user)
        self.assertEqual(thread.user_id, self.user)

    def test_a_continuous_thread_ticks_on_changes_only(self):
        self.fake(["Noted."])
        thread = self.env["pan_ai.thread"].create(
            {
                "name": "Watch contacts",
                "kind": "continuous",
                "agent_id": self.agent.id,
                "user_id": self.user.id,
                "watch_model_id": self.env["ir.model"]._get_id("res.partner"),
                "watch_domain": "[]",
                "watch_interval": 1,
                "next_tick_at": "2020-01-01 00:00:00",
            }
        )
        # first tick: everything the user may see counts as changed
        self.env["pan_ai.thread"]._start_due_ticks()
        self.assertEqual(len(thread.run_ids), 1)
        self.assertEqual(thread.run_ids[0].kind, "continuous")
        self.assertTrue(thread.watch_cursor)
        self.assertTrue(thread.next_tick_at > thread.watch_cursor)
        # nothing changed: a due tick moves the clock and makes no run
        thread.write({"next_tick_at": "2020-01-01 00:00:00"})
        self.env["pan_ai.thread"]._start_due_ticks()
        self.assertEqual(len(thread.run_ids), 1)
        # a change since the cursor: a run with it in the prompt, and memory
        self.user.partner_id.write({"name": "Sam Changed"})
        self.env.cr.flush()
        self.env.cr.execute(
            "UPDATE res_partner SET write_date = now() + interval '1 minute' WHERE id = %s",
            (self.user.partner_id.id,),
        )
        self.user.partner_id.invalidate_recordset()
        thread.write({"next_tick_at": "2020-01-01 00:00:00"})
        self.env["pan_ai.thread"]._start_due_ticks()
        self.assertEqual(len(thread.run_ids), 2)
        prompts = [
            p["content"]
            for m in thread.messages()
            for p in m.get("parts", [])
            if p.get("part_kind") == "user-prompt"
        ]
        self.assertEqual(len(prompts), 2)
        self.assertIn("Sam Changed", prompts[-1])
        # paused: no tick
        thread.write({"paused": True, "next_tick_at": "2020-01-01 00:00:00"})
        self.env["pan_ai.thread"]._start_due_ticks()
        self.assertEqual(len(thread.run_ids), 2)
