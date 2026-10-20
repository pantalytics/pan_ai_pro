# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
from odoo import models


class ResGroups(models.Model):
    _inherit = "res.groups"

    def _get_light_group_xmlids(self):
        # Odoo 20: every internal user may chat, so chatting must not turn a
        # Light user into a regular one. Odoo 19 has no tiers and never calls this.
        return (*super()._get_light_group_xmlids(), "pan_ai_pro.group_user")
