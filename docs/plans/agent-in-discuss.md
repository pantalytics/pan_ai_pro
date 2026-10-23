# Plan: @agent in any Discuss channel

Status: built in 2.10.0, 2026-10-23. The spike (section 6) changed one
decision before a line was written: the agent speaks in a channel as its
dedicated user, not as its chat identity.

## 0. The idea, and where it comes from

Claude Tag is Claude in Slack: you type `@Claude` in a channel, a sandbox
starts for that thread, Claude works with the channel's access and posts
the answer back in the thread. A reply in the thread picks it up again.
([how it works](https://www.claude.com/docs/claude-tag/concepts/how-it-works))

The same move in Odoo: an AI Pro agent is a colleague you can mention in a
Discuss channel. `@Sales assistant which quotes for Acme are still open?`
gets an answer in a thread under the message, from Odoo's own data, visible
to everybody in the channel.

Most of it existed: the run loop, streaming over the bus, approval cards and
limits were built for the `ai` channel. What is new is a trigger outside the
`ai` channel and the question whose rights a shared answer carries.

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
admin: agent > Access > runs as a dedicated user (Ava), Answers in channels
someone invites Ava to #sales, like any colleague
person posts in #sales: "@Ava open quotes for Acme?"
  │  message_post, partner_ids (named mentions) holds Ava's partner
  ├─ the agent is allowed in channels, the asker is an internal user
  ├─ the message gets Odoo's thread (sub-channel), made as the asker
  ├─ one pan_ai.thread on that sub-channel, kind chat
  ├─ placeholder from Ava in the thread, "Thinking"
  └─ Run.start(thread, prompt, kind="chat", caller=asker)
       runs as Ava; same slices, bus events and limits as the chat window
```

The prompt is every message in the thread since the agent last answered, one
line per message, `Name: text`, under one line that says where it was
mentioned. Only a mention starts a run; people can talk in the thread
without the agent butting in.

## 3. The decisions

| # | Decision | Why |
|---|---|---|
| 1 | **An agent in a shared channel runs as its dedicated user**, never as the person who asks. "Answers in channels" needs `run_as = user` (a check constraint). | The answer is read by the whole channel. If it ran as the asker, a manager's question would show their records to the interns in the channel. A dedicated user is a reach an admin chose on purpose, the same for every reader. Claude Tag's "the channel's access". |
| 2 | **In a channel the agent is its dedicated user**: people mention that user, the answer comes from that user's partner, and inviting the user to a channel is how the agent joins it. One user answers for at most one agent. | Measured in section 6: Odoo drops a mention of a partner without a user in any channel limited to a group, which is every channel by default. A real user is mentionable, invitable and filtered by Odoo's own rules with no screen of ours. |
| 3 | One thread (sub-channel) is one `pan_ai.thread`, with one agent. A second agent mentioned in it says "X answers in this thread. Ask me in a new one." | Slack's thread is Odoo's sub-channel. Memory stays where the people can see it; two agents in one thread would need two Stop buttons and two approval owners. |
| 4 | The run starts only on a mention by name, also inside the thread. `@everyone` does not count. | Humans talk in threads, and an announcement is not a question. |
| 5 | Stop, Allow and Skip are the asker's (`run.caller_id`). The rest of the channel sees the card and "Waiting for Sam to decide". | One person is accountable for a write. |
| 6 | Runs count against the asker's hourly limit. Someone who may not use the agent gets "You may not use the agent X" in its bubble. | Same rules as the chat window, no new knob. |
| 7 | Retention deletes an old thread's memory, never the people's sub-channel. | The channel's thread is theirs; the next mention starts fresh. |

Dropped, on purpose:

- **The chatter on a record** (`@agent summarise this lead`). The record
  context, followers and notifications make it its own design.
- **Agents running as the asker in channels.** Decision 1.
- **Two agents in one thread.** Decision 3.
- **Portal and public users** in a channel never start a run.

## 4. Where it lives

| Where | What |
|---|---|
| `models/agent.py` | `in_channels`, its two checks, `_mentioned(partners)` |
| `models/discuss_channel.py` | `_pan_ai_on_mention`, the thread under the message, the prompt; Stop, decide and state checked against the asker, state readable by the channel |
| `models/thread.py` | retention unlinks `ai` channels only |
| `runtime/stream.py` | every bus batch names the asker |
| `static/src/chat/` | the approval card, Stop and the reload state on threads under a message |
| `tests/test_channel_mention.py` | the flow, the prompt, `@everyone`, refusal, approval by the asker, one agent per thread, retention, the checks |

## 5. Why in AI Pro and not in MCP Pro

AI Pro already runs inside Odoo, with the runs and the bus. An outside bot
through MCP Pro (`agents/` in odoo-mcp-pro-admin) would need its own Discuss
bot user, a webhook out of Odoo and its own streaming, for the same result.

## 6. The spike, 2026-10-23

Checked against the source of Odoo 19 and 20 (the `odoo:19` and `odoo:20`
Docker images) and a running Odoo 19 with the CI's stubs, in Chromium:

- `discuss.channel._create_sub_channel(from_message_id=...)` exists on both,
  with the same shape; it adds the asker and the message's author, and the
  parent shows "X started a thread".
- `_get_allowed_message_partner_ids` keeps only partners whose users are in
  the channel's `group_public_id`, which defaults to Internal User. The
  agent's own chat partner has no user and is archived: dropped. Hence
  decision 2.
- Mention suggestions in a channel list members of the channel and its
  parent, active partners only.
- `@everyone` arrives as `special_mentions`, expanded inside `message_post`;
  the composer's `partner_ids` are the named mentions only.
- In the browser: the mention streams into the thread for the asker; a
  second member opening the thread reads the answer, sees "Waiting for
  Administrator to decide" on an approval and no buttons; the asker allows
  and both see the final answer. No JavaScript errors.
