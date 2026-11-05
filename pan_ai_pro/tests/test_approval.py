# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Approval without undo: the card shows the effect, an Allow on a record
that changed since does not run, every decision is counted
(docs/plans/ai-colleague.md, section 8)."""

import json

from .common import AiProCase


class TestApproval(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].create({"name": "Acme", "phone": "111"})
        cls.user.group_ids = [(4, cls.env.ref("base.group_partner_manager").id)]

    def ask(self, script, text="do it"):
        self.fake(script)
        chat = self.env["discuss.channel"].with_user(self.user).pan_ai_chat(self.agent.id)
        chat.message_post(body=text, message_type="comment", subtype_xmlid="mail.mt_comment")
        thread = chat.sudo().pan_ai_thread_ids
        return thread, thread.run_ids.sorted("id")[-1]

    def write_phone(self):
        return [
            (
                "write_record",
                {"model": "res.partner", "id": self.acme.id, "values": {"phone": "222"}},
            )
        ]

    def test_a_change_shows_the_record_and_old_and_new_values(self):
        thread, run = self.ask([self.write_phone(), "done"])
        self.assertEqual(run.status, "interrupted")
        call = thread.pending()[0]
        self.assertEqual(call["effect"], 'Change Contact "Acme": Phone: 111 → 222')
        self.assertEqual((call["model"], call["res_id"]), ("res.partner", self.acme.id))

    def test_a_create_shows_what_it_makes(self):
        thread, run = self.ask(
            [[("create_record", {"model": "res.partner", "values": {"name": "Bolt BV"}})], "ok"]
        )
        self.assertEqual(thread.pending()[0]["effect"], "Create Contact: Name: Bolt BV")

    def test_an_allow_runs_and_is_counted(self):
        thread, run = self.ask([self.write_phone(), "done"])
        run.with_user(self.user).action_decide({thread.pending()[0]["id"]: True})
        self.assertEqual(run.status, "ok")
        self.assertEqual(self.acme.phone, "222")
        self.assertEqual((run.allowed_calls, run.skipped_calls), (1, 0))
        decisions = [e for e in json.loads(run.tool_log) if e.get("decision")]
        self.assertEqual(decisions[0]["decision"], "allowed")

    def test_an_allow_on_a_record_that_changed_since_does_not_run(self):
        thread, run = self.ask([self.write_phone(), "I will read it again."])
        pending = thread.pending()
        # Another transaction changed the record after the proposal.
        pending[0]["stamp"] = "2000-01-01 00:00:00"
        thread.sudo().pending_tool_calls = json.dumps(pending)
        run.with_user(self.user).action_decide({pending[0]["id"]: True})
        self.assertEqual(run.status, "ok")
        self.assertEqual(self.acme.phone, "111", "what the person approved is not what is there")
        self.assertEqual((run.allowed_calls, run.skipped_calls), (0, 1))
        self.assertIn("the record changed", thread.conversation)
