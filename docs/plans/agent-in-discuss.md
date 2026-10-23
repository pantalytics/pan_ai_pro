# Plan: @agent in any Discuss channel

Status: proposal, 2026-10-23. Nothing built. Section 6 is what a spike must
measure before section 3 is a design.

## 0. The idea, and where it comes from

Claude Tag is Claude in Slack: you type `@Claude` in a channel, a sandbox
starts for that thread, Claude works with the channel's access and posts
the answer back in the thread. A reply in the thread picks it up again.
([how it works](https://www.claude.com/docs/claude-tag/concepts/how-it-works))

The same move in Odoo: an AI Pro agent is a member you can mention in any
Discuss channel. `@Sales assistant which quotes for Acme are still open?`
gets an answer in a thread under the message, from Odoo's own data, visible
to everybody in the channel.

Most of it exists. Every agent already has a partner (`agent.partner_id`),
the run loop, streaming over the bus, approval cards and limits are built
for the `ai` channel. What is new is a trigger outside the `ai` channel and
the question whose rights a shared answer carries.

## 1. What success looks like

1. A person in a team channel mentions an agent and the answer streams into
   a thread under their message, the way it streams in the chat window.
2. Everybody in the channel sees the same answer, and nobody sees a record
   through it that the agent's identity could not read.
3. A follow-up in the thread that mentions the agent again continues the
   same conversation, with what the people in the thread said in between.

Not: an agent that reads every channel, answers without being mentioned,
or joins a channel by itself.

## 2. The flow

```
person posts in #sales: "@Sales assistant open quotes for Acme?"
  │  message_post, partner_ids holds agent.partner_id
  ├─ the agent is allowed in channels, the person may use it, internal user
  ├─ the message gets a sub-channel (Odoo's thread under a message), once
  ├─ one pan_ai.thread on that sub-channel, kind chat
  ├─ placeholder from the agent in the sub-channel, "Thinking"
  └─ Run.start(thread, prompt, kind="chat", message=placeholder)
       same slices, same bus events, same limits as the chat window
```

The prompt is every message in the sub-channel since the agent last
answered, one line per message, `Name: text`. Only a mention starts a run;
people can talk in the thread without the agent butting in.

## 3. The decisions

| # | Decision | Why |
|---|---|---|
| 1 | **An agent in a shared channel runs as its dedicated user** (`run_as = user`), never as the person who asks. A new checkbox on the agent, "Can be mentioned in channels", is only allowed with a dedicated user. | The answer is read by the whole channel. If it ran as the asker, a manager's question would show their records to the interns in the channel. A dedicated user is a reach an admin chose on purpose, the same for every reader. This is Claude Tag's "the channel's access". |
| 2 | One sub-channel is one `pan_ai.thread`. | Slack's thread is Odoo's sub-channel (Odoo 18+). Memory stays where the people can see it. |
| 3 | The run starts only on a mention, also inside the thread. | Humans talk in threads; an agent answering every reply is noise. |
| 4 | Approval: only the person who started the run sees Allow and Skip. The rest of the channel sees "Waiting for Anna to approve". | One person is accountable for a write. |
| 5 | Runs count against the asker's hourly limit (`runs_per_user_per_hour`). | Same rule as the chat window, no new knob. |
| 6 | Channel members who may not use the agent see the answer, but their mention does nothing (a short reply: "You may not use this agent."). | Reading a message in a channel you are in is Discuss's rule, using an agent is AI Pro's. |

Dropped, on purpose:

- **The chatter on a record** (`@agent summarise this lead` in a lead's
  chatter). Valuable, but the record context, followers and notification
  rules make it its own design. Next plan, not this one.
- **Agents running as the asker in channels.** Decision 1. The direct chat
  window keeps doing that.
- **Portal and public users** in a channel. Never trigger a run.

## 4. What changes in the code

| Where | Change |
|---|---|
| `models/agent.py` | `in_channels` boolean, a constraint that it needs `run_as = user` |
| `models/discuss_channel.py` | `message_post`: on `channel`, `group` and sub-channels, when `partner_ids` holds the partner of an agent with `in_channels`, start the run in the sub-channel; the ownership checks move from "the thread's user" to "the run's user" |
| `models/thread.py` | a thread may have several people; `user_id` stays the first asker, each run keeps its own user |
| `static/src/chat/*` | the run-event and approval patches also on sub-channels that carry a `pan_ai.thread`, not only on `channel_type == "ai"` |
| `tests/` | a restricted member reads only what the agent's user may read; a mention by a non-user is refused; a reply without a mention starts nothing |

Estimate: a few days, inside the 500-line budget per file
(`discuss_channel.py` is at 193).

## 5. Why in AI Pro and not in MCP Pro

AI Pro already runs inside Odoo, with the partner, the runs and the bus.
An outside bot through MCP Pro (`agents/` in odoo-mcp-pro-admin) would need
its own Discuss bot user, a webhook out of Odoo and its own streaming, for
the same result.

## 6. Spike before building

Measure on Odoo 19 and 20, write down the date and the instance:

- the sub-channel API: creating a sub-channel from a message
  (`_create_sub_channel(from_message_id=...)` or what 19/20 call it), and
  that a member of the parent sees it without being added;
- that `pan_ai.run_event` on a sub-channel's bus reaches every member's
  open window, not only the asker's;
- that the mention autocomplete in the composer offers the agent's partner
  in a channel the agent is not a member of, or whether the agent must be
  added as a member first (then: adding it is the opt-in, and decision 6
  holds).
