# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""2.8.0 marks the shortlist (data/model.xml) as recommended: the agent's
model picker opens on that filter. The seed is noupdate, so a database that
already has the rows gets the flag here."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rows = env["ir.model.data"].search(
        [("module", "=", "pan_ai_pro"), ("model", "=", "pan_ai.model")]
    )
    env["pan_ai.model"].browse(rows.mapped("res_id")).exists().write({"recommended": True})
