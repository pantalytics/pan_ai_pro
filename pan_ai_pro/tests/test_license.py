# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The connection: entitled only on a signed, unexpired answer for this
database; every run start asks."""

import base64
import json
from datetime import timedelta
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from ..compat import params
from ..models import platform


class TestLicense(TransactionCase):
    def setUp(self):
        super().setUp()
        self.private = Ed25519PrivateKey.generate()
        public = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.public_b64 = base64.b64encode(public).decode()
        self.env["pan_ai.license"].sudo().search([]).unlink()
        self.link = self.env["pan_ai.license"].sudo().create({"status": "active", "key": "mp_x"})
        self.db_uuid = params(self.env).get_str("database.uuid")

    def _signed(self, **overrides):
        payload = {
            "version": 1,
            "app": "ai_pro",
            "installation_id": 1,
            "db_uuid": self.db_uuid,
            "status": "active",
            "plan": "beta",
            "issued_at": "2026-10-19T00:00:00+00:00",
            "valid_until": (fields.Datetime.now() + timedelta(days=14)).isoformat() + "+00:00",
            "latest_version": "",
            "message": "",
        }
        payload.update(overrides)
        signature = base64.b64encode(self.private.sign(platform.canonical_json(payload))).decode()
        return {"entitlement": payload, "signature": signature}

    def _heartbeat(self, response, code=200):
        with (
            patch.dict("os.environ", {platform.ENV_PUBLIC_KEY: self.public_b64}),
            patch.object(type(self.link), "_post", return_value=(code, response)),
        ):
            self.link._heartbeat()

    def test_not_connected_refuses_a_run(self):
        self.link.write({"status": "not_connected", "key": False})
        with self.assertRaises(UserError) as caught:
            self.env["pan_ai.license"].require_entitled()
        self.assertIn("Connect to Pantalytics", str(caught.exception))

    def test_a_signed_answer_entitles(self):
        self._heartbeat(self._signed())
        self.assertEqual(self.link.plan, "beta")
        self.assertTrue(self.link.is_entitled())
        self.env["pan_ai.license"].require_entitled()

    def test_a_forged_answer_is_ignored(self):
        body = self._signed()
        body["entitlement"]["plan"] = "max"
        self._heartbeat(body)
        self.assertFalse(self.link.plan)
        self.assertIn("not signed", self.link.last_error)
        self.assertFalse(self.link.is_entitled())

    def test_another_databases_answer_is_ignored(self):
        self._heartbeat(self._signed(db_uuid="other"))
        self.assertFalse(self.link.is_entitled())
        self.assertIn("another Odoo", self.link.last_error)

    def test_revoked_stops_the_runs(self):
        self._heartbeat(self._signed())
        self._heartbeat(self._signed(status="revoked", plan=""))
        self.assertEqual(self.link.status, "revoked")
        with self.assertRaises(UserError):
            self.env["pan_ai.license"].require_entitled()

    def test_a_platform_outage_keeps_the_plan(self):
        self._heartbeat(self._signed())
        self._heartbeat({}, code=500)
        self.assertTrue(self.link.is_entitled())
        self.assertIn("500", self.link.last_error)
        with (
            patch.object(type(self.link), "_post", side_effect=UserError("unreachable")),
        ):
            self.link._heartbeat()
        self.assertTrue(self.link.is_entitled())

    def test_a_forgotten_key_stops_the_runs(self):
        self._heartbeat(self._signed())
        self._heartbeat({}, code=401)
        self.assertFalse(self.link.is_entitled())
        with self.assertRaises(UserError):
            self.env["pan_ai.license"].require_entitled()

    def test_an_expired_answer_lapses(self):
        self._heartbeat(
            self._signed(
                valid_until=(fields.Datetime.now() - timedelta(days=1)).isoformat() + "+00:00"
            )
        )
        self.assertFalse(self.link.is_entitled())
        # accepted, then expired: not refused for some other reason
        self.assertEqual(self.link.status, "active")
        self.assertIn("lapsed", self.link._why_not_entitled())

    def test_the_report_is_counts_only(self):
        report = self.link._report()
        self.assertEqual(
            set(report),
            {
                "db_uuid",
                "module_version",
                "odoo_version",
                "edition",
                "agents",
                "runs_24h",
                "errors",
            },
        )
        json.dumps(report)

    def test_each_state_refuses_with_its_own_reason(self):
        self.link.write({"status": "pending"})
        self.assertIn("waiting for approval", self.link._why_not_entitled())
        self.link.write({"status": "revoked"})
        self.assertIn("disconnected", self.link._why_not_entitled())
        self.link.write({"status": "invalid", "last_error": "nope."})
        self.assertIn("nope.", self.link._why_not_entitled())
        self.link.write({"status": "active", "plan": False})
        self.assertIn("no AI Pro plan", self.link._why_not_entitled())
        self.link.write({"plan": "beta", "valid_until": fields.Datetime.now() - timedelta(days=1)})
        self.assertIn("lapsed", self.link._why_not_entitled())

    def test_the_report_counts_error_codes_not_messages(self):
        thread = (
            self.env["pan_ai.thread"]
            .sudo()
            .create(
                {
                    "name": "t",
                    "agent_id": self.env.ref("pan_ai_pro.agent_assistant").id,
                    "user_id": self.env.uid,
                }
            )
        )
        run = (
            self.env["pan_ai.run"]
            .sudo()
            .create({"thread_id": thread.id, "user_id": self.env.uid, "prompt": "x"})
        )
        run._finish("failed", error="Acme Ltd owes 12,000: secret", code="limit")
        report = json.dumps(self._report_of(self.link))
        self.assertIn('"limit"', report)
        self.assertNotIn("Acme", report)

    def _report_of(self, link):
        return link._report()

    def test_a_platform_override_must_be_https_unless_local(self):
        with patch.dict("os.environ", {platform.ENV_URL: "http://127.0.0.1:8090/"}):
            self.assertEqual(platform._server_url(), "http://127.0.0.1:8090")
        with (
            patch.dict("os.environ", {platform.ENV_URL: "http://example.com"}),
            self.assertRaises(UserError),
        ):
            platform._server_url()
        with patch.dict("os.environ", {platform.ENV_URL: ""}):
            self.assertEqual(platform._server_url(), platform.SERVER_URL)
