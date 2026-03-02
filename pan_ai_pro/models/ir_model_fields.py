# -*- coding: utf-8 -*-
from odoo import api, fields, models


class IrModelFields(models.Model):
    _inherit = 'ir.model.fields'

    x_ai_agent_id = fields.Many2one(
        'ai.agent',
        string="AI Agent",
        help="AI agent used to compute this field. Overrides the global default.",
    )
