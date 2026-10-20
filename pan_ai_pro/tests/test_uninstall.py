# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Uninstall takes AI Pro's settings with it, the OpenRouter key first, and
stops the write hook asking for the columns the uninstall drops."""

from odoo.tests import TransactionCase

from ..compat import params


class TestUninstall(TransactionCase):
    def test_the_hook_drops_our_params_and_stops_the_write_hook(self):
        import odoo.addons.pan_ai_pro as module

        p = params(self.env)
        p.set_str("pan_ai.openrouter_key", "sk-or-test")
        p.set_int("pan_ai.retention_days", 30)
        p.set_str("x_ai.anthropic_key", "sk-ant-test")
        p.set_str("panXai.lookalike", "kept")
        self.addCleanup(vars(self.registry).pop, "_pan_ai_uninstalling", None)

        module.uninstall_hook(self.env)

        ICP = self.env["ir.config_parameter"].sudo()
        self.assertFalse(
            ICP.search(["|", ("key", "=like", "pan\\_ai.%"), ("key", "=like", "x\\_ai.%")])
        )
        self.assertEqual(p.get_str("panXai.lookalike"), "kept")
        # the uninstall drops pan_ai_is_ai next, with this registry still loaded
        self.assertFalse(self.env["ir.model.fields"]._pan_ai_column_ready())
