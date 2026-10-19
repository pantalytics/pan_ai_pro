"""`pan_ai.toolset`: a Pydantic AI `Toolset`, as a record: a named bundle of
tools an agent may hold. Only Odoo tools for now (function tools over the
ORM); an MCP toolset with a bearer token is a later PR, when somebody asks.
"""

from odoo import fields, models


class Toolset(models.Model):
    _name = "pan_ai.toolset"
    _description = "AI toolset"
    _order = "name"

    name = fields.Char(required=True)
    description = fields.Char()
    active = fields.Boolean(default=True)
    tool_ids = fields.One2many("pan_ai.tool", "toolset_id", string="Tools")
    requires_approval = fields.Boolean(
        string="Ask before each tool",
        help="The person approves every call of every tool in this toolset. Tools with their own approval flag ask anyway.",
    )
    agent_ids = fields.Many2many("pan_ai.agent", string="Used by")
    tool_count = fields.Integer(compute="_compute_tool_count")

    def _compute_tool_count(self):
        for toolset in self:
            toolset.tool_count = len(toolset.tool_ids)
