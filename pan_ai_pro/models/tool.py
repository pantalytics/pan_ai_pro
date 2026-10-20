"""`pan_ai.tool`: one Pydantic AI `Tool`, as a record. A built-in (the ORM
verbs), or a server action an administrator exposed with a name, a
description and a JSON schema for its parameters. The runtime
(runtime/odoo_toolset.py) turns rows into functions on the caller's `env`.
"""

import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

BUILTINS = [
    ("describe_model", "Describe a model: its fields and their types"),
    ("search_records", "Search records with a domain"),
    ("read_records", "Read fields of records by id"),
    ("read_group", "Aggregate records (count, sum) grouped by a field"),
    ("create_record", "Create a record"),
    ("write_record", "Update a record"),
    ("open_record", "Show a record or a list to the person"),
    ("today", "The current date and time in the person's time zone"),
]
WRITES = ("create_record", "write_record")


class Tool(models.Model):
    _name = "pan_ai.tool"
    _description = "AI tool"
    _order = "toolset_id, sequence, name"

    name = fields.Char(
        required=True,
        help="The name the model calls, letters, digits and underscores.",
    )
    description = fields.Text(required=True, help="What the model reads to decide when to call it.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    toolset_id = fields.Many2one("pan_ai.toolset", required=True, ondelete="cascade")
    source = fields.Selection(
        [("builtin", "Built in"), ("server_action", "Server action")],
        default="builtin",
        required=True,
    )
    builtin = fields.Selection(BUILTINS)
    action_id = fields.Many2one(
        "ir.actions.server",
        string="Server action",
        domain="[('model_id', '!=', False)]",
        ondelete="cascade",
    )
    parameters_json_schema = fields.Text(
        string="Parameters (JSON schema)",
        help="A server action's parameters, handed to it as pan_ai_args in the context.",
    )
    model_ids = fields.Many2many(
        "ir.model",
        string="Models",
        help="The models a built-in tool may touch; empty is any model the user may access.",
    )
    # The names, stored: the toolset reads them as the run's user, who may
    # not read ir.model itself (Odoo 19 gives plain users no access to it).
    model_names = fields.Char(compute="_compute_model_names", store=True, compute_sudo=True)
    requires_approval = fields.Boolean(
        string="Ask before calling",
        help="The person approves each call in the chat before it runs.",
    )

    @api.depends("model_ids.model")
    def _compute_model_names(self):
        for tool in self:
            tool.model_names = ",".join(tool.model_ids.mapped("model")) or False

    _name_per_toolset = models.Constraint(
        "UNIQUE(toolset_id, name)", "A tool name must be unique within its toolset."
    )

    @api.constrains("name")
    def _check_name(self):
        for tool in self:
            if not tool.name.replace("_", "").isalnum() or not tool.name.isascii():
                raise ValidationError(
                    _("Tool name '%s' may hold letters, digits and underscores only.", tool.name)
                )

    @api.constrains("source", "builtin", "action_id", "parameters_json_schema")
    def _check_source(self):
        for tool in self:
            if tool.source == "builtin" and not tool.builtin:
                raise ValidationError(_("Pick which built-in tool this is."))
            if tool.source == "server_action" and not tool.action_id:
                raise ValidationError(_("Pick the server action."))
            if tool.parameters_json_schema:
                try:
                    schema = json.loads(tool.parameters_json_schema)
                except ValueError as error:
                    raise ValidationError(_("Parameters are not valid JSON: %s", error)) from error
                if not isinstance(schema, dict) or schema.get("type") != "object":
                    raise ValidationError(_("Parameters must be a JSON schema of type object."))

    @api.onchange("builtin")
    def _onchange_builtin(self):
        if self.builtin and not self.name:
            self.name = self.builtin
        if self.builtin and not self.description:
            self.description = dict(BUILTINS)[self.builtin]
        if self.builtin in WRITES:
            self.requires_approval = True

    def asks_approval(self):
        self.ensure_one()
        return self.requires_approval or self.toolset_id.requires_approval
