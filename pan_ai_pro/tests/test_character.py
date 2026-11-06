# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An agent is a character: a face and a name, and as a colleague its user
carries both (docs/plans/ai-colleague.md, section 9)."""

import base64

from .common import AiProCase


def raw(value):
    """An image's bytes: Odoo 20 holds a BinaryValue, Odoo 19 base64."""
    return value.content if hasattr(value, "content") else base64.b64decode(value)


class TestCharacter(AiProCase):
    def new_agent(self, name="Ava"):
        return self.agent.copy({"name": name, "partner_id": False})

    def test_a_new_agent_has_a_face(self):
        agent = self.new_agent()
        self.assertTrue(agent.image_1920, "a character until somebody uploads a photo")
        self.assertEqual(raw(agent.partner_id.image_1920), raw(agent.image_1920))

    def test_an_uploaded_photo_replaces_the_character(self):
        agent = self.new_agent()
        other = self.new_agent("Bo")
        agent.image_1920 = other.image_1920
        self.assertEqual(raw(agent.partner_id.image_1920), raw(other.image_1920))

    def test_picking_a_user_gives_it_the_character(self):
        agent = self.new_agent()
        user = self.env["res.users"].create(
            {
                "name": "Someone",
                "login": "someone",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        agent.write({"run_as": "user", "user_id": user.id, "in_channels": True})
        self.assertEqual(user.name, "Ava")
        agent.name = "Ava Sales"
        self.assertEqual(user.name, "Ava Sales", "the agent is the character's source")
        self.assertEqual(raw(user.partner_id.image_1920), raw(agent.image_1920))
