# S5: built-in tools through OpenRouter

**Claim.** Pydantic AI's web search streams through OpenRouter on the three
model families we care about, and code execution does too.

**How.** `probe.py`: for each of `anthropic/claude-sonnet-5.5`,
`openai/gpt-5.6-terra` and `google/gemini-3.8-flash`, four runs over
`run_stream_events`: a function tool (baseline), the `WebSearch`
capability with OpenRouter's native server tool, the OpenRouter `web`
plugin through the `:online` suffix, and `CodeExecutionTool` as a raw
native tool. Key from Bitwarden (`OPENROUTER_API_KEY`), never printed.

```bash
OPENROUTER_API_KEY=... python probe.py
```

**Result, 2026-10-19: half the claim holds.** Pydantic AI 2.31.1.

| | Sonnet 5.5 | GPT 5.6 terra | Gemini 3.8 flash |
|---|---|---|---|
| function tool, streamed | ok, first token 1.4 s | ok, 1.4 s | ok, 13 s (upstream slow that day) |
| `WebSearch` native (`openrouter:web_search`) | ok, 3.5 s, 13.3k tokens | ok, 5.5 s, 8.5k tokens | ok, 6.4 s, 0.7k tokens |
| `:online` plugin | ok, 3.5 s, 13.3k tokens | ok, 4.4 s, 8.8k tokens | aborted (upstream 429) |
| `CodeExecutionTool` | refused by Pydantic AI: the OpenRouter model supports `WebSearchTool` and `AdvisorTool` only | same | same |

**What this decides.**

1. **Web search ships in v1 as `WebSearch(native=WebSearchTool(max_uses=…,
   search_context_size='low'))` on the agent**, on any model OpenRouter
   serves. It is the same server tool the `:online` suffix uses, with the
   knobs exposed. The search is invisible to the event stream (no
   `NativeToolCallPart` came back on any model), so the window's "Searching
   the web" row comes from the capability being on, not from an event.
2. **Web search is paid in tokens, not only per request.** The results ride
   into the context: 8 to 13k input tokens on Sonnet and GPT for one
   question. `max_uses` and `search_context_size` are the budget, and the
   Runs list must show it. Quality was poor on a live-news question (no
   BBC headline found); that is the engine, and the prompt should say
   when to search.
3. **No code execution through OpenRouter.** Pydantic AI's OpenRouter
   model does not carry `CodeExecutionTool`, on any model. Code execution
   waits for a later version, as its own sandbox or a direct provider
   client; v1 is web search only, as the plan's hard call said.
4. **Pydantic AI 2.31 attaches native tools as capabilities:**
   `Agent(model, capabilities=[WebSearch(...)])`, `NativeTool(tool)` for
   a raw one; there is no `builtin_tools=` argument, and `result.usage` is
   a property. `WebSearch(local=True)` would add a DuckDuckGo fallback for
   models without a native search (`pydantic-ai-slim[duckduckgo]`), not
   measured here.

**Key budget seen:** the shared key has a 50 USD limit with 44 used; the
probe cost under 0.3 USD.
