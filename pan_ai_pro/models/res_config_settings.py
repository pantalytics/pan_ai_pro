"""Settings > AI Pro: the connection, the model, the limits, the danger zone.

The OpenRouter key is stored in `ir.config_parameter` (`pan_ai.openrouter_key`),
readable by `base.group_system` only, never shown back: the page says
Connected or No key and offers Replace and Remove. The 19.0 module kept its
key the same way; there was no encryption helper to inherit.
"""

from odoo import api, fields, models

from .license import STATUS_SELECTION

STATE_SELECTION = [
    ("not_connected", "Not connected"),
    ("pending", "Waiting for approval"),
    ("connected", "Connected"),
    ("broken", "Broken"),
]
BROKEN = ("revoked", "invalid")
DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Model
    pan_ai_has_key = fields.Boolean(compute="_compute_pan_ai_key")
    pan_ai_key_last4 = fields.Char(compute="_compute_pan_ai_key")
    pan_ai_new_key = fields.Char(string="OpenRouter key")
    pan_ai_default_model = fields.Char(
        string="Default model",
        config_parameter="pan_ai.default_model",
        default=DEFAULT_MODEL,
    )
    # Limits
    pan_ai_runs_per_user_per_hour = fields.Integer(
        string="Runs per person per hour",
        config_parameter="pan_ai.runs_per_user_per_hour",
        default=30,
    )
    pan_ai_retention_days = fields.Integer(
        string="Keep chats for (days)",
        config_parameter="pan_ai.retention_days",
        default=90,
        help="0 keeps them forever. Runs are kept.",
    )
    # Connection
    pan_ai_state = fields.Selection(STATE_SELECTION, compute="_compute_pan_ai_link")
    pan_ai_link_status = fields.Selection(STATUS_SELECTION, compute="_compute_pan_ai_link")
    pan_ai_user_code = fields.Char(string="Code", compute="_compute_pan_ai_link")
    pan_ai_verify_url = fields.Char(string="Approve at", compute="_compute_pan_ai_link")
    pan_ai_last_error = fields.Char(compute="_compute_pan_ai_link")
    pan_ai_message = fields.Char(compute="_compute_pan_ai_link")
    pan_ai_connected_by = fields.Char(compute="_compute_pan_ai_link")
    pan_ai_update_available = fields.Char(compute="_compute_pan_ai_link")

    def _compute_pan_ai_key(self):
        key = self.env["ir.config_parameter"].sudo().get_str("pan_ai.openrouter_key", "")
        for record in self:
            record.pan_ai_has_key = bool(key)
            record.pan_ai_key_last4 = key[-4:] if key else ""

    @api.depends("pan_ai_default_model")
    def _compute_pan_ai_link(self):
        link = self.env["pan_ai.license"].current()
        status = (link and link.status) or "not_connected"
        if status == "active":
            state = "connected"
        elif status in BROKEN:
            state = "broken"
        else:
            state = status
        installed = self.env["pan_ai.license"]._module_version()
        latest = link and link.latest_version
        for record in self:
            record.pan_ai_state = state
            record.pan_ai_link_status = status
            record.pan_ai_user_code = link and link.user_code
            record.pan_ai_verify_url = link and link.verify_url
            record.pan_ai_last_error = link and link.last_error
            record.pan_ai_message = link and link.message
            who = link and link.connected_user_id
            when = link and link.connected_on
            record.pan_ai_connected_by = (
                f"{who.name}, {fields.Date.to_string(when)}" if who and when else False
            )
            record.pan_ai_update_available = latest if latest and latest != installed else False

    def set_values(self):
        super().set_values()
        if self.pan_ai_new_key:
            key = self.pan_ai_new_key.strip()
            self.env["ir.config_parameter"].sudo().set_str("pan_ai.openrouter_key", key)

    def _reload(self):
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_pan_ai_remove_key(self):
        """The kill switch: every new run refuses at once."""
        self.env["ir.config_parameter"].sudo().set_str("pan_ai.openrouter_key", "")
        return self._reload()

    def action_pan_ai_connect(self):
        link = self.env["pan_ai.license"].action_connect()
        return {"type": "ir.actions.act_url", "url": link.verify_url, "target": "new"}

    def action_pan_ai_check(self):
        link = self.env["pan_ai.license"].current()
        return (link and link.action_check_approval()) or self._reload()

    def action_pan_ai_disconnect(self):
        link = self.env["pan_ai.license"].current()
        if link:
            link.action_disconnect()
        return self._reload()

    def action_pan_ai_delete_threads(self):
        threads = self.env["pan_ai.thread"].sudo().search([])
        threads.channel_id.sudo().unlink()
        threads.unlink()
        return self._reload()
