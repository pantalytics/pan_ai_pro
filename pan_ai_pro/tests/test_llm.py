# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The default model is picked from OpenRouter's list, and saved as the id
string the runtime reads."""

from unittest.mock import MagicMock, patch

import requests

from ..compat import params
from .common import AiProCase

GET = "odoo.addons.pan_ai_pro.models.llm.requests.get"


def answer(data):
    response = MagicMock()
    response.json.return_value = {"data": data}
    return response


class TestLlm(AiProCase):
    def test_refresh_adds_and_renames(self):
        llm = self.env["pan_ai.llm"]
        llm._for_code("openai/gpt-6")
        with patch(
            GET,
            return_value=answer(
                [
                    {"id": "openai/gpt-6", "name": "OpenAI: GPT-6"},
                    {"id": "x/new", "name": "X: New"},
                    {"name": "no id"},
                ]
            ),
        ):
            self.assertEqual(llm._refresh(), 3)
        self.assertEqual(llm.search([("code", "=", "openai/gpt-6")]).name, "OpenAI: GPT-6")
        self.assertEqual(llm.search_count([("code", "=", "x/new")]), 1)
        self.assertEqual(llm.name_search("New")[0][1], "X: New")

    def test_refresh_failure_keeps_the_list(self):
        llm = self.env["pan_ai.llm"]
        llm._for_code("x/kept")
        with patch(GET, side_effect=requests.ConnectionError("down")):
            self.assertEqual(llm._refresh(), 0)
        self.assertEqual(llm.search_count([("code", "=", "x/kept")]), 1)

    def test_default_model_round_trip(self):
        params(self.env).set_str("pan_ai.default_model", "x/old")
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.pan_ai_default_model_id.code, "x/old")
        settings.pan_ai_default_model_id = self.env["pan_ai.llm"]._for_code("x/picked")
        settings.execute()
        self.assertEqual(params(self.env).get_str("pan_ai.default_model"), "x/picked")
        self.assertEqual(params(self.env).get_str("pan_ai.openrouter_key"), "sk-or-test")

    def test_dialog_fills_an_empty_list(self):
        self.env["pan_ai.llm"].search([]).unlink()
        with patch(GET, return_value=answer([{"id": "a/b", "name": "A: B"}, {"id": "c/d"}])):
            action = self.env["res.config.settings"].create({}).action_pan_ai_openrouter()
        self.assertEqual(action["target"], "new")
        self.assertGreaterEqual(self.env["pan_ai.llm"].search_count([]), 2)
