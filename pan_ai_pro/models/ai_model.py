# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""`pan_ai.model`: the models an agent may pick, as configuration.

In Pydantic AI the model is an argument of the `Agent`, never a global.
So it is a required choice on every agent, from this list, and Settings
keeps only the key. A row is a name a person recognises and the OpenRouter
id the runtime passes to `OpenRouterModel`.

The list is a shortlist (data/model.xml): OpenRouter's `~vendor/family-latest`
aliases, each of which answers as the newest model in its family, and its
Auto Router. Nothing here tracks versions; OpenRouter does. An exact id, to
pin a version, is typed into the list by hand. Once a day the rows OpenRouter
no longer lists are archived; nothing is added.
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
        help="As openrouter.ai/models lists it. A ~vendor/family-latest id follows the"
        " family to its newest model; an exact id pins one version.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # The shortlist's rows. The agent's picker opens on this filter; a
    # model somebody typed in by hand is one filter click away.
    recommended = fields.Boolean(help="Shown first when an agent picks a model.")
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
        """The model a new agent starts with: the top of the recommended list."""
        return self.search([("recommended", "=", True)], limit=1) or self.search([], limit=1)

    @api.model
    def _cron_sync(self):
        """Archive what OpenRouter no longer lists, so nobody picks a dead id.

        Adds nothing: the list is a shortlist, not the catalogue. The
        catalogue needs no key. An answer that fails or lists nothing changes
        nothing: an outage must not empty every agent's picker.
        """
        from ..runtime.agent import ENV_BASE_URL

        base = os.environ.get(ENV_BASE_URL, "").strip() or CATALOGUE_URL
        try:
            response = requests.get(base.rstrip("/") + "/models", timeout=TIMEOUT)
            response.raise_for_status()
            listed = {m["id"] for m in response.json()["data"]}
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            _logger.warning("[AI Pro] OpenRouter's model list unreadable: %s", error)
            return
        if not listed:
            return
        self.search([]).filtered(lambda r: r.model_name not in listed).active = False
