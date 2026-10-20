# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Install pan_ai_pro_enterprise on an Enterprise database upgraded from 1.x.

auto_install only fires when a dependency gets installed. A database that
already had ai_fields and upgrades pan_ai_pro from 1.x therefore never gets
pan_ai_pro_enterprise (prod 2026-10-20). Marking it 'to install' during the
upgrade is enough: Odoo loads modules marked during the same run.
"""

from odoo import api, models


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    @api.model
    def _pan_ai_install_enterprise(self):
        # Called from security/groups.xml on every install and upgrade. On
        # Community the module is not there, or ai_fields is not installed.
        if not self.search_count([("name", "=", "ai_fields"), ("state", "=", "installed")]):
            return
        self.search(
            [("name", "=", "pan_ai_pro_enterprise"), ("state", "=", "uninstalled")]
        ).button_install()
