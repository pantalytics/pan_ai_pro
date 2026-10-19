# AI Pro 20: architecture

The working document for the 20.0 rewrite. `ARCHITECTURE.md` in the root
describes 19.0 and stays as is. The plan and the spikes are in
[plans/ai-pro-20.md](plans/ai-pro-20.md); this file is what we agree on and
build against. Change it in a PR, one decision per commit.

Status: draft, 2026-10-19. Nothing below is built.

## 1. One sentence

The chat lives in Odoo, the brain lives on the Pantalytics platform, the two
speak AG-UI over SSE, and the brain reaches Odoo through the Odoo MCP Pro
tools with the rights of the person who asked.

## 2. The boxes

```
┌─────────────────────────────── browser ───────────────────────────────┐
│  Odoo web client (OWL)                                                 │
│  ┌───────────────────────────┐   ┌───────────────────────────────┐     │
│  │ pan_ai_pro chat window    │   │ AI field widget               │     │
│  │ systray icon, Ctrl+K      │   │ wand / stale / spinner        │     │
│  └──────────┬────────────────┘   └──────────────┬────────────────┘     │
└─────────────┼───────────────────────────────────┼──────────────────────┘
              │ (1) POST /pan_ai/token            │ (6) JSON-RPC
              │ (2) POST /chat  AG-UI over SSE    │
              ▼                                   ▼
┌──────────── platform ────────────┐   ┌────────── Odoo server ──────────┐
│ mcp.pantalytics.com              │   │ pan_ai_pro (Python, no LLM)     │
│                                  │   │                                 │
│  apps/ai_pro.py   door, pairing, │◄──│ pairing key, heartbeat (daily)  │
│                   token mint,    │   │ /pan_ai/token: 15 min token     │
│                   per-user conn. │   │ per-user API key, minted once   │
│                                  │   │ AI fields: metadata, cron,      │
│  agents/          Pydantic AI    │   │   Studio panel, properties      │
│    model.py       OpenRouter,    │   │                                 │
│                   workspace key  │   │ (7) POST /api/v1/ai-pro/field   │
│    toolset.py     MCP Pro tools, │◄──│     structured output, sync     │
│                   pinned, run as │   └───────────────▲─────────────────┘
│                   this user      │                   │
│    runner.py      limits, cost,  │  (3) external API, the user's own   │
│                   agent_runs     │──────key──────────┘ (MCP Pro tools) │
│                                  │                                     │
│  threads          ai_threads,    │  (4) OpenRouter: model + web plugin │
│                   ai_messages    │──────────────────────► openrouter.ai│
└──────────────────────────────────┘                                     │
```

| Box | Repo | Owns | Never does |
|---|---|---|---|
| Chat window | `pan_ai_pro` (LGPL-3) | rendering, the AG-UI parser, approval cards, the thread list | talk to a model, hold a key |
| Odoo module, server side | `pan_ai_pro` | pairing, the token controller, per-user API key, AI field metadata and cron | run an agent, call OpenRouter |
| Door | admin `apps/ai_pro.py` | pairing, heartbeat, entitlement, token mint, per-user connections | know what a chat said |
| Brain | admin `agents/` (public later, section 8) | the Pydantic AI run, toolsets, limits, cost | reach an Odoo other than the pinned one |
| Threads | admin `db/` | `ai_threads`, `ai_messages`, 30-day retention | be trusted from the client |
| Tools | public `odoo-mcp-pro` | the Odoo tools over the external API | know the chat exists |

## 3. One chat turn

```
user types, presses Send
  │
  ├─ 0 ms    window appends the message, shows a muted "Thinking" row
  ├─ (1)     window → Odoo   POST /pan_ai/token          (session cookie)
  │          Odoo → platform POST /api/v1/ai-pro/token   (pairing key, odoo uid)
  │          platform mints a 15 min token bound to {installation, user}
  ├─ (2)     window → platform POST /api/v1/ai-pro/chat  (token, thread id, text)
  │          platform answers one SSE stream, AG-UI events:
  │            RUN_STARTED
  │            TEXT_MESSAGE_START / CONTENT* / END       ← markdown while it streams
  │            TOOL_CALL_START / ARGS* / END             ← "Searching sales orders…"
  │            CUSTOM tool_result                        ← "12 found", foldable
  │            STATE_DELTA                               ← record cards, usage
  │            RUN_FINISHED {outcome: ok | interrupt}
  ├─ (3)     each tool call: platform → Odoo external API, the user's own key
  ├─ (4)     each model call: platform → OpenRouter, the workspace's key
  └─ stop    window closes the stream; platform cancels the run
```

Approval, when "May change data" is on and the tool writes:

```
RUN_FINISHED {outcome: interrupt, pending: [tool call ids]}
window shows a card: the change, Apply, Skip
window → platform POST /chat {resume: [{id, approved, editedArgs?}]}
platform resumes the same run; the stream continues
```

## 4. Identity and rights

```
Odoo user ──(first chat)──► pan_ai_pro mints res.users.apikeys (scope rpc)
                              │
                              └──► platform stores it as this user's
                                   connection on the paired instance
                                   (encrypted, like every Odoo key we hold)

agent run ─ toolset pinned to that connection ─► Odoo external API
                                                  as that user: ACLs and
                                                  record rules apply
```

- The AI sees what its person sees. No service account, no sudo, no
  "AI user" with its own rights.
- Disconnect in the panel, or uninstall in Odoo, revokes the installation;
  the next heartbeat gets `revoked`, every per-user key is deleted.
- Who may chat: every internal Odoo user on a connected instance. Who may
  connect: an Odoo administrator, who is also a workspace administrator.

## 5. Money and limits

| What | Where | Rule |
|---|---|---|
| Tokens | the workspace's OpenRouter key (Workspace settings > LLMs) | no key, no chat; the window says "No key, ask your administrator" |
| Web search | OpenRouter `web` plugin per run | on by default, a few tenths of a cent per request |
| Per run | `runner.py` `UsageLimits` | 20 requests, 300k tokens, 10 min, as agents have today |
| Per workspace | `agent_runs` | cost per run recorded; the LLMs section shows the month |
| Seats | open | an Odoo user who chats is not a workspace member (plan, section 8) |

## 6. AI fields

```
Enterprise 20 (Studio or property AI field)      Community 20 (property AI field)
   ai_fields asks for a value                        our own property type "AI"
          │ (seam: spike 1)                                 │
          ▼                                                 ▼
   pan_ai_pro  ──(7) POST /api/v1/ai-pro/field────────────────► platform
               prompt, field type, record context,            one agent run,
               allowed values                                 output_type = the
          ◄──── value ──────────────────────────────────────  field's schema
          │
   x_ai.field.metadata: is_stale, human_edited  (ported from 19.0 as is)
   auto_fill (cron fills empty), auto_update (recompute on input change)
```

No streaming here: one POST, one value, the widget shows a spinner on the
field. Web search off unless the field's prompt turns it on.

## 7. Protocols

| Boundary | Protocol | Why this one |
|---|---|---|
| browser ↔ platform | AG-UI events, one POST, request-scoped SSE, cancel = close | the 2026 consensus and MCP's own shape; vendor-neutral, approvals and state built in |
| Odoo ↔ platform (server) | HTTPS JSON, bearer pairing key | Mail Pro's door, unchanged |
| platform ↔ Odoo (tools) | Odoo external API through MCP Pro tools | already built, presses buttons, 14+ both editions |
| platform ↔ model | OpenRouter | one key field, any model |
| not used | Odoo's `/mcp`, Odoo's bus, WebSocket, Vercel data stream | Enterprise-only and weaker; holds a worker; no return channel needed; one vendor's format |

## 8. Open source

- `pan_ai_pro` stays LGPL-3, the whole module, both editions.
- The tools are in public `odoo-mcp-pro` already.
- The brain (`agents/`, the chat route, the AG-UI adapter) should move to
  the public server so a self-hosted MCP Pro runs the same chat. That is a
  licence decision (ELv2 vs AGPL) for Rutger; until then it stays in admin.

## 9. Decisions

| # | Decision | Instead of | Date |
|---|---|---|---|
| 1 | Brain on the platform | Pydantic AI inside the Odoo process | 2026-10-19 |
| 2 | Our own window, same on both editions | extending Odoo 20's AI chat | 2026-10-19 |
| 3 | AG-UI over request-scoped SSE | Vercel data stream, WebSocket, Odoo bus | 2026-10-19 |
| 4 | Tools run as the Odoo user, key minted per user | one installation key with admin rights | 2026-10-19 |
| 5 | Threads on the platform | `pan_ai.message` in Odoo | 2026-10-19 |
| 6 | Workspace's OpenRouter key, no credits | our own credits with margin | 2026-10-13 (agents plan) |
| 7 | AI fields metadata ported from 19.0 as is | redesign | 2026-10-19 |

## 10. Open

- Seats: does an Odoo user who chats count? Assumption: no while in beta.
- Licence of the brain (section 8).
- Spike results (plan, section 6) may move boxes; each result lands here.
