# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""`pan_ai.model`: the models an agent may pick, as configuration.

In Pydantic AI the model is an argument of the `Agent`, never a global.
So it is a required choice on every agent, from this list, and Settings
keeps only the key. A row is a name a person recognises and the OpenRouter
id the runtime passes to `OpenRouterModel`.
"""

from odoo import api, fields, models


class AiModel(models.Model):
    _name = "pan_ai.model"
    _description = "AI model"
    _order = "sequence, name"

    name = fields.Char(required=True)
    model_name = fields.Char(
        string="OpenRouter id",
        required=True,
        help="As openrouter.ai/models lists it, like anthropic/claude-sonnet-5.5.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    agent_count = fields.Integer(compute="_compute_agent_count", string="Agents")

    _model_name_unique = models.Constraint("UNIQUE(model_name)", "This model is already listed.")

    def _compute_agent_count(self):
        counts = dict(
            self.env["pan_ai.agent"]._read_group(
                [("model_id", "in", self.ids)], ["model_id"], ["__count"]
            )
        )
        for row in self:
            row.agent_count = counts.get(row, 0)

    @api.model
    def first(self):
        """The model a new agent starts with: the top of the list."""
        return self.search([], limit=1)
