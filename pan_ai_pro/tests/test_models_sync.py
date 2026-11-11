# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The model list is a shortlist per host; the daily sync only retires what a host dropped."""

from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


def _answer(*ids):
    response = MagicMock()
    response.json.return_value = {"data": [{"id": i, "name": i} for i in ids]}
    return response


@tagged("post_install", "-at_install")
class TestModelsSeed(TransactionCase):
    def test_shortlist_of_four_providers_sonnet_first(self):
        self.assertEqual(self.env["pan_ai.model"].search([])[0].host, "openrouter")
        rows = self.env["pan_ai.model"].search([("host", "=", "openrouter")])
        self.assertEqual(rows[0].model_name, "~anthropic/claude-sonnet-latest")
        self.assertEqual(self.env["pan_ai.model"].first(), rows[0])
        vendors = {m.lstrip("~").split("/")[0] for m in rows.mapped("model_name")}
        self.assertEqual(vendors, {"anthropic", "google", "openai", "mistralai"})
        self.assertNotIn("openrouter/auto", rows.mapped("model_name"))
        # OpenRouter's family aliases wherever it has one; Mistral has none.
        for model_name in rows.mapped("model_name"):
            if not model_name.startswith("mistralai/"):
                self.assertTrue(model_name.startswith("~") and model_name.endswith("-latest"))
        self.assertLess(len(rows), 15)
        self.assertTrue(all(rows.mapped("recommended")))

    def test_eurouter_shortlist_is_pinned_mistral_first(self):
        rows = self.env["pan_ai.model"].search([("host", "=", "eurouter")])
        self.assertEqual(rows[0].model_name, "mistral/mistral-large-4")
        self.assertEqual(rows[0].display_name, "Mistral Large (EUrouter)")
        self.assertTrue(all(rows.mapped("recommended")))
        self.assertFalse([m for m in rows.mapped("model_name") if m.startswith("~")])
        # The same id may sit on both hosts; twice on one host it may not.
        self.env["pan_ai.model"].create({"name": "Twin", "model_name": "mistral/mistral-large-4"})
        with self.assertRaises(ValidationError):
            self.env["pan_ai.model"].create({"name": "Bare", "model_name": "mistral-large-4"})

    def test_first_is_on_a_host_with_a_key(self):
        from ..compat import params

        Model = self.env["pan_ai.model"]
        params(self.env).set_str("pan_ai.openrouter_key", "")
        params(self.env).set_str("pan_ai.eurouter_key", "eu-test")
        self.assertEqual(Model.first(), self.env.ref("pan_ai_pro.model_eu_mistral_large"))
        action = self.env.ref("pan_ai_pro.agent_assistant").action_edit_model()
        self.assertEqual(action["params"]["hosts"], ["eurouter"])
        params(self.env).set_str("pan_ai.eurouter_key", "")
        self.assertEqual(Model.first().model_name, "~anthropic/claude-sonnet-latest")

    def test_first_prefers_a_recommended_row(self):
        Model = self.env["pan_ai.model"]
        pinned = Model.create({"name": "Pinned", "model_name": "openai/gpt-pinned", "sequence": 0})
        self.assertFalse(pinned.recommended)
        self.assertEqual(Model.first().model_name, "~anthropic/claude-sonnet-latest")
        Model.search([]).write({"recommended": False})
        self.assertEqual(Model.first(), pinned)

    def test_the_agent_picks_a_model_in_odoos_record_dialog(self):
        action = self.env.ref("pan_ai_pro.agent_assistant").action_edit_model()
        self.assertEqual(action["tag"], "pan_ai_pro.pick_model")
        self.assertEqual(
            action["params"]["agent_id"], self.env.ref("pan_ai_pro.agent_assistant").id
        )


@tagged("post_install", "-at_install")
class TestModelsSync(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Model = self.env["pan_ai.model"].with_context(active_test=False)
        self.Model.search([]).active = False  # agents point at the seeded rows
        self.kept = self.Model.create({"name": "My Sonnet", "model_name": "anthropic/sonnet"})
        self.dropped = self.Model.create({"name": "Old", "model_name": "old/model"})

    def _sync(self, side_effect=None, return_value=None):
        with patch(
            "odoo.addons.pan_ai_pro.models.ai_model.requests.get",
            side_effect=side_effect,
            return_value=return_value,
        ):
            self.Model._cron_sync()

    def test_archives_dropped_adds_nothing(self):
        self._sync(return_value=_answer("anthropic/sonnet", "anthropic/opus"))
        self.assertFalse(self.dropped.active)
        self.assertEqual(self.env["pan_ai.model"].search([]), self.kept)
        self.assertEqual(self.kept.name, "My Sonnet")
        found = self.env["pan_ai.model"].search([("display_name", "ilike", "anthropic/son")])
        self.assertEqual(found, self.kept)

    def test_each_host_is_checked_against_its_own_list(self):
        eu = self.Model.create({"name": "EU", "host": "eurouter", "model_name": "anthropic/sonnet"})
        eu_dropped = self.Model.create(
            {"name": "EU old", "host": "eurouter", "model_name": "x/old"}
        )
        eu_slug = self.Model.create(
            {"name": "EU slug", "host": "eurouter", "model_name": "mistral/large"}
        )

        def answer(url, timeout):
            if "eurouter" in url:
                response = _answer("anthropic/sonnet", "large")
                response.json.return_value["data"][1]["canonical_slug"] = "mistral/large"
                return response
            raise requests.ConnectionError("OpenRouter down")

        self._sync(side_effect=answer)
        self.assertTrue(eu.active)
        self.assertTrue(eu_slug.active)
        self.assertFalse(eu_dropped.active)
        self.assertTrue(self.dropped.active)  # OpenRouter's outage changes nothing

    def test_outage_or_empty_list_changes_nothing(self):
        self._sync(side_effect=requests.ConnectionError("down"))
        self._sync(return_value=_answer())
        self.assertTrue(self.dropped.active)
        self.assertEqual(self.env["pan_ai.model"].search([]), self.kept | self.dropped)
