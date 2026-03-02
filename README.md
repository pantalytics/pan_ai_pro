<p align="center">
  <img src="pan_ai_pro/static/description/icon.png" alt="Pan AI Pro" width="128" />
</p>

<h1 align="center">Pan AI Pro</h1>

<p align="center">
  <strong>Use Claude (Anthropic) as your Odoo 19 AI provider.</strong><br>
  Agents, tool calling, RAG, and web search — all out of the box.
</p>

<p align="center">
  <a href="https://github.com/pantalytics/pan_ai_pro/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-LGPL--3-blue.svg" alt="License: LGPL-3"></a>
  <img src="https://img.shields.io/badge/Odoo-19-purple.svg" alt="Odoo 19">
  <img src="https://img.shields.io/badge/Claude-Opus_|_Sonnet_|_Haiku-orange.svg" alt="Claude Models">
</p>

---

## What This Does

Odoo 19 ships with OpenAI and Google Gemini as AI providers. This module adds **Anthropic Claude** as a third option — same UI, same agents, same tools.

| Feature | Details |
|---------|---------|
| **AI Agents** | Claude works with Odoo's full agent system — topics, tools, system prompts, RAG |
| **Tool Calling** | Claude calls Odoo server actions to search, create, and update records |
| **Web Search** | Per-agent toggle for real-time web search (Anthropic server-side) |
| **RAG / Sources** | Attach PDFs, knowledge articles, websites — Claude uses them as context |
| **Structured Output** | JSON schema support for machine-readable responses |
| **File Support** | Images, PDFs, and text files processed natively by Claude |

## Supported Models

| Model | Best For |
|-------|----------|
| **Claude Opus 4.6** | Complex reasoning, analysis, long-form content |
| **Claude Sonnet 4.6** | Daily productivity — best speed/intelligence balance |
| **Claude Haiku 4.5** | High-volume tasks — fast and cost-effective |

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
