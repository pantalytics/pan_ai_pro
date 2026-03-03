# -*- coding: utf-8 -*-
from odoo import fields, models


class AiFieldMetadata(models.Model):
    _name = 'x_ai.field.metadata'
    _description = 'AI Field Metadata'
    _rec_name = 'field_name'

    model_name = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    field_name = fields.Char(required=True, index=True)
    is_stale = fields.Boolean(default=False)
    human_edited = fields.Boolean(default=False)

    _unique_record_field = models.Constraint(
        'UNIQUE(model_name, res_id, field_name)',
        'Metadata must be unique per record and field',
    )
