# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The model list is a shortlist; the daily sync only retires what OpenRouter dropped."""

from unittest.mock import MagicMock, patch

import requests

from odoo.tests import TransactionCase, tagged


def _answer(*ids):
    response = MagicMock()
    response.json.return_value = {"data": [{"id": i, "name": i} for i in ids]}
    return response


@tagged("post_install", "-at_install")
class TestModelsSeed(TransactionCase):
    def test_shortlist_of_latest_aliases_sonnet_first(self):
        rows = self.env["pan_ai.model"].search([])
        self.assertEqual(rows[0].model_name, "~anthropic/claude-sonnet-latest")
        self.assertEqual(self.env["pan_ai.model"].first(), rows[0])
        self.assertIn("openrouter/auto", rows.mapped("model_name"))
        self.assertTrue(all(m.endswith("-latest") for m in rows.mapped("model_name")[:-1]))
        self.assertLess(len(rows), 10)


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

    def test_outage_or_empty_list_changes_nothing(self):
        self._sync(side_effect=requests.ConnectionError("down"))
        self._sync(return_value=_answer())
        self.assertTrue(self.dropped.active)
        self.assertEqual(self.env["pan_ai.model"].search([]), self.kept | self.dropped)
