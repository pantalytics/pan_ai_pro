#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Fail if a source file is missing the Pantalytics copyright and licence header.

The Elastic License 2.0 forbids removing or obscuring the licensor's notices,
so the notice has to be in every file a copier would take. This check keeps it
there.

Usage:
    python scripts/checks/license_header.py        # check
    python scripts/checks/license_header.py --fix  # add the header where missing
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COPYRIGHT = "Copyright 2025-2026 Pantalytics B.V. All rights reserved."
SPDX = "SPDX-License-Identifier: Elastic-2.0"

# How each file type writes the two lines, and which first line must stay first.
STYLES = {
    ".py": (lambda t: f"# {t}", ("#!",)),
    ".js": (lambda t: f"// {t}", ("/** @odoo-module",)),
    ".scss": (lambda t: f"// {t}", ()),
    ".xml": (lambda t: f"<!-- {t} -->", ("<?xml",)),
}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", *(f"*{ext}" for ext in STYLES)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [Path(line) for line in out.splitlines() if line and not line.startswith(".claude/")]


def header(path: Path) -> list[str]:
    comment, _ = STYLES[path.suffix]
    return [comment(COPYRIGHT), comment(SPDX)]


def has_header(lines: list[str]) -> bool:
    return any(SPDX in line for line in lines[:5])


def add_header(path: Path, lines: list[str]) -> list[str]:
    _, keep_first = STYLES[path.suffix]
    at = 1 if lines and lines[0].startswith(keep_first or ("\0",)) else 0
    return lines[:at] + header(path) + lines[at:]


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    missing: list[Path] = []
    for path in tracked_files():
        full = REPO_ROOT / path
        if not full.is_file():
            continue
        text = full.read_text(encoding="utf-8")
        lines = text.splitlines()
        if has_header(lines):
            continue
        if fix:
            full.write_text("\n".join(add_header(path, lines)) + "\n", encoding="utf-8")
        else:
            missing.append(path)

    if missing:
        print("Files without the Pantalytics licence header:")
        for path in missing:
            print(f"  {path}")
        print("Run: python scripts/checks/license_header.py --fix")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
