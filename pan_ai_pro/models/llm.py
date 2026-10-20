# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The models OpenRouter offers, so a model is picked from a list instead of
typed from memory.

The list is OpenRouter's own (`GET /models`, public, no key), copied in once
a day and whenever the OpenRouter dialog opens on an empty list. A model
OpenRouter drops stays in the list: a stale row is harmless, a missing one
is a setting that no longer shows. The setting itself stays the id string
(`pan_ai.default_model`), which is what the runtime reads.
"""

import logging
import os

import requests

from odoo import api, fields, models

from ..runtime.agent import ENV_BASE_URL

_logger = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT = 15


class Llm(models.Model):
    _name = "pan_ai.llm"
    _description = "OpenRouter model"
    _order = "name"
    _rec_names_search = ["name", "code"]

    name = fields.Char(required=True)
    code = fields.Char(string="Model id", required=True, help="Like anthropic/claude-sonnet-5.5.")

    _unique_code = models.Constraint("UNIQUE(code)", "A model id is listed once.")

    @api.model
    def _for_code(self, code):
        """The row for an id, made on the spot for one the list lacks."""
        llm = self.sudo().search([("code", "=", code)], limit=1)
        return llm or self.sudo().create({"name": code, "code": code})

    @api.model
    def _refresh(self):
        """Copy OpenRouter's list in. A failure is logged, never raised: the
        list we have is still a list."""
        url = (os.environ.get(ENV_BASE_URL) or BASE_URL).rstrip("/") + "/models"
        try:
            response = requests.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()["data"]
        except (requests.RequestException, ValueError, KeyError, TypeError) as e:
            _logger.warning("[AI Pro] the OpenRouter model list did not load: %s", e)
            return 0
        known = {llm.code: llm for llm in self.sudo().search([])}
        new = []
        for item in data:
            code, name = item.get("id"), item.get("name") or item.get("id")
            if not code:
                continue
            if code in known:
                if known[code].name != name:
                    known[code].name = name
            else:
                new.append({"code": code, "name": name})
                known[code] = True
        self.sudo().create(new)
        return len(data)

    @api.model
    def _cron_refresh(self):
        self._refresh()
