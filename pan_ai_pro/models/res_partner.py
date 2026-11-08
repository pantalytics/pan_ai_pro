# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An agent in Discuss is its partner, its character, and Odoo's member
lists only know people (docs/plans/agent-identity.md). Three places learn
about agents here:

- a channel's mention suggestions (Odoo suggests active partners only, and
  an agent's partner is archived so it stays out of Contacts);
- a channel's Invite search, so an agent is added from the channel itself,
  the way a colleague is;
- presence: an agent is always there, so it shows online, not as a person
  who left.
"""

from odoo import api, models
from odoo.fields import Domain


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _pan_ai_agent_partners(self, search=None):
        Agent = self.env["pan_ai.agent"].sudo()
        domain = [("name", "ilike", search)] if search else []
        return Agent.search(domain).partner_id

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
        return Domain(domain) | Domain("id", "in", self._pan_ai_agent_partners(search or "").ids)

    @api.model
    def _search_for_channel_invite(self, store, search_term, channel_id=None, limit=30, *args):
        """The people Odoo finds, then the agents this person may use whose
        name matches and that are not in the channel yet. An agent joins as
        its partner: no user, so no seat. Odoo 19 only: Odoo 20's Invite
        drops archived partners, and an agent's partner is archived, so
        there an agent is added from Agents > Access > Channels."""
        found = super()._search_for_channel_invite(store, search_term, channel_id, limit, *args)
        if not channel_id or not isinstance(found, dict):
            return found
        channel = self.env["discuss.channel"].search([("id", "=", int(channel_id))])
        if not channel:
            return found
        agents = self.env["pan_ai.agent"].search([("name", "ilike", search_term)])
        partners = agents.sudo().partner_id - channel.sudo().channel_member_ids.partner_id
        if not partners:
            return found
        partners.sudo()._search_for_channel_invite_to_store(store, channel)
        ids = partners.ids + found["partner_ids"]
        return {**found, "partner_ids": ids, "count": found["count"] + len(partners)}

    def _compute_im_status(self):
        """Odoo 19: an agent is always there. Odoo 20 keeps presence on the
        user, so there an agent shows no status at all, which is fine."""
        super()._compute_im_status()
        for partner in self & self._pan_ai_agent_partners():
            partner.im_status = "online"
