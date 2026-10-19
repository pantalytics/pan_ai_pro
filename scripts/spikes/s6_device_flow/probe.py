"""S6: MCP Pro as a toolset from inside Odoo, the token from Zitadel's
device-code grant, with no browser on the server.

    ZITADEL_PAT=... python probe.py https://odoo-mcp-pro-xywtof.eu1.zitadel.cloud

What it does, in the order the module would:
1. (one-off, ours, not the module's) finds the `odoo-mcp-pro` project and
   creates the native public app `pan-ai-pro` with the device-code and
   refresh-token grants, idempotent; prints its client id.
2. asks the device authorization endpoint for a user code and prints the
   URL a person opens, which is what Settings > AI Pro > Connect MCP Pro
   would show.
3. polls the token endpoint at the interval Zitadel gives, until the
   person approved or the code expired.
4. calls MCP Pro's `/mcp` with the token (an `initialize`), which is what
   the toolset does on every run.
5. refreshes the token once, since a thread outlives an access token.

Exit non-zero when any step fails. Never prints a token; writes
result.json beside itself with ids, timings and outcomes only.
"""

import json
import os
import pathlib
import sys
import time

import requests

ISSUER = sys.argv[1].rstrip("/")
PAT = os.environ["ZITADEL_PAT"]
PROJECT_NAME = os.environ.get("PROJECT_NAME", "odoo-mcp-pro")
APP_NAME = os.environ.get("APP_NAME", "pan-ai-pro")
MCP_URL = os.environ.get("MCP_URL", "https://mcp.pantalytics.com/mcp")
HERE = pathlib.Path(__file__).parent
result = {"issuer": ISSUER, "steps": []}


def step(name, **kw):
    kw["step"] = name
    result["steps"].append(kw)
    print(json.dumps(kw), flush=True)
    (HERE / "result.json").write_text(json.dumps(result, indent=1))


def mgmt(method, path, body=None):
    r = requests.request(method, f"{ISSUER}{path}", headers={"Authorization": f"Bearer {PAT}"}, json=body, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"{method} {path}: {r.status_code} {r.text[:300]}")
    return r.json()


# 1. the app
projects = mgmt("POST", "/management/v1/projects/_search", {})["result"]
project_id = next(p["id"] for p in projects if p["name"] == PROJECT_NAME)
apps = mgmt("POST", f"/management/v1/projects/{project_id}/apps/_search", {}).get("result", [])
app = next((a for a in apps if a["name"] == APP_NAME), None)
if app:
    client_id = app["oidcConfig"]["clientId"]
    app_id = app["id"]
    created = False
else:
    created_app = mgmt(
        "POST",
        f"/management/v1/projects/{project_id}/apps/oidc",
        {
            "name": APP_NAME,
            "redirectUris": [],
            "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
            "grantTypes": ["OIDC_GRANT_TYPE_DEVICE_CODE", "OIDC_GRANT_TYPE_REFRESH_TOKEN"],
            "appType": "OIDC_APP_TYPE_NATIVE",
            "authMethodType": "OIDC_AUTH_METHOD_TYPE_NONE",
            "devMode": False,
            "loginVersion": {"loginV1": {}},
        },
    )
    client_id, app_id, created = created_app["clientId"], created_app["appId"], True
step("app", project_id=project_id, app_id=app_id, client_id=client_id, created=created)

# 2. the user code
disc = requests.get(f"{ISSUER}/.well-known/openid-configuration", timeout=30).json()
scope = f"openid profile email offline_access urn:zitadel:iam:org:project:id:{project_id}:aud"
t0 = time.monotonic()
r = requests.post(disc["device_authorization_endpoint"], data={"client_id": client_id, "scope": scope}, timeout=30)
if r.status_code != 200:
    step("device_authorization", ok=False, status=r.status_code, body=r.text[:300])
    sys.exit(1)
da = r.json()
step("device_authorization", ok=True, ms=round((time.monotonic() - t0) * 1000), expires_in=da.get("expires_in"), interval=da.get("interval"), user_code=da["user_code"], verification_uri_complete=da.get("verification_uri_complete") or da["verification_uri"])
print(f"\nOPEN THIS: {da.get('verification_uri_complete') or da['verification_uri']}   code {da['user_code']}\n", flush=True)

# 3. poll
interval = int(da.get("interval", 5))
deadline = time.monotonic() + int(da.get("expires_in", 300))
tokens = None
polls = 0
while time.monotonic() < deadline:
    time.sleep(interval)
    polls += 1
    r = requests.post(disc["token_endpoint"], data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": da["device_code"], "client_id": client_id}, timeout=30)
    body = r.json()
    if r.status_code == 200:
        tokens = body
        break
    err = body.get("error")
    if err == "slow_down":
        interval += 5
    elif err != "authorization_pending":
        step("poll", ok=False, error=err, description=body.get("error_description", "")[:200], polls=polls)
        sys.exit(1)
if not tokens:
    step("poll", ok=False, error="expired", polls=polls)
    sys.exit(1)
step("poll", ok=True, polls=polls, waited_s=round(time.monotonic() - t0, 1), has_refresh=bool(tokens.get("refresh_token")), expires_in=tokens.get("expires_in"), scope=tokens.get("scope"))

# 4. MCP Pro
headers = {"Authorization": f"Bearer {tokens['access_token']}", "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "pan_ai_pro s6", "version": "0"}}}
t1 = time.monotonic()
r = requests.post(MCP_URL, headers=headers, json=init, timeout=60)
text = r.text
server = None
for line in text.splitlines():
    if line.startswith("data:"):
        try:
            server = json.loads(line[5:]).get("result", {}).get("serverInfo")
        except ValueError:
            pass
if r.headers.get("content-type", "").startswith("application/json"):
    server = r.json().get("result", {}).get("serverInfo")
step("mcp_initialize", ok=r.status_code == 200 and server is not None, status=r.status_code, ms=round((time.monotonic() - t1) * 1000), server=server, session=bool(r.headers.get("mcp-session-id")), body=None if server else text[:300])
if r.status_code != 200 or server is None:
    sys.exit(1)

# 5. refresh
r = requests.post(disc["token_endpoint"], data={"grant_type": "refresh_token", "refresh_token": tokens.get("refresh_token", ""), "client_id": client_id, "scope": scope}, timeout=30)
step("refresh", ok=r.status_code == 200, status=r.status_code, error=None if r.status_code == 200 else r.text[:200])
sys.exit(0 if r.status_code == 200 else 1)
