# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""After the load: the shortlist is recommended and in the seed's order
(a noupdate seed leaves an existing row's sequence alone), the two rows that
left it are not recommended and sort after it, and the old "GPT" row says
which family it is."""

from odoo import SUPERUSER_ID, api

# The seed's order (data/model.xml; pre-migrate.py carries the ids).
SHORTLIST = (
    "model_claude_sonnet",
    "model_claude_haiku",
    "model_claude_opus",
    "model_claude_fable",
    "model_gemini_flash",
    "model_gemini_pro",
    "model_gpt_luna",
    "model_gpt_sol",
    "model_gpt_astra",
    "model_mistral_small",
    "model_mistral_medium",
    "model_mistral_large",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Model = env["pan_ai.model"].with_context(active_test=False)
    for sequence, xml_id in enumerate(SHORTLIST, 1):
        row = env.ref(f"pan_ai_pro.{xml_id}", raise_if_not_found=False)
        if row:
            row.write({"recommended": True, "sequence": sequence})
    Model.search([("model_name", "in", ["~openai/gpt-terra-latest", "openrouter/auto"])]).write(
        {"recommended": False, "sequence": 90}
    )
    Model.search([("model_name", "=", "~openai/gpt-terra-latest"), ("name", "=", "GPT")]).write(
        {"name": "GPT Terra"}
    )
