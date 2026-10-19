"""Shared fixtures: a connected license, a key, a fake model."""

import asyncio
import json
from datetime import timedelta

from pydantic_ai.messages import ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from odoo import fields
from odoo.tests import TransactionCase

from ..runtime import agent as agent_runtime


class FakeModel:
    """A FunctionModel scripted per test: `script` is a list of turns; each
    turn is either a string (streamed as text) or a list of (tool, args)
    calls. The model walks the script one turn per request."""

    def __init__(self, script):
        self.script = script
        self.requests = 0

    def build(self):
        async def stream_fn(messages, info):
            self.requests += 1
            # how many tool returns since the last user prompt decides the turn
            turn = 0
            for m in messages:
                for p in getattr(m, "parts", []):
                    if isinstance(p, UserPromptPart):
                        turn = 0
                    elif isinstance(p, ToolReturnPart):
                        turn += 1
            step = self.script[min(turn, len(self.script) - 1)]
            await asyncio.sleep(0)
            if isinstance(step, str):
                for tok in step.split(" "):
                    yield tok + " "
                return
            yield {
                i: DeltaToolCall(
                    name=name, json_args=json.dumps(args), tool_call_id=f"call_{turn}_{i}"
                )
                for i, (name, args) in enumerate(step)
            }

        return FunctionModel(stream_function=stream_fn)


class AiProCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str("pan_ai.openrouter_key", "sk-or-test")
        cls.license = (
            cls.env["pan_ai.license"]
            .sudo()
            .create(
                {
                    "status": "active",
                    "key": "mp_test",
                    "plan": "beta",
                    "valid_until": fields.Datetime.now() + timedelta(days=7),
                }
            )
        )
        cls.agent = cls.env.ref("pan_ai_pro.agent_assistant")
        cls.user = cls.env["res.users"].create(
            {
                "name": "Sam",
                "login": "sam",
                "email": "sam@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def fake(self, script):
        agent_runtime.TEST_MODEL = FakeModel(script).build()
        self.addCleanup(setattr, agent_runtime, "TEST_MODEL", None)

    def chat(self, user=None, text="hello"):
        """Open a chat as `user`, post `text`, return (channel, thread)."""
        user = user or self.user
        Channel = self.env["discuss.channel"].with_user(user)
        channel = Channel.pan_ai_chat(self.agent.id)
        channel.message_post(body=text, message_type="comment", subtype_xmlid="mail.mt_comment")
        thread = channel.sudo().pan_ai_thread_ids[:1]
        return channel, thread
