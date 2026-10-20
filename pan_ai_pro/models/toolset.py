# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""`pan_ai.toolset`: a Pydantic AI `Toolset`, as a record. Two kinds: Odoo
tools (function tools over the ORM, the rows in `tool_ids`) and an MCP
server (any server speaking MCP over HTTP, one bearer token per row, the
tools it offers filtered by name). MCP Pro is not one of them (decision
14): an agent inside Odoo does not call the platform's MCP.
"""

from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..compat import params
from ..runtime.mcp_toolset import PARAM_ALLOWED_HOSTS, allowed_hosts


class Toolset(models.Model):
    _name = "pan_ai.toolset"
    _description = "AI toolset"
    _order = "name"

    name = fields.Char(required=True)
    description = fields.Char()
    active = fields.Boolean(default=True)
    kind = fields.Selection(
        [("odoo", "Odoo tools"), ("mcp", "MCP server")], default="odoo", required=True
    )
    tool_ids = fields.One2many("pan_ai.tool", "toolset_id", string="Tools")
    requires_approval = fields.Boolean(
        string="Ask before each tool",
        help="The person approves every call of every tool in this toolset.",
    )
    agent_ids = fields.Many2many("pan_ai.agent", string="Used by")
    tool_count = fields.Integer(compute="_compute_tool_count")

    # MCP server
    url = fields.Char(
        string="Server URL",
        help="https://host/mcp.",
    )
    # The SSRF gate's list (`pan_ai.mcp_allowed_hosts`), set where the URL is.
    host_allowed = fields.Boolean(
        string="Allow this host",
        compute="_compute_host_allowed",
        inverse="_inverse_host_allowed",
        groups="base.group_system",
        help="A Settings administrator allows the server's host once.",
    )
    bearer_token = fields.Char(
        groups="base.group_system",
        copy=False,
        help="Sent as Authorization: Bearer; empty for a server without authentication.",
    )
    allowed_tool_names = fields.Char(help="Comma separated; empty is every tool the server offers.")
    tool_prefix = fields.Char(
        help="Prefix on the tool names the model sees, to keep two servers apart."
    )

    @api.constrains("kind", "url")
    def _check_url(self):
        for toolset in self.filtered(lambda t: t.kind == "mcp"):
            if not (toolset.url or "").startswith(("https://", "http://")):
                raise ValidationError(_("An MCP server needs an http(s) URL."))

    def _host(self):
        return (urlparse(self.url or "").hostname or "").lower()

    def _compute_host_allowed(self):
        allowed = allowed_hosts(self.env)
        for toolset in self:
            toolset.host_allowed = bool(toolset._host()) and toolset._host() in allowed

    def _inverse_host_allowed(self):
        allowed = allowed_hosts(self.env)
        for toolset in self.filtered(lambda t: t._host()):
            if toolset.host_allowed:
                allowed.add(toolset._host())
            else:
                allowed.discard(toolset._host())
        params(self.env).set_str(PARAM_ALLOWED_HOSTS, ",".join(sorted(allowed)))

    def _compute_tool_count(self):
        for toolset in self:
            toolset.tool_count = len(toolset.tool_ids)

    def allowed_names(self):
        self.ensure_one()
        return {n.strip() for n in (self.allowed_tool_names or "").split(",") if n.strip()}
