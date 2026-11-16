# How accurate is Odoo's bill digitization? We measured it

Published 2026-11-13 on pantalytics.com/post/odoo-bill-digitization-benchmark
(Directus blog_posts 127, NL and EN). The forum post below links there. Numbers from `docs/plans/invoice-extraction-benchmark.md`.

---

Odoo reads your vendor bills for you: drop a PDF in Accounting and the
fields fill themselves, with nothing to set up, at one IAP credit a bill
(EUR 0.05 to 0.15, by credit pack). How often are they right?
Odoo does not publish a number, and nobody else has either. So we measured
it, on public test sets, against six AI models.

**The short answer: Odoo got 0 to 9% of the documents fully right. Every
model we tried got 61 to 100%, each for less per document than Odoo's cheapest credit.**

![Bookable without correction against AI cost per document](https://raw.githubusercontent.com/pantalytics/odoo-iap-benchmark/main/figures/fig0_overview.png)

## The test

Three public sets, so anyone can repeat it:

- **Donut invoices**: 100 synthetic invoices, the set Fraunhofer IAIS used in
  their 2025 benchmark.
- **The official EN 16931 sample invoices**: the 23 German and French
  Factur-X examples of the EU e-invoice standard. Each carries its data as
  XML, so we know the right answer down to the VAT rate of every line. We
  removed that XML before anything read the page.
- **SROIE receipts**: 100 real scanned till receipts.

A document counts when an accountant could book it as read: supplier,
number, date, currency, amounts and the amount per VAT rate all right.

## The results

| Fully right | Donut invoices | EN 16931 invoices | Scanned receipts | Cost per document |
|---|---|---|---|---|
| Odoo digitization | 0% | 9% | 8% | EUR 0.05 to 0.15 |
| Claude Sonnet 5.5 | 97% | 96% | 91% | EUR 0.01 |
| Gemini 3.8 Flash | 64% | 100% | 94% | EUR 0.005 |
| Gemini 3.8 Flash + 4 reading rules | 97% | 100% | 95% | EUR 0.005 |
| Claude Opus 5.5 | 97% | 100% | 90% | EUR 0.02 |
| GPT-5.5 | 72% | 100% | 91% | EUR 0.02 |

Where Odoo goes wrong: it often takes a heading as the supplier ("Invoice
no", "Beispiel"), picks a customer or order number as the invoice number,
returns the total as the untaxed amount with zero tax on simple invoices,
and on scanned receipts gets the total right only half the time.

## Is it the OCR?

No. Odoo's answer includes the text its OCR read and, for every field, the
candidates it considered. We gave that same OCR text to Claude Sonnet 5.5:
it booked 94%, 100% and 88% of the documents, against Odoo's 0%, 9% and 8%.
And the right supplier was in Odoo's own candidate list on 99% of the Donut
invoices and 97% of the receipts; Odoo picked it on 0% and 20%. Odoo's OCR
sees what a booking needs. The step that chooses the fields gets it wrong.

That step may lean on the database: in a live Odoo the supplier is matched
on VAT number, IBAN or e-mail against your contacts. This test does not
cover that.

Correcting costs more than reading. Per 100 documents Odoo left about three
hours of corrections, the best models 10 to 20 minutes.

Odoo has one real advantage: setup. Its reader is on by default, with no
module, no API key and no instructions to maintain. A language model needs
all three once; at three hours saved per hundred bills, that pays back after
a few hundred bills.

## Three things we learned

1. **There is no public benchmark for European VAT.** The EU sample invoices
   are the only public material with VAT categories, 23 of them, none with
   reverse charge. More on that below.
2. **One sentence of instruction can beat a bigger model.** Telling the
   model to read dates in the supplier's own convention lifted the cheapest
   model from 64% to 97% on US-style invoices.
3. **Learning from mistakes needs context.** Rules a model wrote from its
   own errors did not help, and one made it worse: "the total is the amount
   due" is right for receipts and wrong for invoices with a prepayment.

## Why only 223 documents

We wanted thousands of real European bills: mixed VAT rates, reverse
charge, foreign currencies, business and consumer side by side. Ten years
old would have been fine. We did not find them.

- **Public sets** (Hugging Face, Kaggle, GitHub): synthetic or American.
  A generated layout says nothing about a real supplier's bill.
- **Buying**: vendors sell tens of thousands of real German and UK invoice
  images, but without the answers. Someone still has to key every field.
- **Bankrupt or dissolved companies**: the trustee keeps the books for the
  creditors and the tax office. After seven years they are destroyed, not
  sold.
- **Old company archives**: real, but paper from before 2000, before
  today's EU VAT rules.

The one source of real bills we found that anyone can check: Dutch public
bodies publish expense claims and invoices under the Open Government Act
(Woo), receipts included. Scattered, scanned, and nobody has keyed the
answers yet.

The cause is simple. Every bookkeeping package reads millions of bills a
day, and none may publish one. Whoever has the data cannot share it. If
you know a better set, tell us.

## What this does not say

This is the raw read. Inside a database Odoo also looks up the supplier in
your contacts, so the booked bill can be better. We test that next on real
Dutch bills.

The paper, the code and every raw answer: github.com/pantalytics/odoo-iap-benchmark

## Using a model on your bills today

AI Pro runs these models inside Odoo, on your own OpenRouter or EUrouter
key. Reading bills is the next thing we are building on it.

---

## Forum post (odoo.com, Accounting)

**Title:** We benchmarked Odoo's bill digitization against AI models on public test sets

We could not find a published accuracy figure for Odoo's document
digitization, so we measured it on 223 public documents (Donut invoices, the
official EN 16931 Factur-X samples, SROIE receipts), every field scored. A
document counted when it could be booked as read. Odoo's Extract API got 0
to 9% fully right; eight AI models got 61 to 100%, the best at EUR 0.01 a
document. Paper, scripts, raw answers and caveats:
github.com/pantalytics/odoo-iap-benchmark. We would like to hear from anyone
who sees different results inside a real database, where Odoo also matches
the supplier from your contacts.
