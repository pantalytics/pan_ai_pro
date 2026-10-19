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

**What actually ran, 2026-10-19.** The probe never ran its hook: Cloudpepper
pulled the branch into an empty addons directory (cause not visible through
its API), and `base.import.module` imports data files only, so a
`post_init_hook` is never called. S1 was answered instead over XML-RPC as
admin against the demo (`odoo-20-enterprise-demo.cloudpepper.site`,
Enterprise 20.0 at commit `6ad61cf43dcd2`) with `ai`, `ai_fields`,
`ai_agentic` and `ai_mcp` installed there, plus the server log through
Cloudpepper and the web asset bundle for the registry names. The modules
stay installed on the demo. `pan_ai_s1_probe/` and `analyse.py` are kept
as the shape of a shell-less source dump for the next host that allows it.

**Result: the claim holds.**

1. **The AI-field seam is one method on `base`.** The widget and the
   nightly cron (`AI Fields: Compute AI fields`, `ai_fields/data/ir_cron_data.xml`)
   both end in `get_ai_field_value(fname, changes)`, a public method on
   every model (`ai_fields/models/models.py`, line 218 raises
   `ValueError("The field {fname} has no AI prompt")` when the field has no
   `system_prompt`). It calls the private `_fill_ai_field`, which goes
   through `odoo.addons.ai.utils.ai_utils` to IAP
   (`https://ai.api.odoo.com/api/odoo_ai/1/get_completions_sync`). With
   0 credits the log reads `Insufficient credit for Odoo AI` and the user
   gets `UserError("Something went wrong. Please rephrase your prompt and
   try again.")`; the cron logs `Could not get a value for an AI Field
   (x_pan_ai_probe on res.partner)` and moves on. So on Enterprise our
   module overrides `_fill_ai_field` on `base` (inherit, not replace) and
   runs the field's `Agent` instead; the widget, the cron, the Studio
   panel and the `ai`/`ai_domain`/`prompt_custom`/`system_prompt`/
   `supports_ai` columns on `ir.model.fields` stay Odoo's. There is no
   provider or model field anywhere: `ai.agent` has `system_prompt`,
   `skill_ids`, `sources_ids`, `allowed_agent_ids`, `automation_ids`,
   `embedding_model` and avatar fields only. IAP is the only engine.

2. **The registry names to remove on Enterprise.** From
   `web.assets_web.min.js`: the systray item is `ai.systray_action`
   (`/ai/static/src/web/systray_action.js`); the Ctrl+K providers are
   `ask_ai` (`/ai/static/src/core/web/command_palette.js`) and
   `ai_agentic`'s `chat_with_agent` (rpc `ai.agent.open_agent_chat`);
   the launcher service is `aiChatLauncher` (`ai.agent.action_launch_ai_chat`).
   Also present, left alone: `ai.client_tools`, the `ai_char` widget family,
   `ai.composer` rows with `interface_key` `systray_ai_button` and
   `chatter_ai_button`.

3. **A bonus, not a claim.** Odoo 20's own chat loop is already a slice
   machine: `ai.session` (one per `discuss.channel`) carries `loop_state`
   in `ready / waiting_model / waiting_confirmation / waiting_answer /
   waiting_client_result / waiting_external_result / waiting_child`,
   `request_round` and `request_round_limit`, `resume_token` and
   `pending_tool_call`, with `ai.session.event` rows beside it. That is
   the S4 design in Odoo's own hands, which settles the "is a slice loop
   on workers reasonable" question a second time.

**Left behind on the demo**, for Rutger to clear or keep: the four AI
modules installed, the Cloudpepper managed module `pan_ai_pro` on branch
`spike/s1-probe` (dirs `scripts/spikes/s1_seam`, pulls empty), and the
orphan branch `spike/s1-probe` on GitHub. Nothing of the probe is in the
database (uninstalled, field rows deleted).

