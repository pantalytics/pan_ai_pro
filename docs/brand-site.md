# The change to brand.pantalytics.com

The brand site is the `pantalytics/pantalytics-brand` repository (GitHub
Pages on push to `main`). The change for AI Pro merged on 2026-10-19 as
[pantalytics-brand#11](https://github.com/pantalytics/pantalytics-brand/pull/11):

- `scripts/app-icons.mjs`: the AI Pro icon's install target is this
  module's `static/description/icon.png`, so `npm run icons -- --install`
  keeps the module's icon the brand's.
- `src/i18n/en.json`, `src/i18n/nl.json` (and the terms table on the
  Product UI page): the fixed term **Agent**, "an AI identity inside Odoo:
  it runs as the person who asks, or as a dedicated user with its own
  rights", never "bot", "assistant" as a product name, or "AI user". This
  is decision 15 of `architecture-20.md`, made the brand's word.
