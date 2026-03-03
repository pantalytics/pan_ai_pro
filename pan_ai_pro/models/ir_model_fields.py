# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class IrModelFields(models.Model):
    _inherit = 'ir.model.fields'

    x_ai_agent_id = fields.Many2one(
        'ai.agent',
        string="AI Agent",
        help="AI agent used to compute this field. Overrides the global default.",
    )
    x_ai_auto_fill = fields.Boolean(
        string="Auto Fill",
        default=False,
        help="Automatically generate values for all records in the background.",
    )
    x_ai_auto_update = fields.Boolean(
        string="Auto Update",
        default=False,
        help="Regenerate when input fields, prompt, or AI agent changes.",
    )

    @api.model
    def get_ai_stale_fields(self, model_name, record_id):
        """Return stale AI field info for a given record.

        Returns dict: {
            'stale': [field_names...],           # all stale fields
            'auto_regenerate': [field_names...],  # subset with auto_update=True
        }
        """
        Metadata = self.env['x_ai.field.metadata'].sudo()
        stale = Metadata.search([
            ('model_name', '=', model_name),
            ('res_id', '=', record_id),
            ('is_stale', '=', True),
        ])
        stale_names = stale.mapped('field_name')
        auto_regenerate = []
        if stale_names:
            auto_fields = self.sudo().search([
                ('model', '=', model_name),
                ('name', 'in', stale_names),
                ('x_ai_auto_update', '=', True),
            ])
            auto_regenerate = auto_fields.mapped('name')
        if stale_names:
            _logger.info("[AI Pro] get_ai_stale_fields(%s, %s) → stale=%s, auto=%s",
                         model_name, record_id, stale_names, auto_regenerate)
        return {'stale': stale_names, 'auto_regenerate': auto_regenerate}

    @api.model
    def has_ai_field_data(self, model_name, field_name):
        """Check if any records have non-null data in the given AI field."""
        try:
            Model = self.env[model_name]
        except KeyError:
            return False
        return Model.search_count([(field_name, '!=', False)], limit=1) > 0

    @api.model
    def action_regenerate_ai_field(self, model_name, field_name, record_ids=None):
        """Clear AI-generated values for a field and trigger regeneration.

        Args:
            model_name: Technical name of the model (e.g. 'res.partner')
            field_name: Technical name of the AI field
            record_ids: Optional list of record IDs. If None, regenerates all records.
        """
        ir_field = self.sudo().search([
            ('model', '=', model_name),
            ('name', '=', field_name),
            ('ai', '=', True),
        ], limit=1)
        if not ir_field:
            return False

        Model = self.env[model_name]

        # Respect human-edit protection: skip human-edited records
        Metadata = self.env['x_ai.field.metadata'].sudo()
        human_metas = Metadata.search([
            ('model_name', '=', model_name),
            ('field_name', '=', field_name),
            ('human_edited', '=', True),
        ])
        human_edited_ids = set(human_metas.mapped('res_id'))

        if record_ids:
            # Filter out human-edited records
            target_ids = [rid for rid in record_ids if rid not in human_edited_ids]
            if not target_ids:
                return True
            records = Model.browse(target_ids)
            records.with_context(_ai_auto_regenerating=True).write({field_name: False})
        else:
            # Clear all non-human-edited records via SQL for efficiency
            if human_edited_ids:
                self.env.cr.execute(SQL(
                    "UPDATE %(table)s SET %(field)s = NULL "
                    "WHERE %(field)s IS NOT NULL AND id NOT IN %(skip_ids)s",
                    table=SQL.identifier(Model._table),
                    field=SQL.identifier(field_name),
                    skip_ids=tuple(human_edited_ids) or (0,),
                ))
            else:
                self.env.cr.execute(SQL(
                    "UPDATE %(table)s SET %(field)s = NULL WHERE %(field)s IS NOT NULL",
                    table=SQL.identifier(Model._table),
                    field=SQL.identifier(field_name),
                ))
            Model.invalidate_model([field_name])

        _logger.info("[AI Pro] Regenerating %s.%s for %s records",
                     model_name, field_name,
                     len(record_ids) if record_ids else 'all')

        # Clear stale flags for affected records
        stale_metas = Metadata.search([
            ('model_name', '=', model_name),
            ('field_name', '=', field_name),
            ('is_stale', '=', True),
        ])
        if stale_metas:
            stale_metas.write({'is_stale': False})

        cron = self.env.ref('ai_fields.ir_cron_fill_ai_fields', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

        return True
