"""Measure S4 against a prefork Odoo (workers=2, limit_time_real=8,
limit_time_real_cron=8) behind proxy.py.

    python measure_s4.py http://127.0.0.1:8080 admin admin

Three scenarios:
A. a chat whose run needs ~6 s of tool time: first slice inline in the
   request, the rest on worker crons; the answer lands; no worker is killed.
B. a crash: one tool call of 90 s on a cron worker that is killed at 75 s;
   the stale heartbeat lets another worker reclaim the thread and finish.
C. a continuous thread: three ticks, each a cron wake a few seconds apart,
   the history growing across ticks.

Exit code non-zero when a claim fails. Prints the numbers as JSON.
"""

import json
import sys
import time

import requests
from playwright.sync_api import sync_playwright

BASE, LOGIN, PASSWORD = sys.argv[1], sys.argv[2], sys.argv[3]


def rpc(session, model, method, args, kwargs=None):
    r = session.post(
        f"{BASE}/web/dataset/call_kw/{model}/{method}",
        json={"jsonrpc": "2.0", "method": "call", "params": {"model": model, "method": method, "args": args, "kwargs": kwargs or {}}},
    )
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"]["data"]["message"])
    return body["result"]


def login_session():
    s = requests.Session()
    r = s.post(f"{BASE}/web/session/authenticate", json={"jsonrpc": "2.0", "params": {"db": "s2", "login": LOGIN, "password": PASSWORD}})
    r.raise_for_status()
    assert r.json()["result"]["uid"], "login failed"
    return s


def wait_done(api, thread_id, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = rpc(api, "pan_ai_s4.thread", "pan_ai_s4_read", [thread_id])
        if t["state"] == "done":
            t["wall_s"] = round(time.time() - t0, 1)
            return t
        time.sleep(1)
    raise TimeoutError(f"thread {thread_id} not done after {timeout}s: {t}")


def scenario_a(api):
    channel_id = rpc(api, "pan_ai_s4.thread", "pan_ai_s4_new_chat", [])
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        page.goto(f"{BASE}/web/login")
        page.fill("input[name=login]", LOGIN)
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url("**/odoo**", timeout=30000)
        page.goto(f"{BASE}/odoo/discuss?active_id={channel_id}")
        page.wait_for_selector(".o-mail-Composer-input", timeout=30000)
        page.fill(".o-mail-Composer-input", "Do the long task")
        t0 = time.time()
        page.press(".o-mail-Composer-input", "Enter")
        page.wait_for_selector(".o-mail-Message .pan-ai-tool", timeout=15000)
        first_tool_s = round(time.time() - t0, 2)
        page.wait_for_selector(".o-mail-Message .o-mail-Message-richBody:has-text('steps done')", timeout=60000)
        wall_s = round(time.time() - t0, 2)
        tool_rows = page.evaluate("document.querySelectorAll('.pan-ai-tool').length")
        page.screenshot(path="/home/user/pan_ai_pro/scripts/spikes/s4_slices/shot_a.png")
        browser.close()
    # the thread
    tid = rpc(api, "pan_ai_s4.thread", "search_read", [[["channel_id", "=", channel_id]]], {"fields": ["id"]})[0]["id"]
    t = rpc(api, "pan_ai_s4.thread", "pan_ai_s4_read", [tid])
    starts = [e for e in t["log"] if e["event"] == "slice_start"]
    return {
        "first_tool_row_after_send_s": first_tool_s,
        "answer_after_send_s": wall_s,
        "slices": t["slices"], "rounds": t["rounds"], "state": t["state"], "text": t["text"],
        "where": [e["where"] for e in starts],
        "workers": sorted({e["worker"].split(":")[0] for e in starts}),
        "cron_wake_ms": [e["wake_ms"] for e in starts if e["wake_ms"] is not None],
        "tool_rows_left_in_stream_div": tool_rows,
    }


def scenario_b(api):
    # limit_time_real_cron cannot go below the cron worker's idle sleep (60 s
    # plus a chorus of up to 10 s), or idle workers are killed; so the crash
    # is a 90 s tool call under a 75 s limit.
    tid = rpc(api, "pan_ai_s4.thread", "pan_ai_s4_start_cron_thread", [{"prompt": "do the steps", "steps": 2, "step_seconds": 90, "budget_seconds": 120, "budget_rounds": 5, "crash_once": True}])
    t = wait_done(api, tid, timeout=600)
    starts = [e for e in t["log"] if e["event"] == "slice_start"]
    return {
        "wall_s": t["wall_s"], "slices_started": len(starts), "slices_finished": t["slices"],
        "workers": [e["worker"].split(":")[0] for e in starts],
        "gap_between_starts_s": [round(b["t"] - a["t"], 1) for a, b in zip(starts, starts[1:])],
        "text": t["text"],
    }


def scenario_c(api):
    tid = rpc(api, "pan_ai_s4.thread", "pan_ai_s4_start_cron_thread", [{"prompt": "tick 0", "kind": "continuous", "max_ticks": 3, "tick_seconds": 3, "steps": 0}])
    t = wait_done(api, tid, timeout=180)
    starts = [e for e in t["log"] if e["event"] == "slice_start"]
    armed = [e for e in t["log"] if e["event"] == "tick_armed"]
    return {
        "wall_s": t["wall_s"], "ticks": t["ticks"], "slices": t["slices"], "messages": t["messages"],
        "cron_wake_ms": [e["wake_ms"] for e in starts if e["wake_ms"] is not None],
        "tick_gap_s": [round(s["t"] - a["t"], 1) for a, s in zip(armed, starts[1:])],
        "text": t["text"],
    }


def main():
    api = login_session()
    out = {}
    for name, fn in (("A", scenario_a), ("B", scenario_b), ("C", scenario_c)):
        out[name] = fn(api)
        print(name, json.dumps(out[name], indent=1, default=str), flush=True)
    f = []
    a, b, c = out["A"], out["B"], out["C"]
    if a["state"] != "done" or "steps done" not in a["text"]:
        f.append("A: the chat did not finish")
    if a["slices"] < 3 or a["where"][:1] != ["inline"] or "cron" not in a["where"]:
        f.append(f"A: expected the first slice inline and later ones on crons, got {a['where']}")
    if a["cron_wake_ms"] and max(a["cron_wake_ms"]) > 3000:
        f.append(f"A: a cron wake took {max(a['cron_wake_ms'])} ms")
    if len(b["workers"]) < 2 or b["slices_finished"] < 1 or "steps done" not in b["text"]:
        f.append("B: the killed slice was not resumed by another worker")
    if c["ticks"] != 3 or c["messages"] < 8 or "Memory holds 4" not in c["text"]:
        f.append("C: three ticks with growing memory did not happen")
    if f:
        print("FAILED:\n- " + "\n- ".join(f))
        sys.exit(1)
    print("CLAIM HOLDS")


if __name__ == "__main__":
    main()
