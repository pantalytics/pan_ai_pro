#!/usr/bin/env python3
# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Download the Donut synthetic invoices (MIT) and write them as a bench set.

The set is katanaml-org/invoices-donut-data-v1 on Hugging Face: 501 invoices,
the "Clean Invoices" set of Fraunhofer IAIS (arXiv 2509.04469). Every image
is wrapped in a one-page A4 PDF, since bills arrive as PDFs and every engine
then gets the same file.

Usage:
    python research/bill-extraction/src/prepare_donut.py OUT_DIR [--limit N]

Writes OUT_DIR/<id>.jpg (as downloaded), OUT_DIR/<id>.pdf and
OUT_DIR/truth.jsonl, each row with the dataset revision and the SHA-256 of
the source image. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import urllib.parse
import urllib.request
from pathlib import Path

DATASET = "katanaml-org/invoices-donut-data-v1"
ROWS = "https://datasets-server.huggingface.co/rows"
SPLITS = ("train", "validation", "test")
PAGE = 100


def jpeg_size(data: bytes) -> tuple[int, int]:
    """Width and height from the first SOF marker of a JPEG."""
    i = 2
    while i < len(data):
        marker, length = data[i + 1], struct.unpack(">H", data[i + 2 : i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        i += 2 + length
    raise ValueError("no SOF marker")


def jpeg_to_pdf(data: bytes) -> bytes:
    """A one-page A4 PDF that shows the JPEG full page."""
    w, h = jpeg_size(data)
    pw, ph = 595, 842
    content = f"q {pw} 0 0 {ph} 0 0 cm /Im0 Do Q".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw} {ph}] "
        "/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>".encode(),
        f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB "
        f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>\nstream\n".encode()
        + data
        + b"\nendstream",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def amount(text: str | None) -> float | None:
    """'$ 1 234,56' -> 1234.56. The last separator is the decimal one."""
    if not text:
        return None
    s = re.sub(r"[^\d.,]", "", text)
    if not s:
        return None
    last = max(s.rfind(","), s.rfind("."))
    if last >= 0 and len(s) - last - 1 in (1, 2):
        s = re.sub(r"[.,]", "", s[:last]) + "." + s[last + 1 :]
    else:
        s = re.sub(r"[.,]", "", s)
    return float(s)


def us_date(text: str | None) -> str | None:
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", (text or "").strip())
    return f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}" if m else None


def currency(summary: dict) -> str | None:
    text = summary.get("total_gross_worth") or ""
    for sign, code in (("$", "USD"), ("€", "EUR"), ("£", "GBP")):
        if sign in text:
            return code
    return None


def truth_row(doc_id: str, gt: dict) -> dict:
    head, summ = gt.get("header", {}), gt.get("summary", {})
    items = gt.get("items", [])
    if isinstance(items, dict):
        items = [items]
    return {
        "id": doc_id,
        "file": f"{doc_id}.pdf",
        "vendor_name": head.get("seller"),
        "vendor_vat": head.get("seller_tax_id"),
        "invoice_ref": head.get("invoice_no"),
        "invoice_date": us_date(head.get("invoice_date")),
        "due_date": None,
        "currency": currency(summ),
        "untaxed": amount(summ.get("total_net_worth")),
        "tax": amount(summ.get("total_vat")),
        "total": amount(summ.get("total_gross_worth")),
        "iban": head.get("iban"),
        # Who received the bill: Odoo sends its own company as a hint, so we do too.
        "buyer_name": re.split(r"\s\d", head.get("client") or "", maxsplit=1)[0].strip() or None,
        "buyer_vat": head.get("client_tax_id"),
        "lines": [
            {
                "description": it.get("item_desc"),
                "quantity": amount(it.get("item_qty")),
                "unit_price": amount(it.get("item_net_price")),
                "tax_rate": amount(it.get("item_vat")),
                "net": amount(it.get("item_net_worth")),
            }
            for it in items
        ],
    }


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--limit", type=int, default=0, help="stop after N documents")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for split in SPLITS:
        offset = 0
        while True:
            q = urllib.parse.urlencode(
                {
                    "dataset": DATASET,
                    "config": "default",
                    "split": split,
                    "offset": offset,
                    "length": PAGE,
                }
            )
            page = get_json(f"{ROWS}?{q}")
            for item in page["rows"]:
                doc_id = f"donut-{split}-{item['row_idx']:03d}"
                pdf = args.out / f"{doc_id}.pdf"
                jpg = args.out / f"{doc_id}.jpg"
                src = item["row"]["image"]["src"]
                if not jpg.exists():
                    with urllib.request.urlopen(src, timeout=60) as r:
                        jpg.write_bytes(r.read())
                if not pdf.exists():
                    pdf.write_bytes(jpeg_to_pdf(jpg.read_bytes()))
                gt = json.loads(item["row"]["ground_truth"])["gt_parse"]
                row = truth_row(doc_id, gt)
                rev = re.search(r"/--/([0-9a-f]{40})/--/", src)
                row["source"] = (
                    f"{DATASET}@{rev[1] if rev else 'unknown'}:{split}/{item['row_idx']}"
                )
                row["source_sha256"] = hashlib.sha256(jpg.read_bytes()).hexdigest()
                rows.append(row)
                if args.limit and len(rows) >= args.limit:
                    break
            offset += PAGE
            if (args.limit and len(rows) >= args.limit) or offset >= page["num_rows_total"]:
                break
        if args.limit and len(rows) >= args.limit:
            break
    with (args.out / "truth.jsonl").open("w") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    print(f"{len(rows)} documents in {args.out}")


if __name__ == "__main__":
    main()
