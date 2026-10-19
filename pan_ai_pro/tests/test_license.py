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

from ..models import license as license_model


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
        self.db_uuid = self.env["ir.config_parameter"].sudo().get_str("database.uuid")

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
        signature = base64.b64encode(
            self.private.sign(license_model.canonical_json(payload))
        ).decode()
        return {"entitlement": payload, "signature": signature}

    def _heartbeat(self, response, code=200):
        with (
            patch.dict("os.environ", {license_model.ENV_PUBLIC_KEY: self.public_b64}),
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

    def test_an_expired_answer_lapses(self):
        self._heartbeat(
            self._signed(
                valid_until=(fields.Datetime.now() - timedelta(days=1)).isoformat() + "+00:00"
            )
        )
        self.assertFalse(self.link.is_entitled())

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
