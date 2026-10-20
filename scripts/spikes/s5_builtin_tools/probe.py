# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""S5: which built-in tools stream through Pydantic AI on OpenRouter, per model.

    OPENROUTER_API_KEY=... python probe.py

For each model: a function tool (baseline), Pydantic AI's WebSearchTool
(native), the OpenRouter `web` plugin (`:online`), and CodeExecutionTool.
Prints one row per combination: ok or the error class, the event kinds
seen, the first-token time, cost. Exit code non-zero when no model has a
working web search that streams.
"""

import asyncio
import json
import os
import sys
import time

from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.capabilities import NativeTool, WebSearch
from pydantic_ai.native_tools import CodeExecutionTool, WebSearchTool
from pydantic_ai.providers.openrouter import OpenRouterProvider

MODELS = ["anthropic/claude-sonnet-5.5", "openai/gpt-5.6-terra", "google/gemini-3.8-flash"]
provider = OpenRouterProvider(api_key=os.environ["OPENROUTER_API_KEY"], app_url="https://pantalytics.com", app_title="Pantalytics S5")


def model(model_id):
    return OpenRouterModel(model_id, provider=provider)


async def run(label, agent, prompt, **kw):
    t0 = time.monotonic()
    kinds, first, text = [], None, []
    try:
        async with agent.run_stream_events(prompt, **kw) as events:
            async for ev in events:
                k = type(ev).__name__
                if k not in kinds:
                    kinds.append(k)
                if k == "PartDeltaEvent" and first is None:
                    first = round(time.monotonic() - t0, 2)
                delta = getattr(getattr(ev, "delta", None), "content_delta", None)
                if delta:
                    text.append(delta)
            res = events.result
            usage = res.usage
            usage = usage() if callable(usage) else usage
        parts = [type(p).__name__ for m in res.all_messages() for p in getattr(m, "parts", [])]
        return {"label": label, "ok": True, "first_token_s": first, "events": kinds, "parts": sorted(set(parts)), "text": "".join(text)[:160], "requests": usage.requests, "tokens": usage.total_tokens}
    except Exception as e:  # noqa: BLE001 - the error class is the finding
        return {"label": label, "ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}", "events": kinds, "after_s": round(time.monotonic() - t0, 2)}


async def main():
    rows = []
    for mid in MODELS:
        # baseline: a function tool, streamed
        a = Agent(model(mid), instructions="Use the tool for arithmetic. Answer in one short sentence.")

        @a.tool_plain
        def multiply(a_: int, b: int) -> int:
            """Multiply two integers."""
            return a_ * b

        rows.append(await run(f"{mid} | function tool", a, "What is 17 times 23?"))

        # Pydantic AI's WebSearch capability: native where the model has it (OpenRouter's server tool), no local fallback
        a = Agent(model(mid), capabilities=[WebSearch(native=WebSearchTool(max_uses=2), local=False)], instructions="Answer in one short sentence with the source's name.")
        rows.append(await run(f"{mid} | WebSearch native", a, "What is the current top headline on bbc.com?"))

        # OpenRouter's web plugin through the :online suffix
        a = Agent(model(f"{mid}:online"), instructions="Answer in one short sentence with the source's name.")
        rows.append(await run(f"{mid} | :online plugin", a, "What is the current top headline on bbc.com?"))

        # CodeExecutionTool as a raw native tool
        a = Agent(model(mid), capabilities=[NativeTool(CodeExecutionTool())], instructions="Use code execution. Answer with the number only.")
        rows.append(await run(f"{mid} | CodeExecutionTool", a, "Compute the 30th Fibonacci number."))
    print(json.dumps(rows, indent=1))
    web_ok = [r for r in rows if r["ok"] and ("WebSearch" in r["label"] or ":online" in r["label"]) and r.get("first_token_s") is not None]
    print("web search streaming on:", [r["label"] for r in web_ok])
    sys.exit(0 if web_ok else 1)


asyncio.run(main())
