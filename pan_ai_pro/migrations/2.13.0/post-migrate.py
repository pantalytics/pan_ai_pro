# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Every agent a person made gets that person as its sponsor: the one who
allows the changes of runs with nobody behind them. The agent the module
ships has no maker, so it gets none until an administrator picks one."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    agents = (
        env["pan_ai.agent"].with_context(active_test=False).search([("sponsor_id", "=", False)])
    )
    for agent in agents:
        maker = agent.create_uid
        if maker and maker.id != SUPERUSER_ID and not maker.share and maker.active:
            agent.sponsor_id = maker
