# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An agent is a character: a face and a name, and as a colleague its user
carries both (docs/plans/ai-colleague.md, section 9)."""

from odoo.exceptions import UserError

from .common import AiProCase


class TestCharacter(AiProCase):
    def new_agent(self, name="Ava"):
        return self.agent.copy({"name": name, "partner_id": False})

    def test_a_new_agent_has_a_face(self):
        agent = self.new_agent()
        self.assertTrue(agent.image_1920, "a character until somebody uploads a photo")
        self.assertEqual(agent.partner_id.image_1920, agent.image_1920)

    def test_an_uploaded_photo_replaces_the_character(self):
        agent = self.new_agent()
        other = self.new_agent("Bo")
        agent.image_1920 = other.image_1920
        self.assertEqual(agent.partner_id.image_1920, other.image_1920)

    def test_a_colleague_is_its_user_with_the_agents_name_and_face(self):
        agent = self.new_agent()
        action = agent.action_make_colleague()
        user = agent.user_id
        self.assertEqual(action["res_model"], "res.users")
        self.assertEqual(action["res_id"], user.id)
        self.assertEqual((agent.run_as, agent.in_channels), ("user", True))
        self.assertEqual(user.name, "Ava")
        self.assertEqual(user.partner_id.image_1920, agent.image_1920)
        self.assertFalse(user.share)
        self.assertEqual(user.group_ids & self.env.ref("base.group_system"), self.env["res.groups"])
        agent.name = "Ava Sales"
        self.assertEqual(user.name, "Ava Sales", "the agent is the character's source")
        with self.assertRaises(UserError):
            agent.action_make_colleague()

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
        self.assertEqual(user.partner_id.image_1920, agent.image_1920)
