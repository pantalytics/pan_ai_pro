# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Small shared helpers."""

from odoo.tools import config


def commit(env):
    """Commit so the browser (and the other worker) sees it now. In a test
    process the cursor may not commit: flush instead, which is what the test
    sees anyway."""
    if config["test_enable"]:
        env.cr.flush()
    else:
        env.cr.commit()
