# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The two Odoo versions through one door: the config parameters and the bus."""

from ..compat import params
from .common import AiProCase


class TestCompat(AiProCase):
    def test_params_agree_on_the_edge_cases(self):
        p = params(self.env)
        # An empty value: 20 stores "", 19 drops the row; both read as empty.
        p.set_str("pan_ai.t", "")
        self.assertEqual(p.get_str("pan_ai.t", ""), "")
        self.assertFalse(p.get_str("pan_ai.t"))
        p.set_int("pan_ai.t", 7)
        self.assertEqual(p.get_int("pan_ai.t"), 7)
        p.set_str("pan_ai.t", "abc")
        self.assertEqual(p.get_int("pan_ai.t", 3), 3)
        p.set_bool("pan_ai.t", True)
        self.assertTrue(p.get_bool("pan_ai.t"))
        p.set_str("pan_ai.t", "off")
        self.assertFalse(p.get_bool("pan_ai.t", True))

    def test_the_run_events_and_the_body_reach_the_channels_bus(self):
        """Every flush commits (a flush, in a test), which writes the bus rows."""
        import json

        Bus = self.env["bus.bus"].sudo()
        last = Bus.search([], order="id desc", limit=1).id or 0
        self.fake(["hi there"])
        channel, thread = self.chat()
        run = thread.run_ids[:1]
        rows = [json.loads(row.message) for row in Bus.search([("id", ">", last)])]
        events = [row["payload"] for row in rows if row.get("type") == "pan_ai.run_event"]
        self.assertTrue(events, rows[:2])
        self.assertTrue(any(e["channel_id"] == channel.id and e["final"] for e in events))
        others = [json.dumps(row) for row in rows if row.get("type") != "pan_ai.run_event"]
        self.assertTrue(any("hi there" in o and str(run.message_id.id) in o for o in others))
