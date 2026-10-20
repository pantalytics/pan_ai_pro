# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Enterprise's own AI fields, computed by AI Pro's agent (19 and 20). Two
ways in, both on `base`, both overridden here:

- the AI button on a field in a form calls `get_ai_field_value`
  (`ai_fields/static/src/model/relational_model/record.js`), which asks
  Odoo's LLM and returns the value for the form to show;
- Odoo's nightly cron calls `_fill_ai_field`, which writes the value.

Both run AI Pro's agent instead, with the field's Odoo prompt
(`system_prompt` on `ir.model.fields`) as the AI Pro prompt when the field
has none of its own. Odoo's widget, Studio panel and columns stay.

AI properties stay Odoo's: a property has no `ir.model.fields` row to carry
an AI Pro prompt, agent or state, so AI Pro has nothing to run it with.
"""

import logging

from odoo import _, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class Base(models.AbstractModel):
    _inherit = "base"

    def _pan_ai_field(self, field, field_prompt=None):
        """The `ir.model.fields` row AI Pro computes `field` with, its Odoo
        prompt made the AI Pro prompt if need be; empty when AI Pro cannot
        (no prompt, or a type AI Pro does not fill): Odoo's own path then."""
        from odoo.addons.pan_ai_pro.models.ir_model_fields import FILLABLE

        ir_field = (
            self.env["ir.model.fields"]
            .sudo()
            .search([("model", "=", self._name), ("name", "=", field.name)], limit=1)
        )
        if not ir_field or ir_field.ttype not in FILLABLE or not ir_field.store:
            return ir_field.browse()
        if not ir_field.pan_ai_prompt:
            prompt = html2plaintext(field_prompt or ir_field.system_prompt or "")
            if not prompt:
                return ir_field.browse()
            # Odoo's prompt becomes the AI Pro prompt, for everyone: a
            # configuration write, as the person who clicked, so only an
            # administrator can make a field an AI Pro field.
            try:
                ir_field.with_user(self.env.user).write({"pan_ai_prompt": prompt})
            except AccessError as error:
                raise UserError(
                    _("Ask an administrator to set the AI Pro prompt on this field first.")
                ) from error
        return ir_field

    def _fill_ai_field(self, field, field_prompt=None):
        from odoo.addons.pan_ai_pro.runtime import field as field_runtime

        ir_field = self._pan_ai_field(field, field_prompt)
        if not ir_field:
            return super()._fill_ai_field(field, field_prompt=field_prompt)
        # A click is the person's (their hourly cap applies); Odoo's own
        # nightly cron reaches this too, with no request behind it.
        field_runtime.fill(self, ir_field, self.env.user, by_hand=bool(request))
        return True

    def get_ai_field_value(self, fname, changes):
        """The AI button: AI Pro writes the value on the saved record and
        returns it as `web_read` does, for the form to show. The form's
        unsaved `changes` are not read: AI Pro reads the record as saved."""
        from odoo.addons.pan_ai_pro.runtime import field as field_runtime
        from odoo.addons.pan_ai_pro.tools import commit

        field = self._fields.get(fname)
        ir_field = field and self._pan_ai_field(field)
        if not ir_field:
            return super().get_ai_field_value(fname, changes)
        if not self:
            raise UserError(_("Save the record first, then ask AI for this field."))
        self.ensure_one()
        self.check_access("read")
        self.check_access("write")
        if not field_runtime.fill(self, ir_field, self.env.user, by_hand=True):
            state = (
                self.env["pan_ai.field.metadata"]
                .sudo()
                .search(
                    [
                        ("model_name", "=", self._name),
                        ("res_id", "=", self.id),
                        ("field_name", "=", fname),
                    ],
                    limit=1,
                )
            )
            # The failed run and its state row outlive the error's rollback.
            commit(self.env)
            raise UserError(state.last_error or _("AI Pro could not fill this field."))
        spec = {"fields": {"display_name": {}}} if field.type == "many2one" else {}
        return self.web_read({fname: spec})[0][fname]

    def write(self, vals):
        # The AI button's value goes back to the form, which saves it again:
        # the value AI Pro just wrote, unchanged, is no person's edit.
        if vals and self.ids and self._name != "ir.model.fields":
            names = self.env["ir.model.fields"].pan_ai_fields_of(self._name).mapped("name")
            same = {name for name in names if name in vals and self._pan_ai_same(name, vals[name])}
            if same:
                vals = {key: value for key, value in vals.items() if key not in same}
        return super().write(vals)

    def _pan_ai_same(self, fname, value):
        field = self._fields[fname]
        try:
            return all(
                record[fname]
                == field.convert_to_record(field.convert_to_cache(value, record), record)
                for record in self
            )
        except (ValueError, TypeError):
            return False
