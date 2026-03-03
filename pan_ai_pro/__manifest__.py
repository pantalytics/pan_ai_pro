# -*- coding: utf-8 -*-
{
    'name': "Pan AI Pro",
    'summary': "Use Claude (Anthropic) as AI provider",
    'description': """Use Claude (Anthropic) as your Odoo AI provider — with web search.""",
    'author': "Pantalytics",
    'website': "https://github.com/pantalytics/pan_ai_pro",
    'support': "rutger@pantalytics.com",
    'category': 'Productivity',
    'version': '19.0.1.4.0',
    'license': 'LGPL-3',

    'depends': [
        'ai_app',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/ai_agent_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'pan_ai_pro/static/src/**/*.xml',
            'pan_ai_pro/static/src/ai_field_async_patch.js',
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
