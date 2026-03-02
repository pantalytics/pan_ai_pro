# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    x_anthropic_key_enabled = fields.Boolean(
        string="Enable custom Anthropic API key",
        compute='_compute_x_anthropic_key_enabled',
        readonly=False,
        groups='base.group_system',
    )
    x_anthropic_key = fields.Char(
        string="Anthropic API key",
        config_parameter='x_ai.anthropic_key',
        readonly=False,
        groups='base.group_system',
    )
    x_ai_fields_agent_id = fields.Many2one(
        'ai.agent',
        string="AI Fields Agent",
        config_parameter='x_ai.ai_fields_agent_id',
        groups='base.group_system',
        help="AI agent used to compute AI field values. "
             "The agent's model, temperature, and web search settings are used.",
    )

    def _compute_x_anthropic_key_enabled(self):
        for record in self:
            record.x_anthropic_key_enabled = bool(record.x_anthropic_key)
