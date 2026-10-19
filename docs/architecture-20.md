# AI Pro 20: architecture

The working document for the 20.0 rewrite. `ARCHITECTURE.md` in the root
describes 19.0 and stays as is. The plan and the spikes are in
[plans/ai-pro-20.md](plans/ai-pro-20.md); this file is what we agree on and
build against. Change it in a PR, one decision per commit.

Status: draft, 2026-10-19. Nothing below is built.

## 1. One sentence

Pydantic AI runs inside Odoo; its objects are Odoo records with Pydantic
AI's names; tools run through `env` as the person who asked; the window
streams the run's own events; MCP Pro is one toolset among the agent's.

## 2. The objects

Pydantic AI's names, one record each. The Python that builds the `Agent`
from the record is a dozen lines, and the form view reads like the docs.

| Record | Pydantic AI | Fields |
|---|---|---|
| `pan_ai.agent` | `Agent` | name, `model` (OpenRouter id), `instructions` (markdown), `toolset_ids`, `output_type` (JSON schema, optional), `model_settings` (temperature, max tokens, reasoning), `usage_limits` (request limit, token limit, time limit), `builtin_tools` (web search, code execution), who may use it (groups) |
| `pan_ai.toolset` | `Toolset` | kind: `odoo` (function tools) or `mcp`; for `odoo`: the `tool_ids`; for `mcp`: url, auth (none, bearer, Pantalytics sign-in), `allowed_tool_names`, `tool_prefix`; `requires_approval` default for its tools |
| `pan_ai.tool` | `Tool` | name, description, `parameters_json_schema`; source: a server action with "Use in AI" (parameters from its AI schema), or a built-in (search, read, read_group, create, write, open menu, compute date); `requires_approval` |
| `pan_ai.thread` | message history | user, agent, record context, `messages` (`ModelMessagesTypeAdapter` JSON), last activity |
| `pan_ai.run` | `agent.run` | thread, user, status (running, ok, cancelled, failed, interrupted), `requests`, `input_tokens`, `output_tokens`, `cost` (OpenRouter reports it), started, finished, error |
| settings | `Model` provider | OpenRouter key (encrypted), default model, retention days, allowed MCP hosts |

Triggers stay Odoo's: an automation rule or a scheduled action whose server
action is "Run agent" with a prompt. We add nothing of our own there.

## 3. The boxes

```
┌──────────────────────────── browser ────────────────────────────┐
│  Odoo web client (OWL)                                           │
│  ┌──────────────────────────┐   ┌──────────────────────────┐     │
│  │ chat window              │   │ AI field widget          │     │
│  │ systray, Ctrl+K          │   │ wand / stale / spinner   │     │
│  └────────────┬─────────────┘   └───────────┬──────────────┘     │
└───────────────┼─────────────────────────────┼────────────────────┘
       (1) POST /pan_ai/run             (6) JSON-RPC get_ai_field_value
           SSE of run events                      │
                ▼                                 ▼
┌──────────────────────────── Odoo server ────────────────────────┐
│  pan_ai_pro                                                      │
│   controllers/run.py    own cursor, as env.user, streams events  │
│   runtime/agent.py      build_agent(record) -> pydantic_ai.Agent │
│   runtime/deps.py       OdooDeps(env, user, record, thread)      │
│   runtime/odoo_toolset  FunctionToolset over env (ACLs apply)    │
│   runtime/mcp_toolset   MCPServerStreamableHTTP per toolset row  │
│   runtime/stream.py     run_stream_events -> SSE JSON            │
│   models/               the records above; AI field metadata     │
│   pan_ai_license.py     pairing, heartbeat, entitlement (Mail Pro)│
└───────┬──────────────────────┬──────────────────────┬────────────┘
   (2) ORM                (3) OpenRouter          (4) MCP servers
   as the user            key from Settings       mcp.pantalytics.com/mcp
                          + web plugin            (Zitadel device-flow token)
                                                  any other MCP server
                                                       │
                          (5) heartbeat daily ──► platform apps/ai_pro.py
                              counts only          signed entitlement back
```

| Box | Owns | Never does |
|---|---|---|
| Window | rendering, the event parser, approval cards, threads list | hold a key, talk to a model |
| Runtime | building the `Agent`, running it, streaming, limits, cost | `sudo`, a second cursor per tool, a path outside `env` |
| Odoo toolset | the built-ins and the server actions, as the user | widen rights, swallow an AccessError |
| MCP toolset | one remote server per row, its token, its filter | reach a host the SSRF gate refuses |
| License | pairing, heartbeat, cached signed entitlement | send a prompt, a record or a thread title |
| Platform (`apps/ai_pro.py`) | entitlement, tiers, telemetry counts | see a message |

## 4. One chat turn

```
user types, presses Send
  │
  ├─ 0 ms    window appends the message, shows a muted "Thinking" row
  ├─ (1)     POST /pan_ai/run {agent, thread, prompt, record}   (session, CSRF)
  │          controller opens its own cursor, env as request.env.user,
  │          loads thread.messages, builds the Agent, starts
  │          agent.run_stream_events(prompt, message_history=..., deps=OdooDeps)
  │          and yields each event as one SSE line:
  │            run_started {run_id}
  │            part_start / part_delta {text}            ← markdown while it streams
  │            function_tool_call {name, args}           ← "Searching sales orders…"
  │            function_tool_result {name, summary}      ← "12 found", foldable
  │            final_result
  │            run_finished {usage, cost}  |  deferred {approvals: [...]}
  ├─ (2)     each Odoo tool: env[model].search/read/write as the user
  ├─ (3)     each model call: OpenRouter, the database's key
  ├─ (4)     each MCP tool: the toolset's server, the user's token
  └─ stop    window closes the stream; the controller cancels the run and
             writes run.status = cancelled; thread.messages keeps what came
```

Approval, when a tool has `requires_approval`:

```
run_finished {deferred: [{tool_call_id, name, args}]}      run.status = interrupted
window shows a card: the change, Apply, Skip
POST /pan_ai/run {thread, deferred_tool_results: {id: true|false}}
the agent resumes from thread.messages; the stream continues
```

## 5. Identity and rights

```
Odoo session ──► request.env.user ──► OdooDeps.env ──► every Odoo tool
                                                       ACLs, record rules,
                                                       multi-company as is
```

- The AI sees what its person sees. No service account, no `sudo` in a
  tool, no "AI user". An `AccessError` inside a tool is returned to the
  model as the tool's error, never caught into a wider path.
- Who may chat: the groups on the `Agent`. Who may configure: Settings
  administrators (`base.group_system`).
- MCP toolsets with a Pantalytics sign-in hold a token per Odoo user,
  obtained with Zitadel's device flow from Odoo, stored encrypted, revoked
  from the same settings row. The AI on our MCP server then acts as that
  person, the way ADR-0011 wants it.
- A deactivated Odoo user loses their threads' access and their MCP tokens
  are deleted by the same hook.

## 6. Money and limits

| What | Where | Rule |
|---|---|---|
| Tokens | OpenRouter key in Settings, one per database | no key, no chat; the window says "No key, ask your administrator" |
| Web search | OpenRouter `web` plugin, or `WebSearchTool` where S5 proves it | on per agent, off by default |
| Per run | `UsageLimits` on the agent | default 20 requests, 300k tokens, 5 min |
| Per user | `pan_ai.run` rows | runs per hour per user, a setting; one live run per user |
| Per database | the signed entitlement | tiers decided later; the beta is "connected is entitled", as Mail Pro |

## 7. AI fields

```
Enterprise 20 (Studio or property AI field)      Community 20 (property AI field)
   ai_fields asks for a value                        our own property type "AI"
          │ (seam: spike S1)                                │
          ▼                                                 ▼
   the field's Agent (per field, or the default one), output_type = the
   field's schema, no toolsets unless the field says so, 60 s limit
          │
   x_ai.field.metadata: is_stale, human_edited (ported from 19.0 as is)
   auto_fill (cron fills empty), auto_update (recompute on input change)
```

No streaming here: one `agent.run`, one value, a spinner on the field.

## 8. Protocols

| Boundary | Protocol | Why this one |
|---|---|---|
| browser ↔ Odoo | one POST, request-scoped SSE of Pydantic AI run events, cancel = close | MCP's own shape; one producer, one consumer, so no third vocabulary |
| Odoo ↔ model | OpenRouter (OpenAI-compatible) through Pydantic AI's provider | one key, any model, web plugin |
| Odoo ↔ MCP servers | MCP Streamable HTTP through Pydantic AI's client | the standard; MCP Pro is one of them |
| Odoo ↔ platform | HTTPS JSON, bearer installation key, Ed25519-signed entitlement | Mail Pro's door, unchanged |
| not used | Odoo's bus for the stream (fallback only), Odoo's `/mcp`, AG-UI, a platform brain | holds commits per token; Enterprise-only; a third vocabulary; the configuration lives in two places |

## 9. Open source

The whole module is LGPL-3 and runs without Pantalytics: an OpenRouter key
is all it needs. Pairing adds the entitlement and, with it, whatever the
paid tier gates. The public MCP server stays as it is.

## 10. Decisions

| # | Decision | Instead of | Date |
|---|---|---|---|
| 1 | Pydantic AI inside Odoo | a brain on the platform (first draft, same day) | 2026-10-19 |
| 2 | Records named as Pydantic AI names them | Odoo 20's agent / skills / sources / triggers | 2026-10-19 |
| 3 | Our own window, same on both editions | extending Odoo 20's AI chat | 2026-10-19 |
| 4 | SSE from the Odoo controller, the run on its own cursor | the bus with commits per token (19.0), WebSocket | 2026-10-19, pending S2 |
| 5 | Identity is the Odoo session; tools through `env` | per-user API keys, members per Odoo user | 2026-10-19 |
| 6 | OpenRouter as the one provider, key per database | provider registry with three request formats (19.0) | 2026-10-19 |
| 7 | MCP Pro as an MCP toolset, Zitadel device flow for the token | pairing per user, a platform-side identity | 2026-10-19, pending S6 |
| 8 | AI fields metadata ported from 19.0 as is | redesign | 2026-10-19 |
| 9 | Triggers are Odoo's automation rules | a trigger model of our own | 2026-10-19 |

## 11. Open

- Spike results (plan, section 6) may move boxes; each result lands here.
- Tiers in the entitlement: what Free gets. After the beta.
