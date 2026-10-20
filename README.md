# AI Pro for Odoo

AI agents in Odoo, with you in control. Bring your own OpenRouter key
and pick any model. Give agents your own tools: server actions and any MCP
server. Decide what each agent may touch, approve every change, and see
what every run cost. Community and Enterprise, Odoo 19 and 20, one module.

- **Chat.** Ask from Odoo's own chat window: the sparkle top right, or
  Ctrl+K "Ask AI". Answers stream in, tool calls are shown, nothing is
  created or changed until you press Allow, and Stop works mid-answer.
- **Agents.** Each agent has its own instructions, model, tools, limits and
  web search. It runs as the person who asks, or as a dedicated Odoo user
  you set up. That user's groups and record rules are the agent's reach.
  Every tool runs through the ORM; nothing is sudo'ed.
- **Tools.** Built-ins search, read, total, create, update and open records.
  A server action marked "Use in AI" becomes a tool, and any MCP server can
  be added as a toolset. Tools that change data ask for approval.
- **Automations.** The server action "Run AI agent" works in automation
  rules and scheduled actions, and posts its answer in the record's chatter
  or as an activity. A continuous thread watches a model and wakes up when
  records change.
- **AI fields.** Write a prompt on any stored field and the agent fills it.
  Auto fill for empty records, auto update for values whose inputs changed,
  and a value a person typed is left alone. On Enterprise, Odoo's own AI
  fields run on AI Pro (`pan_ai_pro_enterprise`).
- **Control.** Every run is logged with its tokens and cost. Limits per run
  and per user per hour, a retention period, an allow list for MCP hosts.
- **Source available** under the Elastic License 2.0. A connection to
  Pantalytics is required to run (Settings > AI Pro > Connect to
  Pantalytics), the same pairing as Mail Pro.

## Install

1. Put `pan_ai_pro` (and `pan_ai_pro_enterprise` on Enterprise) in your
   addons path. Odoo.sh and Cloudpepper install the repository's `requirements.txt`
   on pull (it points at `pan_ai_pro/requirements.txt`); elsewhere
   `pip install -r pan_ai_pro/requirements.txt`. On Odoo's
   Docker image install them in a venv over the system packages
   (`python3 -m venv --system-site-packages`), the way `.github/workflows/ci.yml` does.
2. Install AI Pro from Apps.
3. Settings > AI Pro: Connect to Pantalytics and paste an OpenRouter key.
   Each agent picks its model from AI Pro > Configuration > Models.
4. Press the sparkle top right and ask something.

## Documentation

- [docs/architecture-20.md](docs/architecture-20.md): the objects, the
  boxes, one chat turn, rights, money, the decisions.
- [docs/plans/ai-pro-20.md](docs/plans/ai-pro-20.md): why, and what Odoo 20
  changed.
- [docs/plans/ai-pro-20-execution.md](docs/plans/ai-pro-20-execution.md):
  the checklist and the gates.
- [docs/protocol.md](docs/protocol.md): the contract with the Pantalytics
  platform.

## Development

```bash
pip install -r pan_ai_pro/requirements.txt
odoo -d dev -i pan_ai_pro --test-enable --test-tags /pan_ai_pro --stop-after-init
python scripts/browser/check_chat.py http://127.0.0.1:8080 admin admin   # a real browser against a real server
```

`scripts/browser/fake_platform.py` and `fake_openrouter.py` stand in for
the platform and the model host; CI runs the whole thing
(`.github/workflows/ci.yml`) on Odoo 19 and 20. Work lands on `main`;
`19.0` and `20.0` mirror it on every push (`.github/workflows/mirror.yml`),
because Odoo.sh and Cloudpepper attach a branch named after the Odoo
version. Nobody commits to a mirror.

## License

AI Pro is not open source. You can read the code, run it on your own Odoo
and change it for your own use. That is where it stops. Under the
[Elastic License 2.0](LICENSE) you may not:

- offer AI Pro, or a modified copy, to others as a hosted or managed service;
- remove, disable or work around the connection to Pantalytics, or anything
  that connection unlocks;
- remove or hide the copyright and license notices, including the header at
  the top of every file.

Doing any of these ends your license. From then on every copy you run or
hand out is copyright infringement, and we will treat it that way.

Every installation pairs with Pantalytics and reports in daily, and every
file carries our notice. A copy that has the check taken out still reads as
ours. We look for copies, on the Odoo app store and on GitHub, and we
enforce.

Want to resell or bundle AI Pro? Talk to us first:
[rutger@pantalytics.com](mailto:rutger@pantalytics.com). Built by
[Pantalytics](https://pantalytics.com). See [NOTICE](NOTICE).
