# Plan: AI Pro for Odoo 20, one chat, one brain, both editions

Status: research done 2026-10-19, nothing built. Spikes first (section 6).

## 1. Decision

**The brain leaves Odoo. The Odoo module becomes the face.**

1. The agent runs on the Pantalytics platform: Pydantic AI on OpenRouter,
   the workspace's own key, the Odoo MCP Pro tools against the paired Odoo,
   web search on every model, code execution where the model has it. All of
   that exists in `odoo-mcp-pro-admin/mcp_server_odoo_admin/agents/` today
   (`model.py`, `toolset.py`, `runner.py`, `llm_settings`, `agent_runs`).
2. `pan_ai_pro` 20.0 is a thin module: a chat window of our own (OWL,
   bottom-right, streaming), a "Connect to Pantalytics" pairing like Mail
   Pro, and AI fields. No provider patches, no LLM code, no pip dependency.
3. Same module, same window on Community and Enterprise. On Enterprise 20 we
   do not extend Odoo's AI; we hide its button and ship ours. Odoo 20's AI
   runs on IAP credits only and takes no key of yours, so there is nothing
   left to plug into (section 2).
4. AI fields stay the gold: the 19.0 metadata model (stale, human-edited,
   auto-fill, auto-update, per-field agent) is ported as is. Enterprise 20
   fields route to our brain through whatever seam `ai_fields` still has
   (spike 1); Community gets AI on property fields, which it never had.

The alternative, running Pydantic AI inside the Odoo process, was weighed
and dropped in one line: Odoo has no async loop and no job queue, a run holds
a worker, streaming means committing every 80 ms and patching the DOM (what
19.0 does now), the tools exist twice, and nothing meters it.

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

Consequences for this module:

- The 19.0 approach (append to `PROVIDERS`, patch `LLMApiService`) has no
  target on 20. Three store apps claim BYOK on Odoo 20 agents and fields
  (Midvalley, ERP Heritage, echoBitz), all Enterprise-only, so some seam
  exists; which one is spike 1.
- "AI in Community" is a product that does not exist on the store. The
  closest listings are keyword soup. This is the gap.
- Odoo's native `/mcp` is not our tool layer: Enterprise-only and weaker than
  MCP Pro, which already presses buttons and runs on 14+ both editions.

Sources: [release notes](https://www.odoo.com/odoo-20-release-notes),
[AI docs 20.0](https://www.odoo.com/documentation/20.0/applications/productivity/ai.html)
(the API keys page is "under construction"),
[MCP server docs](https://www.odoo.com/documentation/20.0/applications/productivity/ai/mcp_server.html),
[Octura on ai_agentic](https://octurasolutions.com/resources/odoo-20-ai-agents-skills-triggers-and-ai-in-every-app),
[much. on AI app vs MCP](https://muchconsulting.com/blog/odoo-2/odoo-ai-overview-187),
[KSRO on ai_mcp](https://ksrolabs.com/comparisons/odoo-20-native-mcp-vs-ksrolabs).

## 3. The shape

```
browser (OWL window) ──AG-UI events over SSE──────> platform /api/v1/ai-pro/chat
        │                                                  │ Pydantic AI, OpenRouter
        │ JSON-RPC /pan_ai/token (15 min member token)      │ McpToolset pinned to this Odoo,
        ▼                                                  │ run as this Odoo user
Odoo: pan_ai_pro ──daily heartbeat, pairing key──> platform  │
        ▲                                                  ▼
        └────────── external API, the user's own key ── Odoo MCP Pro tools
```

- **Protocol.** AG-UI, the open agent-to-frontend event standard (16 typed
  events: run and step lifecycle, text message start/content/end, tool call
  start/args/end, state snapshot and JSON Patch delta, custom). Pydantic AI
  ships `AGUIAdapter` with approvals (`RUN_FINISHED` with outcome
  `interrupt`, the client resumes with `resume[]`) and shared state
  (`StateDeps`). Vendor-neutral: Oracle's Open Agent Spec, Google's A2UI and
  Microsoft's Agent Framework align on it, CopilotKit consumes it. The Vercel
  AI data stream was the alternative; it is one vendor's wire format and we
  would need none of its React side.
- **Transport.** One POST per run, the reply a request-scoped SSE stream,
  cancel by closing it. The browser talks to the platform directly. No Odoo
  worker is held, no bus, no commits per token. The OWL component gets a
  small event parser of its own (the `@ag-ui/client` package is TypeScript
  on RxJS, too much to vendor into Odoo assets). WebSocket is reserved for
  what needs a return channel mid-run, which is voice, and voice is not in
  v1. See the transport note in section 9.
- **Identity.** The installation pairs once (Mail Pro's `pairing.py`,
  `door.py`; `PAIRED` gains `AI_PRO`). Per Odoo user, on first chat, the
  module mints an Odoo API key server-side and registers it with the platform
  as that user's connection on the paired instance. Tools then run with
  exactly that user's rights, the way MCP Pro already does per member. The AI
  sees what its person sees, nothing more.
- **Money.** The workspace's OpenRouter key (Workspace settings > LLMs, built
  in #387). No credits, no margin on tokens; `agent_runs` records cost per
  run. Web search is OpenRouter's `web` plugin, a few tenths of a cent per
  request on any model.
- **Threads.** The platform owns them (`ai_threads`, `ai_messages`, 30-day
  retention like Odoo). The module caches nothing; the window loads the list
  on open. One place, and the adapter never trusts client-sent history.
- **Reads and writes.** One switch on the module's settings row: "May change
  data" off by default. Off: the read toolset. On: writes, and every write
  tool gets `requires_approval`, which the window shows as a confirmation
  card (AG-UI carries the interrupt and the resume natively).

## 4. The window

Brand rules apply (Product UI, Design Philosophy). Odoo-native widgets where
they suffice, no shadows, 1 px border, 150 ms transitions, skeleton not
spinner, sentence case, no em dashes.

- Opens from a systray icon and from Ctrl+K ("Ask AI"), like Odoo 20's own.
  Fixed bottom-right, 420 px, beside the chat hub, folds to a bubble.
- Within 100 ms of Send: the user's message, then a muted "Thinking" row.
  First token replaces it. Text renders as markdown while it streams.
- Each tool call is one muted row: "Searching sales orders…", folding to
  "Searched sales orders, 12 found" when done; click unfolds arguments and
  result. Record references become clickable cards that open the record.
- A write needing approval is a card with the change and two buttons, Apply
  and Skip. The run waits.
- Stop, Retry, Copy on hover. New chat, and a list of recent chats, in the
  header. Nothing else in v1: no voice, no attachments, no full page.

## 5. What goes where

| Bucket | Repo | Pieces |
|---|---|---|
| Brain | admin, `agents/` | `run_stream_events` through `runner.run` with the same accounting; `VercelAIAdapter` route; web plugin per run; approvals |
| Door | admin, `apps/` | `ai_pro.py`: pairing, heartbeat, token mint, per-user connection upsert, threads |
| Face | this repo, 20.0 | `static/src/chat/` (the window), `controllers/token.py`, `models/pairing.py`, settings page (two rows: Connected / Not connected, May change data) |
| Fields | this repo, 20.0 | `ai_field_metadata.py`, `ir_model_fields.py` and the Studio panel from 19.0, retargeted; `properties` AI for Community; `/api/v1/ai-pro/field` with `output_type` |
| Open source | this repo + public `odoo-mcp-pro` | module stays LGPL-3. The runner and the chat route belong in the public server so self-hosted MCP Pro gets the same brain; that is a licence decision (ELv2 vs AGPL, see admin `docs/plans/ai-distribution.md`) |

## 6. Spikes before any code

Each one is a directory with a README that exits non-zero when its claim
fails, dated in this file when done.

1. **The Enterprise 20 seam.** Install `ai_agentic` + `ai_fields` on a 20
   Enterprise staging database. Find where `get_ai_value` went, how the IAP
   call is made, and the registry name of the native AI systray item. Decides
   whether Enterprise AI fields route to us or Enterprise gets Community's
   property-field path too.
2. **SSE from the Odoo backend.** A `main_components` component in Odoo 20
   Community POSTs to `mcp.pantalytics.com` and reads the SSE stream with
   `fetch`. CORS, CSP, cookies, the AG-UI event parse with tool rows, and an
   approval round trip (`interrupt`, then `resume[]`). Measures the 100 ms
   first-paint rule and time to first event.
3. **Streaming through the runner.** `runner.run` uses `agent.run`;
   `AGUIAdapter.dispatch_request` wants `run_stream_events`. Keep
   `agent_runs`, limits, timeout and cost; add `on_complete`. Confirm the
   `McpToolset` streams `TOOL_CALL_*` events and that `ag-ui-protocol` is
   at least 0.1.19 (older versions drop the approval resume silently).
4. **Code execution.** Which of Pydantic AI workspaces, Anthropic's server
   tool through OpenRouter, or neither, actually streams through the adapter
   on Sonnet, GPT and Gemini. If neither streams, v1 ships web search only
   and code execution waits.
5. **Per-user key minting.** `res.users.apikeys` from a controller without the
   password prompt, scope `rpc`, revoked on Disconnect; the platform side
   stores it as a connection. Confirm a restricted sales user sees only his
   orders through the chat.

## 7. Order

- [ ] Spikes 1 to 5 (one week)
- [ ] Admin: `apps/ai_pro.py`, chat route, threads, per-user connections,
      switch "AI Pro (beta)" on Workspace settings off by default (like
      Agents). PR A
- [ ] This repo: branch `20.0` from empty, module with pairing + window +
      settings. PR B. Odoo 19 stays on `19.0` as is
- [ ] AI fields: Enterprise seam or property fields, metadata ported. PR C
- [ ] Store listing 20.0, humanizer over every string, README rewritten
- [ ] Licence call on the runner (Rutger), then the move to public

**Not doing:** extending Odoo 20's AI agents, voice, attachments, a full-page
chat, our own credits, an in-Odoo LLM runtime, Odoo's native `/mcp` as the
tool layer.

## 8. Open for Rutger

Who is the chat user on the bill? An Odoo user who chats is not a workspace
member. Assumption until told otherwise: chats run on the workspace's own
OpenRouter key and count no seat while in beta, the same stance as Agents.

## 9. Transport note (checked 2026-10-19)

"Is SSE outdated?" No. What was retired is MCP's old two-endpoint HTTP+SSE
transport (spec 2025-03-26). The current MCP revision, 2026-07-28, went
further the same way: no standalone GET stream, no protocol sessions, no
resumability; each JSON-RPC message is one POST and the reply is a JSON
object or a request-scoped SSE stream, cancel by closing it
([spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports),
[TrueFoundry on the wire protocol](https://www.truefoundry.com/blog/mcp-streamable-http-wire-protocol)).
OpenAI, Anthropic, OpenRouter, the Vercel AI SDK and both Pydantic AI UI
adapters stream over SSE. OpenAI's WebSocket mode (2026) sits between the
agent runtime and the inference API, not between agent and browser, and
OpenRouter does not offer it. WebTransport reached every browser in March
2026 and is built for unreliable datagrams, not for a text stream.

The 2026 consensus, also from the WebSocket vendors: SSE for agent to
browser, AG-UI as the event vocabulary on top, WebSocket only for a return
channel mid-run (voice, collaborative editing)
([zylos.ai on AG-UI convergence](https://zylos.ai/research/2026-05-03-agent-frontend-streaming-protocols-ag-ui-convergence/),
[laramateo.com, SSE vs WebSocket vs WebTransport](https://laramateo.com/blog/sse-vs-websocket-vs-webtransport-how-to-choose-in-2026),
[websocket.org on AI streaming](https://websocket.org/guides/use-cases/ai-streaming/),
[Pydantic AI AG-UI](https://pydantic.dev/docs/ai/integrations/ui/ag-ui/),
[AG-UI architecture](https://docs.ag-ui.com/concepts/architecture)).
Our stack is that consensus: AG-UI over request-scoped SSE, the same shape
as MCP itself. If voice comes, it gets a WebSocket beside it, not instead.
