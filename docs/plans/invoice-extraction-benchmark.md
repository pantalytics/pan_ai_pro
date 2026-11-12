# Plan: benchmark Odoo bill digitization against LLM extraction

Status: plan done 2026-11-12. Nothing run yet, step 1 next. First customer: Giraffe
Coffee Roasters.

## Conclusion

Nobody has published how accurate Odoo's bill digitization is. Odoo gives
no figures, and the numbers online are vendor claims with no method behind
them. Mistral has no invoice-field score either: its OCR 4 figures
(OlmOCRBench 85.2, OmniDocBench 93.1) measure text recognition, not
"is the total right". So we run the benchmark ourselves. That gap is also
the blog post.

## What is known

| Source | What it measures | Result |
|---|---|---|
| Odoo docs (19.0) | Nothing. "OCR and AI", 1 IAP credit per document | No accuracy figure |
| [Odoo IAP privacy policy](https://iap.odoo.com/privacy) | Who processes the bill | Google Vision does the OCR (EU region). The field extraction is Odoo's own, not named; no LLM provider is listed for it. Files kept 6 months to improve the service |
| Fraunhofer IAIS, [arXiv 2509.04469](https://arxiv.org/html/2509.04469v1) | Field accuracy, exact match, zero-shot | Clean invoices: Gemini 2.5 Pro 96.5, GPT-5 96.0. Scanned invoices: Gemini 2.5 Pro 92.7, GPT-5 88.0. Receipts: Gemini 2.5 Pro 87.5. Image in beats PDF-to-text-then-LLM by 10 to 40 points |
| Mistral OCR 4 ([VentureBeat](https://venturebeat.com/data/mistral-launches-ocr-4-turning-document-extraction-into-a-full-enterprise-ai-play), June 2026) | Text, layout | OlmOCRBench 85.2, OmniDocBench 93.1. $4 / 1,000 pages ($2 batch) |
| [Docsumo, 120 docs](https://www.docsumo.com/blog/docsumo-ocr-benchmark) | Mistral OCR (older) text, then GPT-4o for fields | 63.6% of key-value pairs right. Vendor-run |
| [Nanonets IDP leaderboard](https://benchmarking.nanonets.com/benchmarks/idp) | KIE on invoices, receipts, forms | Gemini 3 Flash on top. Run by a vendor on its own data |

The Fraunhofer result decides the design: an OCR step in front of the LLM
loses information. Odoo is built exactly that way (Google Vision text,
then its own model), so the hypothesis is that an image-in LLM beats it.
Mistral OCR earns its place on bad scans only, and the test must show
whether it does.

## Test data

Two sets. The public one makes the blog reproducible, the private one
answers Giraffe's question.

1. **Public: the Fraunhofer sets**, so our numbers line up with theirs.
   - Clean Invoices: 500 synthetic invoices from the Donut paper.
   - Scanned Invoices: inv-cdip, 350 scanned US invoices (tobacco archive).
   - Dropped: SROIE and CORD, those are till receipts, not bills.
   Check each licence before we publish numbers on it.
2. **Private: 50 real Giraffe vendor bills**, already booked and checked by
   their accountant. The booking is the ground truth. Giraffe books in
   Exact Online today: the purchase entries plus their attached PDF come
   out of the Exact API, so nobody has to type a truth file. Mix: green
   coffee importers (often USD, often foreign), packaging, energy, small
   Dutch suppliers, at least 10 phone photos or bad scans. Lives in
   `.data/` of `odoo-customer-giraffecoffee`, gitignored, never in the blog.

## Contestants

| Engine | How it runs |
|---|---|
| Odoo digitization | Odoo's Extract API (`extract.api.odoo.com`, invoice route), straight from the script with an IAP account token. Same service Odoo calls, no database needed |
| Gemini 2.5 Pro and Flash, image in | OpenRouter, native PDF |
| Claude Sonnet, image in | OpenRouter, native PDF |
| GPT-5, image in | OpenRouter, native PDF |
| Mistral OCR 4 then Mistral Small | OpenRouter `file-parser` plugin, engine `mistral-ocr` |
| Mistral Document AI | Mistral's own API, OCR 4 with a JSON schema. The EU-hosted option |

Same JSON schema and prompt for all LLM runs. Temperature 0. We pass
Odoo's Extract API the same hints Odoo sends (`user_company_vat`,
`user_lang`, `perspective`), so it is not handicapped.

## Fields and scoring

Score per field, not per page. The fields are the ones Odoo returns:
supplier VAT number, supplier name, bill reference, bill date, due date,
currency, untaxed amount, tax, total, IBAN, and lines (description,
quantity, unit price). A field counts when it equals the truth after
normalising dates, whitespace and decimal separators.

Vendor: scored on the VAT number, since that is what finds the partner in
Odoo, with the name as fallback for suppliers without one. Dropped: Odoo's
own partner lookup inside the database. The raw API and the LLMs both
return text, so the comparison stays fair.

Report per engine: field accuracy, share of bills with every header field
right ("post without touching"), cost per bill, seconds per bill. Odoo
returns a confidence per field: also report its accuracy on the fields it
is sure of, since Odoo leaves the rest empty.

## The harness

One script, `scripts/bench_invoices.py` in this repo. It reads a folder of
PDFs plus `truth.csv`, runs each engine, caches every raw answer to disk
(a rerun costs nothing), writes `results.csv` and a markdown table.
Develop against Odoo's free integration token (rate-limited per day),
then one paid run.

## Budget

We may spend on this. Estimate for one full run, about 900 documents:

| Item | Cost |
|---|---|
| Odoo IAP credits, 1 per document | about EUR 100 (EUR 0.05 to 0.15 a credit, by pack size) |
| Six LLM engines via OpenRouter and Mistral | about EUR 100 |
| Margin for reruns | EUR 100 |
| **Total** | **under EUR 300** |

## Steps

1. Harness plus the public sets, tested on the free Odoo token. No spend.
2. Paid run on the public sets. Numbers for the blog.
3. Export 50 Giraffe bills from Exact, paid run. Numbers for Giraffe.
4. Blog, forum post, Giraffe advice.
5. AI Pro PDF reading, only if step 3 says so.

## Outputs

1. Giraffe: one table, and a recommendation: keep Odoo digitization or
   route bills through AI Pro.
2. Blog on pantalytics.com, then a forum post on odoo.com linking to it,
   with the public-set numbers and the harness.
3. AI Pro, only if an LLM wins clearly on the Giraffe set: let an agent
   read a PDF attachment, with the PDF engine (native or `mistral-ocr`) as
   a setting on the model. Today AI Pro sends no files to the model.
