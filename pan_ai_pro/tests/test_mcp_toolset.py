# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An MCP server as a toolset: the gate on the host, the bearer token, the
filter, a tool call through a real MCP server on a local port."""

import socket
import threading
import time

from odoo.exceptions import UserError

from ..compat import params
from ..runtime import mcp_toolset
from .common import AiProCase

SEEN = {"auth": None}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_server(port):
    """The SDK renamed FastMCP to MCPServer in 2.x and moved the transport settings
    to run(); pydantic-ai's mcp extra may bring either major."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:
        from mcp.server.fastmcp import FastMCP

        server = FastMCP("test", host="127.0.0.1", port=port, streamable_http_path="/mcp")
        return server, lambda: server.run(transport="streamable-http")
    server = MCPServer("test")
    return server, lambda: server.run(
        transport="streamable-http", host="127.0.0.1", port=port, streamable_http_path="/mcp"
    )


def _serve(port):
    server, run = _make_server(port)

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool()
    def secret() -> str:
        """Never allowed."""
        return "no"

    run()


class TestMcpToolset(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.port = _free_port()
        threading.Thread(target=_serve, args=(cls.port,), daemon=True).start()
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"the MCP test server did not start on port {cls.port}")
        params(cls.env).set_str(mcp_toolset.PARAM_ALLOWED_HOSTS, "127.0.0.1")
        params(cls.env).set_bool("pan_ai.mcp_allow_private_hosts", True)
        cls.mcp = cls.env["pan_ai.toolset"].create(
            {
                "name": "Calc",
                "kind": "mcp",
                "url": f"http://127.0.0.1:{cls.port}/mcp",
                "allowed_tool_names": "add",
                "bearer_token": "tok",
            }
        )
        cls.agent.toolset_ids = [(6, 0, [cls.mcp.id])]

    def test_a_host_off_the_list_is_refused_before_any_connection(self):
        params(self.env).set_str(mcp_toolset.PARAM_ALLOWED_HOSTS, "")
        with self.assertRaises(UserError):
            mcp_toolset.check_url(self.env, self.mcp.url)

    def test_a_private_host_needs_the_switch(self):
        params(self.env).set_bool("pan_ai.mcp_allow_private_hosts", False)
        with self.assertRaises(UserError):
            mcp_toolset.check_url(self.env, "http://127.0.0.1:1/mcp")
        self.assertTrue(mcp_toolset.is_private_host("10.1.2.3"))
        self.assertTrue(mcp_toolset.is_private_host("169.254.169.254"))

    def test_a_tool_call_through_the_server_and_the_filter(self):
        self.fake([[("add", {"a": 2, "b": 40})], "It is 42."])
        channel, thread = self.chat(text="2 plus 40?")
        run = thread.run_ids[:1]
        self.assertEqual(run.status, "ok", run.error)
        self.assertIn("42", run.message_id.body)
        returns = [
            p
            for m in thread.messages()
            for p in m.get("parts", [])
            if p.get("part_kind") == "tool-return"
        ]
        self.assertEqual(returns[0]["tool_name"], "add")
        self.assertIn("42", str(returns[0]["content"]))

    def test_a_filtered_out_tool_cannot_be_called(self):
        """The server offers `secret` too; the row allows `add` only, so a
        model that asks for `secret` gets no tool and the run fails."""
        self.fake([[("secret", {})], "done"])
        channel, thread = self.chat(text="tell me the secret")
        run = thread.run_ids[:1]
        self.assertEqual(run.status, "failed")
        # the server's `secret` never ran: no tool return came back from it
        returns = [
            p
            for m in thread.messages()
            for p in m.get("parts", [])
            if p.get("part_kind") == "tool-return" and p.get("tool_name") == "secret"
        ]
        self.assertFalse(returns)
        self.assertNotIn("no", run.text.lower().split())
