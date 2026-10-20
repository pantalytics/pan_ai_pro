# The contract with the Pantalytics platform

Server side: `pantalytics/odoo-mcp-pro-admin`, `mcp_server_odoo_admin/apps/ai_pro.py`
(tests in `tests/test_ai_pro_app.py`). Module side: `pan_ai_pro/models/license.py`
(tests in `pan_ai_pro/tests/test_license.py`). Mail Pro's shape, paths swapped.

## Pairing

| Call | Body | Answer |
|---|---|---|
| `POST /api/v1/ai-pro/link/start` | `db_uuid`, `odoo_url`, `module_version` | `status: started`, `user_code`, `device_token`, `verify_url`, `verify_url_complete`, `expires_at` |
| `POST /api/v1/ai-pro/link/poll` | `device_token` | `status: pending | too_soon | linked (+ key) | expired | collected` |

The person approves on `verify_url_complete`; Back to Odoo lands on
`/ai_pro/pantalytics/return`, which polls once and collects the key. The
panel can also pair directly through `pan_ai.license.accept_key(key)`.

## Heartbeat, once a day

`POST /api/v1/ai-pro/heartbeat`, `Authorization: Bearer <key>`. The body is
the whole list; a field not here is refused (400):

```json
{"db_uuid": "...", "module_version": "2.0.0", "odoo_version": "20.0",
 "edition": "community", "agents": 3, "runs_24h": 41,
 "errors": [{"code": "timeout", "count": 2}]}
```

`module_version` is the manifest's (`2.0.0`); Odoo stores it with its serie
in front (`20.0.2.0.0`) and the module strips that before sending, so the
platform's `latest_version` compares to it. `errors` counts the failed
runs of the last day by `pan_ai.run.error_code`, one of `limit`, `model`,
`timeout`, `build`, `access`, `unresolved`, `stuck`, `other`: never the
run's error text, which can quote a record.

Answers: 200 with the entitlement below; 401 unknown key; 403
`wrong_database` (a copy of the database); 429 `too_soon`.

## Entitlement

```json
{"entitlement": {"version": 1, "app": "ai_pro", "installation_id": 9,
  "db_uuid": "...", "status": "active" | "revoked", "plan": "beta" | "",
  "issued_at": "...", "valid_until": "... +14 days", "latest_version": "",
  "message": ""},
 "signature": "<base64 Ed25519 over the canonical JSON of entitlement>"}
```

Canonical JSON: `sort_keys=True, separators=(",", ":"), ensure_ascii=False`.

The server and the key are constants in `models/platform.py`. A browser check or
CI points the module at a stand-in with `PAN_AI_PRO_SERVER_URL` (https, or
http on this machine only) and `PAN_AI_PRO_PUBLIC_KEY`; both are logged on
every use, so a production server with either set cannot go unnoticed.
Redirects are never followed.
The module stores an answer only when the signature verifies against the
public key it ships (`PUBLIC_KEY` in `models/platform.py`, the same key as Mail Pro
and Self Learning) and `db_uuid` is its own. A run starts only while
`status` is `active`, `plan` is set and `valid_until` is in the future.
