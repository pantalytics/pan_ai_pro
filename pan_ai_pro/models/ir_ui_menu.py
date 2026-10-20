# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Until this Odoo is connected to Pantalytics, AI Pro is one screen: Settings.

Agents, threads, runs, toolsets, tools and AI fields configure a product that
will not run, so they are left out of the menu. A Settings administrator
still sees the app, and it opens on Settings > AI Pro, where the checklist
is. Everybody else does not see the app at all.

`load_menus` is cached per user; `pan_ai.license.write` drops the cache when
the answer can change.
"""

from odoo import models

# What stays on a database that is not connected: the way to Settings.
KEEP = ("menu_root", "menu_configuration", "menu_settings")


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _load_menus_blacklist(self):
        res = super()._load_menus_blacklist()
        link = self.env["pan_ai.license"].current()
        if link and link.is_entitled():
            return res
        root = self.env.ref("pan_ai_pro.menu_root", raise_if_not_found=False)
        if not root:
            return res
        ours = self.sudo().search([("id", "child_of", root.id)])
        if self.env.user.has_group("base.group_system"):
            keep = {self.env.ref(f"pan_ai_pro.{xmlid}").id for xmlid in KEEP}
            ours = ours.filtered(lambda menu: menu.id not in keep)
        return res + ours.ids
