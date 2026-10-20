# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""`pan_ai.model`: the models an agent may pick, as configuration.

In Pydantic AI the model is an argument of the `Agent`, never a global.
So it is a required choice on every agent, from this list, and Settings
keeps only the key. A row is a name a person recognises and the OpenRouter
id the runtime passes to `OpenRouterModel`.

The list mirrors OpenRouter's catalogue once a day: a new model appears,
one OpenRouter dropped is archived. A name a person changed, and a row a
person archived, stay as they are.
"""

import logging
import os

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CATALOGUE_URL = "https://openrouter.ai/api/v1"
TIMEOUT = 15


class AiModel(models.Model):
    _name = "pan_ai.model"
    _description = "AI model"
    _order = "sequence, name"
    _rec_names_search = ["name", "model_name"]

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

    @api.model
    def _cron_sync(self):
        """Add what OpenRouter lists and this list lacks; archive what it dropped.

        The catalogue needs no key. An answer that fails or lists nothing
        changes nothing: an outage must not empty every agent's picker.
        """
        from ..runtime.agent import ENV_BASE_URL

        base = os.environ.get(ENV_BASE_URL, "").strip() or CATALOGUE_URL
        try:
            response = requests.get(base.rstrip("/") + "/models", timeout=TIMEOUT)
            response.raise_for_status()
            listed = {m["id"]: m.get("name") or m["id"] for m in response.json()["data"]}
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            _logger.warning("[AI Pro] OpenRouter's model list unreadable: %s", error)
            return
        if not listed:
            return
        rows = self.with_context(active_test=False).search([])
        known = set(rows.mapped("model_name"))
        self.create(
            [
                {"name": name, "model_name": model_id, "sequence": 100}
                for model_id, name in listed.items()
                if model_id not in known
            ]
        )
        rows.filtered(lambda r: r.active and r.model_name not in listed).active = False
