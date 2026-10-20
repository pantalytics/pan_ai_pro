# AI Pro for Odoo

Pydantic AI agents and AI fields inside your Odoo, on your own OpenRouter
key, with any model. Odoo 19 and 20, Community and Enterprise, one module.

- **Chat** in Odoo's own chat window, bottom right: streaming answers, tool
  calls you can see, approvals before anything is created or changed, Stop.
  The sparkle top right, or Ctrl+K "Ask AI".
- **Agents are identities.** An agent runs as the person who asks, or as a
  dedicated Odoo user you set up. Its groups, record rules and roles are the
  agent's reach. Every tool runs through the ORM; nothing is sudo'ed.
- **Runs on a schedule, on a rule, or continuously.** The server action
  "Run AI agent" works in automation rules and scheduled actions. A
  continuous thread watches a model and wakes up when records change.
- **AI fields.** Write a prompt on any stored field; the agent fills it.
  Auto fill for empty records, auto update nightly for values whose inputs
  changed, a value a person typed is left alone.
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
3. Settings > AI Pro: Connect to Pantalytics, paste an OpenRouter key, pick
   a default model.
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
