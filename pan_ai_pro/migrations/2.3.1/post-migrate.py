# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""What the 1.x module (the Anthropic provider client, 1.6.1) left behind.

Odoo's own upgrade removes 1.x's fields, server actions and views, since
they have xml ids of this module. It leaves the config parameters, the
Anthropic key among them, and the table of the `x_ai.field.metadata` model,
whose class is gone (measured 1.6.1 > 2.2.1 on Enterprise 19, 2026-10-20).
2.x reads none of it. The columns go here too, in case a database lost the
field rows earlier; Odoo skips a column that is no longer there. Every
statement is a no-op on a database that never ran 1.x; nothing `pan_ai_*` is
touched.
"""

COLUMNS = {
    "ir_model_fields": ["x_ai_agent_id", "x_ai_auto_fill", "x_ai_auto_update"],
    "ai_agent": ["x_web_search", "x_code_execution"],
    "res_config_settings": ["x_ai_fields_agent_id", "x_anthropic_key"],
}


def migrate(cr, version):
    cr.execute(r"DELETE FROM ir_config_parameter WHERE key LIKE 'x\_ai.%'")
    cr.execute("DROP TABLE IF EXISTS x_ai_field_metadata CASCADE")
    for table, columns in COLUMNS.items():
        for column in columns:
            cr.execute(f'ALTER TABLE IF EXISTS "{table}" DROP COLUMN IF EXISTS "{column}" CASCADE')
