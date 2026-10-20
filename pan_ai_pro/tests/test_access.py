# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The access rows, on whichever model this Odoo keeps them in: a user sees
their own threads and runs and reads the agents open to them; a manager
sees everything; a portal user sees nothing."""

from odoo.exceptions import AccessError
from odoo.tools.convert import convert_file

from .common import AiProCase


class TestAccess(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"]
        cls.eve = Users.create(
            {
                "name": "Eve",
                "login": "eve",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.manager = Users.create(
            {
                "name": "Mia",
                "login": "mia",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("pan_ai_pro.group_manager").id,
                        ],
                    )
                ],
            }
        )
        cls.portal = Users.create(
            {
                "name": "Pat",
                "login": "pat_access",
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )
        Thread = cls.env["pan_ai.thread"].sudo()
        cls.sams = Thread.create({"name": "sam", "agent_id": cls.agent.id, "user_id": cls.user.id})
        cls.eves = Thread.create({"name": "eve", "agent_id": cls.agent.id, "user_id": cls.eve.id})
        Run = cls.env["pan_ai.run"].sudo()
        cls.sam_run = Run.create({"thread_id": cls.sams.id, "user_id": cls.user.id, "prompt": "x"})
        cls.eve_run = Run.create({"thread_id": cls.eves.id, "user_id": cls.eve.id, "prompt": "x"})

    def test_an_upgrade_gives_every_internal_user_the_chat(self):
        """Prod 2026-10-20: upgraded from 1.6.1, base.group_user is noupdate, so
        groups.xml never linked it to AI Pro's User and only admins could chat."""
        internal = self.env.ref("base.group_user")
        internal.write({"implied_ids": [(3, self.env.ref("pan_ai_pro.group_user").id)]})
        self.assertFalse(self.agent.may_use(self.eve))
        convert_file(self.env, "pan_ai_pro", "security/groups.xml", {}, mode="update")
        self.env.invalidate_all()
        self.assertTrue(self.agent.may_use(self.eve))

    def test_a_user_sees_their_own_threads_and_runs(self):
        Thread = self.env["pan_ai.thread"].with_user(self.user)
        self.assertEqual(Thread.search([]), self.sams.with_user(self.user))
        with self.assertRaises(AccessError):
            self.eves.with_user(self.user).read(["name"])
        Run = self.env["pan_ai.run"].with_user(self.user)
        self.assertEqual(Run.search([]), self.sam_run.with_user(self.user))
        with self.assertRaises(AccessError):
            Run.create({"thread_id": self.sams.id, "user_id": self.user.id})

    def test_a_user_reads_but_never_writes_the_configuration(self):
        agent = self.agent.with_user(self.user)
        self.assertTrue(agent.read(["name"]))
        with self.assertRaises(AccessError):
            agent.write({"name": "mine"})
        toolset = self.env.ref("pan_ai_pro.toolset_odoo").with_user(self.user)
        self.assertTrue(toolset.read(["name"]))
        with self.assertRaises(AccessError):
            toolset.write({"name": "mine"})
        tool = self.env.ref("pan_ai_pro.tool_search_records").with_user(self.user)
        with self.assertRaises(AccessError):
            tool.write({"description": "mine"})
        with self.assertRaises(AccessError):
            self.env["pan_ai.field.metadata"].with_user(self.user).create(
                {"model_name": "res.partner", "res_id": 1, "field_name": "comment"}
            )

    def test_an_agent_closed_to_the_user_is_not_listed(self):
        closed = (
            self.env["pan_ai.agent"]
            .sudo()
            .create(
                {
                    "name": "Admins only",
                    "group_ids": [(6, 0, [self.env.ref("base.group_system").id])],
                }
            )
        )
        self.assertNotIn(closed.id, self.env["pan_ai.agent"].with_user(self.user).search([]).ids)
        self.assertIn(closed.id, self.env["pan_ai.agent"].with_user(self.manager).search([]).ids)

    def test_a_manager_sees_and_writes_everything_but_the_license(self):
        Thread = self.env["pan_ai.thread"].with_user(self.manager)
        self.assertEqual(
            set(Thread.search([]).ids) & {self.sams.id, self.eves.id}, {self.sams.id, self.eves.id}
        )
        Run = self.env["pan_ai.run"].with_user(self.manager)
        self.assertIn(self.eve_run.id, Run.search([]).ids)
        self.agent.with_user(self.manager).write({"description": "by Mia"})
        self.env.ref("pan_ai_pro.tool_search_records").with_user(self.manager).write(
            {"description": "by Mia"}
        )
        with self.assertRaises(AccessError):
            self.env["pan_ai.license"].with_user(self.manager).search([]).read(["status"])

    def test_a_portal_user_sees_nothing(self):
        for model in (
            "pan_ai.agent",
            "pan_ai.thread",
            "pan_ai.run",
            "pan_ai.toolset",
            "pan_ai.tool",
            "pan_ai.field.metadata",
        ):
            with self.assertRaises(AccessError, msg=model):
                self.env[model].with_user(self.portal).search([]).read(["id"])
                self.env[model].with_user(self.portal).check_access("read")

    def test_the_settings_buttons_are_the_administrators(self):
        Settings = self.env["res.config.settings"].with_user(self.user)
        for method in (
            "action_pan_ai_remove_key",
            "action_pan_ai_delete_threads",
            "action_pan_ai_disconnect",
            "action_pan_ai_connect",
            "action_pan_ai_check",
        ):
            with self.assertRaises(AccessError, msg=method):
                getattr(Settings, method)()
        self.assertTrue(self.sams.exists())

    def test_a_person_never_writes_their_threads_rows(self):
        """The conversation and the pending calls are the runtime's: a person
        who could rewrite them could approve a forged call."""
        mine = self.sams.with_user(self.user)
        with self.assertRaises(AccessError):
            mine.write({"conversation": "[]"})
        with self.assertRaises(AccessError):
            self.env["pan_ai.thread"].with_user(self.user).create(
                {
                    "name": "x",
                    "agent_id": self.agent.id,
                    "user_id": self.user.id,
                    "kind": "continuous",
                }
            )
        # the buttons still work for the owner, and for nobody else
        mine.action_pause()
        self.assertTrue(self.sams.paused)
        mine.action_resume()
        self.assertFalse(self.sams.paused)
        with self.assertRaises(AccessError):
            self.eves.with_user(self.user).action_pause()
