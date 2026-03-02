# -*- coding: utf-8 -*-
{
    'name': "Pan AI Pro",
    'summary': "Adds Claude (Anthropic) as AI provider to Odoo",
    'description': """
Pan AI Pro - Claude for Odoo
============================

Extends the standard Odoo 19 AI module with Anthropic Claude support.

All existing AI features (agents, topics, RAG, tool calling) work
with Claude models out of the box.

Supported Models
----------------
* Claude Opus 4.6
* Claude Sonnet 4.6
* Claude Haiku 4.5
    """,
    'author': "Pan",
    'website': "https://www.yourwebsite.com",
    'support': "support@yourwebsite.com",
    'category': 'Hidden',
    'version': '19.0.1.0.0',
    'license': 'OPL-1',

    'depends': [
        'ai_app',
    ],
    'data': [
        'views/res_config_settings_views.xml',
        'views/ai_agent_views.xml',
    ],

    'images': [
        'static/description/icon.png',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}
