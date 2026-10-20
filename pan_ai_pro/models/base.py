"""Every model: a person's edit of an AI field is remembered, and a change to
an input of an AI field marks the value stale. Also the method a button or
Enterprise's own AI-field button lands on."""

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

# What one RPC may fill at once: a form button or a list selection, not a
# whole table.
FILL_MAX = 50


class Base(models.AbstractModel):
    _inherit = "base"

    def write(self, vals):
        result = super().write(vals)
        if (
            vals
            and self.ids
            and not self.env.context.get("pan_ai_filling")
            and self._name != "ir.model.fields"
        ):
            self._pan_ai_track(set(vals))
        return result

    def _pan_ai_track(self, written):
        ai_fields = self.env["ir.model.fields"].pan_ai_fields_of(self._name)
        if not ai_fields:
            return
        Metadata = self.env["pan_ai.field.metadata"]
        for ir_field in ai_fields:
            if ir_field.name in written:
                Metadata._set(
                    self._name, self.ids, ir_field.name, human_edited=True, is_stale=False
                )
            elif ir_field.pan_ai_inputs() & written:
                Metadata._set(self._name, self.ids, ir_field.name, is_stale=True)

    def pan_ai_fill(self, fname):
        """Compute this AI field for these records now, as the caller: an
        internal user who may write these records and use the field's agent
        (runtime/field.py checks the agent)."""
        from ..runtime import field as field_runtime

        if self.env.user.share:
            raise AccessError(_("Only internal users can fill an AI field."))
        if len(self) > FILL_MAX:
            raise UserError(_("Fill at most %s records at once.", FILL_MAX))
        self.check_access("write")
        ir_field = (
            self.env["ir.model.fields"]
            .pan_ai_fields_of(self._name)
            .filtered(lambda f: f.name == fname)
        )
        if not ir_field:
            return False
        return field_runtime.fill(self, ir_field, self.env.user, by_hand=True)

    @api.model
    def pan_ai_stale_fields(self, res_id):
        """For a form: which AI fields of this record are stale, and which recompute by themselves."""
        self.browse(res_id).check_access("read")
        rows = (
            self.env["pan_ai.field.metadata"]
            .sudo()
            .search(
                [("model_name", "=", self._name), ("res_id", "=", res_id), ("is_stale", "=", True)]
            )
        )
        names = rows.mapped("field_name")
        auto = (
            self.env["ir.model.fields"]
            .pan_ai_fields_of(self._name)
            .filtered(lambda f: f.name in names and f.pan_ai_auto_update)
        )
        return {"stale": names, "auto": auto.mapped("name")}
