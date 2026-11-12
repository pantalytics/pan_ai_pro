# Plan: benchmark Odoo bill digitization against LLM extraction

Status: steps 1 and 2 done 2026-11-12 (harness, Donut set, EU VAT set). Step 3 waits on the database and keys. First customer: Giraffe
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

## The question that matters: is the VAT booked right?

Reading the total is the easy part. What costs an accountant time is the
tax on each line: 21% or 9%, exempt, reverse charged ("btw verlegd"), or
foreign VAT that is not deductible. No public dataset scores this, so we
build one (EU VAT set, below).

In Odoo the reverse charge mostly comes from the vendor's fiscal position,
not from reading the bill. Reading decides it where the master data cannot:
mixed 9/21 bills, exempt lines, Dutch domestic reverse charge (an NL vendor
writing "btw verlegd"), and foreign VAT charged by an EU vendor (a German
hotel), where the EU fiscal position would wrongly book reverse charge.
Those are the scenarios that separate the engines.

## Test data

Two sets. The public one makes the blog reproducible, the private one
answers Giraffe's question.

1. **Public: Donut synthetic invoices** (`katanaml-org/invoices-donut-data-v1`,
   MIT, 501 bills), the "Clean Invoices" set of Fraunhofer, so our numbers
   line up with theirs. We use a fixed random sample of 100 to stay in budget.
   - Dropped: inv-cdip (Fraunhofer's scanned set). Its licence is CC BY-NC,
     and our blog is marketing. Scans are covered by the Giraffe set.
   - Dropped: SROIE and CORD, those are till receipts, not bills.
2. **EU VAT set, 150 bills we generate** (`scripts/bench/make_eu_vat.py`).
   Fictional vendors, born-digital PDFs, NL buyer. Nine scenarios, about
   17 bills each: NL 21%, NL 9%, NL mixed 9/21, NL exempt, NL domestic
   reverse charge, EU goods (intra-community, 0%), EU services (reverse
   charge), non-EU vendor (no VAT), foreign VAT charged (DE, BE, FR rates).
   Vendors in NL, BE, DE, FR, ES, IT, IE, UK, US, CH; labels, number and
   date formats in the vendor's language. Truth per line: net amount, VAT
   rate, treatment. We own it, so we can publish it with the blog.
   Dropped: scanned versions (the Giraffe set has real scans) and credit
   notes.
3. **Private: 50 real Giraffe vendor bills**, already booked and checked by
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

## Two levels

- **A, extraction**: the script reads each bill with every engine and
  compares fields. Cheap, and the Donut numbers line up with Fraunhofer.
- **B, booked in Odoo**: the bills go into a temporary Odoo 19 Enterprise
  database with the Dutch chart of accounts (`l10n_nl`) and the vendors
  already present with country and VAT number, as in a running company.
  Odoo's own path: upload, Odoo digitizes, read the draft bill. The LLM
  path: the script creates the draft bill from the LLM answer and picks
  each line's purchase tax from rate plus treatment, which is what an AI
  Pro agent would do. Score: right `account.tax` per line, and the bill
  total to the cent. Dropped: unknown vendors (creating partners is a
  separate question).
  Where: a new database on the Pantalytics Shared Server 19 (Cloudpepper),
  deleted afterwards. Not our staging: it is a copy of our real books and
  300 test bills would litter it.

AI Pro itself cannot read a PDF yet. The LLM path above uses the same
models through OpenRouter, so it measures what AI Pro would get. The AI
Pro feature gets built only if that path wins.

## Fields and scoring

Score per field, not per page. The fields are the ones Odoo returns:
supplier VAT number, supplier name, bill reference, bill date, due date,
currency, untaxed amount, tax, total, IBAN, and lines (description,
quantity, unit price, VAT rate) and the bill's VAT treatment. A field
counts when it equals the truth after normalising dates, whitespace and
decimal separators.

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

Hard cap EUR 100: EUR 50 on an OpenRouter key with that limit, EUR 50 of
IAP credits. The script also stops at `--max-eur`.

| Item | Bills | Cost |
|---|---|---|
| IAP credits | 100 Donut (level A), 150 EU VAT and 50 Giraffe (level B) | about EUR 45 |
| Five LLM engines via OpenRouter | 300 each | about EUR 35 |

Mistral Document AI needs its own Mistral key: out unless one appears.

## Steps

1. Harness plus the Donut set, tested on the free Odoo token. Done.
2. Generate the EU VAT set; extend the schema with VAT rate and treatment. Done.
3. Temporary Odoo database, then level A on 100 Donut bills and level B on
   the EU VAT set. Numbers for the blog. First run the same 3 EU VAT bills
   on the paid token: on the free token Odoo returned one summary line
   per bill and the word "Factuur" as vendor, and we must know whether the
   free token gives the real service.
4. Export 50 Giraffe bills from Exact, level B. Numbers for Giraffe.
5. Blog, forum post, Giraffe advice. Delete the temporary database.
6. AI Pro PDF reading, only if step 3 or 4 says so.

## Outputs

1. Giraffe: one table, and a recommendation: keep Odoo digitization or
   route bills through AI Pro.
2. Blog on pantalytics.com, then a forum post on odoo.com linking to it,
   with the public-set numbers and the harness.
3. AI Pro, only if an LLM wins clearly on the Giraffe set: let an agent
   read a PDF attachment, with the PDF engine (native or `mistral-ocr`) as
   a setting on the model. Today AI Pro sends no files to the model.
