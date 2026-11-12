#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Benchmark bill extraction: Odoo's digitization against LLMs, per field.

Input: a folder with PDFs and truth.jsonl (one bill per line, the fields of
FIELDS plus "lines"; null means "not scored"). prepare_donut.py makes one.
Every engine answer is cached in OUT/raw/<engine>/<id>.json, so a rerun
only pays for what is missing. Then OUT/results.csv and OUT/summary.md.

Keys come from the environment:
    ODOO_IAP_TOKEN      IAP account token; default "integration_token" (free, rate-limited)
    OPENROUTER_API_KEY  for the OpenRouter engines
    MISTRAL_API_KEY     for mistral-docai

Usage:
    python scripts/bench/bench_invoices.py DATA OUT --engines odoo,gemini-flash
    python scripts/bench/bench_invoices.py DATA OUT --score-only
Plan: docs/plans/invoice-extraction-benchmark.md. Stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import csv
import difflib
import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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
# EN 16931 VAT category codes (UNCL5305), the vocabulary of EU e-invoices.
TREATMENTS = ["S", "Z", "E", "AE", "K", "G", "O"]

# name -> (kind, model). Model ids checked on openrouter.ai/api/v1/models, 2026-11-12.
ENGINES = {
    "odoo": ("odoo", "invoice/2"),
    "gemini-flash": ("openrouter", "google/gemini-3.8-flash"),
    "gemini-pro": ("openrouter", "google/gemini-3.1-pro-preview"),
    "gemini-2.5-pro": ("openrouter", "google/gemini-2.5-pro"),  # Fraunhofer's best, as anchor
    "claude-sonnet": ("openrouter", "anthropic/claude-sonnet-5.5"),
    "gpt": ("openrouter", "openai/gpt-5.5"),
    "mistral-ocr": ("openrouter-ocr", "mistralai/mistral-medium-3-5"),
    "mistral-docai": ("mistral", "mistral-ocr-latest"),
}

# Fields an engine does not produce, so they are not held against it.
NOT_PRODUCED = {"odoo": {"vat_treatment"}}

ODOO_URL = "https://extract.api.odoo.com/api/extract/invoice/2"
ODOO_VERSION = 123
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MISTRAL_URL = "https://api.mistral.ai/v1/ocr"

PROMPT = (
    "This is a bill we received from a supplier. Extract the fields of the JSON schema. "
    "The vendor is the company that issued the bill. Dates as YYYY-MM-DD. Amounts as plain "
    "numbers, no currency sign or thousands separator. Use null for anything not on the bill."
)


def _s(desc: str) -> dict:
    return {"type": ["string", "null"], "description": desc}


def _n(desc: str) -> dict:
    return {"type": ["number", "null"], "description": desc}


LINE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(LINE_FIELDS),
    "properties": {
        "description": _s("Line description as printed"),
        "quantity": _n("Quantity"),
        "unit_price": _n("Price per unit before tax"),
        "tax_rate": _n("VAT rate of this line in percent, 0 when no VAT is charged"),
    },
}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [*FIELDS, "lines"],
    "properties": {
        "vendor_name": _s("Name of the company that issued the bill, without its address"),
        "vendor_vat": _s("The vendor's VAT number or tax id, as printed"),
        "invoice_ref": _s("The bill number"),
        "invoice_date": _s("Bill date, YYYY-MM-DD"),
        "due_date": _s("Due date, YYYY-MM-DD"),
        "currency": _s("ISO 4217 code, e.g. EUR"),
        "untaxed": _n("Total before tax"),
        "tax": _n("Total tax"),
        "total": _n("Total including tax"),
        "iban": _s("The vendor's IBAN"),
        "vat_treatment": {
            "anyOf": [{"type": "string", "enum": TREATMENTS}, {"type": "null"}],
            "description": "EN 16931 VAT category of the bill: S standard rate (any rate above "
            "0), Z zero rated, E exempt, AE reverse charge, K intra-community supply, G export "
            "outside the EU, O outside the scope of VAT",
        },
        "lines": {"type": "array", "items": LINE_SCHEMA},
    },
}


def post(url: str, body: dict, headers: dict | None = None, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}") from None


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def loose_json(text: str) -> dict:
    """Parse a model answer, tolerating a ```json fence around it."""
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m[0] if m else text)


# --- engines: each returns (prediction, raw answer, cost in USD) ---------------


def run_odoo(path: Path, _model: str, cfg: dict) -> tuple[dict, dict, float]:
    token = os.environ.get("ODOO_IAP_TOKEN", "integration_token")
    infos = {k: v for k, v in cfg["user_infos"].items() if v}
    rpc = {"jsonrpc": "2.0", "method": "call", "id": 1}
    params = {"account_token": token, "version": ODOO_VERSION, "documents": [b64(path)]}
    parsed = post(f"{ODOO_URL}/parse", {**rpc, "params": {**params, "user_infos": infos}})
    res = parsed.get("result", parsed)
    if res.get("status") != "success":
        raise RuntimeError(f"parse: {res.get('status')} {res.get('status_msg', '')}")
    get = {"account_token": token, "version": ODOO_VERSION, "document_token": res["document_token"]}
    for _ in range(120):
        time.sleep(5)
        out = post(f"{ODOO_URL}/get_result", {**rpc, "params": get}).get("result", {})
        status = out.get("status", "")
        if status == "success":
            break
        if not status.startswith(("processing", "waiting")):
            raise RuntimeError(f"get_result: {status} {out.get('status_msg', '')}")
    else:
        raise RuntimeError("get_result: timeout")
    doc = out["results"][0]

    def val(feature: str):
        sel = (doc.get(feature) or {}).get("selected_value") or {}
        return sel.get("content")

    pred = {
        "vendor_name": val("supplier"),
        "vendor_vat": val("VAT_Number"),
        "invoice_ref": val("invoice_id"),
        "invoice_date": val("date"),
        "due_date": val("due_date"),
        "currency": val("currency"),
        "untaxed": val("subtotal"),
        "tax": val("total_tax_amount"),
        "total": val("total"),
        "iban": val("iban"),
        "vat_treatment": None,  # Odoo reads rates only; treatment comes from the fiscal position
        "lines": [
            {
                **{k: line.get(k) for k in LINE_FIELDS if k != "tax_rate"},
                "tax_rate": (line.get("taxes") or [None])[0],
            }
            for line in doc.get("invoice_lines") or []
        ],
    }
    doc.pop("full_text_annotation", None)  # keep the cache small
    return pred, doc, 0.0 if token == "integration_token" else cfg["odoo_credit_usd"]


def run_openrouter(path: Path, model: str, cfg: dict, pdf_engine: str = "native"):
    key = os.environ["OPENROUTER_API_KEY"]
    data = f"data:application/pdf;base64,{b64(path)}"
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "file", "file": {"filename": path.name, "file_data": data}},
                ],
            }
        ],
        "plugins": [{"id": "file-parser", "pdf": {"engine": pdf_engine}}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "bill", "strict": True, "schema": SCHEMA},
        },
        "usage": {"include": True},
    }
    out = post(OPENROUTER_URL, body, {"Authorization": f"Bearer {key}"})
    if "error" in out:
        raise RuntimeError(f"openrouter: {out['error']}")
    pred = loose_json(out["choices"][0]["message"]["content"])
    return pred, out, float((out.get("usage") or {}).get("cost") or 0)


def run_openrouter_ocr(path: Path, model: str, cfg: dict):
    return run_openrouter(path, model, cfg, pdf_engine="mistral-ocr")


def run_mistral(path: Path, model: str, cfg: dict):
    key = os.environ["MISTRAL_API_KEY"]
    body = {
        "model": model,
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64(path)}",
        },
        "document_annotation_format": {
            "type": "json_schema",
            "json_schema": {"name": "bill", "strict": True, "schema": SCHEMA},
        },
    }
    out = post(MISTRAL_URL, body, {"Authorization": f"Bearer {key}"})
    pred = loose_json(out.get("document_annotation") or "{}")
    pages = (out.get("usage_info") or {}).get("pages_processed") or 1
    for page in out.get("pages", []):
        page.pop("markdown", None)
        page.pop("images", None)
    return pred, out, pages * cfg["mistral_page_usd"]


RUNNERS = {
    "odoo": run_odoo,
    "openrouter": run_openrouter,
    "openrouter-ocr": run_openrouter_ocr,
    "mistral": run_mistral,
}


def spent_eur(out: Path, usd_eur: float) -> float:
    """What every cached answer cost, so the budget holds across runs."""
    files = (out / "raw").glob("*/*.json") if (out / "raw").exists() else []
    return sum(json.loads(f.read_text()).get("cost_usd", 0) for f in files) * usd_eur


def run_one(engine: str, doc: dict, data: Path, out: Path, cfg: dict) -> str:
    cache = out / "raw" / engine / f"{doc['id']}.json"
    if cache.exists() and not (cfg["retry_errors"] and json.loads(cache.read_text()).get("error")):
        return "cached"
    with cfg["lock"]:
        if cfg["spent"] >= cfg["max_eur"]:
            return "skipped, budget spent"
    kind, model = ENGINES[engine]
    start = time.monotonic()
    try:
        pred, raw, cost = RUNNERS[kind](data / doc["file"], model, cfg)
        entry = {"pred": pred, "cost_usd": cost, "raw": raw}
    except Exception as e:  # noqa: BLE001 - one bad bill must not stop the run
        entry = {"error": f"{type(e).__name__}: {e}"}
    entry["seconds"] = round(time.monotonic() - start, 2)
    with cfg["lock"]:
        cfg["spent"] += entry.get("cost_usd", 0) * cfg["usd_eur"]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(entry, ensure_ascii=False, indent=1))
    return "error" if "error" in entry else "ok"


# --- scoring ---------------------------------------------------------------------


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", type=Path, help="folder with PDFs and truth.jsonl")
    ap.add_argument("out", type=Path, help="folder for the cache and the results")
    ap.add_argument("--engines", default=",".join(ENGINES), help="comma separated")
    ap.add_argument("--limit", type=int, default=0, help="only the first N bills")
    ap.add_argument("--sample", type=int, default=0, help="N bills at random, same N same bills")
    ap.add_argument("--max-eur", type=float, default=100, help="stop starting calls past this")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--retry-errors", action="store_true")
    ap.add_argument("--usd-eur", type=float, default=0.86)
    ap.add_argument("--odoo-credit-usd", type=float, default=0.12, help="price of 1 IAP credit")
    ap.add_argument("--mistral-page-usd", type=float, default=0.007, help="OCR plus annotation")
    ap.add_argument("--company-vat", help="our VAT number, sent to Odoo as a hint")
    ap.add_argument("--company-name")
    ap.add_argument("--country", help="ISO code, e.g. NL")
    ap.add_argument("--lang", help="e.g. nl_NL")
    args = ap.parse_args()
    engines = [e for e in args.engines.split(",") if e]
    unknown = set(engines) - set(ENGINES)
    if unknown:
        ap.error(f"unknown engines: {', '.join(sorted(unknown))}")
    if not args.score_only:
        cfg = {
            "lock": threading.Lock(),
            "spent": spent_eur(args.out, args.usd_eur),
            "max_eur": args.max_eur,
            "usd_eur": args.usd_eur,
            "retry_errors": args.retry_errors,
            "odoo_credit_usd": args.odoo_credit_usd,
            "mistral_page_usd": args.mistral_page_usd,
            "user_infos": {
                "user_company_vat": args.company_vat,
                "user_company_name": args.company_name,
                "user_company_country_code": args.country,
                "user_lang": args.lang,
                "perspective": "client",
            },
        }
        docs = [json.loads(line) for line in (args.data / "truth.jsonl").open()]
        docs = docs[: args.limit] if args.limit else docs
        if args.sample and args.sample < len(docs):
            docs = random.Random(42).sample(docs, args.sample)
        jobs = [(e, d) for e in engines for d in docs]
        with ThreadPoolExecutor(args.workers) as pool:
            done = pool.map(lambda j: (j, run_one(j[0], j[1], args.data, args.out, cfg)), jobs)
            for (engine, doc), status in done:
                print(f"{engine:15} {doc['id']:24} {status}")
        print(f"Spent so far: EUR {cfg['spent']:.2f} of {args.max_eur:.2f}")
    score(args.data, args.out, engines, args.usd_eur)


if __name__ == "__main__":
    main()
