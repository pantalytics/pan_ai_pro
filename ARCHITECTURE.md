# Architecture

Technical documentation for developers working on Pan AI Pro.

---

## 1. Overview

### Purpose

Extends the standard Odoo 19 `ai` module with Claude (Anthropic) as an AI provider. No custom models, no custom encryption — just hooks into the existing Odoo AI infrastructure.

### How Odoo 19 AI Works

Odoo 19 (released September 2025 at Odoo Experience, Brussels) is the first version with **native AI integration** in the core ERP. The AI features are **Enterprise Edition only**.

- **Module technical name**: `ai` (enterprise addon)
- **Pricing**: Included with Enterprise subscription; AI usage consumes **IAP credits**
- **Built-in providers**: OpenAI (GPT-3.5, GPT-4, GPT-4o, GPT-4.1, GPT-5) and Google (Gemini 1.5, 2.5)
- **Anthropic/Claude**: NOT supported natively — this is the gap `pan_ai_pro` fills

### What This Module Adds

| Component | What we do |
|-----------|------------|
| `llm_providers.py` | Register Anthropic provider + Claude models |
| `llm_api_service.py` | Add `_request_llm_anthropic()` method |
| `ai_agent.py` | `x_web_search` toggle + `_generate_response()` override |
| `ai_fields_patch.py` | Patch AI Fields to use configurable agent (optional, requires `ai_fields`) |
| `res_config_settings.py` | Add API key field + AI Fields Agent selector |
| `res_config_settings_views.xml` | Add Claude settings UI + AI Fields Agent dropdown |
| `ai_agent_views.xml` | Web search toggle widget on agent form |

---

## 2. Odoo 19 AI Module — Deep Dive

### 2.1 Core Models

#### `ai.agent`

Central configuration record for an AI agent.

| Field | Type | Description |
|-------|------|-------------|
| System Prompt | Text | Defines the agent's role, purpose, and behavior |
| LLM Model | Selection | Dropdown — supports ChatGPT and Gemini model versions |
| Response Style | Selection | Controls tone (formal, casual, etc.) |
| Topics | One2many → `ai.agent.topic` | Collection of instructions and tool bundles |
| Sources | One2many → `ai.agent.source` | Documentary sources for RAG |

#### `ai.agent.source`

Links documentary sources to agents for RAG (Retrieval-Augmented Generation):

- Knowledge articles
- PDFs and uploaded documents
- Website links
- Content is chunked and embedded via cron jobs
- Status transitions: `Processing` → `Indexed`

#### `ai.agent.topic`

Bridge between agents and Odoo data/actions:

- Bundles AI Tools (server actions) that the agent can use
- Many2many field pointing to `ir.actions.server` records
- Contains instructions specific to the topic

#### `ai.embedding`

Stores embedding vectors centrally:

- Uses PostgreSQL's **pgvector** extension (hard requirement)
- Introduces a new `Vector` field type that interfaces directly with pgvector
- Embeddings are never stored on source records directly
- Two cron jobs:
  - "AI Agent Sources: Process Sources"
  - "AI Embedding: Generate Embeddings"

#### `ir.actions.server` (Extended)

Server actions are extended with AI capabilities:

- New **"AI" type** for server actions
- **"Use in AI"** option in the Usage tab
- **AI Schema** field defines parameter names, types, and descriptions
- Parameter names in AI Schema **must match** variable names in Python code

### 2.2 Two-Level API

**Low-level: `request_llm` function**

- From the AI module's LLM API service
- Query-processing loop supporting LLM tool calling
- Developer defines: model, prompts, tools, and return schema
- Odoo orchestrates: calls AI provider → executes server-side tools → feeds results back
- Supports **structured outputs** via JSON schemas

**High-level: `ai.agent.generate_response` method**

- Wraps `request_llm` with context and configuration
- Includes system prompts, topics, sources, and RAG
- Retrieves relevant document chunks from embedded sources
- Inserts chunks into LLM context automatically

### 2.3 Prompt Assembly Sequence

When an agent processes a request:

```
1. System prompts (base instructions)
2. Agent-specific prompt (from ai.agent record)
3. Context injection (date, user info, record context, RAG chunks)
4. User message
5. API call to LLM
6. Tool execution (recursive — LLM calls tools → gets results → calls more tools)
7. Final response generation
```

### 2.4 Manager-Worker Pattern (AI Server Actions)

| Role | Description |
|------|-------------|
| **Manager** (AI Server Action) | Decision maker — reads record context, interprets prompt, decides which tool to call |
| **Worker** (Tool) | Standard server action with "Use in AI" enabled — performs record updates/writes. Reusable across multiple managers |

### 2.5 System Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ai.max_successive_calls` | 20 | Maximum recursive LLM calls |
| `ai.max_tool_calls_per_call` | 20 | Maximum tool calls per single run |

### 2.6 RAG Implementation

#### Pipeline

```
Source added → ai.agent.source record created
     ↓
Cron: text extraction + chunking (large docs are split)
     ↓
Cron: LLM API call to generate embedding vectors
     ↓
Vectors stored in ai.embedding (pgvector)
     ↓
Status: "Processing" → "Indexed"
```

#### What Gets Embedded vs. What Uses Tools

| Approach | Used For |
|----------|----------|
| **Embeddings (RAG)** | Knowledge articles, PDFs, uploaded documents, website links |
| **Tools (Server Actions)** | Standard Odoo data (leads, products, contacts) — searched via database queries, NOT semantic search |

Key architectural decision: Odoo records are accessed via tools, documents via embeddings.

#### Infrastructure Requirements

| Requirement | Detail |
|-------------|--------|
| PostgreSQL | Version 16+ with pgvector extension |
| pgvector | `CREATE EXTENSION IF NOT EXISTS vector;` on the database |
| Redis/RabbitMQ | Async worker queue for background AI calls (keeps UI responsive) |

### 2.7 Provider Configuration

#### Configuration Path

**Settings → AI** (or **AI app → Configuration → Settings**)

Under Providers:
- Tick "Use your own ChatGPT account" → paste OpenAI API key
- Tick "Use your own Google Gemini account" → paste Gemini API key

#### Architecture Details

- Base URL is configurable per provider
- Individual API endpoints are **hardcoded** per provider (OpenAI and Google API structures)
- Self-hosted LLM compatibility is uncertain without endpoint compatibility
- Different features may use different providers internally

### 2.8 Preconfigured Topics and Default Agents

#### Preconfigured Topics

- **Natural Language Search**: Interprets user queries to open Odoo views with appropriate domain filters
- **Information Retrieval**: Collection of tools to retrieve information about models
- **Create Leads**: Tools supporting automated lead creation

#### Default Prompts

- Pre-configured prompts vary based on where in the database the AI button is clicked
- Customizable via **AI app → Configuration → Default Prompts**

### 2.9 AI Features Across the Platform

| Feature | Description | Where |
|---------|-------------|-------|
| **Ask AI** | Top-bar AI button — natural language → Odoo domain filters → open views/perform actions | Everywhere |
| **Text Improvement** | Select text → AI rewrites → "Use this" to apply | Any text field |
| **Chatter AI** | Draft emails, summarize conversations, improve text — context-aware | Record chatter |
| **AI Fields** (Studio) | Prompts generate text dynamically from other record values | Studio |
| **AI Email Templates** | AI prompts embedded in email templates, evaluated at send time | Email templates |
| **AI Live Chat** | Auto-respond, qualify conversations, generate leads, escalate to humans | Live Chat |
| **AI Document Sort** | Auto-classify, route, extract info, trigger business actions | Documents |
| **AI Voice Transcription** | Audio → text + summaries | Meetings |
| **AI Webpage Generator** | Generate webpages matching business style | Website |
| **AI Server Actions** | Natural-language-driven automations (manager-worker pattern) | Server Actions |

### 2.10 Frontend / UI Integration

- **Ask AI** button in the top bar across all backend views
- Built with **OWL components** (Odoo's component framework, inspired by Vue/React)
- Chatter AI actions as buttons in the chatter composer
- Discuss app integration — AI conversations can open in full Discuss window
- Since Odoo 19.1: progressive feedback during AI processing (not just "AI is thinking")

### 2.11 Security Model

- Standard Odoo security via `ir.model.access` CSV and security groups
- Agent configuration (create/edit agents, topics, tools) → **`base.group_system`**
- Using AI features (Ask AI, text improvement) → **`base.group_user`**
- Tool execution respects the calling user's security context

### 2.12 Odoo 19.1 Updates (Post-Launch)

- Ask questions about files while previewing
- Upload files and link documents in AI agent chats
- More specific feedback during AI processing
- Time period filtering in AI-generated views
- Manual reprocessing of AI agent sources
- AI-powered SEO improvement for web pages

---

## 3. Odoo AI Provider Pattern

### Provider Dispatch Flow

```
User selects "Claude Sonnet 4" in agent config
    │
    ▼
llm_providers.get_provider(env, "claude-sonnet-4-6")
    → returns "anthropic"
    │
    ▼
LLMApiService(env, provider="anthropic")
    │
    ▼
_request_llm_anthropic(model, system_prompts, user_prompts, tools, ...)
    │
    ▼
POST https://api.anthropic.com/v1/messages
```

### Provider Registry (`llm_providers.py`)

Providers are defined as `Provider` named tuples in a `PROVIDERS` list:

```python
Provider(
    name="anthropic",
    display_name="Anthropic",
    embedding_model="...",          # Embedding model name
    embedding_config={...},         # Batch size, token limits
    llms=[                          # Available models
        ("claude-opus-4-6", "Claude Opus 4.6"),
        ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ],
)
```

Model name uniquely identifies the provider — `get_provider()` scans the list.

### API Service (`llm_api_service.py`)

Each provider needs:

1. **`__init__` routing** — base URL for the provider
2. **`_get_api_token()` routing** — config parameter key + env var name
3. **`_request_llm_{provider}()`** — Format and send the API request
4. **`_build_tool_call_response()`** — Format tool results for the provider

### API Key Management

Standard Odoo pattern — no custom encryption needed:

| Provider | Config Parameter | Environment Variable |
|----------|-----------------|---------------------|
| OpenAI | `ai.openai_key` | `ODOO_AI_CHATGPT_TOKEN` |
| Google | `ai.google_key` | `ODOO_AI_GEMINI_TOKEN` |
| **Anthropic** | **`x_ai.anthropic_key`** | **`ODOO_AI_CLAUDE_TOKEN`** |

Keys stored in `ir.config_parameter`, access restricted to `base.group_system`.

---

## 4. What We Extend

### Files We Monkey-Patch or Override

Since `llm_providers.py` and `llm_api_service.py` are plain Python (not Odoo models), we extend them by:

1. **Appending to `PROVIDERS` list** — adds Claude models to the registry
2. **Patching `LLMApiService`** — adds Anthropic routing and request method

### Anthropic Messages API

Claude uses the [Messages API](https://docs.anthropic.com/en/api/messages):

```python
# Request
POST https://api.anthropic.com/v1/messages
{
    "model": "claude-sonnet-4-6",
    "max_tokens": 4096,
    "system": "System prompt here",
    "messages": [
        {"role": "user", "content": "Hello"}
    ],
    "tools": [...]  # Optional
}

# Response
{
    "content": [
        {"type": "text", "text": "Response here"},
        {"type": "tool_use", "id": "call_123", "name": "func", "input": {...}}
    ],
    "stop_reason": "end_turn" | "tool_use"
}
```

### Tool Calling Format

Anthropic tool calling differs from OpenAI:

| Aspect | OpenAI | Anthropic |
|--------|--------|-----------|
| Tool definition | `functions` array | `tools` array with `input_schema` |
| Tool call in response | `tool_calls` field | `tool_use` content block |
| Tool result format | `tool` role message | `tool_result` content block |
| Call ID field | `tool_call_id` | `tool_use_id` |

---

## 5. Module Structure

```
pan_ai_pro/
├── models/
│   ├── __init__.py
│   ├── llm_providers.py           # Registers Anthropic provider
│   ├── llm_api_service.py         # Adds _request_llm_anthropic()
│   ├── ai_agent.py                # x_web_search toggle + response override
│   ├── ai_fields_patch.py         # Patch AI Fields for configurable agent
│   └── res_config_settings.py     # Anthropic API key + AI Fields Agent
├── views/
│   ├── res_config_settings_views.xml  # Settings UI for API key
│   └── ai_agent_views.xml             # Web search toggle on agent form
├── static/description/
│   ├── icon.png
│   └── index.html                 # Odoo app store description
├── __manifest__.py
├── __init__.py
├── README.md
├── ARCHITECTURE.md
└── CLAUDE.md
```

---

## 6. Settings UI

API key configuration follows the same pattern as OpenAI/Google in the built-in module:

```xml
<setting string="Use your own Anthropic account"
         help="Provide your API key to connect with your account"
         groups="base.group_system">
    <field name="x_anthropic_key_enabled" />
    <group invisible="not x_anthropic_key_enabled">
        <field name="x_anthropic_key" placeholder="Key" password="True" />
    </group>
</setting>
```

---

## 7. AI Fields Patch

### Problem

Odoo Studio's `ai_fields` module hardcodes OpenAI (`gpt-4.1`) in its `get_ai_value()` function. There is no configuration to select a different provider or model.

### Solution

`ai_fields_patch.py` monkey-patches two functions at module load time:

1. **`get_ai_value()`** — Replaces the hardcoded OpenAI call with a configurable one that reads the AI agent selected in Settings → AI → AI Fields Agent
2. **`_cron_fill_ai_fields()`** — Checks the configured agent's provider has a valid API key before running the batch cron

### How It Works

```
AI field triggers get_ai_value()
    │
    ▼
_get_ai_fields_config(env)
    → reads x_ai.ai_fields_agent_id from ir.config_parameter
    → browses ai.agent record
    → returns (provider, model, temperature, web_grounding)
    │
    ▼
LLMApiService(env, provider)._request_llm(...)
    → routes to _request_llm_anthropic() / _request_llm_openai() / etc.
```

### Configuration

| Setting | Storage | Description |
|---------|---------|-------------|
| AI Fields Agent | `x_ai.ai_fields_agent_id` in `ir.config_parameter` | Many2one reference to `ai.agent` |

The agent's model, response style (mapped to temperature), and web search toggle are all used.

### Optional Dependency

`ai_fields` is an optional dependency (requires Odoo Studio). The import is wrapped in a `try/except ImportError` in `models/__init__.py` — if `ai_fields` is not installed, the patch is simply skipped.

---

## 8. Design Decisions

### 8.1 Extend, Don't Replace

**Decision:** Extend the built-in `ai` module instead of building a custom provider system.

**Why:**
- Odoo 19 already has a mature AI framework
- All existing features (agents, topics, RAG, tool calling) work automatically
- No custom models or encryption to maintain
- Follows Odoo upgrade path

### 8.2 Monkey-Patching Provider Registry

**Decision:** Patch `llm_providers.PROVIDERS` and `LLMApiService` at module load time.

**Why:**
- `llm_providers.py` and `llm_api_service.py` are plain Python, not Odoo models
- Cannot use standard Odoo model inheritance (`_inherit`)
- Same approach any Odoo module would need to take for this extension point

### 8.3 No Custom Encryption

**Decision:** Use standard `ir.config_parameter` for API keys, same as OpenAI/Google.

**Why:**
- Consistent with how the built-in module stores keys
- Odoo.sh encrypts the database at rest already
- Less code to maintain

---

## 9. References

### Anthropic
- [Anthropic Messages API](https://docs.anthropic.com/en/api/messages)
- [Anthropic Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)

### Odoo Official Documentation
- [AI — Odoo 19.0 documentation](https://www.odoo.com/documentation/19.0/applications/productivity/ai.html)
- [AI Agents](https://www.odoo.com/documentation/19.0/applications/productivity/ai/agents.html)
- [AI API Keys](https://www.odoo.com/documentation/19.0/applications/productivity/ai/apikeys.html)
- [AI Fields](https://www.odoo.com/documentation/19.0/applications/productivity/ai/fields.html)
- [AI Email Templates](https://www.odoo.com/documentation/19.0/applications/productivity/ai/email-templates.html)
- [AI Live Chat](https://www.odoo.com/documentation/19.0/applications/productivity/ai/live-chat.html)
- [AI Server Actions](https://www.odoo.com/documentation/19.0/applications/productivity/ai/server-actions.html)
- [AI Voice Transcription](https://www.odoo.com/documentation/19.0/ko/applications/productivity/ai/voice.html)
- [AI Document Sort](https://www.odoo.com/documentation/19.0/fr/applications/productivity/ai/document_sort.html)
- [AI Webpage Generator](https://www.odoo.com/documentation/19.0/applications/productivity/ai/webpage.html)
- [AI Text Improvement](https://www.odoo.com/documentation/19.0/applications/productivity/ai/improve_text.html)

### Release Notes
- [Odoo 19 Release Notes](https://www.odoo.com/odoo-19-release-notes)
- [Odoo 19.1 Release Notes](https://www.odoo.com/odoo-19-1-release-notes)

### Technical Guides
- [Odoo AI Technical Guide — RAG, Embeddings & Agents (Much Consulting)](https://muchconsulting.com/blog/odoo-2/odoo-ai-technical-138)
- [Odoo AI — New App & Integrated Features (Much Consulting)](https://muchconsulting.com/blog/odoo-2/odoo-ai-app-117)
- [Developing Odoo Modules Using AI: A Practical Guide (Oduist)](https://oduist.com/blog/odoo-experience-2025-ai-summaries-2/357-developing-odoo-modules-using-ai-a-practical-guide-358)
- Odoo 19 `ai` module source: `odoo-enterprise/ai/`

### Community Resources
- [AI in Odoo 19 (OBS Solutions)](https://www.odoo-bs.com/blog/global-5/artificial-intelligence-in-odoo-19-415)
- [AI Agents in Odoo (OBS Solutions)](https://www.odoo-bs.com/blog/global-5/odoo-ai-agents-fully-integrated-ai-inside-the-erp-and-all-business-areas-464)
- [Deploying Intelligent Agents with RAG (Nalios)](https://www.nalios.com/en/blog/what-s-new-in-odoo-6/odoo-19-ai-deploying-your-own-intelligent-agents-with-rag-123)
- [How to Set Up AI Module in Odoo 19 (Sgeede)](https://sgeede.com/blog/sgeede-knowledge-4/how-to-set-up-ai-module-in-odoo-19-116)
- [Community Edition — AI Module Missing (Odoo Forum)](https://www.odoo.com/forum/help-1/community-edition-v19-ai-module-missing-292901)
- [Odoo Experience 2025 — AI Features Talk](https://www.odoo.com/event/odoo-experience-2025-6601/track/discover-the-new-odoo-ai-features-8393)
