# Pan AI Pro

Adds Claude (Anthropic) as an AI provider to the standard Odoo 19 AI module.

## What This Module Does

Odoo 19 ships with a built-in `ai` module supporting OpenAI and Google Gemini. This module extends it with Anthropic Claude support — same UI, same agent system, just one more provider.

**What you get:**
- Claude models available in the AI agent model selector
- API key configuration in Settings → AI
- Full tool calling support for Claude
- Works with all existing Odoo AI features (agents, topics, RAG, etc.)

**Supported Models:**
- Claude Opus 4.6 (`claude-opus-4-6`)
- Claude Sonnet 4.6 (`claude-sonnet-4-6`)
- Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)

---

## Installation

### As Git Submodule (Odoo.sh)

1. In Odoo.sh, go to **Settings → Submodules**
2. Click **Add submodule**
3. Enter: `git@github.com:pantalytics/pan_ai_pro.git`
4. Copy the **Public Key** and add it as Deploy Key in GitHub

```bash
# Local: add submodule
git submodule add git@github.com:pantalytics/pan_ai_pro.git addons/pan_ai_pro
git commit -m "Add pan_ai_pro submodule"
git push
```

### Python Dependencies

```bash
pip install anthropic
```

### Prerequisites

- Odoo 19 Enterprise with the `ai` module installed
- Anthropic API key from [console.anthropic.com](https://console.anthropic.com/)

---

## Setup

1. Install the module via **Apps**
2. Go to **Settings** → **AI** section
3. Enable **"Use your own Anthropic account"**
4. Paste your Anthropic API key
5. Create or edit an AI Agent → select a Claude model from the dropdown

---

## Troubleshooting

### Claude models don't appear in agent dropdown

1. Verify the module is installed (Apps → search "Pan AI Pro")
2. Upgrade the module if recently updated

### API calls fail

1. Verify your API key in Settings → AI
2. Check Odoo logs for error details
3. Confirm the `anthropic` Python package is installed

---

## Security

| Aspect | Implementation |
|--------|----------------|
| API key storage | `ir.config_parameter` (standard Odoo) |
| Key access | System admin only (`base.group_system`) |
| Environment variable | `ODOO_AI_CLAUDE_TOKEN` (optional override) |

See [ARCHITECTURE.md](ARCHITECTURE.md) for technical details.

---

## Development

See [ARCHITECTURE.md](ARCHITECTURE.md) for:
- How the Odoo 19 AI module works
- What this module extends
- Adding new Claude models

### Running Tests

```bash
cd .local
docker-compose stop odoo
docker-compose run --rm odoo python -m odoo -c /etc/odoo/odoo.conf \
  -d test_db -u pan_ai_pro --test-enable --test-tags=pan_ai_pro --stop-after-init
docker-compose start odoo
```
