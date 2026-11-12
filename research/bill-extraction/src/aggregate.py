#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Summarise repeated runs: mean and range per engine over r1, r2, r3.

Usage:
    python research/bill-extraction/src/aggregate.py RESULTS_DIR

RESULTS_DIR holds one folder per set (donut, en16931), each with one folder
per run (r1, r2, ...) that bench_invoices.py scored. Writes
RESULTS_DIR/<set>/aggregate.md and prints it. Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

METRICS = (
    ("Bookable %", "book", "book_n"),
    ("Header fields %", "hits", "n"),
    ("Line fields %", "line_hits", "line_n"),
    ("Line VAT rate %", "rate_hits", "rate_n"),
)


def main() -> None:
    root = Path(sys.argv[1])
    for set_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        runs = sorted(set_dir.glob("r*/summary.json"))
        if not runs:
            continue
        data = [json.loads(r.read_text()) for r in runs]
        engines = list(data[0])
        md = [
            f"# {set_dir.name}: {len(runs)} runs\n",
            "Mean over runs, range in brackets. Odoo was run once: two runs gave "
            "byte-identical output, so the same answers are scored in every run.\n",
            "| Engine | " + " | ".join(m[0] for m in METRICS) + " | EUR per bill |",
            "|---" * (len(METRICS) + 2) + "|",
        ]
        for e in engines:
            cells = []
            for _, hit, n in METRICS:
                vals = [100 * d[e][hit] / d[e][n] for d in data if e in d and d[e][n]]
                if not vals:
                    cells.append("-")
                    continue
                mean = sum(vals) / len(vals)
                cells.append(f"{mean:.1f} [{min(vals):.1f} to {max(vals):.1f}]")
            cost = sum(d[e]["cost"] / d[e]["docs"] for d in data if e in d) / len(data)
            md.append(f"| {e} | " + " | ".join(cells) + f" | {cost:.4f} |")
        text = "\n".join(md) + "\n"
        (set_dir / "aggregate.md").write_text(text)
        print(text)


if __name__ == "__main__":
    main()
