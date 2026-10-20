# Architecture

The module is described in [docs/architecture-20.md](docs/architecture-20.md):
one module, Pydantic AI inside Odoo, on Odoo 19 and 20. The plan and the
spikes behind it are in [docs/plans/](docs/plans/).

The 1.6.x module (Claude as a provider for Odoo 19 Enterprise's `ai` app)
is retired. Its code and its architecture document live on the
[`19.0-legacy`](https://github.com/pantalytics/pan_ai_pro/tree/19.0-legacy)
branch, kept for the installs that have not upgraded yet.
