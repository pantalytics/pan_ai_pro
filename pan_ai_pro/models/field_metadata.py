"""Per record, per AI field: is the value stale (an input changed since it
was computed) and did a person edit it (then the AI leaves it alone). The
19.0 model, renamed."""

from odoo import fields, models


class FieldMetadata(models.Model):
    _name = "pan_ai.field.metadata"
    _description = "AI field state"
    _rec_name = "field_name"

    model_name = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    field_name = fields.Char(required=True, index=True)
    is_stale = fields.Boolean(default=False)
    human_edited = fields.Boolean(default=False)
    last_error = fields.Char()

    _unique_record_field = models.Constraint(
        "UNIQUE(model_name, res_id, field_name)", "One state per record and field."
    )

    def _set(self, model_name, res_ids, field_name, **values):
        """Create or update the state of these records for this field."""
        Metadata = self.sudo()
        existing = {
            m.res_id: m
            for m in Metadata.search(
                [
                    ("model_name", "=", model_name),
                    ("field_name", "=", field_name),
                    ("res_id", "in", list(res_ids)),
                ]
            )
        }
        for res_id in res_ids:
            if res_id in existing:
                existing[res_id].write(values)
            else:
                Metadata.create(
                    {"model_name": model_name, "res_id": res_id, "field_name": field_name, **values}
                )
