# S6: MCP Pro as a toolset, the token from Zitadel's device flow

**Withdrawn 2026-10-19, decision 14.** AI Pro and MCP Pro are two
products: MCP Pro is AI outside Odoo reaching in, AI Pro is AI inside
Odoo. AI Pro never calls `mcp.pantalytics.com`, and no Odoo user signs in
to Zitadel from Odoo. The module's one sign-in is Connect to Pantalytics,
Mail Pro's pairing, once per database. Rutger, after the measurement
below.

**Claim as it stood.** A native Zitadel app with the device-code grant
lets Odoo obtain a token per user with no redirect URI per customer
database; the token opens `mcp.pantalytics.com/mcp`; a refresh outlives
a thread.

**Measured before the withdrawal**, against the real instance
(`odoo-mcp-pro-xywtof.eu1.zitadel.cloud`, project `odoo-mcp-pro`) with
`probe.py`:

- The management API creates a native public app with
  `OIDC_GRANT_TYPE_DEVICE_CODE` and `OIDC_GRANT_TYPE_REFRESH_TOKEN` and
  no redirect URIs; `device_authorization` answers in 556 ms with a user
  code, `expires_in` 300, `interval` 5, and a `verification_uri_complete`.
- Zitadel's `/device` page is its **login v1**, whatever the app's
  `loginVersion` says (tried `loginV1` and the instance default, which is
  `loginV2` with `required: true`). Login v1 sends Microsoft the callback
  `/ui/login/login/externalidp/callback`, which the Azure app registration
  does not have, so "Sign in with Microsoft" on that page fails with
  AADSTS50011 twice. Mail Pro never meets this page: its pairing is
  approved on our own site, where the person is signed in through login
  v2.
- Not reached: the token, `initialize` on `/mcp`, the refresh. The two
  codes expired unapproved.

**Left behind:** the app `pan-ai-pro` (id `395814749905941696`) in project
`odoo-mcp-pro`, deactivated the same hour; the PAT may create and
deactivate apps but not delete them (403), so the delete is a console
click, tracked in issue #5.
`probe.py` stays as the shape of a device-flow probe, should a product
ever want one.
