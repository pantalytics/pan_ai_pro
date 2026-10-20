"""Tools run on the caller's env: ACLs hold, an AccessError is the tool's
error to the model, nothing is sudo'ed."""

import asyncio
import re
from pathlib import Path

from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from odoo import api

from ..runtime.deps import OdooDeps
from ..runtime.odoo_toolset import build_toolset
from .common import AiProCase


class TestOdooToolset(AiProCase):
    def _ctx(self, user):
        env = api.Environment(self.env.cr, user.id, {})
        thread = (
            self.env["pan_ai.thread"].sudo().create({"agent_id": self.agent.id, "user_id": user.id})
        )
        run = self.env["pan_ai.run"].sudo().create({"thread_id": thread.id, "user_id": user.id})
        deps = OdooDeps(env=env, user=user.with_env(env), run=run, thread=thread)
        return RunContext(deps=deps, model=TestModel(), usage=RunUsage()), env

    def _tool(self, toolset, name):
        return next(t for t in toolset.tools.values() if t.name == name)

    def _call(self, tool, ctx, **args):
        return asyncio.run(tool.function(ctx, **args))

    def test_search_runs_as_the_user_and_respects_rights(self):
        toolset = build_toolset(self.env.ref("pan_ai_pro.toolset_odoo"), self.env)
        ctx, _env = self._ctx(self.user)
        search = self._tool(toolset, "search_records")
        out = self._call(
            search,
            ctx,
            model="res.partner",
            domain=[["id", "=", self.user.partner_id.id]],
            fields=["name"],
        )
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["records"][0]["name"], "Sam")
        # ir.cron is for system users only: the error goes back to the model, no exception
        out = self._call(search, ctx, model="ir.cron", domain=[], fields=["name"])
        self.assertIn("error", out)

    def test_a_missing_model_is_the_tools_error(self):
        toolset = build_toolset(self.env.ref("pan_ai_pro.toolset_odoo"), self.env)
        ctx, _env = self._ctx(self.user)
        out = self._call(self._tool(toolset, "describe_model"), ctx, model="no.such.model")
        self.assertIn("no model", out["error"])

    def test_write_tools_ask_for_approval(self):
        toolset = build_toolset(self.env.ref("pan_ai_pro.toolset_odoo"), self.env)
        self.assertTrue(self._tool(toolset, "create_record").requires_approval)
        self.assertTrue(self._tool(toolset, "write_record").requires_approval)
        self.assertFalse(self._tool(toolset, "search_records").requires_approval)

    def test_model_restriction_on_a_tool(self):
        tool = self.env.ref("pan_ai_pro.tool_search_records")
        tool.model_ids = [(6, 0, [self.env["ir.model"]._get_id("res.users")])]
        toolset = build_toolset(self.env.ref("pan_ai_pro.toolset_odoo"), self.env)
        ctx, _env = self._ctx(self.user)
        out = self._call(
            self._tool(toolset, "search_records"),
            ctx,
            model="res.partner",
            domain=[],
            fields=["name"],
        )
        self.assertIn("may only touch", out["error"])

    def test_open_record_is_a_ui_action(self):
        toolset = build_toolset(self.env.ref("pan_ai_pro.toolset_odoo"), self.env)
        ctx, _env = self._ctx(self.user)
        out = self._call(
            self._tool(toolset, "open_record"), ctx, model="res.partner", id=self.user.partner_id.id
        )
        self.assertEqual(out["opened"]["id"], self.user.partner_id.id)
        self.assertEqual(ctx.deps.ui_actions[0]["model"], "res.partner")

    def test_the_tools_never_sudo_or_switch_user(self):
        """The toolset, the deps and the agent builder reach the ORM only
        through the run user's env. Only the slice loop may touch the run
        row as superuser, and nothing else."""
        runtime = Path(__file__).resolve().parent.parent / "runtime"
        for name in ("odoo_toolset.py", "deps.py", "agent.py"):
            # the one sudo the builder may do: read the key from the parameters
            text = (runtime / name).read_text().replace('env["ir.config_parameter"].sudo()', "")
            self.assertIsNone(re.search(r"\.sudo\(|with_user\(|SUPERUSER", text), name)
        for name in ("slices.py", "stream.py"):
            # the slice may post the answer as the run's user, nothing else
            text = (runtime / name).read_text().replace("with_user(run.user_id)", "")
            self.assertIsNone(re.search(r"with_user\(|SUPERUSER", text), name)

    def test_a_server_action_is_a_tool(self):
        self.user.write({"group_ids": [(4, self.env.ref("base.group_partner_manager").id)]})
        action = self.env["ir.actions.server"].create(
            {
                "name": "Double",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "code",
                "code": "action = {'n': env.context['pan_ai_args']['n'] * 2, 'uid': env.uid, 'fields': env.context['pan_ai_args'].get('fields'), 'active_id': env.context.get('active_id')}",
            }
        )
        self.env["pan_ai.tool"].create(
            {
                "name": "double",
                "description": "Double n",
                "source": "server_action",
                "action_id": action.id,
                "toolset_id": self.env.ref("pan_ai_pro.toolset_odoo").id,
                "parameters_json_schema": '{"type":"object","properties":{"n":{"type":"integer"},"fields":{"type":"string"}},"required":["n"]}',
            }
        )
        toolset = build_toolset(self.env.ref("pan_ai_pro.toolset_odoo"), self.env)
        ctx, _env = self._ctx(self.user)
        out = self._call(self._tool(toolset, "double"), ctx, n=21, fields="kept")
        self.assertEqual(
            out["result"], {"n": 42, "uid": self.user.id, "fields": "kept", "active_id": None}
        )
        ctx.deps.record = self.user.partner_id
        out = self._call(self._tool(toolset, "double"), ctx, n=1)
        self.assertEqual(out["result"]["active_id"], self.user.partner_id.id)
