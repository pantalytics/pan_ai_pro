# AI Pro 20: execution plan

Status: proposed 2026-10-19, waiting for Rutger's go. Companion to
[ai-pro-20.md](ai-pro-20.md) (the why) and
[../architecture-20.md](../architecture-20.md) (the shape). This file is the
checklist; tick boxes in commits. Rewritten the same day for the in-Odoo
design with Pydantic AI's vocabulary.

## 0. Ground rules

- Pydantic AI's names everywhere: `Agent`, `Model`, `Toolset`, `Tool`,
  `Run`, `Thread.messages`, `UsageLimits`, `deps`, `output_type`,
  `requires_approval`, `run_stream_events`. A field that has a Pydantic AI
  name gets that name.
- No `sudo` in a tool. No second cursor inside a tool. No fallback: a
  missing key, a refused host, a bad schema is a loud error.
- 500 lines per Python file, ruff, no em dashes, copy through the
  humanizer. The repo's `scripts/checks/` are copied from admin.

## 1. Spikes, one week, nothing else ships before they are done

Each is a directory under `scripts/spikes/<name>/` with a README that exits
non-zero when its claim fails; result and date go into
architecture-20.md.

- [ ] **S1 Enterprise 20 seam.** On a 20 Enterprise staging database
      (Cloudpepper): where `ai_fields` asks for a value, the registry names
      of the native AI systray item and the Ctrl+K command.
- [ ] **S2 Streaming through the bus into a `mail` message.** The `ai`
      channel type on Odoo 20 Community, a patched `Message` that grows
      from `pan_ai.run_event` on the partner channel, commit cadence
      100 ms, first token on screen under 300 ms after the model's first
      byte, Stop mid-run, the final body written once. On Odoo.sh and
      Cloudpepper.
- [ ] **S3 The dependency.** `pydantic-ai-slim[openai,mcp]` on Odoo.sh via
      `requirements.txt` and on Cloudpepper; import inside a worker;
      `asyncio.run` per request; memory per worker before and after.
- [ ] **S4 Slices.** `agent.iter()` stopped at a rounds-and-seconds
      budget, the `Conversation` persisted, resumed on a worker cron woken
      with `ir.cron._trigger()`; a 10-minute chat survives `limit_time_real`
      on both hosts; a killed worker's thread is recovered by the
      heartbeat; a continuous thread ticks for an hour on a watch and
      compacts once. MuK AI's `session_loop.py` and `session_worker.py`
      read first.
- [ ] **S5 Built-in tools.** `WebSearchTool` and `CodeExecutionTool`
      through OpenRouter on Sonnet, GPT and Gemini; the OpenRouter `web`
      plugin as the fallback that works on every model.
- [ ] **S6 MCP Pro as a toolset.** `MCPServerStreamableHTTP` against
      `mcp.pantalytics.com/mcp` with a Zitadel token from the device flow
      (RFC 8628) started in Odoo; the grant enabled on the Zitadel app;
      refresh stored encrypted; `tools/list` filtered by
      `allowed_tool_names`; the SSRF gate on the URL.

## 2. Module (`pan_ai_pro` branch `20.0`), PR A: records, runtime, window

- [ ] branch `20.0` from an empty tree; `19.0` untouched. Manifest
      depends on `web`, `mail`, `base_setup`, `base_automation`; external
      dependency `pydantic_ai`; `requirements.txt` for Odoo.sh
- [ ] `models/agent.py`, `toolset.py`, `tool.py`, `thread.py`, `run.py`
      as architecture-20.md section 2 lists them; `res_config_settings.py`
      (OpenRouter key encrypted with the 19.0 helper, default model,
      retention, allowed MCP hosts)
- [ ] `data/tools.xml`: the built-in `Tools` (search, read, read_group,
      create, write, open menu, compute date), each with its JSON schema
      and `requires_approval` on create and write
- [ ] `runtime/agent.py` `build_agent(record)`; `runtime/deps.py`
      `OdooDeps`; `runtime/odoo_toolset.py` (`FunctionToolset` over
      `deps.env`, server actions with "Use in AI" included by their AI
      schema); `runtime/limits.py`; `runtime/stream.py` (events to JSON
      lines, the approval interrupt, cancel)
- [ ] `runtime/slices.py`: the loop on `agent.iter()` with the slice
      budget, persist `thread.conversation`, resume; `runtime/stream.py`
      batches events to the bus; `models/run.py` with `kind`, slices,
      worker claim and heartbeat; approval resume with
      `deferred_tool_results` from the card's RPC
- [ ] (moved to PR E) scheduled, triggered and continuous runs
- [ ] `models/discuss_channel.py`: channel type `ai`, one channel per
      (user, agent), the agent's partner, `message_post` starts the run;
      `static/src/chat/`: patches on `mail`'s `Message` (streaming body,
      `ToolRow`, `ApprovalCard`), `Composer` (Stop, the "+" actions through
      `mail.composer/actions`), `ChatWindow` header (New chat, agent
      picker); `Systray` icon and Ctrl+K "Ask AI"; `run_events.js` (the bus
      handler); `markdown.js` (no HTML pass-through, links `rel=noopener`)
- [ ] Settings > AI Pro: Model (key: Connected / No key, Replace, Remove;
      default model), Limits (runs per user per hour, retention), Danger
      zone (delete all threads). Agents, Toolsets, Tools as list views under
      a Configuration menu
- [ ] `models/pan_ai_license.py`: Mail Pro's client with the paths
      swapped (`/api/v1/ai-pro/link/*`, `/api/v1/ai-pro/heartbeat`),
      pinned Ed25519 public key, 14-day grace. **Required to run:** every
      run start checks the cached entitlement; not connected or revoked
      refuses with "Connect to Pantalytics in Settings". Settings > AI Pro
      gets the Connection row first: Not connected / Connected, Connect to
      Pantalytics, Disconnect
- [ ] On Enterprise 20: remove the native AI systray item and command (S1)
- [ ] retention cron: threads older than the setting, runs kept
- [ ] tests (Odoo `TransactionCase`): `test_agent_build.py` (record to
      `Agent`), `test_odoo_toolset.py` (ACL respected, AccessError
      returned as tool error, no sudo), `test_run_stream.py` (fake model:
      text, tool call, interrupt, resume, cancel, a second slice),
      `test_channel.py` (portal user cannot post on an `ai` channel,
      groups), `test_retention.py`; one Odoo tour: open, send, stream,
      approve, stop

## 2a. Module, PR E: scheduled, triggered and continuous runs

- [ ] server action "Run agent" (agent, prompt with record context, post
      the answer to, create an activity): automation rules and scheduled
      actions call it; `Run.kind` = `triggered` or `scheduled`, `user` =
      the rule's or action's user, never the superuser
- [ ] two worker crons (`data/ir_cron.xml`), `_trigger()`-woken, an
      advisory lock per thread, heartbeat, stale recovery, one run per
      thread at a time
- [ ] continuous threads: `continuous`, the watch (model, domain, cursor,
      interval), the per-tick prompt ("since your last tick: N records
      changed, here they are"), Pause and Stop on the thread's form, a
      history processor that compacts past a token budget
- [ ] the Runs list view: kind, agent, user, status, cost, duration; a
      thread's form shows its runs
- [ ] tests: a scheduled run posts its answer, a triggered run gets the
      record, a continuous thread ticks twice and compacts, a paused thread
      does not tick, two workers never share a thread

## 3. Module, PR B: AI fields

- [ ] Enterprise: route `ai_fields` to the field's `Agent` through the seam
      S1 found; the 19.0 metadata model, cron, Studio panel and widget
      ported as they are
- [ ] Community: property fields gain an AI type (prompt, `/field`
      references, output type), same metadata, same widget
- [ ] `runtime/field.py`: one `agent.run` with `output_type` = the field's
      schema, no toolsets unless the field says so, 60 s
- [ ] tests with a fake model, both editions' paths

## 4. Module, PR C: MCP toolsets and the Pantalytics sign-in

- [ ] `runtime/mcp_toolset.py`: `MCPServerStreamableHTTP(url, headers)`
      per `pan_ai.toolset` of kind `mcp`, `FilteredToolset` on
      `allowed_tool_names`, `tool_prefix`, `requires_approval` per tool;
      the SSRF gate (copied from the public server) on every URL, plus the
      allowed hosts setting
- [ ] auth `bearer`: a token per toolset, encrypted. Auth `pantalytics`: a
      token per Odoo user, Zitadel device flow from the toolset row
      ("Sign in to Pantalytics", code shown, polled), refresh encrypted,
      Revoke on the same row (S6)
- [ ] the window's tool rows show the server's name for MCP tools
- [ ] tests: a local MCP server in the test (the public `mcp` package),
      filter, prefix, refused host, token refresh

## 5. Platform (admin), PR D: Mail Pro's door for AI Pro

- [ ] `apps/__init__.py`: `AI_PRO = "ai_pro"`, in `PAIRED`, `APP_NAMES`,
      `RETURN_PATHS`
- [ ] `apps/ai_pro.py`: `register_link_routes` on `/api/v1/ai-pro/link`;
      heartbeat `/api/v1/ai-pro/heartbeat` through `door.admit` with its own
      request model (db uuid, module and Odoo version, edition, agents
      count, runs in 24 h, errors `[{code, count}]`; nothing that can carry
      a prompt, a record or a thread title); entitlement with `plan`,
      `latest_version`, `message`, same signing key
- [ ] the module's client is in PR A (required to run); here the server
      side, so PR D lands on staging before PR A's gate
- [ ] instance page: the app tile shows Connected / Not connected and
      Disconnect
- [ ] tests: `test_ai_pro_door.py`, `test_db_ai_pro.py` (integration)

## 6. CI/CD

### pan_ai_pro (none today, add)

- [ ] `.github/workflows/ci.yml`: ruff format and check; `no_em_dash`,
      `loc_budget` (scripts copied from admin); Odoo 20 install and tests in
      Docker (`odoo:20` image, `postgres:16` service, `pip install -r
      requirements.txt`, `odoo -i pan_ai_pro --test-enable
      --stop-after-init`) on Community; the tour runs there
- [ ] `.github/workflows/browser.yml`: Playwright drives the dockerised
      Odoo against `scripts/browser/fake_openrouter.py` (an OpenAI-compatible
      stub that streams text and one tool call), `fake_platform.py` (start,
      poll, a signed entitlement with a test key) and a local MCP stub;
      screenshots at desktop and 390 px as the artifact, Mail Pro's
      `check_flow.py` as the shape
- [ ] `.github/workflows/gitleaks.yml`, copied from admin
- [ ] `.github/workflows/release.yml`: a tag `20.0.x.y.z` builds the zip and
      a GitHub release; the store listing is uploaded by hand
- [ ] branch protection on `20.0`: CI and browser green required, no force
      push; Dependabot for the Actions, Playwright and `pydantic-ai-slim`
- [ ] `requirements.txt` pinned; a CI step installs exactly it

### admin (exists, extend)

- [ ] `ci.yml`: the new tests join by glob; `loc_budget` holds; gitleaks
      unchanged; staging then prod through the existing chain
- [ ] `tests/e2e/test_ai_pro_pairing.py` against staging: pair a stub
      Odoo, heartbeat, signed entitlement verifies

### The contract between the two

- [ ] `pan_ai_pro/docs/protocol.md`: the pairing paths, the heartbeat
      body, the entitlement fields, the public key. Fixtures in
      `contract/*.json` in the module repo, pinned by commit in admin's
      `tests/fixtures/ai_pro/`; a field added on one side without the
      fixture fails the other side's CI

## 7. Security checklist, every PR

Run the `security-review` skill on each PR; these are the items it must
find answered.

**Rights**
- [ ] every tool runs on `deps.env`, the caller's; no `sudo`, no
      `with_user`; a test greps the runtime for both
- [ ] `AccessError` inside a tool is the tool's error to the model, never
      caught into a wider path; the restricted-user test (a sales user sees
      only his orders) is a `TransactionCase`
- [ ] create and write tools carry `requires_approval`; the resume is
      validated against the pending `tool_call_id` on the thread, never
      trusted from the client; Skip is recorded
- [ ] the controller admits internal users only, with CSRF; portal and
      public users get 403; the agent's groups are checked per run
- [ ] triggered runs (automation rules) run as the rule's user, never as
      the superuser; a rule saved by a non-administrator cannot pick an
      agent above its groups

**Secrets at rest**
- [ ] OpenRouter key: encrypted with the 19.0 helper, system group only,
      shown as last four, never logged, never in a bus message
- [ ] MCP bearer tokens and Zitadel refresh tokens: same helper, deleted
      on toolset delete, on user deactivation, on Revoke
- [ ] the Ed25519 public key in the module is the one
      `signing.public_key_b64()` prints on prod; the release checklist
      checks it

**Input**
- [ ] tool results and record content are data: the agent's base
      instructions say so; an injection test case in `test_run_stream.py`
      (a record whose text says "ignore your rules")
- [ ] prompt size capped (16 kB), thread length capped, `output_type`
      schemas validated before a run; one 400 shape for every bad body
- [ ] the markdown renderer escapes HTML; no `innerHTML` of model output;
      links `rel="noopener noreferrer"`; record cards built from ids, not
      from model text

**Network**
- [ ] every MCP URL passes `_is_unreachable_host` and the allowed hosts
      setting before any connection; redirects not followed
- [ ] OpenRouter is the only model host; the base URL is a constant
- [ ] no route of our own streams anything; the bus and `mail`'s own
      controllers carry it, same-origin as always

**Limits**
- [ ] `UsageLimits` per agent (requests, tokens, time) enforced by
      Pydantic AI; runs per user per hour and one live run per user
      enforced by the controller; both refusals have one shape
- [ ] a slice cannot outlive `limit_time_real` or `limit_time_real_cron`:
      the slice budget is read from the config at runtime and capped
      below it, as MuK does; a run past its total budget stops with an
      error the thread shows
- [ ] continuous threads: a watch domain is validated against the
      model's ACL for the thread's user; a tick that finds nothing makes
      no model call; a thread whose user is deactivated is paused

**Supply chain**
- [ ] `requirements.txt` pinned, Dependabot on it; gitleaks on both repos;
      Actions pinned to major versions

**Privacy**
- [ ] heartbeat and telemetry carry counts, tool names, outcomes and
      cost; never a prompt, a record, a thread title or a user's name (the
      request model is the boundary, as Mail Pro's)
- [ ] threads deleted by the retention cron; "Delete all threads" in the
      danger zone; the privacy page lists AI Pro

**Operations**
- [ ] a stuck run is visible in `pan_ai.run` with `status = running` past
      its limit and a cron marks it failed
- [ ] kill switch: Remove the key stops every new run at once

## 8. Order and gates

| Step | Gate to pass |
|---|---|
| Spikes S1 to S6 | results dated in architecture-20.md |
| PR D (platform door) | admin CI green, staging walk: pair a stub, heartbeat, entitlement verifies. Lands first: PR A cannot run without it |
| PR A (records, runtime, window) | module CI and browser check green, security checklist, a real Odoo 20 Community on Cloudpepper connected to staging with a real OpenRouter key, the whole chat by hand in Odoo's chat window and in Discuss, screenshots dated in the plan |
| PR E (runs) | CI green, a scheduled run and a triggered run seen by hand, a continuous thread watched for a day on staging |
| PR B (fields) | CI green, Enterprise and Community field each computed once by hand |
| PR C (MCP toolsets) | CI green, `mcp.pantalytics.com/mcp` as a toolset from a real Odoo, one vault tool called by hand |
| Release | tag, store listing, the Ed25519 key check, `20.0` protected |

Each PR is reviewable on its own and leaves production working: without a
connection the module shows "Connect to Pantalytics" and does nothing
else; without a key, "No key".

**Not in this plan:** voice, attachments, a full-page chat, our own
credits, a brain on the platform, Odoo's native `/mcp`, OCA `queue_job`,
SSO into the customer's Odoo.
