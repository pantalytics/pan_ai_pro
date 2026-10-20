# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""One flag in the session: may this person open the chat.

The sparkle top right and Ctrl+K "Ask AI" show only on an Odoo that is
connected to Pantalytics and has an OpenRouter key, so nobody meets a chat
window that can only answer "not set up". `session_info` is fetched once per
page load anyway, so the sparkle knows before the first paint. Stale by one
page load, on purpose: connecting and saving the key both reload the page.

Every page load runs this, so a failure here would be a 500 on every
screen. A database the upgrade has not reached yet reads as "no".
"""

import logging

from psycopg2 import errors

from odoo import models

from ..compat import params

_logger = logging.getLogger(__name__)

SCHEMA_BEHIND = (errors.UndefinedTable, errors.UndefinedColumn)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        result = super().session_info()
        if self.env.user._is_internal():
            ready = False
            try:
                with self.env.cr.savepoint():
                    ready = self._pan_ai_chat_ready()
            except SCHEMA_BEHIND:
                _logger.warning("[AI Pro] The database is behind the code. Upgrade pan_ai_pro.")
                self.env.invalidate_all()
            result["pan_ai_chat_ready"] = ready
        return result

    def _pan_ai_chat_ready(self):
        link = self.env["pan_ai.license"].current()
        return bool(
            link and link.is_entitled() and params(self.env).get_str("pan_ai.openrouter_key", "")
        )
