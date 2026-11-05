# Plan: the agent as a colleague

Status: slice 1 (direct messages) built in 2.11.0, 2026-11-05. Slice 2
(activities) is designed here, not built. Slice 3 (teams) needs no code.

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
| Give an agent work | An activity assigned to Ava | **slice 2, designed** |
| An agent in a team or project | Ava as a member of a sales team, helpdesk team, project | **slice 3, no code** |
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
2. A person assigns Ava an activity on a lead, a ticket or a task. Ava does
   it, posts what she did in the record's chatter and marks the activity
   done.
3. Ava sits in a sales team or helpdesk team like any member, and the team's
   own assignment gives her work through the same activities.

Not: an agent that picks up work nobody gave it, reads channels it was not
invited to, or decides on its own writes.

## 2. Slice 1: a direct message (built)

```
admin: agent > Access > runs as a dedicated user (Ava), Answers in Discuss
person opens a direct chat with Ava, like with any colleague
person: "which quotes for Acme are still open?"
  │  message_post on the chat
  ├─ the other member is the dedicated user of an agent that answers in Discuss
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
| `models/agent.py` | the switch is called "Answers in Discuss" |
| `static/src/chat/compat.js` | `agentMayAnswer`: the AI chat, a thread under a message, a direct chat |
| `tests/test_direct_message.py` | the flow, a chat between people, the switch off, refusal, approval by the asker |

## 3. Slice 2: an activity is a to-do for Ava (designed)

Activities are how every Odoo app gives a person work: CRM, Helpdesk,
Project, Accounting, all of them. A to-do for Ava is an activity with
`user_id` = Ava.

```
Sam schedules an activity on lead "Acme", assigned to Ava:
  "Call back: ask for their budget and log it on the lead"
  │  mail.activity create (or user_id changed to Ava)
  ├─ Ava's agent works as a colleague; Sam is an internal user
  ├─ the work runs in the direct chat Sam and Ava share (slice 1):
  │    Ava: "Working on: Call back on Acme (Lead)" ... streams, approval card
  ├─ the thread carries the record (res_model, res_id) as its context
  └─ done: Ava's answer as a note in the lead's chatter,
           the activity marked done with that answer as its feedback
```

| # | Decision | Why |
|---|---|---|
| 1 | **The work runs in the direct chat between the assigner and Ava.** | A run that writes needs an approval card and a Stop button, and they live in Discuss. The chatter has neither. The assigner sees Ava work, the way a manager sees a colleague's message. |
| 2 | **The assigner is the caller**: their hourly limit, their Allow and Skip. The run is Ava's reach. | One person is accountable for a write, as in a channel. |
| 3 | **One at a time per chat.** A second activity for Ava from Sam waits until the first is done; the open activity is the queue. A cron picks the oldest open one whose chat has no live run. | A colleague does one thing at a time, and the activity list already is Ava's inbox. No new queue model. |
| 4 | **Done means the activity is marked done** (`action_feedback` with the answer). A failure or a Stop leaves it open, with the reason in the chat. | The person sees the to-do close, or stay open, like any colleague's. |
| 5 | **An activity made by OdooBot does not start work.** Ava posts on the record that a person must assign it. | Nobody could approve its writes. |
| 6 | **The same switch**, relabelled "Works as a colleague": mention, direct message and activities. | One idea, one switch. A second switch for activities is a case nobody asked for. |

Where it lives: `models/mail_activity.py` (create and write hooks, the
pick-up cron), `models/discuss_channel.py` (open the chat and start the run
with the record as context), `runtime/slices.py` (`_after` marks the
activity done), `tests/test_activity.py`.

Dropped: a record assigned to Ava (its `user_id`) without an activity does
nothing. The fields differ per app and carry no question. An automation
rule "when assigned to Ava, schedule an activity" is Odoo's own and needs
no code from us.

## 4. Slice 3: Ava in a team (no code)

Ava is an internal user, so every team takes her as a member: a sales team,
a helpdesk team, a project's followers. Odoo's own assignment rules then
give her leads and tickets, and with slice 2's automation rule each of them
becomes an activity she works on. The docs get a short recipe; AI Pro gets
no screen for it.

## 5. What it costs

On Odoo Enterprise every internal user is a paid user, so an AI colleague
takes a seat. On Community it is free. Ava must be internal: a portal user
cannot be mentioned or invited (plans/agent-in-discuss.md, section 6).
