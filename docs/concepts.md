# The words AI Pro uses

The screen uses plain words. The code and the architecture use Pydantic AI's
names, so a developer can read its documentation and recognise every record.

| On screen | What it is | Pydantic AI | Record |
|---|---|---|---|
| Agent | Answers questions and acts in Odoo, with a model, instructions and tools | `Agent` | `pan_ai.agent` |
| Model | The language model an agent thinks with, picked per agent | `model` | `pan_ai.model` |
| Tool group | A set of tools an agent may use: Odoo records, server actions, or a connected (MCP) server | `Toolset` | `pan_ai.toolset` |
| Tool | One thing an agent can do, like search records or create one | `Tool` | `pan_ai.tool` |
| Conversation | Everything said with an agent about one subject, kept so the agent remembers | conversation (message history) | `pan_ai.thread` |
| Activity, a run | One question to one answer, with the tools it called, the tokens and the cost | `agent.run()` | `pan_ai.run` |

## Three levels

1. **Start.** Settings > AI Pro: connect, save a key, ask the agent that is
   already there. Nothing to configure.
2. **Agents.** Name, model, instructions, which tool groups it may use, who
   may use it.
3. **Deeper.** The tools inside a tool group, models, AI fields; and in
   developer mode the agent's Advanced tab (model settings, usage limits,
   output type).

A Member never sees any of this: they ask from the sparkle or Ctrl+K.
