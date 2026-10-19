# The change to brand.pantalytics.com

The brand site is the `pantalytics/pantalytics-brand` repository (GitHub
Pages on push to `main`). This session could read it but was not allowed
to push to it, so the change is here as a patch, ready to apply:

```bash
cd pantalytics-brand && git apply ../pan_ai_pro/docs/brand-site.patch && npm run icons -- --install
```

What it changes, 2026-10-19:

- `scripts/app-icons.mjs`: the AI Pro icon gets its install target, this
  module's `static/description/icon.png`, so `npm run icons -- --install`
  keeps the module's icon the brand's.
- `src/i18n/en.json`, `src/i18n/nl.json` (and the terms table on the
  Product UI page): the fixed term **Agent**, "an AI identity inside Odoo:
  it runs as the person who asks, or as a dedicated user with its own
  rights", never "bot", "assistant" as a product name, or "AI user". This
  is decision 15 of `architecture-20.md`, made the brand's word.
