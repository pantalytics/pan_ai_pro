# -*- coding: utf-8 -*-
{
    'name': "AI Pro",
    'summary': "Use Claude (Anthropic) as AI provider",
    'description': """
Adds Anthropic Claude as an AI provider for Odoo 19.

Extends the built-in AI module with Claude Opus, Sonnet, and Haiku models.
Supports agents, tool calling, RAG, web search, structured output, and
Airtable-style AI Fields with per-field agents, auto-fill, auto-update,
and human-edit protection.
""",
    'author': "Pantalytics",
    'website': "https://github.com/pantalytics/pan_ai_pro",
    'support': "rutger@pantalytics.com",
    'category': 'Productivity',
    'version': '19.0.1.6.1',
    'license': 'LGPL-3',

    'external_dependencies': {
        'python': ['markdown2'],
    },
    'depends': [
        'ai_app',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_actions_server_data.xml',
        'views/res_config_settings_views.xml',
        'views/ai_agent_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'pan_ai_pro/static/src/**/*.xml',
            'pan_ai_pro/static/src/ai_field_async_patch.js',
            'pan_ai_pro/static/src/stream_service.js',
        ],
        'web_studio.studio_assets_minimal': [
            'pan_ai_pro/static/src/field_properties_patch.js',
        ],
    },

    'images': [
        'static/description/banner.png',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}
