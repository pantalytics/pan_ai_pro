# Plan: AI Pro for Odoo 20, Pydantic AI inside Odoo

Status: research done 2026-10-19; design flipped the same day (section 1).
Spikes first (section 6). Nothing built.

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
4. The chat is our own OWL window, bottom-right, the same on Community and
   Enterprise, streaming Pydantic AI's run events (`part_delta`,
   `function_tool_call`, `function_tool_result`, `final_result`) straight
   to the browser. On Enterprise 20 we hide Odoo's AI button and ship ours.
5. **MCP Pro compatibility is an MCP `Toolset`.** An agent can hold
   `https://mcp.pantalytics.com/mcp` (vault, `pan_` and hosting tools) and
   any other MCP server, through Pydantic AI's MCP client. The person signs
   in to Pantalytics from Odoo once, with Zitadel's device flow, which
   needs no redirect URI per customer database.
6. AI fields stay the gold: the 19.0 metadata model (stale, human-edited,
   auto-fill, auto-update, per-field agent) is ported as is and computes
   through an `Agent` with `output_type` = the field's schema.
7. The platform keeps Mail Pro's role only: pairing for the entitlement and
   the heartbeat (counts, never a prompt), paid tiers through the signed
   entitlement. It never sees a message.

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
browser (OWL window) ──POST /pan_ai/run, SSE of run events──> Odoo controller
                                                                 │ own cursor, as env.user
                                                                 ▼
                                                     Pydantic AI Agent (in-process)
                                                       Model: OpenRouter (key in Settings)
                                                       Toolsets: Odoo tools (env), MCP servers
                                                       deps: OdooDeps(env, user, record)
                                                       UsageLimits, output_type
                                                                 │
                                   ┌─────────────────────────────┼──────────────────────┐
                                   ▼                             ▼                      ▼
                              Odoo ORM (ACLs)           openrouter.ai           mcp.pantalytics.com/mcp
                                                        (+ web plugin)          (Zitadel token, device flow)
```

- **Stream.** One POST per run; the reply is a request-scoped SSE stream of
  Pydantic AI's `run_stream_events`, serialized as JSON; cancel by closing
  it. The run executes inside that request on its own cursor, so nothing
  waits on a bus commit. Same shape as MCP's own transport. If the spike
  shows a hosting proxy buffering it (S2), the fallback is the bus, same
  events.
- **Rights.** `deps.env` is the caller's `env`. No `sudo` in a tool, ever.
  A write tool carries `requires_approval`; the window shows the card and
  the run resumes with Pydantic AI's `DeferredToolResults`.
- **Money.** The OpenRouter key per Odoo database, in Settings, encrypted
  at rest with the 19.0 helper. `Run` records usage and cost per run, per
  user. No credits of ours.
- **Messages.** `Thread.messages` is `ModelMessagesTypeAdapter` JSON, so a
  thread replays losslessly into the next run and the window renders from
  the same parts. 30-day retention by cron, off by a setting.
- **MCP.** `Toolset` of kind `mcp`: URL, auth (none, bearer, or Pantalytics
  sign-in), `allowed_tool_names`, tool prefix. The SSRF gate from the
  public server runs on every user-supplied URL.

## 4. The window

Brand rules apply (Product UI, Design Philosophy). Odoo-native widgets
where they suffice, no shadows, 1 px border, 150 ms transitions, skeleton
not spinner, sentence case, no em dashes.

- Opens from a systray icon and Ctrl+K ("Ask AI"). Fixed bottom-right,
  420 px, beside the chat hub, folds to a bubble. An agent picker in the
  header when the user may use more than one.
- Within 100 ms of Send: the user's message, then a muted "Thinking" row.
  First `part_delta` replaces it. Text renders as markdown while it streams.
- Each `function_tool_call` is one muted row: "Searching sales orders…",
  folding to "Searched sales orders, 12 found" on its result; click unfolds
  arguments and result. Record references become clickable cards.
- A tool with `requires_approval` is a card with the change, Apply and
  Skip. The run waits.
- Stop, Retry, Copy on hover. New chat and recent threads in the header.
  Not in v1: voice, attachments, a full page.

## 5. What goes where

| Bucket | Where | Pieces |
|---|---|---|
| Agent | `pan_ai_pro/models/agent.py`, `toolset.py`, `tool.py`, `run.py`, `thread.py` | the records, named as Pydantic AI names them |
| Runtime | `pan_ai_pro/runtime/` | `build_agent(record)`, `OdooDeps`, `odoo_toolset.py` (the built-in tools and server actions as `FunctionToolset`), `mcp_toolset.py`, `stream.py` (events to SSE), `limits.py` |
| Window | `pan_ai_pro/static/src/chat/` | OWL, the event parser, markdown, approval card, tool row, threads |
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
2. **S2 SSE from an Odoo controller.** A `type='http'` route returning a
   generator on its own `registry.cursor()`, running a Pydantic AI stream,
   through Odoo.sh's and Cloudpepper's proxies unbuffered; first event
   under 100 ms; cancel on disconnect. Fallback measured too: the same
   events over the bus.
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
- [ ] This repo: branch `20.0` from empty; records, runtime, window,
      settings. PR A. Odoo 19 stays on `19.0` as is
- [ ] AI fields: Enterprise seam or property fields, metadata ported. PR B
- [ ] MCP toolsets and the Pantalytics sign-in. PR C
- [ ] Admin: `apps/ai_pro.py`, pairing and entitlement, Mail Pro's shape.
      PR D (small)
- [ ] Store listing 20.0, humanizer over every string, README rewritten

**Not doing:** extending Odoo 20's AI, voice, attachments, a full-page
chat, our own credits, a brain on the platform, Odoo's native `/mcp` as
the tool layer, a queue dependency (OCA `queue_job`) in v1.

## 8. Open for Rutger

- Pricing of the app through the entitlement (what Free gets: one agent,
  no MCP toolsets?). Not needed before PR D.
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
Here the vocabulary is Pydantic AI's own run events rather than AG-UI,
because the producer and the consumer are the same module and nothing
outside it reads the stream. If voice comes, it gets a WebSocket beside
it, not instead.
