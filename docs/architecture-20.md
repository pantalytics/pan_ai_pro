# AI Pro 20: architecture

The architecture of the module: one module on Odoo 19 and 20, released as
2.0.0 on 2026-10-19. The 1.6.x client it replaced lives on the `19.0-legacy`
branch. The plan and the spikes are in [plans/ai-pro-20.md](plans/ai-pro-20.md);
this file is what we agree on and build against. Change it in a PR, one
decision per commit.

Status: built and released; what is still open is in
[plans/ai-pro-20-execution.md](plans/ai-pro-20-execution.md).

## 1. One sentence

Pydantic AI runs inside Odoo; its objects are Odoo records with Pydantic
AI's names; tools run through `env` as the person who asked; the chat is
Odoo's own chat window on an `ai` channel, fed by the run's own events over
the bus; a run starts from a chat, a schedule, a trigger or a continuous
thread, in slices on Odoo's workers; the one sign-in is Connect to
Pantalytics, Mail Pro's pairing, and MCP Pro is a different product.

## 2. The objects

Pydantic AI's names, one record each. The Python that builds the `Agent`
from the record is a dozen lines, and the form view reads like the docs.

| Record | Pydantic AI | Fields |
|---|---|---|
| `pan_ai.agent` | `Agent` | name, `model` (OpenRouter id), `instructions` (markdown), `toolset_ids`, `output_type` (JSON schema, optional), `model_settings` (temperature, max tokens, reasoning), `usage_limits` (request limit, token limit, time limit), `web_search` (on, max uses), `run_as` (the caller or a dedicated user), who may use it (groups) |
| `pan_ai.toolset` | `Toolset` | kind: `odoo` (function tools) or `mcp`; for `odoo`: the `tool_ids`; for `mcp`: url, auth (none, bearer), `allowed_tool_names`, `tool_prefix`; `requires_approval` default for its tools |
| `pan_ai.tool` | `Tool` | name, description, `parameters_json_schema`; source: a server action with "Use in AI" (parameters from its AI schema), or a built-in (search, read, read_group, create, write, open menu, compute date); `requires_approval` |
| `pan_ai.thread` | `Conversation` | user, agent, record context, `conversation` (`ConversationTypeAdapter` JSON: messages, usage across runs, `deferred_tool_requests`), the `discuss.channel` it shows in (chat kind), `continuous` with its watch (model, domain, cursor, interval), paused, last activity |
| `pan_ai.run` | `agent.run` / `agent.iter()` | thread, user, `kind` (chat, scheduled, triggered, continuous), status (running, ok, cancelled, failed, interrupted), slices, `requests`, `input_tokens`, `output_tokens`, `cost` (OpenRouter reports it), started, finished, error, worker claim and heartbeat |
| settings | `Model` provider | OpenRouter key (an `ir.config_parameter` readable by Settings administrators only, never shown back; plain, decision 16), default model, retention days, allowed MCP hosts |

Triggers stay Odoo's: an automation rule or a scheduled action whose server
action is "Run agent" with a prompt. We add nothing of our own there.

## 3. The boxes

```
┌──────────────────────────── browser ────────────────────────────┐
│  Odoo web client (OWL)                                           │
│  ┌──────────────────────────┐   ┌──────────────────────────┐     │
│  │ mail chat window         │   │ AI field widget          │     │
│  │ on an `ai` channel,      │   │ wand / stale / spinner   │     │
│  │ patched Message/Composer │   │                          │     │
│  │ systray, Ctrl+K          │   │                          │     │
│  └──────┬─────────▲─────────┘   └───────────┬──────────────┘     │
└─────────┼─────────┼─────────────────────────┼────────────────────┘
   (1) message_post │ bus: pan_ai.run_event   (6) JSON-RPC get_ai_field_value
          ▼         │                                     ▼
┌──────────────────────────── Odoo server ────────────────────────┐
│  pan_ai_pro                                                      │
│   models/discuss_channel  the `ai` channel type, the agent partner│
│   runtime/slices.py       agent.iter() to a budget, persist, resume
│   runtime/agent.py        build_agent(record) -> pydantic_ai.Agent│
│   runtime/deps.py         OdooDeps(env, user, record, thread)    │
│   runtime/odoo_toolset    FunctionToolset over env (ACLs apply)  │
│   runtime/mcp_toolset     MCPToolset over HTTP, bearer, host gate │
│   runtime/stream.py       run events -> batched bus events       │
│   data/ir_cron.xml        two worker crons, woken by _trigger()  │
│   models/                 the records; AI field metadata         │
│   models/license.py       pairing, heartbeat, entitlement        │
└───────┬──────────────────────┬──────────────────────┬────────────┘
   (2) ORM                (3) OpenRouter          (4) MCP servers
   as the user            key from Settings       any server, bearer token
                          + web plugin            on the row; never MCP Pro
                                                       │
                          (5) heartbeat daily ──► platform apps/ai_pro.py
                              counts only          signed entitlement back
```

| Box | Owns | Never does |
|---|---|---|
| Window | the patches on `mail`'s components, the bus handler, markdown, tool rows, approval cards | hold a key, talk to a model, keep state the thread does not have |
| Runtime | building the `Agent`, the slice loop, streaming, limits, cost, the worker crons | `sudo` or `with_user` inside a tool (the run row's bookkeeping is sudo; the record is touched as the run user), a second cursor per tool, a path outside `env`, a thread of its own |
| Odoo toolset | the built-ins and the server actions, as the user | widen rights, swallow an AccessError |
| MCP toolset | one remote server per row, its bearer token, its filter | reach a host the SSRF gate refuses; hold a token per user |
| License | pairing, heartbeat, cached signed entitlement | send a prompt, a record or a thread title |
| Platform (`apps/ai_pro.py`) | entitlement, tiers, telemetry counts | see a message |

## 4. One chat turn

```
user types in the ai channel's composer, presses Send
  │
  ├─ 0 ms    message_post: the user's message is in the thread (mail does this)
  │          a placeholder message from the agent follows, body "Thinking"
  ├─ (1)     the runtime starts Run(kind=chat) inline in the same request:
  │          loads thread.conversation, builds the Agent, drives agent.iter()
  │          and batches events every ~100 ms into one pan_ai.run_event
  │          on the channel's bus, then commits:
  │            delta {text}                            ← the message body grows
  │            tool_call {id, name, args}              ← a tool row
  │            tool_result {id, summary}               ← "12 records" on the row
  │            open {model, id or domain}              ← what a tool asked to open
  │            run_finished {status, error, pending}   ← the body is written once
  ├─ (2)     each Odoo tool: env[model].search/read/write as the user
  ├─ (3)     each model call: OpenRouter, the database's key
  ├─ (4)     each MCP tool: the toolset's server, the user's token
  ├─ slice   past the slice budget: conversation persisted, run stays
  │          `running`, a worker cron is woken with ir.cron._trigger(),
  │          the stream continues into the same message from there
  └─ stop    Stop in the composer sets the run cancelled; the loop sees it
             at its next check; the body keeps what came
```

Approval, when a tool has `requires_approval`:

```
the run ends with DeferredToolRequests on thread.conversation
the message shows a card per call: the tool, its arguments, Allow, Skip     run.status = interrupted
Allow or Skip writes deferred_results on the run; the same run continues inline
```

Scheduled, triggered and continuous runs follow the same loop on a worker
cron, without the placeholder. A scheduled or triggered run gets a fresh
thread per execution (per record for a rule); when the record allows it
the answer lands as a note in its chatter and, when asked, as an activity;
a scheduled run without a record keeps its answer on the run. A continuous
thread keeps one thread and its memory, trimmed to the last 60 messages,
and ticks on its watch settings (plan, section 3a). The slice boundary, measured in S4: stop
when the next node is a model request, persist `all_messages()` plus that
node's request, resume with `message_history` and no prompt.

## 5. Identity and rights

```
Odoo session ──► request.env.user ──► OdooDeps.env ──► every Odoo tool
                                                       ACLs, record rules,
                                                       multi-company as is
```

- The AI sees what its identity sees. An agent runs as the person who
  asks, or as a dedicated Odoo user an administrator made for it (`run_as`
  on the agent, decision 15): that user's groups, record rules and roles
  are the agent's reach, and governance's scoped roles apply to it like to
  any user. No `sudo` in a tool, no user with everything. An `AccessError`
  inside a tool is returned to the model as the tool's error, never caught
  into a wider path.
- Who may chat: the groups on the `Agent`. Who may configure agents,
  toolsets, tools and AI fields: the AI Pro Administrator group
  (`pan_ai_pro.group_manager`). Settings, the OpenRouter key and the
  connection to Pantalytics: Settings administrators (`base.group_system`).
- No Odoo user ever signs in to Zitadel from Odoo. The module's one
  sign-in is Connect to Pantalytics, once per database, by a Settings
  administrator, Mail Pro's pairing (decision 14). An MCP toolset holds
  one bearer token per row, readable by administrators only, not per user.
- A deactivated Odoo user loses their threads' access.

## 6. Money and limits

| What | Where | Rule |
|---|---|---|
| Tokens | OpenRouter key in Settings, one per database | no key, no chat; the agent's bubble says "No OpenRouter key. Add one in Settings > AI Pro." |
| Web search | Pydantic AI `WebSearch(native=WebSearchTool(max_uses))` on OpenRouter's server tool (S5: works on Sonnet, GPT, Gemini; 8 to 13k input tokens per question) | on per agent, off by default; `max_uses` on the agent (`search_context_size` not exposed); never on an AI field fill that keeps the tools off |
| Per run | `UsageLimits` on the agent, carried from slice to slice, and the slice loop for the clock | defaults in `defaults.py` and the agent's fields: 25 requests, 200k tokens, 300 s, all across slices; a run past any of them fails with the reason, and a continuous thread that hits one pauses |
| Per user | `pan_ai.run` rows | chats per hour per person, a setting; it counts what a person starts by hand (a chat, a Fill button, the Action menu); a watch's ticks, schedules and the nightly fills are the administrator's and never refused; one live run per thread (a unique index) |
| Per database | the signed entitlement, required | not connected or revoked: no run; the beta is "connected is entitled", as Mail Pro; tiers decided later |

## 7. AI fields

```
any stored field of any model, on both editions        Enterprise 20
   a prompt on ir.model.fields (AI Pro > Configuration     Odoo's own AI-field button and cron
   > AI fields, or Settings > Technical > Fields)          land on `_fill_ai_field` on `base`
          │  Fill now (the cron, in batches), the nightly      │  (the seam S1 found); Odoo's prompt
          │  cron (auto fill empties, auto update stale),      │  becomes the AI Pro prompt
          │  `pan_ai_fill` for a button of your own             │
          ▼                                                     ▼
   the field's Agent (per field, or the first one), output_type = the
   field's schema, no toolsets unless the field says so, 60 s per value
          │
   pan_ai.field.metadata: is_stale, human_edited, last_error (the 19.0
   model, renamed); a value a person typed is left alone; a record that
   failed waits a day before a batch takes it again
```

No streaming here: one `agent.run` per value, as the caller or the agent's
dedicated user, within what that user may read and write. Community has no
widget of its own: the field fills on the schedule, and a form shows the
value like any other.

## 8. Protocols

| Boundary | Protocol | Why this one |
|---|---|---|
| browser ↔ Odoo | `mail`'s message_post in, Pydantic AI run events batched over the bus out | the chat window already listens on the bus; one producer, one consumer, so no third vocabulary |
| Odoo ↔ model | OpenRouter (OpenAI-compatible) through Pydantic AI's provider | one key, any model, web plugin |
| Odoo ↔ MCP servers (later) | MCP Streamable HTTP through Pydantic AI's client, a bearer token per row | the standard; MCP Pro is not one of them |
| Odoo ↔ platform | HTTPS JSON, bearer installation key, Ed25519-signed entitlement | Mail Pro's door, unchanged |
| not used | an SSE route of our own, Odoo's `/mcp`, AG-UI, a platform brain, DBOS | a second channel beside the one the window has; Enterprise-only; a third vocabulary; the configuration lives in two places; its own tables and launch step in the process |

## 9. Open source, and signed in

The whole module is LGPL-3. It runs for a database that is connected to
Pantalytics, exactly as Mail Pro does: Connect to Pantalytics once, a
daily heartbeat, a signed entitlement cached with 14 days of grace. No
live entitlement, no run: the window and the Runs list say "Connect to
Pantalytics in Settings". The OpenRouter key is the customer's own and
stays theirs. What the entitlement gates beyond "connected" is decided
later. The public MCP server stays as it is.

## 10. Decisions

| # | Decision | Instead of | Date |
|---|---|---|---|
| 1 | Pydantic AI inside Odoo | a brain on the platform (first draft, same day) | 2026-10-19 |
| 2 | Records named as Pydantic AI names them | Odoo 20's agent / skills / sources / triggers | 2026-10-19 |
| 3 | Odoo's own `mail` chat window on an `ai` channel, patched for streaming, tool rows and approvals | a window of our own (second draft), MuK AI's client, a web component | 2026-10-19 |
| 4 | Run events batched over the bus into the message | an SSE route of our own (second draft), WebSocket | 2026-10-19, **S2 measured the same day**: first token 50 ms after the server sent it, slowest batch 97 ms, Stop works, final body written once (`scripts/spikes/s2_bus_stream/`) |
| 5 | Identity is the Odoo session; tools through `env` | per-user API keys, members per Odoo user | 2026-10-19 |
| 6 | OpenRouter as the one provider, key per database | provider registry with three request formats (19.0) | 2026-10-19 |
| 7 | ~~MCP Pro as an MCP toolset, Zitadel device flow for the token~~ replaced by 14 | pairing per user, a platform-side identity | 2026-10-19, withdrawn the same day |
| 8 | AI fields metadata ported from 19.0 as is | redesign | 2026-10-19 |
| 9 | Triggers are Odoo's automation rules and scheduled actions | a trigger model of our own | 2026-10-19 |
| 10 | Runs in slices on Odoo's workers, `agent.iter()` plus `ir.cron._trigger()`, MuK AI's loop shape | a daemon, OCA `queue_job`, DBOS durability | 2026-10-19, **S4 measured the same day** on a prefork server: a chat of 5 slices outlives an 8 s HTTP limit, cron wake 122 to 849 ms, a killed worker's thread is reclaimed, a continuous thread keeps its memory (`scripts/spikes/s4_slices/`) |
| 11 | `Thread.conversation` is Pydantic AI's `Conversation` | a message model of our own | 2026-10-19 |
| 12 | Connect to Pantalytics is required to run, as Mail Pro | an optional pairing | 2026-10-19, Rutger |
| 15 | An agent is an identity: `run_as` is the person who asks or a dedicated Odoo user whose groups, record rules and roles (governance's `res.users.role` when installed) are the agent's reach; chosen per agent by an administrator; never `sudo`, never a user with everything | one identity for every run (first draft of decision 5) | 2026-10-19, Rutger: "wie de agent aanstuurt kan een mens zijn of een autonome agent, met andere rechten" |
| 16 | The OpenRouter key sits in `ir.config_parameter`, system group only, never shown back (last four) | "encrypted with the 19.0 helper" (the plan): 19.0 had no such helper | 2026-10-19, found while porting |
| 14 | AI Pro and MCP Pro are two products: AI Pro never calls `mcp.pantalytics.com`, no Zitadel sign-in from Odoo, the only sign-in is Connect to Pantalytics (Mail Pro's pairing); MCP servers in general stay a later, bearer-token toolset | decision 7 | 2026-10-19, Rutger, after S6: Zitadel's device page is its login v1, whose Microsoft callback Azure does not know, and a sign-in per user was never the product (`scripts/spikes/s6_device_flow/`) |
| 13 | On Enterprise 20, AI fields keep Odoo's widget, cron and Studio panel; we inherit `_fill_ai_field` on `base` and remove `ai.systray_action`, `ask_ai` and `chat_with_agent` from the registries | replacing `ai_fields`, or patching `ai.utils` | 2026-10-19, **S1 measured the same day** on the Enterprise demo: widget and cron both end in `get_ai_field_value` then `_fill_ai_field` then IAP `get_completions_sync`; `ai.agent` has no provider or model field (`scripts/spikes/s1_seam/`) |
| 17 | One module for Odoo 19 and 20, Community and Enterprise, on one branch: a manifest version without the Odoo prefix, `compat.py` for the two APIs that differ (`ir.config_parameter` typed getters, the base-field write guard), the access rows created for whichever access model the server has (`models/access.py`), CI on `odoo:19` and `odoo:20`; `19.0` and `20.0` are mirrors of `main` for the hosts that attach by version | a branch per Odoo version with its own code, the 19.0 clients kept alive beside the rebuild | 2026-10-19, Rutger; S7 measured the breaks the same day (`scripts/spikes/s7_one_module/`) |

The brand's Product UI rules, applied item by item: [brand.md](brand.md).

## 11. Open

- Spike results (plan, section 6) may move boxes; each result lands here.
  S2 done 2026-10-19 (decision 4). One rule from it: latency is measured
  against a real server with Playwright, never in `HttpCase`, whose
  `TestCursor` defers the bus to the end of the request.
  S6 withdrawn 2026-10-19 (decision 14): the device flow itself worked
  up to the login page; the product did not want it.
  S1 done 2026-10-19 (decision 13). One thing it showed beyond its
  claim: Odoo 20's `ai.session` is itself a slice loop (`loop_state`,
  `request_round`, `resume_token`, `pending_tool_call`), the same shape
  as decision 10.
  S4 done 2026-10-19 (decision 10). Rules from it: the slice boundary is
  before the next model request and carries `node.request`; the cron slice
  budget is the host's `limit_time_real_cron` minus a margin, and that
  limit cannot sit below about 70 s; a cron wake runs every claimable
  slice, not one; writes after a slice need a claim fence; continuous
  ticks have a `next_tick_at` and no interval under a minute.
- Tiers in the entitlement: what Free gets. After the beta.
