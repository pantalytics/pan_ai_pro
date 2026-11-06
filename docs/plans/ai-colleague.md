# Plan: the agent as a colleague

Status: built in 2.11.0, 2026-11-06: slice 1 (direct messages to a
dedicated user), slice 2 (an agent does a to-do, no user per agent), the
approval rules A1, A2, A3, A6 and A8, and the character (section 9). Channels:
decided, not built (section 4, agent-identity.md). Not built: A5 for automation
runs ([#58](https://github.com/pantalytics/pan_ai_pro/issues/58)).

## 0. The idea, and where it comes from

Buzz (Block, [github.com/block/buzz](https://github.com/block/buzz), Apache
2.0, July 2026): "your people, your agents, your project, all in one place".
Agents are members, not bots: they have their own identity, sit in channels
and work alongside people.

The same move in Odoo: an AI Pro agent with a dedicated user is a colleague.
You message it, mention it, put it in a team and give it a to-do, the way
you would a person. It works with its own rights, and what it did is in the
chatter like anybody's work.

Most of it exists. What Buzz has, and where it lives in Odoo:

| Buzz | In Odoo with AI Pro | Status |
|---|---|---|
| An agent is a member with its own identity | The agent's dedicated user (`run_as = user`) | built (2.10.0) |
| Mention an agent in a channel | `@Ava` in a Discuss channel, answer in a thread | built (2.10.0) |
| Message an agent directly | A direct chat with Ava, answered there | **slice 1, built** |
| Give an agent work | "Done by agent" on an activity | **slice 2, built** |
| An agent in a team channel | `@Ava` in a team channel, without a user | **slice 3, open** |
| Workflows on a message, schedule or webhook | Automation rules and scheduled actions with "Run AI agent", continuous threads | built |
| Approve before a write | Allow and Skip on the approval card | built |
| One signed log of everything | The chatter, and every run with its tool calls and cost | built |
| Outside agents (Claude Code, Codex) as members | [pan_ai_pro#56](https://github.com/pantalytics/pan_ai_pro/issues/56) | later |

Dropped, on purpose: Nostr and signed events (Odoo's chatter and the run log
are the audit trail), git hosting, approving by emoji reaction, YAML
workflows (Odoo's automation rules are the workflow engine).

## 1. What success looks like

1. A person opens a direct chat with Ava and gets an answer there, the way a
   colleague answers. No mention needed.
2. A person hands Ava an activity on a lead, a ticket or a task. Ava does
   it, posts what she did on the record and marks the activity done.
3. Five agents cost no extra Odoo user.

Not: an agent that picks up work nobody gave it, reads channels it was not
invited to, or decides on its own writes.

## 2. Slice 1: a direct message (built)

```
admin: agent > Access > Give it its own user (Ava), Works as a colleague
person opens a direct chat with Ava, like with any colleague
person: "which quotes for Acme are still open?"
  │  message_post on the chat
  ├─ the other member is the dedicated user of an agent that works as a colleague
  ├─ one pan_ai.thread on the chat, kind chat
  ├─ placeholder from Ava, "Thinking"
  └─ Run.start(thread, prompt, kind="chat", caller=person), runs as Ava
```

The prompt is every message since Ava last answered, under one line that
says who sent it. Stop, Allow and Skip are the person's. The rules of a
mention hold: the agent's groups decide who may use it, the person's hourly
limit counts, retention deletes the memory and keeps the chat.

| Where | What |
|---|---|
| `models/discuss_channel.py` | `_pan_ai_on_direct`, the prompt's head for a chat |
| `models/agent.py` | the switch is called "Works as a colleague" |
| `static/src/chat/compat.js` | `agentMayAnswer`: the AI chat, a thread under a message, a direct chat |
| `tests/test_direct_message.py` | the flow, a chat between people, the switch off, refusal, approval by the asker |

## 3. Slice 2: an agent does a to-do (built)

Activities are how every Odoo app gives a person work: CRM, Helpdesk,
Project, Accounting, all of them. The activity dialog gets one field,
**Done by agent**: pick Ava and she does the to-do for the person it is
assigned to.

```
Sam schedules an activity on lead "Acme", assigned to himself, Done by agent: Ava
  "Call back: ask for their budget and log it on the lead"
  │  mail.activity create (or the agent or the person changed)
  ├─ queued; the cron starts it after Sam's save, never inside it
  ├─ the work runs in Sam's AI chat with Ava:
  │    Ava: "To-do: Call back, on Acme" ... streams, approval card
  ├─ the prompt names the activity and the record (model, id)
  └─ done: Ava's answer as a note on the lead, from Ava,
           and the activity marked done ("Done by Ava")
```

| # | Decision | Why |
|---|---|---|
| 1 | **The to-do stays the person's; the agent does it for them.** No Odoo user per agent. | Five agents cost no seat. The person stays accountable, as for work they hand to an intern. |
| 2 | **The person it is assigned to is the caller**: their rights, their hourly limit, their Allow and Skip. | Whoever owns the to-do owns what changes. A to-do an automation or OdooBot made waits for its person's Allow, so background work has a decider too. |
| 3 | **The work runs in that person's AI chat with the agent**, one at a time per chat. The open activities are the queue; a cron picks the oldest whose chat has no live run. | The approval card and Stop live in Discuss. A colleague does one thing at a time, and the activity list already is the inbox. |
| 4 | **Done means a note from the agent on the record and the activity marked done.** A failure or a Stop leaves it open, with the reason in the chat. | The person sees the to-do close, or stay open, like any colleague's. |
| 5 | **A person who may not use the agent gets nothing done**: the agent is taken off the activity. | The agent's "Who may use it" holds here too. |

Where it lives: `models/mail_activity.py` (the field, the queue, the
prompt, marking done), `views/mail_activity_views.xml` (the field in the
schedule dialog), `runtime/slices.py` (`_after` calls `_pan_ai_finish`),
`data/ir_cron.xml` (the queue and the 24-hour expiry),
`tests/test_activity.py`.

Dropped: a record assigned to an agent (its `user_id`): that needs a user,
so a seat. An automation rule that schedules an activity with "Done by
agent" set is Odoo's own and needs no code from us.

## 4. Slice 3: agents in team channels (decided, not built)

Decided in [agent-identity.md](agent-identity.md) after reading thirteen
sources: in a shared channel an agent without a user answers with what
every member of the channel may read (the intersection of their read
rights), and writes stay the asker's, with their Allow. Tools we cannot
filter (server actions, MCP) are off there. No seat. The asker's rights
alone were dropped: that is the OpenID Foundation's "CFO in a channel"
disclosure.

## 5. What it costs

**No Odoo user per agent.** An agent is a character (a partner with a name
and a face), not a user, so five agents cost nothing extra on Enterprise.
It works with the rights of the person it works for: in their AI chat, and
on the to-dos they hand it. A dedicated user stays possible for an agent
that needs rights of its own; that one is a seat on Enterprise.

Not done, on purpose: an archived user, like OdooBot, as the agent. Odoo
counts active users only (`mail/models/update.py`), but it treats an
archived user as gone everywhere a colleague needs to be: the invite search
and mention suggestions require `user_ids.active`, mentions in a channel go
through `partner.user_ids` (active only), and archiving a user archives its
partner (`base/models/res_users.py`). Working around that is working around
the licence.

## 6. Success, and how it is measured

**Success: people give the agent work the way they give a colleague work,
and it finishes that work without anybody redoing it.**

| Metric | What it counts | Where it comes from |
|---|---|---|
| Work done (the one number) | Colleague runs that end Done (a mention, a direct message, later an activity), plus activities the agent marked done, per database per week | `pan_ai.run` (`status = ok`) joined to its thread's channel: a thread under a message, a direct chat; `mail.activity` done by the agent's user |
| Redo rate (guardrail) | Colleague runs the person stopped or that failed, as a share of all colleague runs | `pan_ai.run.status` in `cancelled`, `failed` |
| Adoption | Connected databases with at least one agent that answers in Discuss and at least one colleague run that week | the daily heartbeat (step 3) |

A Stop is the person saying "not like that", so it counts as a redo. Approve
or Skip is not stored per call today; it is not a metric until it is.

Today the numbers exist only inside each database. On our own Odoo they are
one `record_aggregate` on `pan_ai.run` through Odoo MCP Pro. Customers'
numbers need step 3.

## 7. The steps, each with a gate

| # | Step | Done when | Gate to the next step |
|---|---|---|---|
| 1 | Slice 1, direct messages (PR #57) | merged; it lands on 19.0 and 20.0, and `odoo.pantalytics.com` deploys it | CI green, the browser check passes |
| 2 | Dogfood on `odoo.pantalytics.com` for two weeks: one agent with a dedicated user, the team messages and mentions it for real work | two weeks of runs | **15 or more colleague runs Done a week, redo rate under 10%.** Below that, find out why before building more |
| 3 | Measure customers: the heartbeat sends colleague runs per week (Done, Stopped, Failed) and the number of colleague agents. The server's request model in `odoo-mcp-pro-admin` takes the new counts first, the module sends them second | the numbers show per database on the platform | numbers arrive from at least our own database |
| 4 | Approval rules A1, A2, A8 (section 8), then slice 2, an activity is a to-do (section 3), with A3, A5, A6 | built, tested, shipped | on our own Odoo: **10 or more activities a week for the agent, 80% marked done by it, median 15 minutes from assigned to done** |
| 5 | Slice 3, the agent in a team: a short recipe in the docs and the brand site's AI Pro page | published | **25% of connected databases have a colleague agent with a Done run in the week, 8 weeks after step 4 ships** |
| 6 | Outside agents (Claude Code, Codex) as members, [#56](https://github.com/pantalytics/pan_ai_pro/issues/56) | only when step 5's number is met | none set |

Not on the path: approving a background run outside Discuss
([#58](https://github.com/pantalytics/pan_ai_pro/issues/58)). Slice 2
does not need it, because its work runs in a direct chat.

## 8. Approval: Odoo has no undo

A write in Odoo cannot be taken back with one key. A confirmed order, a
posted invoice, an email an automation sent on a stage change: once done,
a person fixes it by hand, if at all. So the agent asks **before**, and what
it asks has to be something a person can judge in five seconds.

What exists today: every built-in write (`create_record`, `write_record`),
every server action and every MCP tool asks by default; the card says "The
agent wants to run write_record" with the arguments as JSON; Allow and Skip
are the asker's; a background run that asks can only be stopped (#58).

### The rules

| # | Rule | Why |
|---|---|---|
| A1 | **The card shows the effect, not the call.** "Change lead *Acme*: Expected revenue 0 → 25,000; Stage New → Qualified." "Create contact *Acme BV*, email info@acme.nl." Field labels and current values are read as the agent's user when the call is proposed. A server action shows its name and the records; an MCP tool its own description and arguments (we cannot know its effect). | Nobody approves JSON well. Without undo, the person has to see what changes. |
| A2 | **What you approved is what happens.** The proposal keeps the record's `write_date`. If the record changed before Allow, the call does not run: the agent is told it changed, reads it again and proposes again. | An Allow given on stale values is a write nobody saw. |
| A3 | **An approval expires after 24 hours.** The run stops, the agent says so in the chat, an activity stays open. | Allowing a three-day-old change to a quote is a guess. |
| A4 | **Only the person who gave the work decides**: who asked, mentioned, messaged or assigned the activity. Not the rest of the channel, not an admin on their behalf. | One person is accountable for a write. Already so in channels. |
| A5 | **An approval always waits in a chat of the person who decides.** A run with a dedicated user asks in that person's direct chat with the agent; one that runs as the person asks in their own AI chat with it. Background runs (automation rules, schedules, watches) follow the same rule, which closes #58. | The card and Stop live in Discuss; Discuss pings the person on their phone. |
| A6 | **Several calls, one decision.** The card lists every pending change with Allow all and Skip all, and each line can still be skipped alone. | A to-do of five updates should not be five round trips. |
| A7 | **After, the trail is in the record.** The write is the agent's user's, so Odoo's own tracking shows old → new in the chatter, and the agent's note names who allowed it, with a link to the run. | Without undo, the next best thing is knowing exactly what changed, by whom, on whose word. |
| A8 | **Each Allow and Skip is logged on the run.** | The skip rate is the quality metric for proposals (section 6): a high one means the agent proposes the wrong change. |

### Dropped, on purpose

- **An undo button.** AI Pro could keep the old values and write them back,
  but not the email the stage change sent, nor the order an automation
  confirmed. An undo that works only sometimes is worse than none.
- **Delete.** The built-in tools cannot delete and will not. A server action
  an admin added can; it asks like any other.
- **Auto-allow by amount or by model.** An admin can already switch off the
  question per tool. A rule engine on top is a case nobody asked for.

### Order of work

A1, A2 and A8 first (step 4): they improve every approval that exists
today. A3, A5 and A6 come with slice 2, which needs approvals that wait
while nobody watches.

## 9. The character

People warm to a colleague with a face and a name. Every agent gets one.

- **A face from the start.** A new agent gets a portrait in the brand's
  character style (brand.pantalytics.com, design philosophy: animals in
  Japanese ink, navy lines, one purple bloom, cream paper, no robots):
  fox, owl, heron, otter, hare, badger, picked by the agent's id
  (`static/img/characters/`, made with Flux on the brand's character
  preset). An uploaded photo replaces it. Existing agents get one on
  upgrade.
- **The name is the character's.** "Ava", with "Sales assistant" as the
  line under it, on the agent's partner: what people see in their AI chat,
  on a to-do and on the note it leaves. An agent with a dedicated user gives
  that user its name and photo too; the agent is the source.

Dropped: a picker for the six portraits (upload replaces the default, and
that is enough), a personality field (the instructions are the personality).
