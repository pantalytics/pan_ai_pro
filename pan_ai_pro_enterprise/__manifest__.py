{
    "name": "AI Pro for Enterprise",
    "summary": "Enterprise 20's AI fields computed by AI Pro's agents; Odoo's AI button replaced by AI Pro's",
    "author": "Pantalytics",
    "website": "https://github.com/pantalytics/pan_ai_pro",
    "category": "Productivity",
    "version": "20.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["pan_ai_pro", "ai_fields"],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "pan_ai_pro_enterprise/static/src/hide_native_ai.js",
        ],
    },
    "installable": True,
    "auto_install": True,
}
