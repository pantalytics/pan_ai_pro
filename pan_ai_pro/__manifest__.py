# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
{
    "name": "AI Pro",
    "summary": "AI agents that work in your Odoo, under your control",
    "description": """
AI Pro for Odoo
===============

AI agents in Odoo, with you in control.

- Your key: bring your own OpenRouter key and pick any model per agent.
- Your tools: Odoo's records, your own server actions and any MCP server.
- Your rules: each agent runs with an Odoo user's rights, asks before it
  creates or changes a record, and logs what every run did and cost.

Community and Enterprise, Odoo 19 and 20.

Chat
----
Ask from Odoo's own chat window, the sparkle top right or Ctrl+K "Ask AI".
Answers stream in, every tool call is shown, and nothing is created or
changed until you press Allow. Stop works mid-answer. Pick the agent per
conversation.

Agents
------
Each agent has its own instructions, model, tools, limits and web search.
It runs as the person who asks, or as a dedicated Odoo user you set up, so
Odoo's groups and record rules decide what it may see and touch.

Tools
-----
Built-in tools search, read, total, create, update and open records. Any
server action added to a toolset becomes a tool, and any MCP server can be
added as a toolset. Tools that change data ask for approval by default.

Automations
-----------
The server action "Run AI agent" works in automation rules and scheduled
actions. The answer lands as a note in the record's chatter, or as an
activity. A continuous thread watches a model and acts when records change.

AI fields
---------
Put a prompt on any stored field and the agent fills it. Auto fill empty
records, auto update values whose inputs changed, and a value a person typed
stays. On Enterprise, Odoo's own AI fields run on AI Pro's agents.

Control
-------
Every run is logged with its tokens and cost. Limits per run and per user,
a retention period, and an allow list for MCP hosts.

Requires a connection to Pantalytics
(Settings > AI Pro > Connect to Pantalytics).
""",
    "author": "Pantalytics",
    "website": "https://github.com/pantalytics/pan_ai_pro",
    "support": "rutger@pantalytics.com",
    "category": "Productivity",
    "version": "2.6.0",
    "license": "Other proprietary",
    "external_dependencies": {
        "python": ["pydantic-ai-slim", "markdown2", "cryptography", "requests"]
    },
    "depends": ["mail", "bus", "base_automation"],
    "data": [
        "security/groups.xml",
        "security/access.xml",
        "data/model.xml",
        "data/tools.xml",
        "data/agent.xml",
        "data/ir_cron.xml",
        "views/model_views.xml",
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
            "pan_ai_pro/static/src/settings/**/*",
        ],
    },
    "images": [
        "static/description/banner.png",
        "static/description/chat_screenshot.png",
        "static/description/agent_screenshot.png",
        "static/description/ai_field_screenshot.png",
    ],
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
