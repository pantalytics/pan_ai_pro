# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Scheduled, triggered and continuous runs: the server action "Run AI
agent", the ticks of a continuous thread, and who they run as."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..compat import params
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
        # The answer is posted as the person; Odoo 19 lets a plain user post
        # a note only on a record they may write, so Sam manages contacts.
        self.user.write({"group_ids": [(4, self.env.ref("base.group_partner_manager").id)]})
        self.fake(["A fine contact."])
        action = self._action(pan_ai_post=True)
        partner = self.user.partner_id
        action.with_user(self.user).with_context(
            active_model="res.partner", active_ids=partner.ids, active_id=partner.id
        ).run()
        thread = self.env["pan_ai.thread"].search(
            [("res_model", "=", "res.partner"), ("res_id", "=", partner.id)]
        )
        # The person's request only created the run; a worker runs it.
        self.assertEqual(thread.run_ids[:1].slices, 0)
        self.env["pan_ai.run"]._cron_run_slices()
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
        # a new watch starts from now: the first tick sets the cursor and
        # makes no run (the model's history is not a change)
        self.env["pan_ai.run"]._cron_run_slices()
        self.assertEqual(len(thread.run_ids), 0)
        self.assertTrue(thread.watch_cursor)
        self.assertTrue(thread.next_tick_at > thread.watch_cursor)
        # nothing changed: a due tick moves the clock and makes no run (the
        # cursor sits past the test transaction's own clock, which stamps
        # whatever the fixtures still write)
        thread.write(
            {
                "next_tick_at": "2020-01-01 00:00:00",
                "watch_cursor": fields.Datetime.now() + timedelta(seconds=30),
            }
        )
        self.env["pan_ai.thread"]._start_due_ticks()
        self.assertEqual(len(thread.run_ids), 0)
        # a change since the cursor: a run with it in the prompt, and memory
        self.user.partner_id.write({"name": "Sam Changed"})
        self.env.cr.flush()
        self.env.cr.execute(
            "UPDATE res_partner SET write_date = now() + interval '1 minute' WHERE id = %s",
            (self.user.partner_id.id,),
        )
        self.user.partner_id.invalidate_recordset()
        thread.write({"next_tick_at": "2020-01-01 00:00:00"})
        self.env["pan_ai.run"]._cron_run_slices()
        self.assertEqual(len(thread.run_ids), 1)
        self.assertEqual(thread.run_ids[0].kind, "continuous")
        prompts = [
            p["content"]
            for m in thread.messages()
            for p in m.get("parts", [])
            if p.get("part_kind") == "user-prompt"
        ]
        self.assertEqual(len(prompts), 1)
        self.assertIn("Sam Changed", prompts[-1])
        # paused: no tick
        thread.write({"paused": True, "next_tick_at": "2020-01-01 00:00:00"})
        self.env["pan_ai.thread"]._start_due_ticks()
        self.assertEqual(len(thread.run_ids), 1)

    def test_the_hourly_cap_refuses_by_hand_starts_only(self):
        from odoo.exceptions import UserError as _UserError

        from ..compat import params

        params(self.env).set_str("pan_ai.runs_per_user_per_hour", "1")
        self.fake(["one"])
        thread = (
            self.env["pan_ai.thread"]
            .sudo()
            .create({"name": "t", "agent_id": self.agent.id, "user_id": self.user.id})
        )
        Run = self.env["pan_ai.run"]
        Run.start(thread, "a", kind="chat", caller=self.user)._finish("ok")
        with self.assertRaises(_UserError):
            Run.start(thread, "b", kind="chat", caller=self.user)
        # a watch's tick and a rule's run are not the person's doing: never refused
        Run.start(thread, "c", kind="continuous", caller=self.user)._finish("ok")
        Run.start(thread, "d", kind="triggered", caller=self.user)._finish("ok")
        # a Fill button is: the cap applies
        with self.assertRaises(_UserError):
            Run._check_may_start(self.agent, self.user, "triggered", by_hand=True)

    def _watch(self, **vals):
        return self.env["pan_ai.thread"].create(
            {
                "name": "Watch contacts",
                "kind": "continuous",
                "agent_id": self.agent.id,
                "user_id": self.user.id,
                "watch_model_id": self.env["ir.model"]._get_id("res.partner"),
                "watch_domain": "[]",
                "watch_interval": 1,
                "next_tick_at": "2020-01-01 00:00:00",
                **vals,
            }
        )

    def test_a_watch_pauses_instead_of_looping(self):
        from ..compat import params

        Thread = self.env["pan_ai.thread"]
        # a deactivated user
        gone = self._watch()
        self.user.sudo().write({"active": False})
        Thread._start_due_ticks()
        self.assertTrue(gone.paused)
        self.assertFalse(gone.run_ids)
        self.user.sudo().write({"active": True})
        # a watch that cannot be read (past its first look, which only sets the cursor)
        bad = self._watch(
            watch_domain="[('no_such_field', '=', 1)]", watch_cursor="2020-01-01 00:00:00"
        )
        Thread._start_due_ticks()
        self.assertTrue(bad.paused)
        self.assertFalse(bad.run_ids)
        # a start that is refused keeps the cursor, so Resume sees the changes
        refused = self._watch(watch_cursor="2020-01-01 00:00:00")
        params(self.env).set_str("pan_ai.openrouter_key", "")
        self.fake(["never"])
        Thread._start_due_ticks()
        self.assertTrue(refused.paused)
        self.assertFalse(refused.run_ids)
        self.assertEqual(refused.watch_cursor, fields.Datetime.from_string("2020-01-01 00:00:00"))
        self.assertGreater(refused.next_tick_at, fields.Datetime.from_string("2020-01-02 00:00:00"))
        params(self.env).set_str("pan_ai.openrouter_key", "sk-or-test")
        self.fake(["Noted."])
        refused.action_resume()
        self.env["pan_ai.run"]._cron_run_slices()
        self.assertEqual(len(refused.run_ids), 1)
        self.assertEqual(refused.run_ids.status, "ok")

    def test_a_watch_that_hits_a_limit_pauses(self):
        watch = self._watch(watch_cursor="2020-01-01 00:00:00")
        self.agent.sudo().write({"request_limit": 1})
        self.addCleanup(self.agent.sudo().write, {"request_limit": 25})
        self.fake([[("today", {})], [("today", {})], "never"])
        self.env["pan_ai.run"]._cron_run_slices()
        run = watch.run_ids[:1]
        self.assertEqual((run.status, run.error_code), ("failed", "limit"))
        self.assertTrue(watch.paused)
        watch.write({"next_tick_at": "2020-01-01 00:00:00"})
        self.env["pan_ai.thread"]._start_due_ticks()
        self.assertEqual(len(watch.run_ids), 1)

    def test_a_record_that_refuses_the_note_leaves_the_run_ok(self):
        from unittest.mock import patch

        from odoo.exceptions import AccessError

        self.fake(["A fine contact."])
        action = self._action(pan_ai_post=True)
        other = self.env["res.partner"].sudo().create({"name": "Not mine"})
        action.with_user(self.user).with_context(
            active_model="res.partner", active_ids=other.ids, active_id=other.id
        ).run()
        with patch.object(
            type(self.env["res.partner"]), "message_post", side_effect=AccessError("no")
        ):
            self.env["pan_ai.run"]._cron_run_slices()
        run = self.env["pan_ai.thread"].search([("res_id", "=", other.id)]).run_ids[:1]
        self.assertEqual(run.status, "ok")
        self.assertIn("fine contact", run.text)
        self.assertIn("could not be posted", run.error)

    def test_a_failed_triggered_run_says_so_on_the_record(self):
        from pydantic_ai.exceptions import ModelHTTPError
        from pydantic_ai.models.function import FunctionModel

        from ..runtime import agent as agent_runtime

        async def stream_fn(messages, info):
            raise ModelHTTPError(status_code=429, model_name="fake", body=None)
            yield  # pragma: no cover - makes this an async generator

        agent_runtime.TEST_MODEL = FunctionModel(stream_function=stream_fn)
        self.user.write({"group_ids": [(4, self.env.ref("base.group_partner_manager").id)]})
        partner = self.user.partner_id
        self._action(pan_ai_post=True).with_user(self.user).with_context(
            active_model="res.partner", active_ids=partner.ids, active_id=partner.id
        ).run()
        self.env["pan_ai.run"]._cron_run_slices()
        thread = self.env["pan_ai.thread"].search([("res_id", "=", partner.id)])
        self.assertEqual(thread.run_ids.status, "failed")
        note = partner.message_ids.filtered(lambda m: "429" in (m.body or ""))
        self.assertTrue(note, partner.message_ids.mapped("body"))
        self.assertIn("failed", note.body)
        self.assertEqual(note.author_id, self.user.partner_id)

    def test_a_run_sees_every_company_of_its_user(self):
        main = self.env.company
        other = self.env["res.company"].create({"name": "Company B"})
        self.env["res.partner"].create({"name": "Only in B", "company_id": other.id})
        both = self.env["res.users"].create(
            {
                "name": "Bo",
                "login": "bo",
                "company_id": main.id,
                "company_ids": [(6, 0, [main.id, other.id])],
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        search = (
            "search_records",
            {"model": "res.partner", "domain": [["name", "=", "Only in B"]], "fields": ["name"]},
        )
        for user, count in ((both, 1), (self.user, 0)):
            self.fake([[search], "Done."])
            channel, thread = self.chat(user=user, text="Find it")
            self.assertEqual(thread.run_ids.status, "ok", thread.run_ids.error)
            found = [
                p["content"]["count"]
                for m in thread.messages()
                for p in m["parts"]
                if p["part_kind"] == "tool-return"
            ]
            self.assertEqual(found, [count], user.name)

    def test_the_action_menu_is_by_hand_and_bounded(self):
        from ..compat import params
        from ..models.ir_actions_server import BY_HAND_MAX

        action = self._action()
        many = (
            self.env["res.partner"]
            .sudo()
            .create([{"name": f"m{i}"} for i in range(BY_HAND_MAX + 1)])
        )
        with self.assertRaisesRegex(UserError, "at most"):
            action.with_user(self.user).with_context(
                active_model="res.partner", active_ids=many.ids, active_id=many[0].id
            ).run()
        params(self.env).set_str("pan_ai.runs_per_user_per_hour", "1")
        one = many[:1]
        action.with_user(self.user).with_context(
            active_model="res.partner", active_ids=one.ids, active_id=one.id
        ).run()
        run = self.env["pan_ai.thread"].search([("res_id", "=", one.id)]).run_ids
        self.assertEqual(run.caller_id, self.user)
        with self.assertRaisesRegex(UserError, "hourly limit"):
            action.with_user(self.user).with_context(
                active_model="res.partner", active_ids=many[1:2].ids, active_id=many[1].id
            ).run()

    def test_a_tick_with_more_changes_than_it_names_keeps_its_place(self):
        from unittest.mock import patch

        from ..models import thread as thread_model

        self.fake(["Noted."])
        watch = self._watch()
        self.env["pan_ai.thread"]._start_due_ticks()  # a new watch starts from now
        self.assertFalse(watch.run_ids)
        self.assertTrue(watch.watch_cursor)
        # the cursor sits past the test transaction's own clock, which stamps
        # whatever the fixtures still write (Sam's partner, on Odoo 20)
        watch.write({"watch_cursor": fields.Datetime.now() + timedelta(seconds=30)})
        # three records changed in one transaction: they share one write_date
        new = self.env["res.partner"].sudo().create([{"name": f"t{i}"} for i in range(3)])
        self.env.cr.flush()
        self.env.cr.execute(
            "UPDATE res_partner SET write_date = now() + interval '1 minute' WHERE id IN %s",
            (tuple(new.ids),),
        )
        new.invalidate_recordset()
        watch.write({"next_tick_at": "2020-01-01 00:00:00"})
        with patch.object(thread_model, "TICK_BATCH", 2):
            self.env["pan_ai.run"]._cron_run_slices()
        self.assertEqual(len(watch.run_ids), 1)
        prompt = watch.messages()[0]["parts"][0]["content"]
        self.assertIn("More changed after these", prompt)
        self.assertIn(f"res.partner {new[0].id}:", prompt)
        self.assertIn(f"res.partner {new[1].id}:", prompt)
        self.assertNotIn(f"res.partner {new[2].id}:", prompt)
        # the cursor sits on the last change named; the rest comes next time
        self.assertEqual(watch.watch_cursor_id, new[1].id)
        watch.write({"next_tick_at": "2020-01-01 00:00:00"})
        with patch.object(thread_model, "TICK_BATCH", 2):
            self.env["pan_ai.run"]._cron_run_slices()
        self.assertEqual(len(watch.run_ids), 2)
        prompts = [
            p["content"]
            for m in watch.messages()
            for p in m.get("parts", [])
            if p.get("part_kind") == "user-prompt"
        ]
        self.assertIn(f"res.partner {new[2].id}:", prompts[-1])
        self.assertNotIn("More changed", prompts[-1])

    def test_a_waiting_run_with_a_recent_heartbeat_is_not_stuck(self):
        self.fake([[("today", {})], [("today", {})], "Never."])
        from unittest.mock import patch

        from ..runtime import slices

        with patch.object(slices, "slice_budget", return_value=0.0):
            thread = (
                self.env["pan_ai.thread"]
                .sudo()
                .create({"name": "t", "agent_id": self.agent.id, "user_id": self.user.id})
            )
            run = self.env["pan_ai.run"].start(thread, "go", caller=self.user)
            run._run_now("inline")
        self.assertEqual(run.status, "running")
        # started long ago, but served a moment ago: the workers are just busy
        run.write(
            {
                "started_at": fields.Datetime.now() - timedelta(hours=2),
                "heartbeat_at": fields.Datetime.now(),
            }
        )
        self.env["pan_ai.run"]._cron_mark_stuck()
        self.assertEqual(run.status, "running")
        run.write({"heartbeat_at": fields.Datetime.now() - timedelta(hours=2)})
        self.env["pan_ai.run"]._cron_mark_stuck()
        self.assertEqual(run.status, "failed")


# A rule is wired into the registry only once it is ready, so after install.
@tagged("post_install", "-at_install")
class TestRuleSave(AiProCase):
    _action = TestRuns._action

    def test_a_rule_never_fails_the_save_when_the_agent_may_not_run(self):
        """A rule whose agent is refused (no key, lapsed plan, closed agent)
        lets the person's save through and runs nothing; the log says why."""
        rule = self.env["base.automation"].create(
            {
                "name": "Summarise on save",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "trigger": "on_create_or_write",
            }
        )
        self._action(base_automation_id=rule.id)
        params(self.env).set_str("pan_ai.openrouter_key", "")
        admin = self.env.ref("base.user_admin")
        with self.assertLogs("odoo.addons.pan_ai_pro.models.ir_actions_server", "WARNING") as log:
            partner = self.env["res.partner"].with_user(admin).create({"name": "Saved anyway"})
            partner.write({"name": "Saved anyway, twice"})
        self.assertEqual(partner.name, "Saved anyway, twice")
        self.assertIn("OpenRouter key", log.output[0])
        self.assertFalse(
            self.env["pan_ai.thread"].search(
                [("res_model", "=", "res.partner"), ("res_id", "=", partner.id)]
            )
        )
