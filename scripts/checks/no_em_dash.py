#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Fail if an em-dash (U+2014) appears in user-facing prose.

Em-dashes are a tell-tale sign of unedited AI text; we use a hyphen, comma, or
period instead (see .claude/rules/conventions.md).

Scope: the prose (markdown) and everything a person reads on screen (the
views, the data records, the chat bundle). Python is left out: its strings
are checked where they are rendered, and its comments are not copy.

Usage:
    python scripts/checks/no_em_dash.py [path ...]

With no args it checks the default prose paths. Exits non-zero on any hit.
"""

from __future__ import annotations

import sys
from pathlib import Path

EM_DASH = "—"

DEFAULT_PATHS = [
    "README.md",
    "docs",
    "pan_ai_pro/views",
    "pan_ai_pro/data",
    "pan_ai_pro/static/src",
]


def iter_files(paths: list[str]):
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for pattern in ("*.md", "*.xml", "*.js", "*.scss"):
                yield from sorted(p.rglob(pattern))
        elif p.is_file():
            yield p


def main(argv: list[str]) -> int:
    paths = argv[1:] or DEFAULT_PATHS
    hits: list[str] = []
    for f in iter_files(paths):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if EM_DASH in line:
                hits.append(f"{f}:{lineno}: {line.strip()}")

    if hits:
        print("Em-dash found in user-facing text (use a hyphen, comma, or period):")
        for h in hits:
            print(f"  {h}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
