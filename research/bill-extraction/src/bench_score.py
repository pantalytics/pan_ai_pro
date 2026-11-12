#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Scoring for bench_invoices.py: which fields count, and when a value is right."""

from __future__ import annotations

import csv
import difflib
import json
import math
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


# What an accountant needs to book the bill. A bill is "bookable" when all of
# these are right; due date, IBAN and line descriptions are for paying and
# reading, not for booking, and VAT category is reported on its own.
BOOKING = ("vendor", "invoice_ref", "invoice_date", "currency", "untaxed", "tax", "total")


def breakdown(lines: list[dict], truth: bool) -> dict[float, float] | None:
    """Net amount per VAT rate. Merged lines with the right total per rate are
    as bookable as split ones (Odoo itself offers one line per tax)."""
    out: dict[float, float] = {}
    for line in lines:
        rate = num(line.get("tax_rate"))
        net = num(line.get("net")) if truth or line.get("net") is not None else None
        if net is None:
            q, p = num(line.get("quantity")), num(line.get("unit_price"))
            net = q * p if q is not None and p is not None else None
        if rate is None or net is None:
            if truth:
                return None  # truth incomplete: not scored
            continue
        out[rate] = out.get(rate, 0.0) + abs(net)
    return out


def breakdown_of(doc: dict, truth: bool) -> dict[float, float] | None:
    """The bill's VAT summary as rate -> base: the printed table when there is
    one (it carries document-level discounts), else built from the lines."""
    table: dict[float, float] = {}
    for r in doc.get("vat_breakdown") or []:
        rate, base = num(r.get("rate")), num(r.get("base"))
        if rate is not None and base is not None:
            table[rate] = table.get(rate, 0.0) + abs(base)
    return table or breakdown(doc.get("lines") or [], truth)


def breakdown_ok(truth: dict | None, pred: dict | None) -> bool:
    if not pred or set(truth) != set(pred):
        return False
    return all(abs(truth[r] - pred[r]) <= 0.05 for r in truth)


# Strict mode: the scoring rules as first written, before we looked at any
# answer. The default rules were adjusted after inspecting LLM errors (see
# the paper, section Deviations); strict mode lets anyone see the effect.
STRICT = False


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n."""
    if not n:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def same(field: str, truth, pred) -> bool:
    if field in ("untaxed", "tax", "total", "quantity", "unit_price", "tax_rate"):
        t, p = num(truth), num(pred)
        if p is None:
            return False
        if STRICT:
            return abs(t - p) < 0.005
        # Absolute values: a credit note prints -218.48 where its XML says 218.48.
        return abs(abs(t) - abs(p)) < 0.005
    if field in ("invoice_date", "due_date"):
        return date(truth) == date(pred)
    if field in ("vendor_name", "description"):
        # The truth may carry the address after the name (Donut) or a GLN before
        # it (EN 16931 samples), and the page may add the legal form ("SARL"):
        # a prediction counts when one contains the other, or they are close.
        t, p = text(truth), text(pred)
        close = difflib.SequenceMatcher(None, t, p).ratio() >= 0.9
        if STRICT:
            return bool(p) and (t.startswith(p) or close)
        if len(p) < 4:
            return False
        return p in t or t in p or close
    if field == "vendor_vat":
        return bool(vat(pred)) and vat(truth) == vat(pred)
    if field == "currency":
        return code(truth) == code(CURRENCY_SIGNS.get(str(pred).strip(), pred))
    return bool(code(pred)) and code(truth) == code(pred)


def score(data: Path, out: Path, engines: list[str], usd_eur: float, strict: bool = False) -> dict:
    global STRICT
    STRICT = strict
    suffix = "_strict" if strict else ""
    truths = [json.loads(line) for line in (data / "truth.jsonl").open()]
    rows, stats = [], {}
    for engine in engines:
        st = stats[engine] = {"docs": 0, "errors": 0, "hits": 0, "n": 0, "all": 0}
        st |= {"line_hits": 0, "line_n": 0, "cost": 0.0, "secs": 0.0, "field": {}}
        st |= {"rate_hits": 0, "rate_n": 0, "book": 0, "book_n": 0, "book_field": {}}
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
                if f == "iban" and not strict and not iban_ok(doc[f]):  # broken label
                    continue
                ok = same(f, doc[f], pred.get(f))
                all_right &= ok
                st["hits"] += ok
                st["n"] += 1
                hit, n = st["field"].get(f, (0, 0))
                st["field"][f] = (hit + ok, n + 1)
                rows.append([doc["id"], engine, f, doc[f], pred.get(f), int(ok)])
            st["all"] += all_right
            # Bookable: the accountant's view of the same answer.
            vendor_key = "vendor_vat" if doc.get("vendor_vat") else "vendor_name"
            checks = {
                "vendor": same(vendor_key, doc.get(vendor_key), pred.get(vendor_key)),
                **{f: same(f, doc[f], pred.get(f)) for f in BOOKING[1:] if doc.get(f) is not None},
            }
            tb = breakdown_of(doc, truth=True)
            if tb:
                checks["vat_breakdown"] = breakdown_ok(tb, breakdown_of(pred, truth=False))
            for f, ok in checks.items():
                hit, n = st["book_field"].get(f, (0, 0))
                st["book_field"][f] = (hit + ok, n + 1)
            st["book"] += all(checks.values())
            st["book_n"] += 1
            plines = pred.get("lines") or []
            for i, tline in enumerate(doc.get("lines") or []):
                pline = plines[i] if i < len(plines) else {}
                for f in LINE_FIELDS:
                    if tline.get(f) is None:
                        continue
                    ok = same(f, tline[f], pline.get(f))
                    st["line_hits"] += ok
                    st["line_n"] += 1
                    if f == "tax_rate":
                        st["rate_hits"] += ok
                        st["rate_n"] += 1
                    rows.append([doc["id"], engine, f"line{i + 1}.{f}", tline[f], pline.get(f), ok])
    with (out / f"results{suffix}.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["doc", "engine", "field", "truth", "pred", "ok"])
        w.writerows(rows)

    def pct(a: float, b: float) -> str:
        return f"{100 * a / b:.1f}" if b else "-"

    def ci(a: int, b: int) -> str:
        lo, hi = wilson(a, b)
        return f"{100 * lo:.1f} to {100 * hi:.1f}" if b else "-"

    used = [e for e in engines if stats[e]["docs"]]
    book_fields = [*BOOKING, "vat_breakdown"]
    md = [
        f"# Bill extraction benchmark: {data.name}{' (strict scoring)' if strict else ''}\n",
        "## Bookable without correction\n",
        "A bill counts when vendor, number, date, currency, untaxed, tax, total and the net "
        "amount per VAT rate are all right.\n",
        "| Engine | Bills | Bookable % | 95% CI | " + " | ".join(book_fields) + " |",
        "|---" * (4 + len(book_fields)) + "|",
    ]
    for e in used:
        s = stats[e]
        cells = [pct(*s["book_field"].get(f, (0, 0))) for f in book_fields]
        md.append(
            f"| {e} | {s['book_n']} | {pct(s['book'], s['book_n'])} | {ci(s['book'], s['book_n'])} | "
            + " | ".join(cells)
            + " |"
        )
    md += [
        "",
        "## All fields\n",
        "| Engine | Bills | Errors | Header fields right % | 95% CI | Bills fully right % "
        "| 95% CI | Line fields right % | Line VAT rate right | EUR per bill | Seconds per bill |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for e in used:
        s = stats[e]
        rate = f"{s['rate_hits']}/{s['rate_n']}" if s["rate_n"] else "-"
        md.append(
            f"| {e} | {s['docs']} | {s['errors']} | {pct(s['hits'], s['n'])} "
            f"| {ci(s['hits'], s['n'])} | {pct(s['all'], s['docs'])} | {ci(s['all'], s['docs'])} "
            f"| {pct(s['line_hits'], s['line_n'])} | {rate} "
            f"| {s['cost'] / s['docs']:.4f} | {s['secs'] / s['docs']:.1f} |"
        )
    md += ["", "Per field, % right:", "", "| Field | " + " | ".join(used) + " |"]
    md.append("|---" * (len(used) + 1) + "|")
    for f in FIELDS:
        cells = [pct(*stats[e]["field"].get(f, (0, 0))) for e in used]
        if any(c != "-" for c in cells):
            md.append(f"| {f} | " + " | ".join(cells) + " |")
    (out / f"summary{suffix}.md").write_text("\n".join(md) + "\n")
    summary = {e: {k: v for k, v in stats[e].items()} for e in used}
    (out / f"summary{suffix}.json").write_text(json.dumps(summary, indent=1) + "\n")
    print("\n".join(md))
    return summary
