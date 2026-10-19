#!/usr/bin/env python3
"""Fail if a Python file grows past its line budget.

Default budget is 500 lines per file (see .claude/rules/conventions.md). Files
that were already over budget when this check landed are frozen at their size
in loc_baseline.json: they may shrink but never grow. The baseline is a
ratchet, not an allowlist - do not raise numbers or add new entries; create a
new module instead.

Usage:
    python scripts/checks/loc_budget.py                    # check
    python scripts/checks/loc_budget.py --update-baseline  # ratchet down only

--update-baseline lowers baseline entries to the current line count and drops
entries for files that are deleted or back under budget. It never raises a
number and never adds an entry.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

LIMIT = 500
REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).resolve().parent / "loc_baseline.json"


def tracked_python_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [Path(line) for line in out.splitlines() if line and not line.startswith(".claude/")]


def count_lines(path: Path) -> int:
    return len((REPO_ROOT / path).read_text(encoding="utf-8").splitlines())


def main(argv: list[str]) -> int:
    baseline: dict[str, int] = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    counts = {str(f): count_lines(f) for f in tracked_python_files() if (REPO_ROOT / f).is_file()}

    if "--update-baseline" in argv:
        new_baseline = {
            path: min(counts[path], frozen)
            for path, frozen in baseline.items()
            if counts.get(path, 0) > LIMIT
        }
        BASELINE_PATH.write_text(
            json.dumps(new_baseline, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Baseline ratcheted: {len(new_baseline)} files still over {LIMIT} lines.")
        return 0

    failures: list[str] = []
    for path, lines in sorted(counts.items()):
        budget = baseline.get(path, LIMIT)
        if lines > budget:
            failures.append(f"  {path}: {lines} lines (budget {budget})")

    if failures:
        print(f"Files over their line budget (default {LIMIT}):")
        for f in failures:
            print(f)
        print(
            "Split the new code into its own module instead of growing the file.\n"
            "Frozen legacy files (scripts/checks/loc_baseline.json) may only shrink;\n"
            "after shrinking one, run: python scripts/checks/loc_budget.py --update-baseline"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
