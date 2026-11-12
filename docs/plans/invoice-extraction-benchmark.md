# Plan: benchmark Odoo bill digitization against LLM extraction

Status: 2026-11-12, LLMs run on both public sets (results below). Odoo
waits on IAP credits. First customer: Giraffe Coffee
Roasters.

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

## Results so far (LLMs only, 2026-11-12)

Odoo not yet run: it waits on IAP credits. Spend so far EUR 9.30.

| Engine | Donut 100: header fields | Donut: bills fully right | EN 16931 23: header fields | EN 16931: lines (incl. VAT rate) | EN 16931: VAT category | EUR per bill |
|---|---|---|---|---|---|---|
| Claude Sonnet 5.5 | 99.5% | 96% | 99.1% | 99.5% | 23/23 | 0.008 to 0.013 |
| Gemini 3.1 Pro | 96.2% | 70% | 100% | 99.5% | 23/23 | 0.023 to 0.026 |
| GPT-5.5 | 96.1% | 69% | 99.1% | 98.6% | 23/23 | 0.018 to 0.020 |
| Gemini 2.5 Pro | 96.0% | 68% | 99.1% | 98.6% | 23/23 | 0.015 |
| Gemini 3.8 Flash | 95.5% | 64% | 100% | 99.5% | 23/23 | 0.004 to 0.006 |
| Mistral OCR into Medium 3.5 | 94.9% | 60% | 97.4% | 94.3% | 23/23 | 0.005 to 0.008 |

What it says:
- Our Gemini 2.5 Pro score on Donut (96.0%) matches Fraunhofer's 96.5% on
  the same set, so the harness measures what they measured.
- Almost every Donut miss is the date. Donut prints US dates (09/10/2015);
  only Claude reads them as US every time, the others take the European
  order 30% of the time. Same trap on a French sample with a US date.
- Mistral OCR first, then an LLM, is last on every set: it lost the IBAN
  on 3 of 10 and line detail. Fraunhofer's "image in beats OCR first"
  holds.
- VAT on the EN 16931 samples is no problem for any LLM: every rate per
  line and every category right, mixed 7/19 and 5.5/20 included. The set
  is small and has no reverse charge, so the real VAT test is Giraffe's.
- Fixed in the scoring on the way: Donut's truth has 25 broken IBANs (made
  by OCR, they fail the checksum; not scored now), credit notes print
  negative amounts, and names come with or without the legal form.

## The question that matters: is the VAT read right?

Reading the total is the easy part. What costs an accountant time is the
VAT on each line: high or low rate, exempt, intra-EU, export, reverse
charge. We score the VAT rate per line and the bill's EN 16931 VAT
category (S, Z, E, AE, K, G, O), the vocabulary of EU e-invoices.

## Test data: standard sets only

Only public, standard sets, or the numbers mean nothing to anyone else.
Finding: **no standard benchmark scores EU VAT treatment.** The public
invoice benchmarks (Donut, inv-cdip, DocILE, SROIE, CORD) are US or
receipts and carry no VAT category. The only standard EU material with VAT
truth is the official EN 16931 sample set, and it is small. That gap is a
finding for the blog too.

1. **Donut synthetic invoices** (`katanaml-org/invoices-donut-data-v1`,
   MIT, 501 bills): Fraunhofer's "Clean Invoices" set, so our field numbers
   line up with theirs. A fixed random sample of 100 to stay in budget.
2. **EN 16931 sample invoices** (FeRD and FNFE Factur-X samples from the
   ZUGFeRD corpus, Apache-2.0): 23 unique invoices after deduplication, the
   truth from the XML each PDF carries, which we strip before the engines
   see the page. VAT mix: 17 standard rate (8 with two rates on one bill:
   DE 7/19, FR 5.5/20), 3 exempt, 2 intra-EU (K), 1 export (G). No
   reverse charge (AE) sample exists in the set. Mostly German. Too small
   for a percentage claim: we report it per invoice.
3. **Private: 50 real Giraffe vendor bills**, already booked by their
   accountant: the booking is the truth, VAT code per line included.
   Giraffe books in Exact Online today, so the entries plus their PDF come
   out of the Exact API. Lives in `.data/` of `odoo-customer-giraffecoffee`,
   gitignored, never in the blog. Not a standard set: it answers Giraffe's
   question, not the public one.

Dropped:
- inv-cdip (Fraunhofer's scanned set): the UCSF library refuses automated
  downloads, and it is 1980s US invoices without VAT.
- DocILE: English US documents, test labels not public.
- A generated EU VAT set of our own (built, then removed): not standard.

## Contestants

| Engine | How it runs |
|---|---|
| Odoo digitization | Odoo's Extract API (`extract.api.odoo.com`, invoice route), straight from the script with an IAP account token. Same service Odoo calls, no database needed |
| Gemini 3.8 Flash, Gemini 3.1 Pro | OpenRouter, native PDF |
| Gemini 2.5 Pro | OpenRouter, native PDF. Fraunhofer's best, as anchor |
| Claude Sonnet 5.5 | OpenRouter, native PDF |
| GPT-5.5 | OpenRouter, native PDF |
| Mistral OCR then Mistral Medium 3.5 | OpenRouter `file-parser` plugin, engine `mistral-ocr` |

Same JSON schema and prompt for all LLM runs. Temperature 0. We pass
Odoo's Extract API the same hints Odoo sends (`user_company_vat`,
`user_lang`, `perspective`), so it is not handicapped. The Extract API
returns VAT rates but no VAT category: Odoo takes the category from the
vendor's fiscal position, so the category is not held against it.

## Booked in Odoo (Giraffe only)

For Giraffe the real question is whether the bill lands with the right
purchase tax in their Odoo. Once their vendors are in Giraffe staging, the
50 bills go in there: Odoo's path is upload and digitize, the LLM path is
the script creating the draft bill and picking each line's tax from rate
and category, which is what an AI Pro agent would do. Score: right
`account.tax` per line and the total to the cent. The public sets cannot
be booked this way: their buyers are other companies.

AI Pro itself cannot read a PDF yet. The LLM path uses the same models
through OpenRouter, so it measures what AI Pro would get. The AI Pro
feature gets built only if that path wins.

## Fields and scoring

Score per field, not per page. The fields are the ones Odoo returns:
supplier VAT number, supplier name, bill reference, bill date, due date,
currency, untaxed amount, tax, total, IBAN, and lines (description,
quantity, unit price, VAT rate) and the bill's VAT category. A field
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

`scripts/bench/prepare_donut.py` and `scripts/bench/prepare_zugferd.py`
build the two public sets as PDFs plus `truth.jsonl`.
`scripts/bench/bench_invoices.py` runs each engine, caches every raw
answer (a rerun costs nothing), writes `results.csv` and `summary.md`, and
stops starting calls once the cached spend passes `--max-eur`.

## Budget

Hard cap EUR 100: EUR 50 on an OpenRouter key with that limit, EUR 50 of
IAP credits. The script also stops at `--max-eur`.

| Item | Bills | Cost |
|---|---|---|
| IAP credits | 100 Donut, 23 EN 16931, 50 Giraffe | about EUR 25 |
| Six LLM engines via OpenRouter | 173 each | about EUR 25 |

## Steps

1. Harness plus both public sets. Done.
2. Paid run on the 3 bills that came back odd on Odoo's free test token
   (one summary line, "Factuur" as vendor), to learn whether the free
   token gives the real service. Then the full public run. Numbers for the
   blog.
3. Export 50 Giraffe bills from Exact; extraction run, then booked in
   Giraffe staging once their vendors are in. Numbers for Giraffe.
4. Blog, forum post, Giraffe advice.
5. AI Pro PDF reading, only if step 2 or 3 says so.

## Outputs

1. Giraffe: one table, and a recommendation: keep Odoo digitization or
   route bills through AI Pro.
2. Blog on pantalytics.com, then a forum post on odoo.com linking to it,
   with the public-set numbers and the harness.
3. AI Pro, only if an LLM wins clearly on the Giraffe set: let an agent
   read a PDF attachment, with the PDF engine (native or `mistral-ocr`) as
   a setting on the model. Today AI Pro sends no files to the model.
