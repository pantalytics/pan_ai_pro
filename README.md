<p align="center">
  <img src="pan_ai_pro/static/description/icon.png" alt="Pan AI Pro" width="128" />
</p>

<h1 align="center">Pan AI Pro</h1>

<p align="center">
  <strong>Claude AI provider + Airtable-style AI Fields for Odoo 19</strong><br>
  Use Anthropic Claude for agents, tool calling, RAG, and web search — plus smart auto-fill, auto-update, and per-field AI agents for Studio AI fields.
</p>

<p align="center">
  <a href="https://github.com/pantalytics/pan_ai_pro/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-LGPL--3-blue.svg" alt="License: LGPL-3"></a>
  <img src="https://img.shields.io/badge/Odoo-19-purple.svg" alt="Odoo 19">
  <img src="https://img.shields.io/badge/Claude-Opus_|_Sonnet_|_Haiku-orange.svg" alt="Claude Models">
</p>

<p align="center">
  <img src="pan_ai_pro/static/description/ProductShowcase.gif" alt="Pan AI Pro Demo" width="800" />
</p>

> **Warning**
> This project is a **work in progress** and under active development. APIs, features, and configuration may change without notice. **Use at your own risk** — not recommended for production environments without thorough testing. No warranty is provided.

---

## What This Does

This module extends Odoo 19's built-in AI with two major capabilities:

### 1. Claude as AI Provider

Odoo 19 ships with OpenAI and Google Gemini. This module adds **Anthropic Claude** as a third provider — same UI, same agents, same tools.

| Feature | Details |
|---------|---------|
| **AI Agents** | Claude works with Odoo's full agent system — topics, tools, system prompts, RAG |
| **Tool Calling** | Claude calls Odoo server actions to search, create, and update records |
| **Web Search** | Per-agent toggle for real-time web search (Anthropic server-side) |
| **RAG / Sources** | Attach PDFs, knowledge articles, websites — Claude uses them as context |
| **Structured Output** | JSON schema support for machine-readable responses |
| **File Support** | Images, PDFs, and text files processed natively by Claude |

| Model | Best For |
|-------|----------|
| **Claude Opus 4.6** | Complex reasoning, analysis, long-form content |
| **Claude Sonnet 4.6** | Daily productivity — best speed/intelligence balance |
| **Claude Haiku 4.5** | High-volume tasks — fast and cost-effective |

### 2. Airtable-style AI Fields

Upgrades Odoo Studio's AI Fields from basic single-provider generation to a smart, configurable system — inspired by [Airtable's AI fields](https://support.airtable.com/docs/using-airtable-ai-in-fields).

| Feature | Details |
|---------|---------|
| **Per-Field Agent** | Each AI field can use a different AI agent (model, temperature, web search) |
| **Auto Fill** | Fills all records with empty values in the background via cron |
| **Auto Update** | Regenerates the value automatically when input fields change |
| **Human-Edit Protection** | Manual edits are preserved — AI skips human-edited values |
| **Stale Indicators** | Shows "Inputs changed" when source data changes (if auto-update is off) |
| **Any Provider** | AI Fields work with Claude, OpenAI, or Gemini — no longer hardcoded to OpenAI |

---

## Setup

### Prerequisites

- Odoo 19 Enterprise with the AI module installed
- Anthropic API key from [console.anthropic.com](https://console.anthropic.com/)

### Installation

**Odoo.sh** — Add as a Git submodule:

```bash
git submodule add https://github.com/pantalytics/pan_ai_pro.git addons/pan_ai_pro
git commit -m "Add pan_ai_pro submodule"
git push
```

**Self-hosted** — Clone into your addons path:

```bash
cd /path/to/odoo/addons
git clone https://github.com/pantalytics/pan_ai_pro.git
```

Then install from **Apps** → search "Pan AI Pro".

### Configuration

1. Go to **Settings → AI**
2. Enable **"Use your own Anthropic account"**
3. Paste your API key
4. Create or edit an AI Agent → select a Claude model

> **Environment variable alternative:** Set `ODOO_AI_CLAUDE_TOKEN` to skip the UI — useful for Odoo.sh and Docker deployments.

---

## AI Fields Setup

> Requires the `ai_fields` module (installed with Odoo Studio). If Studio is not installed, this feature is simply skipped.

1. Go to **Settings → AI**
2. Select a default agent in the **AI Fields Agent** dropdown
3. Optionally, override the agent per field in Studio's properties panel
4. Enable **Auto Fill** and/or **Auto Update** per field as needed

When neither auto option is enabled, the field shows an **"Inputs changed"** indicator when source data changes, and the user can click to regenerate manually.

If a user manually edits an AI-generated value, the field is marked as **human-edited** and skipped during automatic processing — AI never overwrites deliberate manual changes.

---

## Web Search

Enable the **Web Search** toggle on any Claude agent to give it access to real-time web information.

- Powered by Anthropic's native `web_search` capability
- No external services to configure
- Location-aware results using your company address
- Up to 5 searches per conversation turn

---

## How It Works

This module extends the standard Odoo 19 AI infrastructure — no custom framework.

```
Agent selects "Claude Sonnet 4.6"
  → Provider registry resolves to "anthropic"
    → LLMApiService routes to _request_llm_anthropic()
      → POST https://api.anthropic.com/v1/messages
```

All existing Odoo AI features work automatically: Ask AI, text improvement, chatter AI, AI server actions, live chat, and more.

See [ARCHITECTURE.md](ARCHITECTURE.md) for technical details.

---

## Security

| Aspect | Implementation |
|--------|----------------|
| API key storage | Standard Odoo `ir.config_parameter` |
| Access control | System admin only (`base.group_system`) |
| Environment variable | `ODOO_AI_CLAUDE_TOKEN` (optional) |

API keys are stored the same way as OpenAI and Google keys in the built-in AI module.

---

## Contributing

Contributions are welcome. Please open an issue or pull request on [GitHub](https://github.com/pantalytics/pan_ai_pro).

---

## License

[LGPL-3](LICENSE) — Built by [Pantalytics](https://github.com/pantalytics), Odoo implementation partner.
