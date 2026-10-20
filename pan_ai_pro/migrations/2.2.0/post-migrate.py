# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""2.2.0: the model moves from a free text on the agent, with a fallback to
Settings' default model, to a required choice from `pan_ai.model`.

Every id an agent named, and the default it fell back on, becomes a row;
each agent points at its own. Runs after the load and before Odoo drops the
old `model` column, so the column is still there to read. The Settings
parameter goes: nothing reads it any more.
"""

from odoo import SUPERUSER_ID, api
from odoo.tools.sql import column_exists

# What 2.1.0 fell back on when neither the agent nor Settings said.
OLD_DEFAULT = "anthropic/claude-sonnet-5.5"


def migrate(cr, version):
    if not column_exists(cr, "pan_ai_agent", "model"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = 'pan_ai.default_model'")
    row = cr.fetchone()
    default = ((row and row[0]) or OLD_DEFAULT).strip()
    Model = env["pan_ai.model"].with_context(active_test=False)
    by_name = {m.model_name: m for m in Model.search([])}

    cr.execute("SELECT id, model FROM pan_ai_agent")
    for agent_id, name in cr.fetchall():
        name = (name or "").strip() or default
        if name not in by_name:
            by_name[name] = Model.create({"name": name, "model_name": name})
        cr.execute(
            "UPDATE pan_ai_agent SET model_id = %s WHERE id = %s", (by_name[name].id, agent_id)
        )
    # The column was added before the model rows existed, so the ORM could
    # not make it NOT NULL; every agent has one now.
    cr.execute("ALTER TABLE pan_ai_agent ALTER COLUMN model_id SET NOT NULL")
    cr.execute("DELETE FROM ir_config_parameter WHERE key = 'pan_ai.default_model'")
    env.invalidate_all()
