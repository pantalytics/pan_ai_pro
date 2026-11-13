# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""`pan_ai.model`: the models an agent may pick, as configuration.

In Pydantic AI the model is an argument of the `Agent`, never a global.
So it is a required choice on every agent, from this list, and Settings
keeps only the keys. A row is a name a person recognises, the host that
answers it (`hosts.py`) and the id the runtime passes to `OpenRouterModel`.

The list is a shortlist (data/model.xml). On OpenRouter: four providers,
Claude, Gemini, GPT and Mistral, each with its families. Where OpenRouter has a
`~vendor/family-latest` alias the row is that alias, which answers as the
newest model in its family; Mistral has none, so its rows are pinned ids.
EUrouter has no aliases at all, so the daily sync does their work for its
shortlist: each seeded EUrouter row moves to the newest id of its family
(`anthropic/claude-sonnet-5-5` to `-5-6`), and its agents with it. An exact
id, to pin a version, is typed into the list by hand and never moves. Once a
day the rows their host no longer lists are archived; nothing is added.
"""

import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..hosts import HOST_SELECTION, HOSTS, keyed, stand_in

_logger = logging.getLogger(__name__)

TIMEOUT = 15
VERSION = re.compile(r"\d+(\.\d+)*")


def family(slug):
    """A vendor/model id as its family and its version, read from the name:
    `anthropic/claude-sonnet-5-5` is `anthropic/claude-sonnet`, (5, 5), and
    `openai/gpt-6.1-sol` is `openai/gpt-sol`, (6, 1)."""
    vendor, _sep, name = slug.partition("/")
    words, version = [], []
    for word in name.split("-"):
        if VERSION.fullmatch(word):
            version += [int(part) for part in word.split(".")]
        else:
            words.append(word)
    return f"{vendor}/{'-'.join(words)}", tuple(version)


def newest(slug, catalogue):
    """The newest id of `slug`'s family in a host's catalogue that can chat
    with tools, or `slug` itself: never an older one."""
    name, best = family(slug)
    found = slug
    for entry in catalogue:
        other = entry.get("canonical_slug") or entry.get("id") or ""
        if "tools" not in (entry.get("supported_parameters") or []):
            continue
        if "chat.completions" not in (entry.get("supported_api_endpoints") or []):
            continue
        other_name, version = family(other)
        if other_name == name and version > best:
            found, best = other, version
    return found


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
        help="vendor/model, as the host lists it on openrouter.ai/models or"
        " eurouter.ai/models. On"
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

    @api.constrains("model_name")
    def _check_model_name(self):
        """The runtime reads the vendor from the id: a bare id fails every run."""
        for row in self:
            if "/" not in row.model_name:
                raise ValidationError(
                    _("Write the model id as vendor/model, like mistral/%s.", row.model_name)
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
        """Archive what a host no longer lists, so nobody picks a dead id, and
        move EUrouter's seeded rows to the newest of their family.

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
                data = response.json()["data"]
                # EUrouter lists a bare id beside the vendor/model slug the rows use.
                listed = {m["id"] for m in data} | {m.get("canonical_slug") for m in data}
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                _logger.warning("[AI Pro] %s's model list unreadable: %s", host.label, error)
                continue
            if code == "eurouter":
                rows._follow_families(data)
            if listed:
                rows.filtered(lambda r, listed=listed: r.model_name not in listed).active = False

    def _follow_families(self, catalogue):
        """What OpenRouter's `-latest` aliases do, for rows this module seeded.
        A row typed by hand has no xml id and stays pinned; a newer id that
        is already a row of its own is left to that row."""
        seeded = self.get_external_id()
        for row in self.filtered(lambda r: seeded.get(r.id, "").startswith("pan_ai_pro.")):
            target = newest(row.model_name, catalogue)
            if target == row.model_name or self.with_context(active_test=False).search_count(
                [("host", "=", row.host), ("model_name", "=", target)], limit=1
            ):
                continue
            _logger.info("[AI Pro] %s moves from %s to %s", row.name, row.model_name, target)
            row.model_name = target
