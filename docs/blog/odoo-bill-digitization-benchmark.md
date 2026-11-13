# How accurate is Odoo's bill digitization? We measured it

Draft, 2026-11-13. Live as a draft on Directus (blog_posts 127, NL and EN,
with figures from the benchmark repo). Then a short post on the Odoo forum
linking there. Numbers from `docs/plans/invoice-extraction-benchmark.md`.

---

Odoo reads your vendor bills for you: drop a PDF in Accounting and the
fields fill themselves, with nothing to set up, at one IAP credit a bill
(EUR 0.05 to 0.15, by credit pack). How often are they right?
Odoo does not publish a number, and nobody else has either. So we measured
it, on public test sets, against six AI models.

**The short answer: Odoo got 0 to 9% of the documents fully right. Every
model we tried got 61 to 100%, each for less per document than Odoo's cheapest credit.**

![Bookable without correction against AI cost per document](https://raw.githubusercontent.com/pantalytics/odoo-iap-benchmark/claude/eager-faraday-u72rsm/figures/fig0_overview.png)

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

Correcting costs more than reading. Per 100 documents Odoo left about three
hours of corrections, the best models 10 to 20 minutes.

Odoo has one real advantage: setup. Its reader is on by default, with no
module, no API key and no instructions to maintain. A language model needs
all three once; at three hours saved per hundred bills, that pays back after
a few hundred bills.

## Three things we learned

1. **There is no public benchmark for European VAT.** The EU sample invoices
   are the only public material with VAT categories, 23 of them, none with
   reverse charge. If you know a better set, tell us.
2. **One sentence of instruction can beat a bigger model.** Telling the
   model to read dates in the supplier's own convention lifted the cheapest
   model from 64% to 97% on US-style invoices.
3. **Learning from mistakes needs context.** Rules a model wrote from its
   own errors did not help, and one made it worse: "the total is the amount
   due" is right for receipts and wrong for invoices with a prepayment.

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
