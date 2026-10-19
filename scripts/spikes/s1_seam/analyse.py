"""Read the zip the probe produced and print what S1 asks for.

    python analyse.py pan_ai_s1_seam.zip

Prints: the modules found, their manifests' depends, the files that mention
each seam we care about, and the lines themselves for the few that decide
the design. Never prints a whole file; the zip stays local.
"""

import re
import sys
import zipfile
from collections import defaultdict

PATTERNS = {
    "ai_fields value request": r"def get_ai_value|get_ai_field_value|_fill_ai_field|def _get_ai_context|request_llm\(|\.iap_|iap\.jsonrpc|_call_iap|ai_credits|credits",
    "llm service / provider": r"class LLMApiService|def _request_llm|PROVIDERS|Provider\(|openai|gemini|anthropic|base_url",
    "systray / command": r'registry\.category\("systray"\)|category\("command_provider"\)|command_provider|systray_items|registry\.add\("ai|hotkey',
    "agent response": r"def _generate_response|def generate_response|run_stream|stream|_bus_send|ai_response",
    "server action tool": r"use_in_ai|ai_tool|_get_ai_tools|ai_schema",
    "mcp": r"ai_mcp|/mcp|mcp_",
}


def main(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    modules = sorted({n.split("/", 1)[0] for n in names})
    print("modules:", modules)
    for m in modules:
        man = f"{m}/__manifest__.py"
        if man in names:
            text = z.read(man).decode("utf-8", "replace")
            dep = re.search(r"depends['\"]?\s*:\s*\[([^\]]*)\]", text, re.S)
            print(f"\n== {m}: {sum(1 for n in names if n.startswith(m + '/'))} files; depends: {dep.group(1).strip() if dep else '?'}")
    hits = defaultdict(list)
    for n in names:
        if not n.endswith((".py", ".js", ".xml")):
            continue
        text = z.read(n).decode("utf-8", "replace")
        for label, pat in PATTERNS.items():
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(pat, line):
                    hits[label].append((n, i, line.strip()[:140]))
    for label, rows in hits.items():
        print(f"\n### {label}: {len(rows)} lines in {len({r[0] for r in rows})} files")
        for n, i, line in rows[:60]:
            print(f"  {n}:{i}: {line}")


if __name__ == "__main__":
    main(sys.argv[1])
