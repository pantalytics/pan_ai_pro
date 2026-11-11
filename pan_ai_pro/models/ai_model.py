# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""`pan_ai.model`: the models an agent may pick, as configuration.

In Pydantic AI the model is an argument of the `Agent`, never a global.
So it is a required choice on every agent, from this list, and Settings
keeps only the keys. A row is a name a person recognises, the host that
answers it (`hosts.py`) and the id the runtime passes to `OpenRouterModel`.

The list is a shortlist (data/model.xml). On OpenRouter: four providers,
Claude, Gemini, GPT and Mistral, each with its families. On EUrouter, which
has no family aliases: Mistral, Claude and GPT, pinned. Where OpenRouter has a
`~vendor/family-latest` alias the row is that alias, which answers as the
newest model in its family; Mistral has none, so its rows are pinned ids.
Nothing here tracks versions; OpenRouter does. An exact id, to pin a
version, is typed into the list by hand. Once a day the rows their host no
longer lists are archived; nothing is added.
"""

import logging

import requests

from odoo import api, fields, models

from ..hosts import HOST_SELECTION, HOSTS, keyed, stand_in

_logger = logging.getLogger(__name__)

TIMEOUT = 15


class AiModel(models.Model):
    _name = "pan_ai.model"
    _description = "AI model"
    _order = "sequence, name"
    _rec_names_search = ["name", "model_name"]

    name = fields.Char(required=True)
    host = fields.Selection(
        HOST_SELECTION,
        required=True,
        default="openrouter",
        help="Who answers this model, with the key saved for it in Settings > AI Pro."
        " EUrouter routes to EU-hosted providers only.",
    )
    model_name = fields.Char(
        string="Model id",
        required=True,
        help="As the host lists it, on openrouter.ai/models or eurouter.ai/models. On"
        " OpenRouter a ~vendor/family-latest id follows the family to its newest model;"
        " an exact id pins one version.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # The shortlist's rows. The agent's picker opens on this filter; a
    # model somebody typed in by hand is one filter click away.
    recommended = fields.Boolean(help="Shown first when an agent picks a model.")
    agent_count = fields.Integer(compute="_compute_agent_count", string="Agents")

    _model_name_unique = models.Constraint(
        "UNIQUE(host, model_name)", "This model is already listed."
    )

    @api.depends("name", "host")
    def _compute_display_name(self):
        """The host in the name wherever it is not the default, so two
        "Claude Sonnet" rows never look alike on an agent."""
        for row in self:
            label = dict(HOST_SELECTION).get(row.host)
            row.display_name = f"{row.name} ({label})" if row.host != "openrouter" else row.name

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
        """The model a new agent starts with: the top of the recommended list,
        on a host with a key when there is one."""
        hosts = [("host", "in", keyed(self.env) or list(HOSTS))]
        return (
            self.search([("recommended", "=", True), *hosts], limit=1)
            or self.search(hosts, limit=1)
            or self.search([], limit=1)
        )

    @api.model
    def _cron_sync(self):
        """Archive what a host no longer lists, so nobody picks a dead id.

        Adds nothing: the list is a shortlist, not the catalogue. Neither
        catalogue needs a key. An answer that fails or lists nothing changes
        nothing: an outage must not empty every agent's picker.
        """
        for code, host in HOSTS.items():
            rows = self.search([("host", "=", code)])
            if not rows:
                continue
            base = stand_in(host) or host.base_url
            try:
                response = requests.get(base.rstrip("/") + "/models", timeout=TIMEOUT)
                response.raise_for_status()
                listed = {m["id"] for m in response.json()["data"]}
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                _logger.warning("[AI Pro] %s's model list unreadable: %s", host.label, error)
                continue
            if listed:
                rows.filtered(lambda r, listed=listed: r.model_name not in listed).active = False
