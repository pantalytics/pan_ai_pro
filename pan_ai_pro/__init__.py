# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
from . import controllers, models


def uninstall_hook(env):
    """Uninstall takes the module's settings along, the OpenRouter key among
    them: a config parameter has no xml id, so Odoo would leave it. 1.x's
    `x_ai.*` rows go too."""
    # From here the uninstall drops our columns, while this registry still
    # runs our write hook on every model: it must stop asking for them.
    env.registry._pan_ai_uninstalling = True
    env["ir.config_parameter"].sudo().search(
        ["|", ("key", "=like", "pan\\_ai.%"), ("key", "=like", "x\\_ai.%")]
    ).unlink()
