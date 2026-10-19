{
    "name": "AI Pro spike S2: streaming through the bus into a mail message",
    "version": "20.0.0.1.0",
    "license": "LGPL-3",
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
