# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
{
    "name": "AI Pro spike S2: streaming through the bus into a mail message",
    "version": "20.0.0.1.0",
    "license": "Other proprietary",
    "depends": ["mail", "bus"],
    "data": ["data/partner.xml"],
    "assets": {
        "web.assets_backend": [
            "pan_ai_s2/static/src/run_events.js",
            "pan_ai_s2/static/src/message_patch.js",
            "pan_ai_s2/static/src/message_patch.xml",
        ],
        "web.assets_tests": ["pan_ai_s2/static/tests/tours/s2_tour.js"],
    },
    "installable": True,
}
