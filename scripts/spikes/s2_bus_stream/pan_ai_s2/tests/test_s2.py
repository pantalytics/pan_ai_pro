import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "pan_ai_s2")
class TestS2(HttpCase):
    def test_stream_into_message(self):
        admin = self.env.ref("base.user_admin")
        channel_id = self.env["discuss.channel"].with_user(admin).pan_ai_s2_new_chat()
        self.start_tour(f"/odoo/discuss?active_id={channel_id}", "pan_ai_s2", login="admin")
        report = json.loads(self.env["ir.config_parameter"].sudo().get_str("pan_ai_s2.report"))
        print("\n[pan_ai_s2] REPORT", json.dumps(report, indent=1))
        # Behaviour only. Latency is NOT measurable here: HttpCase's TestCursor
        # turns commits into savepoints, so the bus rows and the NOTIFY land at
        # the end of the request and every batch arrives at once (measured
        # 2026-10-19: 2084 ms here, 50 ms on a real server). measure.py is
        # the latency check, against a real server.
        self.assertGreater(report["batches"], 3)
        self.assertEqual(report["stream_divs_left"], 0, "the stream must hand over to the final body")
        channel = self.env["discuss.channel"].browse(channel_id)
        bodies = channel.message_ids.sorted("id").mapped("body")
        self.assertIn("Azure Interior", str(bodies[-1]))
        self.assertEqual(len(channel.message_ids), 2, "one user message, one agent message, written once")
