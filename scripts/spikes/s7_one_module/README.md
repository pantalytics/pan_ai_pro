# S7: one module on Odoo 19 and 20

Question: can the 20.0 module run unchanged on Odoo 19, and if not, where
exactly does it break? Measured 2026-10-19 against a shallow clone of
`odoo/odoo` branch `19.0` (`4fd1a2ea`) in the Odoo 20 venv (Python 3.13),
database `ai19`, and against the Odoo 20 checkout the module was built on.

What is not run here: this README has no code; the measurement is the
install and the test suite on both servers, which `ci.yml` now repeats on
`odoo:19` and `odoo:20`.

## Breaks, in the order they appeared

| | Odoo 19 | Odoo 20 | Done |
|---|---|---|---|
| Manifest version `20.0.x` | "incompatible version, installable=False" | fine | version without prefix (`1.1.0`); Odoo prefixes its own serie |
| `security/ir.access.csv` | `KeyError: 'ir.access'` (the model is 20's; 19 has `ir.model.access` + `ir.rule`) | fine | `security/access.xml` calls `pan_ai.access.install`, which creates the rows for whichever model exists (`models/access.py`); the 20 xml ids are kept, 19 gets `rule_*` rows plus a manager rule per model with a domain |
| `<function model=... name=...>` with no arguments | `ValueError: not enough values to unpack` (the first argument is the record ids) | same code | `eval="[[]]"` |
| `ir.config_parameter.get_str/set_str/get_int/get_bool` | `AttributeError` (19 has `get_param`/`set_param`) | fine | `compat.params(env)`: 20's object as is, a shim on 19 |
| `ir.model.fields._get_writable_properties` | does not exist; 19 refuses every write on a base field | the whitelist | a `write` that touches only our columns skips 19's guard |
| `ir.model` read by a plain user | refused (19 grants `base.group_user` nothing on it) | allowed | `pan_ai.tool.model_names`, stored by a sudo compute; the toolset reads that |
| `ir.actions.server.run` by a plain user | asks write on the action's model; Sam may not write `res.partner` on 19 | same check, Sam may on 20 | "Run AI agent" asks AI Pro access and read on the records instead |
| `message_post` of a note by a plain user on a contact | refused without write on the contact | allowed | the test gives Sam contacts rights; the product keeps posting as the person |
| `Store(bus_channel=...).add(...)` | nothing reaches the browser until `bus_send()` | sends by itself | `compat.send_fields` |
| `import { proxy } from "@odoo/owl"` | Owl 2 has `reactive` and needs `useState` in the component | Owl 3 tracks reads | `static/src/chat/compat.js`: `liveState`, `useLive` |
| `user.isRegularUser` | undefined, so the systray item never showed | present | `user.isInternalUser`, present on both |
| `store["mail.thread"]`, `thread.channel.channel_type` | `store.Thread`, `thread.channel_type` | as written | `threadModel(store)`, `channelType(thread)` in the same file |

Things that turned out the same on both: `res.groups.privilege`,
`res.users.all_group_ids`, `discuss.channel.channel_type` with
`selection_add`, `Store(bus_channel=...)`, `registerThreadAction`,
`registerComposerAction`, `_load_records` with xml ids, the `<function>`
tag, the cron, the server action state.

## Result

Measured 2026-10-19 18:24 UTC, both servers prefork with two workers,
`check_chat.py` through `proxy.py`, the stand-ins for the platform and the
model host:

| | Odoo 19 | Odoo 20 |
|---|---|---|
| suite | 46 tests, 0 failed, 0 errors | 46 tests (62 with the shared cases), 0 failed, 0 errors |
| first token after the server sent it | 29 ms | 40 ms |
| slowest batch | 36 ms | 61 ms |
| JavaScript errors | none | none |

## Still to measure

- Enterprise 19: whether `_fill_ai_field` exists there with the same shape
  as on 20 (`pan_ai_pro_enterprise` is written against 20's `ai_fields`).
