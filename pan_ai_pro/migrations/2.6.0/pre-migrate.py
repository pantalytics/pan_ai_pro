# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""2.5.0 mirrored OpenRouter's whole catalogue into the model list: 468 rows,
batch variants and image models among them, and every one pinned to a
version. 2.6.0 keeps a shortlist of OpenRouter's `~vendor/family-latest`
aliases plus its Auto Router (data/model.xml).

Runs before the data load, so the seeded xml ids land on rows that are
already there: the three 2.x seeds are pointed at their family's alias, a
catalogue row that already carries an alias gets the xml id, and the rest of
the catalogue goes, except a row an agent uses or a person made, which stays
as a pinned model. Agents never lose their row.
"""

# xml id: (OpenRouter id, name, the 2.x seed name it replaces or None).
SHORTLIST = {
    "model_claude_sonnet": (
        "~anthropic/claude-sonnet-latest",
        "Claude Sonnet",
        "Claude Sonnet 5.5",
    ),
    "model_claude_haiku": ("~anthropic/claude-haiku-latest", "Claude Haiku", None),
    "model_claude_opus": ("~anthropic/claude-opus-latest", "Claude Opus", None),
    "model_gemini_flash": ("~google/gemini-flash-latest", "Gemini Flash", "Gemini 3.8 Flash"),
    "model_gemini_pro": ("~google/gemini-pro-latest", "Gemini Pro", None),
    "model_gpt": ("~openai/gpt-terra-latest", "GPT", "GPT 5.6"),
    "model_auto": ("openrouter/auto", "Auto (OpenRouter picks per question)", None),
}
# What 2.5.0's catalogue sync wrote on every row it made, as OdooBot.
CATALOGUE_SEQUENCE = 100
ROOT_UID = 1


def _one(cr, query, params):
    cr.execute(query, params)
    row = cr.fetchone()
    return row[0] if row else None


def migrate(cr, version):
    for position, (xml_id, (alias, name, old_name)) in enumerate(SHORTLIST.items(), start=1):
        seed_id = _one(
            cr,
            "SELECT res_id FROM ir_model_data WHERE module = 'pan_ai_pro' AND name = %s",
            (xml_id,),
        )
        alias_id = _one(cr, "SELECT id FROM pan_ai_model WHERE model_name = %s", (alias,))
        if seed_id and alias_id and seed_id != alias_id:
            # The catalogue made the alias row yesterday; the seed is older
            # and may be renamed. Keep the seed, fold the other into it.
            cr.execute(
                "UPDATE pan_ai_agent SET model_id = %s WHERE model_id = %s", (seed_id, alias_id)
            )
            cr.execute("DELETE FROM pan_ai_model WHERE id = %s", (alias_id,))
            alias_id = None
        if seed_id:
            cr.execute(
                "UPDATE pan_ai_model SET model_name = %s, sequence = %s WHERE id = %s",
                (alias, position, seed_id),
            )
            if old_name:
                cr.execute(
                    "UPDATE pan_ai_model SET name = %s WHERE id = %s AND name = %s",
                    (name, seed_id, old_name),
                )
        elif alias_id:
            cr.execute(
                "INSERT INTO ir_model_data (module, name, model, res_id, noupdate,"
                " create_date, write_date) VALUES ('pan_ai_pro', %s, 'pan_ai.model', %s,"
                " true, now(), now())",
                (xml_id, alias_id),
            )
            cr.execute(
                "UPDATE pan_ai_model SET sequence = %s, active = true WHERE id = %s",
                (position, alias_id),
            )
            cr.execute(
                "UPDATE pan_ai_model SET name = %s WHERE id = %s AND create_uid = %s",
                (name, alias_id, ROOT_UID),
            )
        # Neither: the data load creates the row.

    cr.execute(
        "DELETE FROM pan_ai_model WHERE create_uid = %s AND sequence = %s"
        " AND model_name != ALL(%s)"
        " AND id NOT IN (SELECT model_id FROM pan_ai_agent WHERE model_id IS NOT NULL)",
        (ROOT_UID, CATALOGUE_SEQUENCE, [alias for alias, _, _ in SHORTLIST.values()]),
    )
