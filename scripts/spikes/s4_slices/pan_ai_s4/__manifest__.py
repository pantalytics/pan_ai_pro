# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
{
    "name": "AI Pro spike S4: runs in slices on Odoo's workers",
    "version": "20.0.0.1.0",
    "license": "Other proprietary",
    "author": "Pantalytics",
    "depends": ["pan_ai_s2"],
    "data": ["security/ir.access.csv", "data/ir_cron.xml"],
    "installable": True,
}
