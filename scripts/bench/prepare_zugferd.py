#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Turn the official EN 16931 sample invoices into a bench set with VAT truth.

Source: the ZUGFeRD corpus (github.com/ZUGFeRD/corpus, Apache-2.0), which
holds the FeRD and FNFE Factur-X samples. Each PDF carries its invoice as
CII XML; that XML is the truth, VAT category per line included (S standard,
E exempt, K intra-EU, G export, AE reverse charge, Z zero, O out of scope).
The XML is stripped from the PDF we hand to the engines, or they would not
need to read the page. Duplicates (same number, same seller) are dropped.

Usage:
    pip install pypdf
    python scripts/bench/prepare_zugferd.py CORPUS_DIR OUT_DIR

Writes OUT_DIR/<id>.pdf and OUT_DIR/truth.jsonl for bench_invoices.py.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pypdf


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def find(node, *path: str):
    """First descendant chain by local names, any namespace prefix."""
    for name in path:
        node = next((c for c in node.iter() if c is not node and local(c.tag) == name), None)
        if node is None:
            return None
    return node


def text(node, *path: str) -> str | None:
    n = find(node, *path)
    return n.text.strip() if n is not None and n.text else None


def num(v: str | None) -> float | None:
    return float(v) if v not in (None, "") else None


def cii_date(v: str | None) -> str | None:
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", v or "")
    return f"{m[1]}-{m[2]}-{m[3]}" if m else None


def truth_from_xml(xml: bytes, doc_id: str) -> dict | None:
    root = ET.fromstring(xml)
    seller = find(root, "SellerTradeParty")
    totals = find(root, "SpecifiedTradeSettlementHeaderMonetarySummation")
    if seller is None or totals is None:
        return None
    vat = next(
        (
            r.text.strip()
            for r in seller.iter()
            if local(r.tag) == "ID" and r.get("schemeID") == "VA" and r.text
        ),
        None,
    )
    lines = []
    for item in (n for n in root.iter() if local(n.tag) == "IncludedSupplyChainTradeLineItem"):
        tax = find(item, "SpecifiedLineTradeSettlement", "ApplicableTradeTax")
        lines.append(
            {
                "description": text(item, "SpecifiedTradeProduct", "Name"),
                "quantity": num(text(item, "SpecifiedLineTradeDelivery", "BilledQuantity")),
                "unit_price": num(text(item, "NetPriceProductTradePrice", "ChargeAmount")),
                "tax_rate": num(text(tax, "RateApplicablePercent")) if tax is not None else None,
                "vat_category": text(tax, "CategoryCode") if tax is not None else None,
            }
        )
    cats = sorted({x["vat_category"] for x in lines if x["vat_category"]})
    if not cats:  # BASIC WL profile: no lines, only the VAT breakdown in the header
        settlement = find(root, "ApplicableHeaderTradeSettlement")
        cats = sorted(
            {
                c.text.strip()
                for t in (settlement.iter() if settlement is not None else ())
                if local(t.tag) == "ApplicableTradeTax"
                for c in t
                if local(c.tag) == "CategoryCode" and c.text
            }
        )
    if not cats:
        return None
    return {
        "id": doc_id,
        "file": f"{doc_id}.pdf",
        "vendor_name": text(seller, "Name"),
        "vendor_vat": vat,
        "vendor_country": text(seller, "CountryID"),
        "invoice_ref": text(find(root, "ExchangedDocument"), "ID"),
        "invoice_date": cii_date(text(root, "IssueDateTime", "DateTimeString")),
        "due_date": cii_date(text(root, "DueDateDateTime", "DateTimeString")),
        "currency": text(root, "InvoiceCurrencyCode"),
        "untaxed": num(text(totals, "TaxBasisTotalAmount")),
        "tax": num(text(totals, "TaxTotalAmount")),
        "total": num(text(totals, "GrandTotalAmount")),
        "iban": text(root, "IBANID"),
        "vat_treatment": "+".join(cats),
        "lines": lines,
    }


def strip_pdf(reader: pypdf.PdfReader) -> bytes:
    """The pages only: no embedded files, no XMP metadata."""
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("corpus", type=Path, help="a checkout of github.com/ZUGFeRD/corpus")
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    seen, rows = set(), []
    for path in sorted(args.corpus.rglob("*.pdf")):
        rel = str(path.relative_to(args.corpus))
        if "/fail" in rel or rel.startswith("ZUGFeRDv1"):  # broken on purpose, or no VAT detail
            continue
        try:
            reader = pypdf.PdfReader(str(path))
            xml = next(
                (v[0] for k, v in reader.attachments.items() if k.lower().endswith(".xml")), None
            )
            truth = xml and truth_from_xml(xml, f"zugferd-{len(rows):03d}")
        except Exception:  # noqa: BLE001 - a corpus file we cannot read is skipped
            continue
        if not truth or (truth["invoice_ref"], truth["vendor_name"]) in seen:
            continue
        seen.add((truth["invoice_ref"], truth["vendor_name"]))
        truth["source"] = rel
        (args.out / truth["file"]).write_bytes(strip_pdf(reader))
        rows.append(truth)
    with (args.out / "truth.jsonl").open("w") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    cats: dict[str, int] = {}
    for r in rows:
        cats[r["vat_treatment"]] = cats.get(r["vat_treatment"], 0) + 1
    print(f"{len(rows)} invoices in {args.out}; VAT categories: {cats}")


if __name__ == "__main__":
    main()
