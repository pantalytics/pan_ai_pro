# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The way back from the Pantalytics approval page: collect the key, land on
the settings page. An ordinary link to this Odoo, not an OAuth redirect."""

from odoo import http
from odoo.http import request

SETTINGS_URL = "/odoo/settings#pan_ai_pro"


class AiProController(http.Controller):
    @http.route("/ai_pro/pantalytics/return", type="http", auth="user")
    def pantalytics_return(self, **kwargs):
        if request.env.user.has_group("base.group_system"):
            link = request.env["pan_ai.license"].current()
            if link:
                link.collect_on_return()
        return request.redirect(SETTINGS_URL)
