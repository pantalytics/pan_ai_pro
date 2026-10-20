# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""A stand-in for mcp.pantalytics.com, for a browser check and CI: the
pairing (start, poll: approved at once) and the AI Pro heartbeat, answered
with an entitlement signed by a key made at start.

    python fake_platform.py 8090 /tmp/fake_platform_public_key

Writes the public key (base64) to the file, so the Odoo under test can be
started with PAN_AI_PRO_SERVER_URL=http://127.0.0.1:8090 and
PAN_AI_PRO_PUBLIC_KEY=<that key>. Nothing here is the real contract; the
real one is admin's apps/ai_pro.py and tests/test_ai_pro_app.py.
"""

import base64
import json
import sys
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
KEY_FILE = sys.argv[2] if len(sys.argv) > 2 else "/tmp/fake_platform_public_key"

PRIVATE = Ed25519PrivateKey.generate()
PUBLIC_B64 = base64.b64encode(
    PRIVATE.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
).decode()
INSTALL_KEY = "mp_fake_" + "a" * 40
STATE = {"revoked": False, "heartbeats": []}


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def iso(dt):
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/v1/ai-pro/link/start":
            now = datetime.now(UTC)
            return self._json(
                200,
                {
                    "status": "started",
                    "user_code": "FAKE-CODE",
                    "device_token": "tok",
                    "verify_url": f"http://127.0.0.1:{PORT}/admin/link",
                    "verify_url_complete": f"http://127.0.0.1:{PORT}/admin/link?code=FAKE-CODE",
                    "expires_at": iso(now + timedelta(minutes=15)),
                },
            )
        if self.path == "/api/v1/ai-pro/link/poll":
            return self._json(200, {"status": "linked", "key": INSTALL_KEY})
        if self.path == "/api/v1/ai-pro/heartbeat":
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {INSTALL_KEY}":
                return self._json(401, {"status": "invalid"})
            STATE["heartbeats"].append(body)
            now = datetime.now(UTC)
            payload = {
                "version": 1,
                "app": "ai_pro",
                "installation_id": 1,
                "db_uuid": body.get("db_uuid", ""),
                "status": "revoked" if STATE["revoked"] else "active",
                "plan": "" if STATE["revoked"] else "beta",
                "issued_at": iso(now),
                "valid_until": iso(now + timedelta(days=14)),
                "latest_version": "",
                "message": "",
            }
            signature = base64.b64encode(PRIVATE.sign(canonical(payload))).decode()
            return self._json(200, {"entitlement": payload, "signature": signature})
        if self.path == "/_revoke":
            STATE["revoked"] = True
            return self._json(200, {"ok": True})
        return self._json(404, {"status": "not_found"})

    def do_GET(self):
        if self.path == "/_state":
            return self._json(200, STATE)
        self._json(200, {"public_key": PUBLIC_B64})


if __name__ == "__main__":
    with open(KEY_FILE, "w") as f:
        f.write(PUBLIC_B64)
    print(f"fake platform on :{PORT}, public key in {KEY_FILE}", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
