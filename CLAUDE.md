# Claude Code Context

Project context for Claude Code AI assistant.

## Module Overview

**pan_ai_pro** — Extends the standard Odoo 19 `ai` module with Claude (Anthropic) as an AI provider.

Does NOT build a custom AI framework. Instead, hooks into the existing Odoo AI infrastructure (provider registry, API service, agent system) and adds Anthropic support alongside the built-in OpenAI and Google providers.

## Development Principles

1. **Extend, Don't Replace** — Use the built-in Odoo `ai` module, add Claude support only
2. **Odoo 19 Compatibility** — Before every commit, verify code meets Odoo 19 requirements
3. **Minimal Footprint** — No custom models unless absolutely necessary
4. **Code Discipline** — Push back on feature requests that duplicate what Odoo already provides
5. **Follow Existing Patterns** — Match how OpenAI/Google are implemented in the base `ai` module

### Odoo 19 Checklist (verify before commit)
- [ ] No `attrs` in views → use `invisible`, `readonly`, `required` directly
- [ ] No `numbercall` on cron jobs (deprecated)
- [ ] Stored computed fields have `@api.depends` decorator
- [ ] Use `groups` attribute for field access control
- [ ] XML ids follow pattern: `module_name.record_name`
- [ ] Bump version in `__manifest__.py` (format: `19.0.X.Y.Z`)

## How Odoo 19 AI Works

### Key Source Files (in `odoo-enterprise/ai/`)

| File | Purpose |
|------|---------|
| `models/llm_providers.py` | `PROVIDERS` list — maps model names to providers |
| `models/llm_api_service.py` | `LLMApiService` class — provider-specific API calls |
| `models/ai_agent.py` | Agent config model — `_get_provider()`, `request_llm()` |
| `models/res_config_settings.py` | API key fields for each provider |
| `views/res_config_settings_views.xml` | Settings UI for API keys |

### Provider Dispatch Pattern

```
Model name → get_provider() → provider name → LLMApiService → _request_llm_{provider}()
```

- Provider determined by model name (e.g. "claude-sonnet-4-20250514" → "anthropic")
- No provider model — it's a plain Python `PROVIDERS` list
- API service routes to `_request_llm_openai()`, `_request_llm_google()`, etc.

### API Key Pattern

Keys stored in `ir.config_parameter` with env var fallback:
- `ai.openai_key` / `ODOO_AI_CHATGPT_TOKEN`
- `ai.google_key` / `ODOO_AI_GEMINI_TOKEN`
- `x_ai.anthropic_key` / `ODOO_AI_CLAUDE_TOKEN` ← we add this

## Key Files (This Module)

| File | Purpose |
|------|---------|
| `models/llm_providers.py` | Registers Anthropic provider + Claude models |
| `models/llm_api_service.py` | Adds `_request_llm_anthropic()` to API service |
| `models/ai_agent.py` | `x_web_search` toggle + `_generate_response()` override |
| `models/res_config_settings.py` | Adds Anthropic API key field to settings |
| `views/res_config_settings_views.xml` | Settings UI for Claude API key |
| `views/ai_agent_views.xml` | Web search toggle on agent form |

## Naming Conventions

- Config param: `x_ai.anthropic_key` (custom fields use `x_` prefix)
- Env var: `ODOO_AI_CLAUDE_TOKEN` (follows `ODOO_AI_CHATGPT_TOKEN` pattern)
- All custom fields/params use `x_` prefix (Odoo.sh convention)
- Log prefix: `[AI Pro]`

## Development

Shared Docker setup with pan_outlook_pro. See parent directory structure.

### Directory structure
```
~/Documents/GitHub/
├── .docker/
│   └── Dockerfile               ← Shared Dockerfile (Enterprise + deps)
├── odoo-enterprise/              ← Odoo 19 Enterprise source (reference)
│   └── ai/                       ← Built-in AI module we extend
├── pan_outlook_pro/              ← Email integration module
├── pan_ai_pro/                   ← This repo
│   └── .local/                   ← Per-repo Docker config (gitignored)
│       ├── docker-compose.yml
│       └── odoo.conf
```

### Local Docker Setup
```bash
cd .local
docker-compose up -d             # Odoo at http://localhost:8069
```

### Restart after Python changes
```bash
cd .local
docker-compose restart odoo
```

### Upgrade module
```bash
cd .local
docker-compose exec -T odoo python -m odoo -c /etc/odoo/odoo.conf -d test_db -u pan_ai_pro --stop-after-init
docker-compose restart odoo
```

### View logs
```bash
cd .local
docker-compose logs -f odoo
```

### Run unit tests
```bash
cd .local
docker-compose stop odoo
docker-compose run --rm odoo python -m odoo -c /etc/odoo/odoo.conf \
  -d test_db -u pan_ai_pro --test-enable --test-tags=pan_ai_pro --stop-after-init
docker-compose start odoo
```

## Common Tasks

### Adding a new Claude model
1. Add model tuple to `PROVIDERS` entry in `models/llm_providers.py`
2. Upgrade the module

### Debugging
1. Check Odoo logs for `[AI Pro]` tag
2. Verify API key in Settings → AI
3. Check `ir.config_parameter` for `x_ai.anthropic_key`
4. Reference `odoo-enterprise/ai/models/llm_api_service.py` for dispatch logic

## Odoo Settings Page Layout (res.config.settings)

### Two-column layout - WHAT WORKS

For custom two-column layouts in Odoo 19 settings pages, **don't use** nested `<group>` elements inside `<setting>` - they don't render side-by-side.

**Working pattern** (Bootstrap grid + Odoo CSS classes):

```xml
<h2>Section Title</h2>
<div class="row mt-4 mb-4 o_settings_container">
    <div class="col-12 col-lg-6 o_setting_box">
        <div class="o_setting_left_pane"/>
        <div class="o_setting_right_pane">
            <span class="o_form_label">Column Title</span>
            <div class="content-group">
                <div class="row mt-2">
                    <label class="col-lg-3 o_light_label" for="field_name">Label</label>
                    <field name="field_name"/>
                </div>
            </div>
        </div>
    </div>
</div>
```

## Context Management

After every `/compact`, update the **Lessons Learned** section below with new insights from the session.

## Lessons Learned

- The built-in Odoo 19 `ai` module uses plain Python files (`llm_providers.py`, `llm_api_service.py`), not Odoo models, for provider dispatch. Extension requires monkey-patching, not model inheritance.
- API keys follow `ai.{provider}_key` naming in `ir.config_parameter` with `ODOO_AI_{NAME}_TOKEN` env var fallback.
- Provider is determined by model name — no separate provider configuration model.

## Documentation

- [README.md](README.md) - Setup instructions for users
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical details for developers
