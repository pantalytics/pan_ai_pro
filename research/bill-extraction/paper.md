# How well does Odoo read a vendor bill? A reproducible comparison of Odoo's document digitization with six multimodal language models

Pantalytics B.V., Rotterdam. Working paper, version 1, November 2026.

Code, data manifests and every raw answer: `research/bill-extraction/` in
this repository ([README](README.md)).

## Abstract

<!-- RESULTS:ABSTRACT -->

## 1. Introduction

Odoo, an open-source ERP used by small and mid-sized companies, can read
vendor bills: a PDF is sent to Odoo's Extract API, and the fields of a
draft bill are filled in. The service costs one IAP credit per document.
Odoo publishes no accuracy figure for it, and we found no independent
measurement. Accuracy claims that circulate online come from vendors of
competing products and come without a method.

Meanwhile general-purpose multimodal language models (LLMs) read documents
directly from the page image. Berghaus et al. (2025) compared eight such
models on three public invoice sets and found that sending the page image
to the model beats extracting the text first and giving the model the text,
by 10 to 40 percentage points.

Odoo's service is built the second way: according to Odoo's IAP privacy
policy the document is converted to text by Google Cloud Vision, after
which Odoo's own model extracts the fields. That makes the comparison
interesting beyond Odoo: it is a production OCR-then-extract pipeline
against current image-in models.

What matters to the people who use it is not character accuracy but
whether the bill can be booked as read. We therefore define the main
outcome from an accountant's point of view (section 4.4).

### Research questions

- **RQ1.** How often does Odoo's document digitization return a vendor bill
  that can be booked without correction?
- **RQ2.** How do current multimodal LLMs compare on the same bills, in
  accuracy, cost and time?
- **RQ3.** Does putting a dedicated OCR step in front of an LLM (Mistral OCR,
  then Mistral Medium) lose accuracy against giving the LLM the page?
- **RQ4.** How often are the VAT rate per line, the VAT summary and the VAT
  category read correctly?

## 2. Hypotheses

The study plan was written before any data was collected and kept under
version control (`docs/plans/invoice-extraction-benchmark.md`); the commit
hashes below show when each statement was made.

- **H1** (stated in commit `61632b1`, 2026-11-12 13:49 UTC, before any
  Odoo answer existed): image-in LLMs extract bill fields more accurately
  than Odoo's digitization, because Odoo puts an OCR step first.
- **H2** (commit `61632b1`): the OCR-first LLM pipeline is less accurate
  than image-in LLMs on these born-digital documents; OCR earns its place on
  bad scans only.
- RQ1 and RQ4 had no directional hypothesis; they are descriptive.

## 3. Related work

- **Berghaus et al. (2025)**, Fraunhofer IAIS: eight multimodal models,
  three public sets (Donut synthetic invoices, SROIE receipts, inv-cdip
  scanned invoices), exact-match field accuracy. Gemini 2.5 Pro scored
  96.5% on the Donut invoices. We reuse their Donut set to anchor our
  harness against theirs.
- **Text-recognition benchmarks** (OlmOCRBench, OmniDocBench) score how well
  text and layout are recognised, not whether a field holds the right
  value. Mistral reports 85.2 and 93.1 on them for OCR 4.
- **Key-information-extraction sets**: SROIE and CORD are till receipts;
  DocILE (Šimsa et al., 2023) holds 6,680 English business documents from
  US sources, with hidden test labels; inv-cdip (Gao et al., 2022) holds 350
  scanned US invoices from the 1980s and 1990s. None of them labels the VAT
  treatment of a bill.
- **Vendor leaderboards** (Nanonets IDP) are run by a vendor on its own
  task definitions.

We found no public benchmark that scores European VAT treatment. That gap
shaped the choice of data below.

## 4. Data and method

### 4.1 Test sets

Only public, standard sets were used, so that results can be compared and
repeated.

**Donut invoices.** `katanaml-org/invoices-donut-data-v1` on Hugging Face,
revision `d2cde298e79c94fb05bc320999deb4b7889b0464`, MIT licence. 501
synthetic English invoices with US addresses, rendered at 2481 × 3508
pixels, with structured ground truth (header, line items, summary). This is
the "clean invoices" set of Berghaus et al. Each JPEG was wrapped unchanged
in a one-page A4 PDF, so that every engine received the same file type.
For cost reasons we drew a fixed random sample of 100 bills
(`random.Random(42).sample`). The sample has 366 lines; 355 carry a VAT
rate (all 10%), 11 carry none. Currency is printed as "$" on 96 bills and
missing on 4.

**EN 16931 sample invoices.** The official Factur-X/ZUGFeRD sample invoices
published by FeRD (Germany) and FNFE-MPE (France) for the European
e-invoicing standard EN 16931, as collected in the ZUGFeRD corpus
(github.com/ZUGFeRD/corpus, commit
`84f8d8f68f6c3698aa3019d701a8b82db9ba0aac`, Apache-2.0). Each PDF carries
its invoice as CII XML, which gives exact ground truth, including the VAT
rate and EN 16931 VAT category per line and the VAT summary per rate.
Selection, applied in this order:

1. all PDFs in the corpus (151);
2. excluded: folders `fail/` (deliberately broken files) and
   `ZUGFeRDv1/` (format version without VAT detail);
3. excluded: PDFs without embedded CII XML, or without any VAT category;
4. excluded: duplicates, defined as the same invoice number and seller name
   (the same FeRD sample appears in several folders and versions).

That leaves 23 invoices with 53 lines: 18 from German sellers, 4 French,
1 British. VAT categories: 17 standard rate (S), 3 exempt (E), 2
intra-community supply (K), 1 export (G); 9 carry two VAT rates (7/19% or
5.5/20%); 2 are credit notes. No sample uses reverse charge (AE). The XML
was removed from each PDF before any engine saw it (only the pages were
copied to a new PDF), so that no engine could read the answer from the
attachment.

For both sets, `truth.jsonl` records for every bill the source (dataset
and revision, or corpus commit and path) and the SHA-256 of the source
file.

### 4.2 Sets considered and not used

| Set | Reason |
|---|---|
| inv-cdip (scanned invoices of Berghaus et al.) | The UCSF Industry Documents Library refused automated download; also US documents without VAT |
| DocILE | English US documents, test labels not public |
| SROIE, CORD | Till receipts, not vendor bills |
| A synthetic EU VAT set of our own (150 bills, nine VAT scenarios) | Built, then discarded: a set we generate ourselves is not a standard and invites the suspicion of being tuned to a result |

### 4.3 Engines

| Engine | Model | Route |
|---|---|---|
| Odoo | Odoo Extract API, invoice route, API version 123 | `extract.api.odoo.com`, called directly with an IAP account token |
| Gemini 3.8 Flash | `google/gemini-3.8-flash` | OpenRouter, PDF passed natively |
| Gemini 3.1 Pro | `google/gemini-3.1-pro-preview` | same |
| Gemini 2.5 Pro | `google/gemini-2.5-pro` | same; the best model of Berghaus et al., as anchor |
| Claude Sonnet 5.5 | `anthropic/claude-sonnet-5.5` | same |
| GPT-5.5 | `openai/gpt-5.5` | same |
| Mistral OCR → Mistral Medium 3.5 | `mistralai/mistral-medium-3-5` | OpenRouter `file-parser` plugin with engine `mistral-ocr`: the page goes through Mistral OCR, the model gets its text |

All LLMs received the same one-paragraph prompt and the same JSON schema
(`src/bench_invoices.py`, `PROMPT` and `SCHEMA`), at temperature 0, with
structured output enforced. The prompt says the document is a bill
received from a supplier, asks for ISO dates and plain numbers, and asks
for null where a value is absent. The schema asks for the header fields,
the lines (description, quantity, unit price, VAT rate, net amount), the
VAT summary (rate, base, tax per rate) and the EN 16931 VAT category.

Odoo received what an Odoo database sends: `perspective: client` (the
bill was received) and the buyer's company name, VAT number and country as
`user_infos`, taken per bill from the ground truth, since a database always
knows its own company. Odoo's API returns no VAT category: in Odoo the
category follows from the vendor's fiscal position in the database, so that
field is not held against Odoo.

Model ids were checked against OpenRouter's model list on 2026-11-12, the
day all runs took place. Costs per call are OpenRouter's reported cost.
Odoo's cost is the price of one IAP credit, about EUR 0.13 at the pack size
used (an assumption; Odoo bills credits in packs). Seconds are wall-clock
time per bill, including Odoo's polling at 5-second intervals.

### 4.4 Outcomes

**Primary outcome: bookable without correction.** A bill counts as
bookable when every field an accountant needs to post it is right:

- the vendor: its VAT number when the bill has one, else its name;
- invoice number, invoice date, currency;
- untaxed amount, tax amount, total;
- the VAT summary: the base amount per VAT rate. Truth is the printed VAT
  table (EN 16931) or, where a bill has none, the sum of line amounts per
  rate (Donut). A prediction's summary is its VAT table if it gave one,
  else the sum of its line amounts per rate. One line per VAT rate is as
  bookable as many: Odoo itself offers that option.

Due date, IBAN and line descriptions serve payment and reading, not
booking, and are reported separately. A field whose truth is absent is not
scored.

**Secondary outcomes:** accuracy per field, all header fields together,
line fields (description, quantity, unit price, VAT rate) matched by
position, VAT rate per line, VAT category, cost and time per bill.

**Matching rules.** Amounts and quantities match within 0.005, compared by
absolute value. Dates are compared as ISO dates. VAT numbers are compared
without separators and without a leading country code. Codes (invoice
number, IBAN, currency) are compared upper-case without separators; a
currency sign counts as its ISO code. Names count when one contains the
other (after lower-casing and removing punctuation) or when their
similarity ratio is at least 0.9, and the prediction is at least 4
characters. Truth IBANs that fail the ISO 13616 checksum are not scored
(section 6.3).

**Statistics.** Proportions carry a 95% Wilson score interval. For field
accuracy the interval treats fields as independent, which they are not
within a bill; it is a lower bound on the uncertainty. Each LLM was run
three times on every bill; we report the mean and the range. Odoo was run
twice on all 123 bills, once without and once with the buyer hints, and
returned byte-identical answers both times, so one run is scored for all
three.

## 5. Results

<!-- RESULTS:TABLES -->

## 6. Discussion

<!-- RESULTS:DISCUSSION -->

### 6.3 The ground truth has errors too

In 25 of the 100 Donut bills of our sample, the IBAN in the ground truth
fails its own checksum ("GB82D)FU82ZI3146210425"): the labels were partly
produced by OCR. Every model read these IBANs as printed, and was marked
wrong. Berghaus et al. name IBAN as the hardest field on this set; part of
that difficulty is in the labels. We exclude such truths from scoring.

## 7. Limitations

- **Raw read, not the booked bill.** We scored what Odoo's Extract API
  returns. Inside a database Odoo also searches the vendor in the partner
  list (by VAT number, name, bank account) and applies the vendor's fiscal
  position and default taxes. The bill an accountant finally sees can be
  better than the raw read, or worse where defaults override a correct
  read. A follow-up study books real bills in a real database.
- **Clean, born-digital documents.** Both sets are generated PDFs. Phone
  photos and bad scans, where OCR matters most, are absent. H2 is tested
  only for clean documents.
- **Small VAT set.** The EN 16931 set has 23 bills, mostly German, and no
  reverse-charge sample. Its VAT results show capability, not a rate that
  carries to a company's real mix of bills.
- **US conventions in Donut.** Donut prints US dates (month first), which
  European readers, human or model, misread when the day is 12 or less.
  This affects the date field and so the bookable rate.
- **Model drift.** Hosted models change behind the same name, and
  temperature 0 does not make their output deterministic. The run-to-run
  range shows the second; nothing here guards against the first.
- **Possible caching at Odoo.** Odoo's two runs were identical to the byte.
  The service may cache results per file, in which case our two runs are
  not independent evidence of determinism.
- **Scoring rules revised after a first look.** See section 8. Results under
  the original rules are published alongside (`*_strict.*`).

## 8. Deviations from the plan

| Planned (plan commit) | Done | Why |
|---|---|---|
| Fraunhofer's scanned set inv-cdip (`a889638`) | Not used | Automated download refused by the source library |
| A synthetic EU VAT set of our own (`ffa4567`) | Built, then removed (`32a3c5f`) | Not a standard set; decided by the research owner before any result on it |
| Primary outcome: header-field accuracy | Primary outcome: bookable without correction | Header-field accuracy does not answer the practical question; changed at the research owner's request after the first results, before the repeated runs |
| One run per engine | Three runs per LLM | To measure run-to-run variation |
| Scoring rules as first written | Four rules revised after inspecting the first LLM answers: (1) names match by containment, not prefix ("Au bon moulin" against "Au bon moulin SARL"); (2) amounts by absolute value (credit notes print negative amounts where the XML holds positive ones); (3) truth IBANs failing their checksum not scored; (4) the VAT summary added to the schema, since line amounts computed as quantity × price miss discounts | Each revision corrects a scoring error that marked a right answer wrong for every engine alike. The original rules remain available (`--strict`) and their results are published |

## 9. Reproducibility

All code is in `src/`, all raw answers of all engines in `results/`, with
the truth files and their source hashes. Scores can be recomputed from the
raw answers at no cost; the full study can be repeated with an OpenRouter
key and an Odoo IAP account (README). Runs took place on 2026-11-12 with
Python 3.13.18 and pypdf 7.0.1. Total cost: <!-- RESULTS:COST -->.

## 10. Conflict of interest

Pantalytics sells AI Pro, a module that runs language models inside Odoo,
and so has an interest in language models doing well against Odoo's own
service. To keep that interest from steering the result we used only
public data, wrote the hypotheses down before collecting it, publish every
raw answer and the scoring under the original rules, and give the code to
anyone who wants to check it.

## References

- Berghaus, D., Berger, A., Hillebrand, L., Cvejoski, K., Sifa, R. (2025).
  Multi-Modal Vision vs. Text-Based Parsing: Benchmarking LLM Strategies for
  Invoice Processing. arXiv:2509.04469.
- Kim, G. et al. (2022). OCR-free Document Understanding Transformer.
  ECCV 2022.
- Šimsa, Š. et al. (2023). DocILE Benchmark for Document Information
  Localization and Extraction. ICDAR 2023. arXiv:2302.05658.
- Gao, M. et al. (2022). Field Extraction from Forms with Unlabeled Data
  (inv-cdip). github.com/salesforce/inv-cdip.
- CEN (2017). EN 16931-1: Electronic invoicing, semantic data model.
- Odoo S.A. Extract API, Odoo 19.0 documentation; In-App Purchase privacy
  policy, iap.odoo.com/privacy (consulted 2026-11-12).
- Mistral AI (2026). Mistral OCR 4 announcement, as reported by VentureBeat,
  2026-06-24.
