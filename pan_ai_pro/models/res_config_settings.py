# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Settings > AI Pro: the setup checklist, the limits, the danger zone.

Three steps, in the order a person has to take them: connect to Pantalytics,
save an OpenRouter key, have a first chat. Until the first is done nothing
else is on the page (or in the menu, `ir_ui_menu.py`).

The OpenRouter key is stored in `ir.config_parameter` (`pan_ai.openrouter_key`),
readable by `base.group_system` only, never shown back: the page says
Saved, ends in the last four, or shows an empty paste field; Remove key sits
in the Danger zone. The 19.0 module kept its
key the same way; there was no encryption helper to inherit.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ..compat import params
from ..defaults import DEFAULT_MODEL, RETENTION_DAYS, RUNS_PER_USER_PER_HOUR
from .license import STATUS_SELECTION

STATE_SELECTION = [
    ("not_connected", "Not connected"),
    ("pending", "Waiting for approval"),
    ("connected", "Connected"),
    ("broken", "Broken"),
]
BROKEN = ("revoked", "invalid")


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
        string="Chats per person per hour",
        config_parameter="pan_ai.runs_per_user_per_hour",
        default=RUNS_PER_USER_PER_HOUR,
    )
    pan_ai_retention_days = fields.Integer(
        string="Keep chats for (days)",
        config_parameter="pan_ai.retention_days",
        default=RETENTION_DAYS,
    )
    pan_ai_mcp_allowed_hosts = fields.Char(
        string="Allowed MCP hosts",
        config_parameter="pan_ai.mcp_allowed_hosts",
        help="Comma separated.",
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
    pan_ai_entitled = fields.Boolean(compute="_compute_pan_ai_link")
    pan_ai_why_not = fields.Char(compute="_compute_pan_ai_link")
    # Step 3: a run that finished proves the connection, the key and the model.
    pan_ai_has_chatted = fields.Boolean(compute="_compute_pan_ai_key")

    def _compute_pan_ai_key(self):
        key = params(self.env).get_str("pan_ai.openrouter_key", "")
        chatted = bool(self.env["pan_ai.run"].sudo().search_count([("status", "=", "ok")], limit=1))
        for record in self:
            record.pan_ai_has_chatted = chatted
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
        latest = link.latest_version
        entitled = bool(link) and link.is_entitled()
        why_not = link._why_not_entitled() if link and not entitled else False
        for record in self:
            record.pan_ai_entitled = entitled
            record.pan_ai_why_not = why_not
            record.pan_ai_state = state
            record.pan_ai_link_status = status
            record.pan_ai_user_code = link.user_code
            record.pan_ai_verify_url = link.verify_url
            record.pan_ai_last_error = link.last_error
            record.pan_ai_message = link.message
            who = link.connected_user_id
            when = link.connected_on
            record.pan_ai_connected_by = (
                f"{who.name}, {fields.Date.to_string(when)}" if who and when else False
            )
            record.pan_ai_update_available = latest if latest and latest != installed else False

    def set_values(self):
        super().set_values()
        if self.pan_ai_new_key:
            key = self.pan_ai_new_key.strip()
            params(self.env).set_str("pan_ai.openrouter_key", key)

    def _reload(self):
        return {"type": "ir.actions.client", "tag": "reload"}

    def _pan_ai_check_admin(self):
        """Every button on this page: a public method any session can call
        by name, so it asks for the Settings administrator itself."""
        if not (self.env.su or self.env.user.has_group("base.group_system")):
            raise AccessError(_("Only a Settings administrator can do this."))

    def action_pan_ai_remove_key(self):
        """The kill switch: every new run refuses at once."""
        self._pan_ai_check_admin()
        params(self.env).set_str("pan_ai.openrouter_key", "")
        return self._reload()

    def action_pan_ai_connect(self):
        self._pan_ai_check_admin()
        link = self.env["pan_ai.license"].action_connect()
        return {"type": "ir.actions.act_url", "url": link.verify_url, "target": "new"}

    def action_pan_ai_check(self):
        self._pan_ai_check_admin()
        link = self.env["pan_ai.license"].current()
        return (link and link.action_check_approval()) or self._reload()

    def action_pan_ai_open_chat(self):
        """Step 3: the chat window with the default agent."""
        channel_id = self.env["discuss.channel"].pan_ai_open()
        return {
            "type": "ir.actions.client",
            "tag": "pan_ai_pro.open_chat",
            "params": {"channel_id": channel_id},
        }

    def action_pan_ai_disconnect(self):
        self._pan_ai_check_admin()
        link = self.env["pan_ai.license"].current()
        if link:
            link.action_disconnect()
        return self._reload()

    def action_pan_ai_delete_threads(self):
        """Every thread of every kind, with its chat window and its runs."""
        self._pan_ai_check_admin()
        self.env["pan_ai.thread"].sudo().search([])._unlink_with_channels()
        return self._reload()
