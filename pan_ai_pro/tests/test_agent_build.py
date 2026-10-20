# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
from pydantic_ai import Agent

from ..compat import params
from ..runtime.agent import build_agent, model_for, output_type, usage_limits
from .common import AiProCase


class TestAgentBuild(AiProCase):
    def test_a_record_becomes_an_agent(self):
        self.fake(["hi"])
        agent = build_agent(self.agent, self.env)
        self.assertIsInstance(agent, Agent)
        self.assertEqual(agent.name, self.agent.name)
        limits = usage_limits(self.agent)
        self.assertEqual(limits.request_limit, self.agent.request_limit)
        self.assertEqual(limits.total_tokens_limit, self.agent.total_tokens_limit)

    def test_no_key_is_a_loud_refusal(self):
        params(self.env).set_str("pan_ai.openrouter_key", "")
        with self.assertRaises(Exception) as caught:
            build_agent(self.agent, self.env)
        self.assertIn("OpenRouter key", str(caught.exception))

    def test_output_type_is_a_schema_or_text_plus_approvals(self):
        kinds = output_type(self.agent)
        self.assertEqual(kinds[0], str)
        self.agent.output_type = '{"type": "object", "properties": {"n": {"type": "integer"}}}'
        kinds = output_type(self.agent)
        self.assertEqual(len(kinds), 2)

    def test_a_bad_output_schema_is_refused_on_the_record(self):
        from odoo.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self.agent.output_type = '{"type": "string"}'

    def test_run_as_a_dedicated_user_needs_one(self):
        import psycopg2

        from odoo.tools import mute_logger

        with (
            mute_logger("odoo.sql_db"),
            self.assertRaises(psycopg2.errors.CheckViolation),
            self.env.cr.savepoint(),
        ):
            self.agent.write({"run_as": "user", "user_id": False})
            self.env.cr.flush()
        self.agent.write({"run_as": "user", "user_id": self.user.id})
        self.assertEqual(self.agent.run_user(self.env.user), self.user)
        self.agent.write({"run_as": "caller", "user_id": False})
        self.assertEqual(self.agent.run_user(self.user), self.user)

    def test_who_may_use_it(self):
        self.assertTrue(self.agent.may_use(self.user))
        self.agent.group_ids = [(6, 0, [self.env.ref("base.group_system").id])]
        self.assertFalse(self.agent.may_use(self.user))
        self.assertTrue(self.agent.may_use(self.env.ref("base.user_admin")))

    def test_the_model_is_the_agents_own(self):
        """Pydantic AI's model is an argument of the Agent: no default from
        Settings, a parameter that says otherwise is not read."""
        gpt = self.env.ref("pan_ai_pro.model_gpt")
        self.agent.model_id = gpt
        params(self.env).set_str("pan_ai.default_model", "someone/else")
        self.assertEqual(model_for(self.agent, self.env).model_name, gpt.model_name)

    def test_a_new_agent_starts_on_the_first_model(self):
        agent = self.env["pan_ai.agent"].create({"name": "New"})
        self.assertEqual(agent.model_id, self.env["pan_ai.model"].first())

    def test_a_model_in_use_cannot_be_deleted(self):
        import psycopg2

        from odoo.exceptions import UserError
        from odoo.tools import mute_logger

        with (
            mute_logger("odoo.sql_db"),
            self.assertRaises((UserError, psycopg2.IntegrityError)),
            self.env.cr.savepoint(),
        ):
            self.agent.model_id.unlink()
            self.env.cr.flush()
