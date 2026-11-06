# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Every agent gets a face: a character for an agent without a photo, and
that photo for the dedicated user of an agent that answers in Discuss, when
the user has none of its own. Names stay as they are: renaming a user
somebody picked is the administrator's call."""

from odoo import SUPERUSER_ID, api
from odoo.addons.pan_ai_pro.models.agent import character_image


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    agents = env["pan_ai.agent"].with_context(active_test=False).search([])
    for agent in agents:
        partner = agent.partner_id
        if partner and not partner.image_1920:
            partner.image_1920 = character_image(agent.id)
        user_partner = agent.user_id.partner_id
        if agent.in_channels and user_partner and not user_partner.image_1920:
            user_partner.image_1920 = partner.image_1920
