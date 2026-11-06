# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An agent added to a channel shows in its mention suggestions. Odoo
suggests active partners only, and an agent's partner (its character) is
archived so it stays out of Contacts; inside a channel's suggestions the
agents are added back (docs/plans/agent-identity.md)."""

from odoo import api, models
from odoo.fields import Domain


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def get_mention_suggestions_from_channel(self, *args, **kwargs):
        return super(
            ResPartner, self.with_context(pan_ai_agents=True)
        ).get_mention_suggestions_from_channel(*args, **kwargs)

    @api.model
    def _get_mention_suggestions_domain(self, search):
        domain = super()._get_mention_suggestions_domain(search)
        if not self.env.context.get("pan_ai_agents"):
            return domain
        agents = self.env["pan_ai.agent"].sudo().search([("name", "ilike", search or "")])
        return Domain(domain) | Domain("id", "in", agents.partner_id.ids)
