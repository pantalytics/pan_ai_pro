# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""2.9.0's shortlist is four providers, each with its families (data/model.xml):
Claude Sonnet, Haiku, Opus and Fable; Gemini Flash and Pro; GPT Luna, Sol and
Astra; Mistral Small, Medium and Large. GPT Terra and the Auto Router leave
the shortlist.

Runs before the data load. The two rows that leave the shortlist give up
their xml ids, so the load does not delete them (an agent may use them; they
stay as pinned models). A row somebody typed in by hand under one of the new
ids takes that xml id, so the load adopts it instead of tripping over the
unique OpenRouter id. The flags are set in post-migrate, once the columns
are there.
"""

# xml id: OpenRouter id, as data/model.xml seeds it.
SHORTLIST = {
    "model_claude_sonnet": "~anthropic/claude-sonnet-latest",
    "model_claude_haiku": "~anthropic/claude-haiku-latest",
    "model_claude_opus": "~anthropic/claude-opus-latest",
    "model_claude_fable": "~anthropic/claude-fable-latest",
    "model_gemini_flash": "~google/gemini-flash-latest",
    "model_gemini_pro": "~google/gemini-pro-latest",
    "model_gpt_luna": "~openai/gpt-luna-latest",
    "model_gpt_sol": "~openai/gpt-sol-latest",
    "model_gpt_astra": "~openai/gpt-astra-latest",
    "model_mistral_small": "mistralai/mistral-small-2603",
    "model_mistral_medium": "mistralai/mistral-medium-3-5",
    "model_mistral_large": "mistralai/mistral-large-4-0",
}
LEAVING = ("model_gpt", "model_auto")


def migrate(cr, version):
    cr.execute("DELETE FROM ir_model_data WHERE module = 'pan_ai_pro' AND name IN %s", (LEAVING,))
    for xml_id, model_name in SHORTLIST.items():
        cr.execute(
            "SELECT 1 FROM ir_model_data WHERE module = 'pan_ai_pro' AND name = %s", (xml_id,)
        )
        if cr.fetchone():
            continue
        cr.execute("SELECT id FROM pan_ai_model WHERE model_name = %s", (model_name,))
        row = cr.fetchone()
        if not row:
            continue
        cr.execute(
            """INSERT INTO ir_model_data (module, name, model, res_id, noupdate,
                                         create_date, write_date)
               VALUES ('pan_ai_pro', %s, 'pan_ai.model', %s, true, now(), now())""",
            (xml_id, row[0]),
        )
