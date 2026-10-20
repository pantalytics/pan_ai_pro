"""An MCP server as a toolset: Pydantic AI's `MCPToolset` over HTTP, the
row's bearer token, its tools filtered by name and prefixed. Before any
connection the host passes the gate: it must be on the allowed list in
Settings (`pan_ai.mcp_allowed_hosts`), and a private, loopback or link-local
address is refused unless the config parameter `pan_ai.mcp_allow_private_hosts`
is true (set by hand, for a test or a server on the same network). Redirects
are not followed.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from pydantic_ai.mcp import MCPToolset

from odoo import _
from odoo.exceptions import UserError

from ..compat import params

PARAM_ALLOWED_HOSTS = "pan_ai.mcp_allowed_hosts"


def allowed_hosts(env):
    raw = params(env).get_str(PARAM_ALLOWED_HOSTS, "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def is_private_host(host):
    """True for loopback, link-local, private and metadata addresses, by
    name or by what the name resolves to."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            return True
    return False


def check_url(env, url):
    """The SSRF gate. Raises with the reason; returns the host."""
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("https", "http") or not host:
        raise UserError(_("The MCP server URL must be an http(s) URL with a host."))
    allowed = allowed_hosts(env)
    if host not in allowed:
        raise UserError(_("The MCP host %s is not on the allowed list in Settings > AI Pro.", host))
    if is_private_host(host) and not params(env).get_bool("pan_ai.mcp_allow_private_hosts"):
        raise UserError(_("The MCP host %s is a private address.", host))
    return host


def build_mcp_toolset(toolset_record, env):
    check_url(env, toolset_record.url)
    token = toolset_record.sudo().bearer_token or None
    client = httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"} if token else None,
        follow_redirects=False,
        timeout=30,
    )
    toolset = MCPToolset(
        toolset_record.url,
        id=f"mcp-{toolset_record.id}",
        http_client=client,
        tool_error_behavior="error",
    )
    allowed = toolset_record.allowed_names()
    if allowed:
        toolset = toolset.filtered(lambda ctx, tool: tool.name in allowed)
    if toolset_record.tool_prefix:
        toolset = toolset.prefixed(toolset_record.tool_prefix)
    if toolset_record.requires_approval:
        toolset = toolset.approval_required()
    return toolset
