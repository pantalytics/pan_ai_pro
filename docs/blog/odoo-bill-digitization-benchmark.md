# How accurate is Odoo's bill digitization? We measured it

Draft, 2026-11-12. For pantalytics.com, then a short post on the Odoo forum
linking here. Numbers from `docs/plans/invoice-extraction-benchmark.md`.

---

Odoo reads your vendor bills for you: drop a PDF in Accounting and the
fields fill themselves, at one IAP credit a bill. How often are they right?
Odoo does not publish a number, and nobody else has either. So we measured
it, on public test sets, against six AI models.

**The short answer: Odoo got 52 to 67% of the header fields right. Every
model we tried got 95 to 100%, at a fifth of the price or less.**

## The test

Two public sets, so anyone can repeat it:

- **Donut invoices**: 100 synthetic invoices (MIT licence). The same set
  Fraunhofer IAIS used in their 2025 benchmark of AI models on invoices.
- **The official EN 16931 sample invoices**: the 23 German and French
  Factur-X examples that ship with the EU e-invoice standard. Each one
  carries its data as XML, so we know the right answer down to the VAT
  rate of every line. We removed that XML before anything read the page.

We scored every field separately: vendor, VAT number, bill number, dates,
currency, untaxed amount, tax, total, IBAN, and the lines with their VAT
rate. Odoo ran through its own Extract API, the service your database
calls, with the same hints a database sends. The models ran through
OpenRouter with one prompt and one answer format.

## The results

| | Header fields right, Donut | Header fields right, EN 16931 | VAT rate right per line | Cost per bill |
|---|---|---|---|---|
| Odoo digitization | 52% | 67% | 20 of 53 | about EUR 0.13 |
| Claude Sonnet 5.5 | 99.5% | 99% | 53 of 53 | EUR 0.01 |
| Gemini 3.1 Pro | 96% | 100% | 53 of 53 | EUR 0.02 |
| GPT-5.5 | 96% | 99% | 53 of 53 | EUR 0.02 |
| Gemini 3.8 Flash | 95.5% | 100% | 53 of 53 | EUR 0.005 |
| Mistral OCR, then Mistral Medium | 95% | 97% | 53 of 53 | EUR 0.006 |

Where Odoo goes wrong:

- **The vendor.** It often takes a heading as the vendor name ("Invoice
  no", "Beispiel") and found the vendor's VAT number on 2 of 100 Donut
  bills.
- **Untaxed and tax.** On Donut it returned the total as the untaxed amount
  with zero tax, on 93 of 99 bills.
- **Lines and VAT.** It merged lines (1.4 per bill, the bills have 2.3)
  and had the VAT rate right on 20 of 53 lines. Every model had all 53.

Totals and dates Odoo reads fine.

## Three things we learned on the way

1. **There is no public benchmark for European VAT.** The invoice test sets
   people use are American or are till receipts. The EU sample invoices are
   the only public material with VAT categories, and there are 23 of them,
   none with reverse charge. If you know of a better set, tell us.
2. **Reading the image beats OCR first.** Mistral's OCR followed by a model
   came last among the models, as Fraunhofer found too. Odoo works that way
   (Google Vision OCR, then its own model).
3. **Test sets have errors too.** 25 of the IBANs in the Donut answers fail
   their own checksum: they were made by OCR. We left those out.

## What this does not say

This is the raw read. Inside a database Odoo also looks up the vendor in
your contacts and applies your fiscal positions, so the booked bill can be
better than what the Extract API returns. We are testing that next on 50
real bills of a Dutch coffee roaster, with their accountant's booking as
the answer.

The scripts are open: [link to repo]. Run them on your own bills.

## Using a model on your bills today

AI Pro runs these models inside Odoo, on your own OpenRouter or EUrouter
key. Reading bills is the next thing we are building on it.

---

## Forum post (odoo.com, Accounting)

**Title:** We benchmarked Odoo's bill digitization against AI models on public test sets

We could not find any published accuracy figure for Odoo's document
digitization, so we measured it: 123 invoices from two public sets (the
Donut invoices and the official EN 16931 Factur-X samples), every field
scored on its own. Odoo's Extract API got 52% and 67% of the header fields
right. Gemini, Claude, GPT and Mistral all got 95 to 100%, and the VAT rate
on all 53 lines, where Odoo had 20. The method, the scripts and the caveats
are here: [link to blog]. We would like to hear from anyone who sees
different results inside a real database, where Odoo also matches the
vendor from your contacts.
