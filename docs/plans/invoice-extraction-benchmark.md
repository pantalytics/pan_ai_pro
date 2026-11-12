# Plan: benchmark Odoo bill digitization against LLM extraction

Status: step 1 done 2026-11-12 (harness, Donut set). Step 2 waits on keys. First customer: Giraffe
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

1. **Public: Donut synthetic invoices** (`katanaml-org/invoices-donut-data-v1`,
   MIT, 501 bills), the "Clean Invoices" set of Fraunhofer, so our numbers
   line up with theirs. We use a fixed random sample of 150 to stay in budget.
   - Dropped: inv-cdip (Fraunhofer's scanned set). Its licence is CC BY-NC,
     and our blog is marketing. Scans are covered by the Giraffe set.
   - Dropped: SROIE and CORD, those are till receipts, not bills.
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
right ("post without touching"), line accuracy, cost per bill, seconds per
bill. The Extract API ranks candidates but returns no confidence score, so
no confidence analysis.

## The harness

`scripts/bench/prepare_donut.py` downloads the Donut set and wraps each
image in a PDF. `scripts/bench/bench_invoices.py` reads a folder of PDFs
plus `truth.jsonl`, runs each engine, caches every raw answer (a rerun
costs nothing), writes `results.csv` and `summary.md`. It stops starting
calls once the cached spend passes `--max-eur`. Odoo's free integration
token worked on 2026-11-12 (one bill, 7 seconds).

## Budget

Hard cap EUR 100 for everything, enforced by `--max-eur 100`.

| Item | Bills | Cost |
|---|---|---|
| Odoo IAP credits | 200 (150 Donut, 50 Giraffe) | about EUR 25 (EUR 0.10 to 0.15 a credit) |
| Seven LLM engines | 200 each | about EUR 30, GPT and Gemini Pro the dearest |
| Reruns and margin | | EUR 45 |

## Steps

1. Harness plus the Donut set, tested on the free Odoo token. Done.
2. Paid run on 150 Donut bills. Numbers for the blog.
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
