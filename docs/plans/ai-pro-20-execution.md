# AI Pro 20: execution plan

Status: proposed 2026-10-19, waiting for Rutger's go. Companion to
[ai-pro-20.md](ai-pro-20.md) (the why) and
[../architecture-20.md](../architecture-20.md) (the shape). This file is the
checklist; tick boxes in commits.

## 0. The one change to the design: a chat user is a member

AI Pro is compatible with MCP Pro by making the chat **an MCP Pro session**.
An Odoo user who opens the window signs in with Pantalytics once (the same
Zitadel login as everywhere), becomes a member of the workspace the Odoo is
paired to, and chats under their own membership: daily limit, seat tier,
usage log, learning capture, cap-hit upsell, all unchanged. Their Odoo API
key is minted by the module and attached to their connection, so "Add key"
happens without a screen.

This replaces decision 4 in architecture-20.md (per-user key without a
Pantalytics identity). That version needed a shadow user per Odoo uid, which
the data model forbids: membership lives on `workspace_members` and nowhere
else. It also closes the open question on seats: a chatter is a member, on
Free until upgraded.

```
Odoo user, first open of the window
  │  "Sign in with Pantalytics"  (popup to our site, Zitadel)
  │  platform links zitadel_sub <-> (installation, odoo uid), joins them to
  │  the workspace as User when the pairing allows it, stores the Odoo API
  │  key the module minted as their connection on this instance
  ▼
every later open
  window → Odoo /pan_ai/token (session cookie)
  Odoo  → platform /api/v1/ai-pro/token  (installation key, odoo uid)
  platform → a 15 min member token, or `unlinked` → the window shows Sign in
```

## 1. Spikes, one week, nothing else ships before they are done

Each is a directory under `scripts/spikes/<name>/` with a README that exits
non-zero when its claim fails; the result and the date go into
architecture-20.md.

- [ ] **S1 Enterprise 20 seam.** On a 20 Enterprise staging database
      (Cloudpepper): where `ai_fields` asks for a value now, the IAP call,
      the registry name of the native AI systray item and the Ctrl+K
      command. Decides whether Enterprise fields route to us.
- [ ] **S2 SSE from the Odoo backend.** A `main_components` OWL component in
      Odoo 20 Community POSTs to a stub on another origin and reads the
      stream with `fetch`. CORS with credentials off, Odoo's CSP, first paint
      under 100 ms, an interrupt and a resume. The stub emits AG-UI events.
- [ ] **S3 Streaming through the runner.** `AGUIAdapter.dispatch_request`
      around `runner.run` with `agent_runs`, limits, timeout and cost kept;
      `McpToolset` emits `TOOL_CALL_*`; `ag-ui-protocol` >= 0.1.19.
- [ ] **S4 Code execution.** Which of Pydantic AI workspaces, Anthropic's
      server tool through OpenRouter, or neither streams through the adapter
      on Sonnet, GPT and Gemini. Neither: v1 is web search only.
- [ ] **S5 Key minting.** `res.users.apikeys` from a controller without the
      password prompt, scope `rpc`, revoked on Disconnect and on user
      deactivation; a restricted sales user sees only his orders in chat.
- [ ] **S6 Member join from a paired Odoo.** The popup sign-in, the link
      row, auto-join as User, the token mint. Measured against the real
      Zitadel on staging.

## 2. Platform (admin), PR A: door, identity, threads

- [ ] `apps/__init__.py`: `AI_PRO = "ai_pro"`, in `PAIRED`, `APP_NAMES`,
      `RETURN_PATHS`
- [ ] `apps/ai_pro.py`: `LINK_PREFIX = /api/v1/ai-pro/link` through
      `register_link_routes`; heartbeat `/api/v1/ai-pro/heartbeat` through
      `door.admit` with a request model of its own (db uuid, module version,
      Odoo version, edition, users who chatted in 24 h as a count; nothing
      that can carry a prompt or a record)
- [ ] entitlement rides the signed answer: `ai_pro_enabled` (the workspace
      switch), `latest_version`, `message`. Same signing key
- [ ] schema v84: `ai_pro_links (installation_id, odoo_uid, user_id,
      connection_id, linked_at, revoked_at)` unique on (installation,
      odoo_uid); `ai_threads`, `ai_messages` (workspace, user, instance,
      created, last_message_at; 30-day retention in the retention cron);
      `workspaces.ai_pro_enabled` default false; pairing approval gains
      `members_may_join` on `app_installations`
- [ ] `POST /api/v1/ai-pro/token` (installation key bearer): odoo uid in,
      member token out (JWT, 15 min, audience `ai-pro`, claims: sub,
      workspace, installation, connection); `unlinked` when no row
- [ ] `POST /api/v1/ai-pro/keys` (installation key bearer): the module hands
      over a freshly minted Odoo API key for an odoo uid; stored encrypted
      as that member's connection on the instance (`encrypt_api_key`),
      replaced on re-mint, deleted on revoke
- [ ] `GET /admin/ai-pro/connect?install=<one-time code>`: the popup. Login,
      link row, join as User if `members_may_join`, `postMessage` done. Code
      is single-use, 5 min, bound to installation and odoo uid
- [ ] Workspace settings: switch **AI Pro (beta)** through
      `flip_workspace_switch`, off by default; the LLMs section says "AI Pro
      uses this key" when on
- [ ] Instance page: the app tile shows Connected / Not connected, the users
      linked, Disconnect (revokes installation, every link, every minted
      key)
- [ ] tests: `test_ai_pro_door.py`, `test_ai_pro_token.py`,
      `test_ai_pro_links.py` (integration), `test_db_ai_pro.py`

## 3. Platform (admin), PR B: the brain over AG-UI

- [ ] `agents/chat.py`: `POST /api/v1/ai-pro/chat` (member token). One
      request = one run. `AGUIAdapter` with `run_stream_events`, threads
      loaded and saved server-side, client history ignored
- [ ] `agents/chat_tools.py`: `McpToolset(app, sub, connection_id=...,
      writes=<installation flag>)`; every write tool `requires_approval`;
      web search as the OpenRouter `web` plugin; code execution per S4
- [ ] `runner.run` grows a streaming path with the same accounting, limits
      (20 requests, 300k tokens, 10 min) and `agent_runs` row
- [ ] cancel: client closes the stream, the run is cancelled, the row says
      `cancelled`
- [ ] rate limit: 1 live run per member, 60 runs per member per hour, one
      answer shape for every refusal
- [ ] `GET /api/v1/ai-pro/threads`, `GET .../threads/{id}` (member token)
- [ ] CORS: the allowed origin is the instance's URL on file, exact match,
      no wildcard, no credentials; preflight cached 10 min
- [ ] telemetry: `ai_pro_run` with tool names, outcome, duration, tokens,
      cost. Never a prompt, never a record, never a thread title
- [ ] tests: `test_ai_pro_chat.py` with a fake model (text, a tool call, an
      interrupt, a resume, a cancel), `test_ai_pro_cors.py`,
      `test_ai_pro_limits.py`

## 4. Module (`pan_ai_pro` branch `20.0`), PR C: pairing and the window

- [ ] branch `20.0` from an empty tree; `19.0` untouched. Manifest depends
      on `web`, `mail`, `base_setup`; no `ai*`, no pip dependency
- [ ] `models/pan_ai_license.py`: the pairing client, copied from Mail Pro's
      `pan_mail_license.py` with the paths swapped: start, poll, store the
      key (`ir.config_parameter`, system group only), daily heartbeat cron,
      cached entitlement verified against the pinned Ed25519 public key,
      14-day grace, dormant on `revoked` or `ai_pro_enabled: false`
- [ ] `controllers/token.py`: `POST /pan_ai/token` (logged-in internal user,
      CSRF): mints the user's Odoo API key on first call (S5), hands it to
      the platform once, then asks for a member token; returns the token or
      `unlinked` with the one-time connect URL
- [ ] `static/src/chat/`: `ChatWindow` (main_components, bottom-right,
      folds to a bubble), `Systray` icon, Ctrl+K command "Ask AI",
      `agui_stream.js` (the event parser, 16 events), `markdown.js` (a
      small renderer, no HTML pass-through, links `rel=noopener`),
      `approval_card.js`, `tool_row.js`, `thread_list.js`
- [ ] Settings > AI Pro: two rows. Connection: Connected / Not connected,
      Connect to Pantalytics, Disconnect. Permissions: switch "May change
      data", off by default, administrators only
- [ ] On Enterprise 20: remove the native AI systray item and command (S1);
      nothing else of Odoo's AI is touched
- [ ] user deactivation (`res.users` `active` to false): revoke the minted
      key, tell the platform
- [ ] copy through the humanizer; no em dashes; sentence case
- [ ] tests: `tests/test_license.py` (pairing, entitlement verify, grace,
      revoked), `tests/test_token.py` (controller, CSRF, non-internal user
      refused), `tests/test_tour.py` (an Odoo tour: open, send, stream,
      approve, stop)

## 5. Module, PR D: AI fields

- [ ] Enterprise: route `ai_fields` to `/api/v1/ai-pro/field` through the
      seam S1 found; the 19.0 metadata model, cron, Studio panel and widget
      ported as they are
- [ ] Community: property fields gain an AI type (prompt, `/field`
      references, output type), same metadata, same widget
- [ ] platform: `POST /api/v1/ai-pro/field` (member token): one run with
      `output_type` = the field's schema, no tools, web search off unless
      asked, 60 s timeout
- [ ] tests on both sides with a fake platform / fake Odoo

## 6. CI/CD

### admin (exists, extend)

- [ ] `ci.yml`: the new tests join by glob; `loc_budget` holds every new
      file under 500 lines; `env_passthrough` covers `AI_PRO_*` variables
- [ ] `gitleaks.yml` unchanged, it already scans every push
- [ ] `tests/e2e/test_ai_pro_flow.py` against staging: pair a stub Odoo,
      link a member, run one chat with a fake OpenRouter key refused
      cleanly ("No key"); runs in `deploy-staging.yml` before prod
- [ ] staging then prod through the existing chain, nothing new

### pan_ai_pro (none today, add)

- [ ] `.github/workflows/ci.yml`: ruff format and check; `no_em_dash`
      (copied script); Odoo 20 install and tests in Docker (`odoo:20` image,
      `postgres:16` service, `odoo -i pan_ai_pro --test-enable
      --stop-after-init`) on Community; the tour runs there too
- [ ] `.github/workflows/browser.yml`: Playwright drives the dockerised Odoo
      against `scripts/browser/fake_platform.py` (start, poll, token, an
      AG-UI stream with a tool call and an interrupt); screenshots at
      desktop and 390 px as the artifact, like Mail Pro's `check_flow.py`
- [ ] `.github/workflows/gitleaks.yml`, copied
- [ ] `.github/workflows/release.yml`: a tag `20.0.x.y.z` builds the zip and
      a GitHub release; the store listing is uploaded by hand
- [ ] branch protection on `20.0`: CI green required, no force push
- [ ] Dependabot for the Actions and the Playwright pin

### The contract between the two

- [ ] `pan_ai_pro/docs/protocol.md`: every path, body and status code, the
      token claims, the AG-UI subset used, the entitlement fields. The
      admin tests and the module's fake platform both read their fixtures
      from `contract/*.json` in the module repo, pinned by commit in admin's
      `tests/fixtures/ai_pro/`. A field added on one side without the
      fixture fails the other side's CI

## 7. Security checklist, every PR

Run the `security-review` skill on each PR; these are the items it must find
answered.

**Identity and tokens**
- [ ] member token: 15 min, audience `ai-pro`, bound to sub, workspace,
      installation and connection; signed with the platform's session key;
      never in a URL, never logged
- [ ] one-time connect code: 5 min, single use, bound to installation and
      odoo uid, consumed in one transaction
- [ ] installation key: SHA-256 at rest, shown once, `looks_like_key` shape
      check before any query, revoked on Disconnect and uninstall
- [ ] minted Odoo API key: Fernet at rest on the platform, scope `rpc`,
      replaced on re-mint, deleted on revoke and on user deactivation; the
      Odoo module keeps no copy
- [ ] a token minted for one installation cannot run against another
      connection (test), and a db uuid mismatch is refused at the door

**Rights**
- [ ] tools run as the member with that member's key; no sudo, no service
      account; the restricted-user test from S5 is a CI test with a fake Odoo
- [ ] writes only with "May change data" on, and every write tool
      `requires_approval`; the approval is validated server-side against
      the pending call id, not trusted from the client
- [ ] the Odoo controller admits internal users only, with CSRF; portal and
      public users get 403

**Input**
- [ ] tool results are data: the system prompt says so, record content is
      never promoted to instructions; an injection test case in
      `test_ai_pro_chat.py` (a record whose text says "ignore your rules")
- [ ] every request body is a Pydantic model with max lengths; one 400 for
      every bad body; prompt size capped (16 kB) and thread length capped
- [ ] the markdown renderer in the window escapes HTML; no `innerHTML` of
      model output; links `rel="noopener noreferrer"`

**Network**
- [ ] CORS exact origin, no wildcard, no credentials; CSP on the Odoo side
      allows `connect-src` to the platform host only
- [ ] platform → Odoo goes through the existing `_is_unreachable_host`
      gate; the Odoo URL is the instance's on file, never from the request
- [ ] rate limits: pairing starts per address (exists), token mints per
      installation, runs per member; all return the same refusal shape

**Secrets and supply chain**
- [ ] gitleaks on both repos; `env_prod_no_secrets` on admin
- [ ] `ag-ui-protocol`, `pydantic-ai-slim` pinned; Playwright pinned;
      Actions pinned to major versions
- [ ] the Ed25519 public key in the module is the one `signing.public_key_b64()`
      prints on prod, checked in the release checklist

**Privacy**
- [ ] heartbeat and telemetry carry counts, names of tools, outcomes and
      cost; never a prompt, a record, a thread title or a user's name
      (the request model is the boundary, as Mail Pro's)
- [ ] threads deleted after 30 days; Disconnect deletes them at once;
      the privacy page lists AI Pro

**Operations**
- [ ] `/healthz` on the platform reports the AI Pro route; the run timeout
      cannot hold a worker past 10 min; a stuck run is visible in
      `agent_runs`
- [ ] kill switch: the workspace switch off stops every new run within one
      heartbeat; the platform refuses tokens for a switched-off workspace
      at once

## 8. Order and gates

| Step | Gate to pass |
|---|---|
| Spikes S1 to S6 | results dated in architecture-20.md |
| PR A (door, identity) | CI green, security checklist, staging walk: pair a stub, link, token |
| PR B (brain) | CI green, security checklist, staging walk: one chat with tool call and approval from `curl` |
| PR C (module) | module CI green, browser check green, a real Odoo 20 Community on Cloudpepper paired to staging, the whole chat by hand, screenshots dated in the plan |
| PR D (fields) | both CIs green, Enterprise and Community field each computed once by hand |
| Release | tag, store listing, the Ed25519 key check, `20.0` protected |

Each PR is reviewable on its own and leaves production working: a workspace
with the switch off sees nothing.

**Not in this plan:** voice, attachments, a full-page chat, our own credits,
an in-Odoo LLM runtime, Odoo's native `/mcp`, SSO into the customer's Odoo
(that plan comes after pairing proves the member link).
