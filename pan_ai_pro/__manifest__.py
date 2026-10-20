{
    "name": "AI Pro",
    "summary": "Chat with AI agents in Odoo, let them run on schedules and rules, and fill fields with AI. Any model, your own OpenRouter key",
    "description": """
AI Pro for Odoo
===============

AI agents that live inside your Odoo and work with your real data.

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
server action marked "Use in AI" becomes a tool, and any MCP server can be
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

Odoo 19 and 20, Community and Enterprise. Bring your own OpenRouter key and
use any model. Requires a connection to Pantalytics
(Settings > AI Pro > Connect to Pantalytics).
""",
    "author": "Pantalytics",
    "website": "https://github.com/pantalytics/pan_ai_pro",
    "support": "rutger@pantalytics.com",
    "category": "Productivity",
    "version": "2.0.0",
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
    },
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
