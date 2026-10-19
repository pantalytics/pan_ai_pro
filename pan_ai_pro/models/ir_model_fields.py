"""AI fields: a field whose value an agent writes. The prompt, the agent and
the two switches live on `ir.model.fields`, so any stored field of any model
can become one (Settings > Technical > Fields, or AI Pro > Configuration >
AI fields). Auto fill computes empty records nightly; auto update recomputes
when an input named in the prompt changes. A value a person typed is left
alone. The compute itself is runtime/field.py.
"""

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

FILLABLE = (
    "char",
    "text",
    "html",
    "integer",
    "float",
    "monetary",
    "boolean",
    "date",
    "datetime",
    "selection",
    "many2one",
)
# {{ object.partner_id.name }} names an input: its root field is watched.
INPUT_RE = re.compile(r"\{\{\s*object\.([a-zA-Z_][a-zA-Z0-9_]*)")


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    pan_ai_prompt = fields.Text(
        string="AI prompt",
        help="What the agent should put in this field. {{ object.name }} and other fields are filled in and watched.",
    )
    pan_ai_agent_id = fields.Many2one(
        "pan_ai.agent", string="AI agent", ondelete="set null", help="Empty: the first agent."
    )
    pan_ai_auto_fill = fields.Boolean(string="Auto fill", help="Fill empty records nightly.")
    pan_ai_auto_update = fields.Boolean(
        string="Auto update", help="Recompute when an input named in the prompt changes."
    )
    pan_ai_use_tools = fields.Boolean(
        string="Let the agent use its tools",
        help="Off: the prompt and the record are all the agent sees.",
    )
    pan_ai_is_ai = fields.Boolean(compute="_compute_pan_ai_is_ai", store=True, index=True)

    def _get_writable_properties(self):
        # Our columns may change on any field, base fields included: they
        # describe what the agent does, not the field itself.
        return super()._get_writable_properties() + [
            "pan_ai_prompt",
            "pan_ai_agent_id",
            "pan_ai_auto_fill",
            "pan_ai_auto_update",
            "pan_ai_use_tools",
        ]

    @api.depends("pan_ai_prompt")
    def _compute_pan_ai_is_ai(self):
        for field in self:
            field.pan_ai_is_ai = bool(field.pan_ai_prompt)

    @api.constrains("pan_ai_prompt", "ttype", "store")
    def _check_pan_ai(self):
        for field in self.filtered("pan_ai_prompt"):
            if field.ttype not in FILLABLE or not field.store:
                raise UserError(
                    _("An AI field must be a stored field of type %s.", ", ".join(FILLABLE))
                )

    def pan_ai_inputs(self):
        """The record fields the prompt names, so a change to one marks the value stale."""
        self.ensure_one()
        return set(INPUT_RE.findall(self.pan_ai_prompt or ""))

    @api.model
    def pan_ai_fields_of(self, model_name):
        return self.sudo().search([("model", "=", model_name), ("pan_ai_is_ai", "=", True)])

    def action_pan_ai_fill_all(self):
        """Fill now: every record whose value is empty, this field. Runs on the
        worker crons as the person who pressed the button."""
        self.ensure_one()
        from ..runtime import field as field_runtime

        n = field_runtime.fill_missing(self, self.env.user, limit=200)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"message": _("%s record(s) filled.", n), "type": "info"},
        }

    @api.model
    def _cron_fill_ai_fields(self, batch_size=20):
        """Nightly: auto fill empties, auto update stale, as the agent's
        dedicated user or the administrator who set the field up."""
        from ..runtime import field as field_runtime

        for ir_field in self.sudo().search([("pan_ai_is_ai", "=", True)]):
            user = (
                ir_field.write_uid
                if ir_field.write_uid.active and not ir_field.write_uid.share
                else self.env.ref("base.user_admin")
            )
            try:
                if ir_field.pan_ai_auto_fill:
                    field_runtime.fill_missing(ir_field, user, limit=batch_size)
                if ir_field.pan_ai_auto_update:
                    field_runtime.fill_stale(ir_field, user, limit=batch_size)
            except Exception:  # noqa: BLE001 - one bad field never stops the others
                _logger.exception("[AI Pro] AI field %s.%s failed", ir_field.model, ir_field.name)
