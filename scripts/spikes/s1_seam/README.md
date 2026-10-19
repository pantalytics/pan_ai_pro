# S1: the Enterprise 20 seam

**Claim.** Odoo 20 Enterprise's `ai_fields` (and `ai_agentic`) have a place
where a value is asked from the model that our `Agent` can take over, and
the native AI systray item and Ctrl+K command have registry names we can
remove.

**How.** We have no shell on the Enterprise demo and no login, only
Cloudpepper's MCP: attach this directory as a git addons source and
install `pan_ai_s1_probe`. Its `post_init_hook` zips the source of the AI
modules on disk into one attachment with an access token and logs the URL;
`tail_instance_log` gives the URL, `curl` the zip. Nothing is installed
from Enterprise's AI, nothing is called, no credit is spent.

**Result.** (filled in when run)
