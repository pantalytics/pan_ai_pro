"""Measure the S2 claim against a real Odoo server (not HttpCase: its
TestCursor turns commits into savepoints, so bus rows and the NOTIFY land at
the end of the request and every batch arrives at once).

    python measure.py http://127.0.0.1:8069 admin admin

Exit code non-zero when the claim fails. Prints the numbers as JSON.
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


def run_chat(page, channel_id, stop_after=None, api=None):
    page.goto(f"{BASE}/odoo/discuss?active_id={channel_id}")
    page.wait_for_selector(".o-mail-Composer-input", timeout=30000)
    page.evaluate("window.panAiS2 = Object.assign(window.panAiS2 || {}, {first_delta_latency_ms: null, first_delta_at: null, batches: 0, events: 0, max_batch_latency_ms: 0, final_latency_ms: null, server_stats: null})")
    page.fill(".o-mail-Composer-input", "How many open sales orders are there?")
    sent_at = time.time()
    page.evaluate("window.panAiS2.sent_at = Date.now()")
    page.press(".o-mail-Composer-input", "Enter")
    if stop_after:
        page.wait_for_selector(".o-mail-Message .pan-ai-text", timeout=15000)
        time.sleep(stop_after)
        msg_id = page.evaluate("Number(Object.keys(window.panAiS2Streams || {})[0] || 0)")
        api and rpc(api, "discuss.channel", "pan_ai_s2_stop", [msg_id])
    page.wait_for_function("window.panAiS2 && window.panAiS2.final_latency_ms !== null", timeout=30000)
    page.wait_for_selector(".o-mail-Message .o-mail-Message-richBody", timeout=10000)
    page.wait_for_function("document.querySelectorAll('.pan-ai-stream').length === 0", timeout=5000)
    metrics = page.evaluate("window.panAiS2")
    metrics["first_visible_after_send_ms"] = (metrics["first_delta_at"] - metrics["sent_at"]) if metrics.get("first_delta_at") else None
    metrics["wall_ms"] = int((time.time() - sent_at) * 1000)
    metrics["last_body"] = page.evaluate("(() => { const b = document.querySelectorAll('.o-mail-Message-richBody'); return b.length ? b[b.length-1].innerText.slice(0, 200) : ''; })()")
    return metrics


def main():
    api = login_session()
    channel_id = rpc(api, "discuss.channel", "pan_ai_s2_new_chat", [])
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(f"{BASE}/web/login")
        page.fill("input[name=login]", LOGIN)
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url("**/odoo**", timeout=30000)

        full = run_chat(page, channel_id)
        page.screenshot(path="/home/user/pan_ai_pro/scripts/spikes/s2_bus_stream/shot_full.png")
        stopped_channel = rpc(api, "discuss.channel", "pan_ai_s2_new_chat", [])
        stopped = run_chat(page, stopped_channel, stop_after=0.6, api=api)
        page.screenshot(path="/home/user/pan_ai_pro/scripts/spikes/s2_bus_stream/shot_stopped.png")
        browser.close()

    out = {"full": {k: v for k, v in full.items() if k != "streams"}, "stopped": {k: v for k, v in stopped.items() if k != "streams"}}
    print(json.dumps(out, indent=1, default=str))
    failures = []
    if full["first_delta_latency_ms"] is None or full["first_delta_latency_ms"] > 300:
        failures.append(f"first token {full['first_delta_latency_ms']} ms after the server sent it (limit 300)")
    if full["max_batch_latency_ms"] > 500:
        failures.append(f"slowest batch {full['max_batch_latency_ms']} ms (limit 500)")
    if full["batches"] < 5:
        failures.append("fewer than 5 batches: not streaming")
    if "Azure Interior" not in full["last_body"]:
        failures.append("final body is not the markdown table")
    if "Stopped." not in stopped["last_body"]:
        failures.append("Stop did not end the run")
    if failures:
        print("FAILED:\n- " + "\n- ".join(failures))
        sys.exit(1)
    print("CLAIM HOLDS")


if __name__ == "__main__":
    main()
