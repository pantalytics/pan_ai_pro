# Scenarios

What the product promises, and which test holds each promise. `✗` is a known
gap (with its issue), `–` does not apply. Matrix: Odoo 19 and 20, Community
and Enterprise; upgrade from the 1.x module on 19 Enterprise.

| Flow | Happy | Edge | Fout | Rechten | 19 | 20 | UI | Test |
|---|---|---|---|---|---|---|---|---|
| Chat: stream, tools, Stop | ✓ | ✓ | ✓ 429/401/402, ✗ network | ✓ | ✓ | ✓ | ✓ | test_run_stream, scripts/browser/check_chat.py |
| Approve or skip a change | ✓ | ✓ | – | ✓ | ✓ | ✓ | ✗ | test_run_stream::test_a_write_waits_for_approval_then_runs |
| Agents: run as user or dedicated user | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | test_agent_build, test_runs::test_a_dedicated_user_carries_the_run |
| Every internal user may chat, also after an upgrade; a Light user stays Light (20) | ✓ | – | – | ✓ | ✓ | ✓ | – | test_access::test_an_upgrade_gives_every_internal_user_the_chat, ::test_a_light_user_stays_light_and_may_chat |
| Built-in Odoo tools | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | test_odoo_toolset |
| Server action as tool | ✓ | ✗ | ✗ | ✗ approval #26 | ✓ | ✓ | – | test_odoo_toolset::test_a_server_action_is_a_tool |
| MCP toolset | ✓ | ✓ | ✗ server down | ✓ allow list, ✗ approval #26 | ✓ | ✓ | – | test_mcp_toolset |
| Automation rule, schedule, Action menu | ✓ | ✓ | ✓ refusal never fails a save (logged, nothing runs), ✗ nobody told #28 | ✓ | ✓ | ✓ | – | test_runs, test_runs::TestRuleSave |
| Continuous watch | ✓ | ✓ | ✓ | – | ✓ | ✓ | – | test_runs::test_a_continuous_thread_ticks_on_changes_only |
| AI fields (Community) | ✓ | ✓ | ✗ model error | ✓ | ✓ | ✓ | – | test_fields |
| AI fields (Enterprise seam) | ✗ #27 | ✗ | ✗ | ✗ | ✗ | ✗ | – | none |
| Control: tokens, limits, retention | ✓ tokens, ✗ cost | ✓ | ✓ | ✓ | ✓ | ✓ | – | test_run_stream, test_channel::test_retention_deletes_old_chats_and_their_runs |
| License connection | ✓ | ✓ | ✓ outage keeps plan, 401 stops | ✓ | ✓ | ✓ | – | test_license |
| Onboarding and menus | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | test_onboarding |
| Multi-company | ✗ #28 | ✗ | ✗ | ✗ | ✗ | ✗ | – | none |
| Install, upgrade from 1.6.1, upgrade in place | ✓ | – | – | – | ✓ | ✓ | – | local matrix (not in CI); pan_ai_pro_enterprise on upgrade ✗ #25 |
