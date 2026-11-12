#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Scoring for bench_invoices.py: which fields count, and when a value is right."""

from __future__ import annotations

import csv
import difflib
import json
import re
from pathlib import Path

FIELDS = (
    "vendor_name",
    "vendor_vat",
    "invoice_ref",
    "invoice_date",
    "due_date",
    "currency",
    "untaxed",
    "tax",
    "total",
    "iban",
    "vat_treatment",
)
LINE_FIELDS = ("description", "quantity", "unit_price", "tax_rate")
# Fields an engine does not produce, so they are not held against it.
NOT_PRODUCED = {"odoo": {"vat_treatment"}}


def num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, int | float):
        return float(v)
    s = re.sub(r"[^\d.,-]", "", str(v))
    last = max(s.rfind(","), s.rfind("."))
    if last >= 0 and len(s) - last - 1 in (1, 2):
        s = re.sub(r"[.,]", "", s[:last]) + "." + s[last + 1 :]
    else:
        s = re.sub(r"[.,]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def code(v) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(v or "").upper())


CURRENCY_SIGNS = {"$": "USD", "€": "EUR", "£": "GBP"}


def iban_ok(v) -> bool:
    """Mod-97 check. Donut's truth IBANs were partly made by OCR ('GB82D)FU...')."""
    c = code(v)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", c):
        return False
    return int("".join(str(int(ch, 36)) for ch in c[4:] + c[:4])) % 97 == 1


def vat(v) -> str:
    """VAT without its country prefix: Odoo returns 'GB958743511' for '958-74-3511'."""
    c = code(v)
    return c[2:] if re.match(r"[A-Z]{2}\d", c) else c


def text(v) -> str:
    return re.sub(r"[^0-9a-z]+", " ", str(v or "").lower()).strip()


def date(v) -> str:
    s = str(v or "").strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}" if m else s


def same(field: str, truth, pred) -> bool:
    if field in ("untaxed", "tax", "total", "quantity", "unit_price", "tax_rate"):
        # Absolute values: a credit note prints -218.48 where its XML says 218.48.
        t, p = num(truth), num(pred)
        return p is not None and abs(abs(t) - abs(p)) < 0.005
    if field in ("invoice_date", "due_date"):
        return date(truth) == date(pred)
    if field in ("vendor_name", "description"):
        # The truth may carry the address after the name (Donut) or a GLN before
        # it (EN 16931 samples), and the page may add the legal form ("SARL"):
        # a prediction counts when one contains the other, or they are close.
        t, p = text(truth), text(pred)
        if len(p) < 4:
            return False
        return p in t or t in p or difflib.SequenceMatcher(None, t, p).ratio() >= 0.9
    if field == "vendor_vat":
        return bool(vat(pred)) and vat(truth) == vat(pred)
    if field == "currency":
        return code(truth) == code(CURRENCY_SIGNS.get(str(pred).strip(), pred))
    return bool(code(pred)) and code(truth) == code(pred)


def score(data: Path, out: Path, engines: list[str], usd_eur: float) -> None:
    truths = [json.loads(line) for line in (data / "truth.jsonl").open()]
    rows, stats = [], {}
    for engine in engines:
        st = stats[engine] = {"docs": 0, "errors": 0, "hits": 0, "n": 0, "all": 0}
        st |= {"line_hits": 0, "line_n": 0, "cost": 0.0, "secs": 0.0, "field": {}}
        for doc in truths:
            cache = out / "raw" / engine / f"{doc['id']}.json"
            if not cache.exists():
                continue
            entry = json.loads(cache.read_text())
            st["docs"] += 1
            st["secs"] += entry.get("seconds", 0)
            st["cost"] += entry.get("cost_usd", 0) * usd_eur
            pred = entry.get("pred") or {}
            st["errors"] += "error" in entry
            all_right = True
            for f in FIELDS:
                if doc.get(f) is None or f in NOT_PRODUCED.get(engine, ()):
                    continue
                if f == "iban" and not iban_ok(doc[f]):  # a broken label, not scored
                    continue
                ok = same(f, doc[f], pred.get(f))
                all_right &= ok
                st["hits"] += ok
                st["n"] += 1
                hit, n = st["field"].get(f, (0, 0))
                st["field"][f] = (hit + ok, n + 1)
                rows.append([doc["id"], engine, f, doc[f], pred.get(f), int(ok)])
            st["all"] += all_right
            plines = pred.get("lines") or []
            for i, tline in enumerate(doc.get("lines") or []):
                pline = plines[i] if i < len(plines) else {}
                for f in LINE_FIELDS:
                    if tline.get(f) is None:
                        continue
                    ok = same(f, tline[f], pline.get(f))
                    st["line_hits"] += ok
                    st["line_n"] += 1
                    rows.append([doc["id"], engine, f"line{i + 1}.{f}", tline[f], pline.get(f), ok])
    with (out / "results.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["doc", "engine", "field", "truth", "pred", "ok"])
        w.writerows(rows)

    def pct(a: float, b: float) -> str:
        return f"{100 * a / b:.1f}" if b else "-"

    used = [e for e in engines if stats[e]["docs"]]
    md = [
        f"# Bill extraction benchmark: {data.name}\n",
        "| Engine | Bills | Errors | Header fields right % | Bills fully right % "
        "| Line fields right % | EUR per bill | Seconds per bill |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in used:
        s = stats[e]
        md.append(
            f"| {e} | {s['docs']} | {s['errors']} | {pct(s['hits'], s['n'])} "
            f"| {pct(s['all'], s['docs'])} | {pct(s['line_hits'], s['line_n'])} "
            f"| {s['cost'] / s['docs']:.4f} | {s['secs'] / s['docs']:.1f} |"
        )
    md += ["", "Per field, % right:", "", "| Field | " + " | ".join(used) + " |"]
    md.append("|---" * (len(used) + 1) + "|")
    for f in FIELDS:
        cells = [pct(*stats[e]["field"].get(f, (0, 0))) for e in used]
        if any(c != "-" for c in cells):
            md.append(f"| {f} | " + " | ".join(cells) + " |")
    (out / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
