# Plan: AI Pro for Odoo 20, Pydantic AI inside Odoo

Status: research done 2026-10-19; design flipped the same day (section 1).
Spikes first (section 6). Nothing built.

## 0. What success looks like

The constraints below only make sense against the goal. In order:

1. **The Enterprise AI button, on Community, and better.** A person on
   Odoo Community opens a chat bottom-right that answers from their own
   data, streams while it thinks, shows what it is doing, asks before it
   writes, and can be stopped. Measured: first token on screen under a
   second after the model's first byte; a restricted user never sees a
   record the chat shows that Odoo would not.
2. **A stronger engine than Odoo's, on the customer's own key.** Any model
   through OpenRouter, web search, code execution where the model has it,
   MCP servers as toolsets. No credits, no proxy of ours, no model picked
   for them. Measured: switching model is one field; the bill is on the
   customer's OpenRouter account and nowhere else.
3. **AI fields that stay right.** A field knows when its inputs changed,
   when a person overrode it, and fills itself in the background when
   asked. Measured: the 19.0 metadata behaviour, unchanged, on both
   editions.
4. **Agents that work unattended.** Scheduled, triggered and continuous
   runs with memory, bounded by limits, visible in one Runs list with
   their cost. Measured: a continuous thread ticks for a day on staging
   without a hand on it and stops when paused.
5. **Open source, swappable, signed in.** One LGPL-3 module; Pydantic AI
   is the one seam to the model world, so when AI changes shape the
   records and the window stay. It runs for a database that is connected
   to Pantalytics, the way Mail Pro does: Connect to Pantalytics in
   Settings, a code, approve on our site, done. Measured: the module
   installs from the store on Odoo.sh and on Cloudpepper and answers its
   first question within ten minutes of install, with one connection made
   and one key pasted.

What success is not: feature parity with Odoo's AI app, a brain on our
platform, or a second chat beside Discuss.

## 1. Decision

**Pydantic AI runs inside Odoo, in this module. The vocabulary is Pydantic
AI's, not Odoo's.**

1. The agent loop is Pydantic AI, in-process, on OpenRouter as the one
   provider (any model, web search as a plugin). The key lives in Odoo's
   Settings like the Anthropic key did in 19.0. No platform in the loop.
2. The Odoo records mirror Pydantic AI's objects one to one: an `Agent` has
   a `Model`, `instructions`, `Toolsets`, an `output_type`, `model_settings`
   and `UsageLimits`; a `Toolset` is a set of function `Tools` (Odoo server
   actions and the built-in ORM tools) or an MCP server; a `Run` is one
   `agent.run`, with its usage and cost; a `Thread` holds the `messages` as
   Pydantic AI's own `ModelMessage` JSON. Nobody has to learn Odoo's AI app
   to configure this one, and the code reads like the Pydantic AI docs.
3. Identity is the Odoo session. Tools run through `env` as the user who
   asked; ACLs and record rules apply with no key, no token, no pairing.
4. The chat is Odoo's own chat window: a `discuss.channel` of type `ai`
   with the agent as a partner, the `mail` stack for threads, messages,
   composer, Discuss and mobile, and our patches for what Odoo's AI chat
   lacks: streaming, tool rows, approval cards, Stop. The same on Community
   and Enterprise; on Enterprise 20 we hide Odoo's AI button and ship ours.
   Section 4 has the options that were weighed.
5. **MCP Pro compatibility is an MCP `Toolset`.** An agent can hold
   `https://mcp.pantalytics.com/mcp` (vault, `pan_` and hosting tools) and
   any other MCP server, through Pydantic AI's MCP client. The person signs
   in to Pantalytics from Odoo once, with Zitadel's device flow, which
   needs no redirect URI per customer database.
6. AI fields stay the gold: the 19.0 metadata model (stale, human-edited,
   auto-fill, auto-update, per-field agent) is ported as is and computes
   through an `Agent` with `output_type` = the field's schema.
7. One runtime, four ways to start a `Run`: on demand from the chat,
   scheduled by a cron, triggered by an automation rule, and continuous (a
   thread the cron keeps resuming, with memory). Section 3a.
8. **Connecting to Pantalytics is required**, decided 2026-10-19, the
   same as Mail Pro: the module pairs once (Connect to Pantalytics, a
   code, approve on our site), heartbeats daily, and runs only on a live
   signed entitlement; not connected or revoked means "Connect to
   Pantalytics in Settings" and no run. The platform's role stays Mail
   Pro's: the entitlement, the heartbeat (counts, never a prompt), paid
   tiers later. It never sees a message. How this is marketed is a later
   conversation.

### Why the first design was dropped

The first draft (same day) put the brain on the platform and made every
Odoo user a workspace member. Rutger's objection decided it: the agent would
be configured on our site while its tools, documents and triggers are Odoo
records, so an administrator sets AI up in two places and the shape differs
from everything else in Odoo. That costs pairing per user, key minting, a
token exchange, CORS and CSP, and a chat that needs us to be up. In-process
costs a pip dependency and a run that holds a worker for its duration; both
are spikes, and Odoo 19's own AI ran its loop in-process too.

## 2. What Odoo 20 changed (measured 2026-10-19)

| | Odoo 19 | Odoo 20 |
|---|---|---|
| AI module | `ai` / `ai_app`, Enterprise | `ai_agentic`, Enterprise, Custom plan upsell |
| Your own key | OpenAI, Gemini; we added Anthropic | None. Every request goes to Odoo's proxy, billed in IAP credits. "Select an AI provider and Odoo automatically uses the best AI model" |
| MCP | none | `ai_mcp`, `<db>/mcp`, Enterprise. Read-first, 5 write tools an admin enables one by one. Tested by us: no workflow buttons, no delete, read-only flag not enforced ([our post](https://www.pantalytics.com/post/odoo-20-mcp-server)) |
| AI fields | Studio only | Studio or property fields, daily cron, `/field` references in the prompt |
| Chat | Discuss channel, agent as partner | same, plus live status rows, confirmation cards, "+" menu, voice, files, 30-day retention |
| Topics | topics | renamed skills |
| Community | no AI | no AI. `odoo/odoo` 20.0 has 642 addons, none `ai*`; `mail` has the chat hub and composer action registry, nothing AI |

Consequences:

- The 19.0 approach (append to `PROVIDERS`, patch `LLMApiService`) has no
  target on 20. Three store apps claim BYOK on Odoo 20 agents and fields
  (Midvalley, ERP Heritage, echoBitz), all Enterprise-only, so some seam
  exists for AI fields; which one is spike S1.
- "AI in Community" is a product that does not exist on the store. That is
  the gap.
- Odoo's native `/mcp` is not our tool layer: Enterprise-only and weaker
  than MCP Pro, which presses buttons and runs on 14+ both editions. An
  agent here reaches Odoo through `env`, which is more than either.

Sources: [release notes](https://www.odoo.com/odoo-20-release-notes),
[AI docs 20.0](https://www.odoo.com/documentation/20.0/applications/productivity/ai.html)
(the API keys page is "under construction"),
[MCP server docs](https://www.odoo.com/documentation/20.0/applications/productivity/ai/mcp_server.html),
[Octura on ai_agentic](https://octurasolutions.com/resources/odoo-20-ai-agents-skills-triggers-and-ai-in-every-app),
[much. on AI app vs MCP](https://muchconsulting.com/blog/odoo-2/odoo-ai-overview-187),
[KSRO on ai_mcp](https://ksrolabs.com/comparisons/odoo-20-native-mcp-vs-ksrolabs).

## 3. The shape

```
browser (Odoo chat window, patched) ◄──bus: pan_ai.run_event──┐
        │ message_post on the ai channel                        │
        ▼                                                       │
Odoo controller / cron ──► Pydantic AI Agent (in-process) ──────┘
                             Model: OpenRouter (key in Settings)
                             Toolsets: Odoo tools (env), MCP servers
                             deps: OdooDeps(env, user, record, thread)
                             conversation: Thread.conversation (messages,
                               usage, deferred_tool_requests)
                             UsageLimits per slice; agent.iter() to stop
                               at the slice budget and resume later
                                        │
                   ┌────────────────────┼──────────────────────┐
                   ▼                    ▼                       ▼
              Odoo ORM (ACLs)      openrouter.ai        mcp.pantalytics.com/mcp
                                   (+ web plugin)       (Zitadel token, device flow)
```

- **Stream.** The run emits Pydantic AI's events; the runtime batches them
  (about every 100 ms) into one bus event on the user's partner channel
  and commits, the way Odoo's own AI chat and MuK AI deliver. The patched
  `Message` renders the growing text, the tool rows and the approval card;
  the final answer is written as the message body. Nothing outside the
  module reads the events, so they keep Pydantic AI's names.
- **Rights.** `deps.env` is the caller's `env`. No `sudo` in a tool, ever.
  A write tool carries `requires_approval`; the run ends with
  `DeferredToolRequests` on the `Conversation`, the card shows, and the
  next run passes `deferred_tool_results`.
- **Money.** The OpenRouter key per Odoo database, in Settings, encrypted
  at rest with the 19.0 helper. `Run` records usage and cost per run, per
  user. No credits of ours.
- **Conversation.** `Thread.conversation` is Pydantic AI's `Conversation`
  (`ConversationTypeAdapter` JSON): messages, usage across runs, pending
  deferred tools. A thread replays losslessly into the next run, and
  `UsageLimits` count against what the thread already spent. 30-day
  retention by cron, off by a setting.
- **MCP.** `Toolset` of kind `mcp`: URL, auth (none, bearer, or Pantalytics
  sign-in), `allowed_tool_names`, tool prefix. The SSRF gate from the
  public server runs on every user-supplied URL.

## 3a. Four ways to start a Run

One runtime, one `Run` model, a `kind` field. Nothing runs outside Odoo's
own workers: an HTTP request for the chat, `ir.cron` for the rest.

| `Run.kind` | Started by | Thread | Ends when |
|---|---|---|---|
| `chat` | the user's message on the `ai` channel | the channel's thread | the answer, an approval, or the slice budget |
| `scheduled` | a scheduled action whose server action is "Run agent" with a prompt | a thread per (agent, action), memory kept | `final_result`; the answer is posted to the agent's channel with the owner and, when asked, an activity |
| `triggered` | an automation rule (on create, on write, on message, time-based) with the record as `deps.record` | a thread per (agent, rule, record) | `final_result` |
| `continuous` | a thread marked continuous: a cron resumes it every N minutes with "what changed since your last tick" (a watch: model, domain, cursor) | one thread, memory kept, compacted when long | never; Pause and Stop on the thread |

**Slices.** A run is driven with `agent.iter()` so the runtime can stop at
the slice budget (rounds and seconds, both below the worker's time limit),
persist the `Conversation`, and continue: for a chat, inline in the request
and, past the budget, on a worker cron woken with `ir.cron._trigger()`;
for the other kinds, always on that cron. Two worker crons, an advisory
lock per thread so two workers never share one, a heartbeat so a dead
worker's thread is recovered. This is MuK AI's session loop shape, proven
on Odoo 19 and 20, with Pydantic AI's `Conversation` as the state instead
of their own. A chat that needs a second slice shows "Still working" and
keeps streaming; the person sees no difference.

**Memory.** Continuous and scheduled threads keep their `Conversation`; a
history processor compacts it past a token budget (summary of the old
turns, the last N kept). The compaction itself is a run on a small model.

**Not a daemon, not DBOS.** Odoo has no long-lived process of ours and we
add none. Pydantic AI's DBOS durability would give resume-after-crash for
free, but it runs its own workflow tables and launch step inside the
process; the cron slice gives the same for a chat without it. Revisit if
slices prove fragile in S4.

## 4. The window: Odoo's own, patched

Weighed on 2026-10-19, against the wish that it be as native as possible.

| Option | What it is | Verdict |
|---|---|---|
| **Odoo's `mail` chat window, a channel of type `ai`** (chosen) | Community ships the whole stack: `ChatHub`, `ChatWindow`, `Thread`, `Message`, `Composer`, Discuss, the messaging menu, mobile, notifications, attachments. Enterprise 20's AI chat is built on exactly this. Extension points are registries (`mail.composer/actions`, `mail.message/actions`, `discuss.component`) and OWL patches | Native by definition. What Odoo's AI chat does badly is not the stack, it is the use of it: no streaming, "AI is thinking", no tool rows, no Stop. Those are ours to add on top |
| [MuK AI](https://github.com/muk-it/odoo-modules) (`muk_ai`, LGPL-3, branch 20.0 updated 2026-10-18) | A standalone OWL chat client (17.7k lines JS, imports `@mail` only for the dock), its own agents, providers, approval gate, sessions, spaces, handoff; tools from `muk_mcp` (8k lines). Turns run in slices across worker crons with advisory locks | The reference for the run engine (`session_loop.py`, `session_worker.py`), not for the UI: a second chat stack beside Discuss, its own vocabulary, 23k lines of Python we would carry. Study it, copy the shape, do not depend on it |
| [apexive/odoo-llm](https://github.com/apexive/odoo-llm) (`llm_thread`, LGPL-3) | Threads, tools, providers, RAG, an MCP server; own chat UI on `mail.store` | 18.0 only (last update May 2026), no 19 or 20, not Pydantic AI. Nothing to reuse |
| [OCA/ai](https://github.com/OCA/ai) (AGPL-3) | `ai_tool` on 19.0, bridges to n8n-style external systems | No chat, no runtime; the LLM modules offered to OCA were declined |
| Our own OWL window (the earlier draft) | A `main_components` window with its own parser and renderer | A second chat stack beside Discuss, like MuK's. Dropped |
| A generic web chat component (deep-chat, assistant-ui, CopilotKit) | React or a web component in Odoo assets | Not Odoo, not OWL. Dropped |

What the patches add to the `mail` window:

- The `ai` channel type: one channel per (user, agent), the agent as a
  partner with its avatar, "New chat" in the window header, the agent
  picker there when the user may use more than one. Open from a systray
  icon and Ctrl+K ("Ask AI"); "Open in Discuss" comes with the stack.
- Streaming: within 100 ms of Send the user's message is in the thread
  and a muted "Thinking" row follows; the first `part_delta` replaces it;
  the text renders as markdown while it streams; the final body is
  written once. Stop in the composer while a run is live.
- Tool rows inside the message: one muted row per `function_tool_call`
  ("Searching sales orders…"), folding to its result ("12 found"), click
  unfolds arguments and result. Record references become clickable cards.
- Approval card: a message part with the change, Apply and Skip; the run
  waits. The "+" menu in the composer (attach a record, pick a toolset)
  through the composer actions registry.
- Not in v1: voice, attachments beyond what `mail` already does, a page
  of our own (Discuss is the page).

## 5. What goes where

| Bucket | Where | Pieces |
|---|---|---|
| Agent | `pan_ai_pro/models/agent.py`, `toolset.py`, `tool.py`, `run.py`, `thread.py` | the records, named as Pydantic AI names them |
| Runtime | `pan_ai_pro/runtime/` | `build_agent(record)`, `OdooDeps`, `odoo_toolset.py` (the built-in tools and server actions as `FunctionToolset`), `mcp_toolset.py`, `stream.py` (events to SSE), `limits.py` |
| Window | `pan_ai_pro/static/src/chat/` | patches on `mail`'s `Message`, `Composer`, `ChatWindow`; the event handler on the bus; markdown; approval card; tool row |
| Runs | `pan_ai_pro/models/run.py`, `runtime/slices.py`, `data/ir_cron.xml` | the four kinds, the slice loop on `agent.iter()`, two worker crons, the advisory lock, the watch for continuous threads |
| Fields | `pan_ai_pro/models/ai_field_*.py` | the 19.0 metadata, cron and Studio panel, retargeted to an `Agent` with `output_type` |
| Pantalytics | `pan_ai_pro/models/pan_ai_license.py`, admin `apps/ai_pro.py` | pairing, heartbeat, entitlement; the device-flow sign-in for the MCP toolset |

## 6. Spikes before any code

Each one is a directory under `scripts/spikes/<name>/` with a README that
exits non-zero when its claim fails; the result and the date land in
`docs/architecture-20.md`.

1. **S1 Enterprise 20 seam.** On a 20 Enterprise staging database: where
   `ai_fields` asks for a value, and the registry names of the native AI
   systray item and Ctrl+K command. Decides whether Enterprise fields
   route to our `Agent`.
2. **S2 Streaming through the bus into a `mail` message.** The `ai`
   channel type, a patched `Message` that grows from `pan_ai.run_event`
   on the partner channel, commit cadence 100 ms, first token on screen
   under 300 ms after the model's first byte, Stop mid-run, and the final
   body written once. On Odoo.sh and Cloudpepper.
3. **S3 The dependency.** `pydantic-ai-slim[openai,mcp]` installed on
   Odoo.sh (`requirements.txt`) and on Cloudpepper; import inside an Odoo
   worker; `asyncio.run` per request; memory per worker.
4. **S4 Workers and time.** A 5-minute run under `limit_time_real` and
   `limit_time_cpu` on both hosts; what the window shows when a worker is
   recycled mid-run.
5. **S5 Built-in tools.** Pydantic AI's `WebSearchTool` and
   `CodeExecutionTool` through OpenRouter on Sonnet, GPT and Gemini, and
   the OpenRouter `web` plugin as the fallback that works on every model.
6. **S6 MCP Pro as a toolset.** `MCPServerStreamableHTTP` against
   `mcp.pantalytics.com/mcp` with a Zitadel token from the device flow
   (RFC 8628) started in Odoo; refresh stored encrypted; `tools/list`
   filtered by `allowed_tool_names`.

## 7. Order

- [ ] Spikes S1 to S6 (one week)
- [ ] This repo: branch `20.0` from empty; records, runtime, the `ai`
      channel and the window patches, settings. PR A. Odoo 19 stays on
      `19.0` as is
- [ ] Runs: scheduled, triggered, continuous, the slice loop and the
      worker crons. PR E
- [ ] AI fields: Enterprise seam or property fields, metadata ported. PR B
- [ ] MCP toolsets and the Pantalytics sign-in. PR C
- [ ] Admin: `apps/ai_pro.py`, pairing and entitlement, Mail Pro's shape.
      PR D (small), before PR A ships: the module needs it to run at all
- [ ] Store listing 20.0, humanizer over every string, README rewritten

**Not doing:** extending Odoo 20's AI, voice, attachments, a full-page
chat, our own credits, a brain on the platform, Odoo's native `/mcp` as
the tool layer, a queue dependency (OCA `queue_job`) in v1.

## 8. Open for Rutger

- Pricing and marketing of the app through the entitlement. Later, on
  purpose; the beta is "connected is entitled", as Mail Pro's.
- Licence of the public server stays as it is; this module is LGPL-3.

## 9. Transport note (checked 2026-10-19)

"Is SSE outdated?" No. What was retired is MCP's old two-endpoint HTTP+SSE
transport (spec 2025-03-26). The current MCP revision, 2026-07-28, went
further the same way: no standalone GET stream, no protocol sessions, no
resumability; each JSON-RPC message is one POST and the reply is a JSON
object or a request-scoped SSE stream, cancel by closing it
([spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports),
[TrueFoundry on the wire protocol](https://www.truefoundry.com/blog/mcp-streamable-http-wire-protocol)).
OpenAI, Anthropic, OpenRouter, the Vercel AI SDK and Pydantic AI's UI
adapters stream over SSE. OpenAI's WebSocket mode (2026) sits between the
agent runtime and the inference API, not between agent and browser, and
OpenRouter does not offer it. WebTransport reached every browser in March
2026 and is built for unreliable datagrams, not for a text stream.

The 2026 consensus, also from the WebSocket vendors: SSE for agent to
browser, a typed event vocabulary on top, WebSocket only for a return
channel mid-run (voice, collaborative editing)
([zylos.ai on AG-UI convergence](https://zylos.ai/research/2026-05-03-agent-frontend-streaming-protocols-ag-ui-convergence/),
[laramateo.com, SSE vs WebSocket vs WebTransport](https://laramateo.com/blog/sse-vs-websocket-vs-webtransport-how-to-choose-in-2026),
[websocket.org on AI streaming](https://websocket.org/guides/use-cases/ai-streaming/)).
Inside Odoo the native push channel is the bus (a websocket since 16),
and the `mail` chat window already listens on it, so the run's events ride
the bus into the message rather than a stream of our own; the vocabulary
stays Pydantic AI's run events, because the producer and the consumer are
the same module. If voice comes, it gets a WebSocket beside it, not
instead.
