# Pending: "Is it the OCR?" section for the live post

Status: **not yet live.** The post is live at
pantalytics.com/post/odoo-bill-digitization-benchmark (Directus `blog_posts`
127, translations `en` and `nl`). This section is in
`odoo-bill-digitization-benchmark.md` but could not be added to Directus on
2026-11-13, because every connector of that session returned 502.

To publish it:

1. In Directus, open `blog_posts` 127 and edit the `body` of each translation.
2. Find the examples image (asset `ed72deab-8eb0-4983-a044-3f483f030ff2`),
   which closes "Where does Odoo go wrong?" / "Waar gaat Odoo de mist in?".
3. Paste the matching block below directly after that image's `</p>`.
4. Save. The "Auto-deploy website" flow rebuilds the site; check both URLs.
5. Delete this file.

Source of the numbers: pantalytics/odoo-iap-benchmark, paper section 6.1,
`results/<set>/odoo-ocr/` and `results/odoo_candidates.md`.

## en

```html
<h2>Is it the OCR?</h2>
<p>No. Odoo's answer includes the text its OCR read and, for every field, the candidates it considered. We gave that same OCR text to Claude Sonnet 5.5: it booked 94%, 100% and 88% of the documents, against Odoo's 0%, 9% and 8%. And the right supplier was in Odoo's own candidate list on 99% of the Donut invoices and 97% of the receipts; Odoo picked it on 0% and 20%. Odoo's OCR sees what a booking needs. The step that chooses the fields gets it wrong.</p>
<p>That step may lean on the database: in a live Odoo the supplier is matched on VAT number, IBAN or e-mail against your contacts. This test does not cover that.</p>
```

## nl

```html
<h2>Ligt het aan de OCR?</h2>
<p>Nee. Het antwoord van Odoo bevat de tekst die de OCR las, en per veld de kandidaten die Odoo overwoog. Dezelfde OCR-tekst gaven we aan Claude Sonnet 5.5. Dat boekte 94%, 100% en 88% van de documenten, tegen 0%, 9% en 8% voor Odoo. De juiste leverancier stond bij 99% van de Donut-facturen en 97% van de bonnetjes in Odoo's eigen kandidatenlijst, maar Odoo koos hem bij 0% en 20%. De OCR van Odoo ziet wat een boeking nodig heeft. De stap die de velden kiest, gaat de mist in.</p>
<p>Die stap leunt mogelijk op de database: in een echte Odoo wordt de leverancier via btw-nummer, IBAN of e-mail aan je contacten gekoppeld. Dat meet deze test niet.</p>
```
