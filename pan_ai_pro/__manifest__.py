{
    "name": "AI Pro",
    "summary": "AI agents and AI fields inside Odoo: chat, scheduled and continuous runs, any model through OpenRouter",
    "description": """
AI Pro for Odoo
==================

Pydantic AI agents that run inside your Odoo, on your own OpenRouter key,
with any model. An agent chats in Odoo's own chat window, runs on a
schedule, answers an automation rule, or watches records continuously.
Every tool runs through the ORM as the person who asked, or as a dedicated
user you set up, so Odoo's access rights are the agent's rights.

Works on Community and Enterprise. Requires a connection to Pantalytics
(Settings > AI Pro > Connect to Pantalytics).
""",
    "author": "Pantalytics",
    "website": "https://github.com/pantalytics/pan_ai_pro",
    "support": "rutger@pantalytics.com",
    "category": "Productivity",
    "version": "1.1.0",
    "license": "LGPL-3",
    "external_dependencies": {"python": ["pydantic_ai", "markdown2", "cryptography", "requests"]},
    "depends": ["mail", "bus", "base_automation"],
    "data": [
        "security/groups.xml",
        "security/access.xml",
        "data/tools.xml",
        "data/agent.xml",
        "data/ir_cron.xml",
        "views/agent_views.xml",
        "views/toolset_views.xml",
        "views/tool_views.xml",
        "views/thread_views.xml",
        "views/run_views.xml",
        "views/ir_actions_server_views.xml",
        "views/res_config_settings_views.xml",
        "views/ir_model_fields_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pan_ai_pro/static/src/chat/**/*",
        ],
        "web.assets_tests": [
            "pan_ai_pro/static/tests/tours/**/*",
        ],
    },
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
