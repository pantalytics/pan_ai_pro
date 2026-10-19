# S4: runs in slices on Odoo's workers

**Claim.** A Pydantic AI run can be driven with `agent.iter()`, stopped at a
budget of rounds and seconds, its messages persisted, and continued by a
worker cron woken with `ir.cron._trigger()`: a chat starts inline in the
request and outlives the HTTP worker's time limit; a worker killed mid-slice
is followed by another that finishes the thread; a continuous thread ticks
with its memory growing.

**How.** `pan_ai_s4/` (throwaway, on top of the S2 module): a
`pan_ai_s4.thread` with the messages as JSON, a claim (`UPDATE ... WHERE
heartbeat_at is stale RETURNING id`, committed), a heartbeat on every bus
flush, two worker crons, and a fake model that asks for N tool calls then
answers. `measure_s4.py` runs three scenarios with Playwright and RPC
against a **prefork** server (`workers = 2`, `limit_time_real = 8`,
`limit_time_real_cron = 75`, `max_cron_threads = 2`) behind `proxy.py`
(routes `/websocket` to the gevent worker as Caddy would).

```bash
odoo-bin -c odoo-prefork.conf -d s2 --db-filter='^s2$' &
python proxy.py 8080 &
python measure_s4.py http://127.0.0.1:8080 admin admin
```

**Result, 2026-10-19: the claim holds.** Odoo 20.0 Community, Python 3.13,
Postgres 16, Pydantic AI 2.31.1, two HTTP workers and two cron workers.

| Scenario | Numbers |
|---|---|
| A. chat, 12 tool calls of 0.4 s, budget 3 rounds or 2.5 s per slice, HTTP limit 8 s | 5 slices: the first inline, four on crons, on two worker processes. Cron wake after `_trigger()`: 122, 377, 537, 849 ms. First tool row 1.0 s after Send, the answer 8.9 s after Send, stream handed over to the final body |
| B. crash: one 90 s tool call on a cron worker, killed at 75 s | the other worker reclaimed the thread on the stale heartbeat and finished it; 70 s between the two slice starts, 71 s in all |
| C. continuous: 3 ticks, memory kept | 4 slices, 8 messages in the history, the fourth answer reads "Memory holds 4 prompts" |

**Five findings that shape the module.**

1. **The boundary is before the next model request, and the pending
   request travels.** Stopping inside the tool node loses the tool returns
   (`run.all_messages()` lacks them until the next node runs): the fake
   model re-asked for the same step every slice. Stop when the next node
   is a `ModelRequestNode`, persist `all_messages() + [node.request]`,
   resume with `message_history=` and no prompt. `scripts/spikes/`'s
   `slice_probe.py` is the pure Pydantic AI proof.
2. **`limit_time_real_cron` cannot go below about 70 s.** The cron worker
   sleeps up to 60 s (plus a chorus of up to 10 s) between jobs without
   pinging the master, so a smaller limit kills idle workers forever
   (measured at 8 s: a kill every 9 s). The slice budget on a cron is
   therefore the host's `limit_time_real_cron` minus a margin, never a
   number of ours.
3. **Odoo consumes every due trigger of a cron in one run.** A job that
   does one slice and returns strands the other threads until the next
   scheduled run (measured: 66 s). The job loops over claimable threads
   inside its own time budget and re-triggers if work is left.
4. **A trigger placed while every cron worker is busy waits for the
   next scheduled run** (up to 60 s): the NOTIFY is heard only by a worker
   that is sleeping. Two workers are the floor; the module should ship
   with the number of cron workers in its docs, and a continuous tick
   interval under a minute is not a promise we can keep.
5. **Two bugs the real module must not inherit.** A claim is a row
   update, so a worker that is killed in a tool but not yet dead (B: the
   "dead" worker slept on for 70 s) could still write its slice after
   another worker reclaimed the thread: writes need a fence (the claim's
   token compared before writing). And the continuous ticks ran back to
   back instead of 3 s apart, because the loop in finding 3 re-claimed the
   thread the moment it was released: a `next_tick_at` on the thread, and
   the claim refuses before it.

Also met on the way: Odoo 20 replaced `ir.model.access` and record rules
with `ir.access` (CSV columns `id,name,model_id,group_id/id,operation,
domain`); Odoo runs REPEATABLE READ, so two workers updating one row is a
`SerializationFailure` to catch, not a wait; a killed cron worker shows up
in the log as "Job ... timed out" on the next run, which is bookkeeping,
not a failure.

**Not measured here, still open:** Odoo.sh and Cloudpepper (their
`limit_time_real`, `limit_time_real_cron` and cron worker counts), memory
compaction of a long thread, and the fence from finding 5.
