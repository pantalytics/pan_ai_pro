# S2: streaming through the bus into a mail message

**Claim.** On Odoo 20 Community, a `discuss.channel` of type `ai` can show a
Pydantic AI run streaming inside the agent's `mail.message`: text as it
comes, a tool row that folds to its result, and the final markdown body
written once, with the first token on screen under 300 ms after the server
sent it and no commit cadence faster than 100 ms.

**How.** `pan_ai_s2/` is a throwaway module: the channel type, a
`FunctionModel` that makes one tool call then streams an answer at 50 tokens
a second, `agent.run_stream_events()` mapped to four event kinds, batched
every 100 ms into one `pan_ai.run_event` bus notification plus a commit, a
patched `Message` that renders the live state, and a tour that measures.

**Run.**

```bash
odoo-bin -c odoo.conf -d s2 -i pan_ai_s2 --test-enable --test-tags /pan_ai_s2 --stop-after-init
```

Exit code non-zero means the claim failed. The numbers are printed as
`[pan_ai_s2] REPORT`.

**Result, 2026-10-19: the claim holds.** Odoo 20.0 Community (git 20.0 of
that day), Python 3.13, Postgres 16, one threaded server (`workers = 0`),
Chromium 141 on the same machine, `measure.py` against the real server:

| | full run | stopped at 0.6 s |
|---|---|---|
| first token, server send to browser | 50 ms | 35 ms |
| slowest batch, server send to browser | 97 ms | 52 ms |
| batches / events | 24 / 73 | 11 / 29 |
| first token after Send (fake model adds ~350 ms, two RPC round trips) | 1148 ms | 947 ms |
| final body (markdown table) replaces the stream, written once | yes | yes, ends with *Stopped.* |
| messages on the channel | 2 | 2 |

Screenshots: `shot_full.png`, `shot_stopped.png` (Discuss, the `ai`
channel, the agent partner, the rendered table).

**Two findings worth more than the numbers.**

1. **HttpCase cannot measure this.** Its `TestCursor` turns `commit()` into
   a savepoint, so `bus.bus`'s precommit insert and postcommit `NOTIFY`
   run at the end of the request: every batch arrived at once, 2084 ms
   after the first was sent. The tour in `tests/test_s2.py` therefore
   checks behaviour only (stream shows, hands over to the body, two
   messages); latency is `measure.py` against a real server, which is what
   the module's `browser.yml` must run.
2. **Owl 3 in Odoo 20.** `reactive` is `proxy`, there is no `useState`: a
   `proxy` read during render is tracked. `run_stream_events()` in
   Pydantic AI 2.31 is an async context manager (`async with ... as
   events`), and `FunctionToolResultEvent` carries `part`, not `result`.
   `ir.config_parameter` has `get_str`/`set_str`, not `get_param`.

**Not measured here, still open:** Odoo.sh and Cloudpepper (their proxies
and `limit_time_real`), and the chat window (the test ran in Discuss; the
chat window renders the same `Message` component).
