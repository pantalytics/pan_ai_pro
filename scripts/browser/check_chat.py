# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Drive the chat in a real browser against a real server (never HttpCase:
its TestCursor defers the bus to the end of the request, S2).

    python check_chat.py http://127.0.0.1:8080 admin admin [prompt]

Logs in, opens the chat from the systray, sends the prompt, waits for the
agent's answer, and writes screenshots (desktop and phone) beside itself.
Prints the stream metrics the window kept. Exit code non-zero when the
page logged a JavaScript error or no answer came.
"""

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE, LOGIN, PASSWORD = sys.argv[1], sys.argv[2], sys.argv[3]
PROMPT = sys.argv[4] if len(sys.argv) > 4 else "How many contacts are there?"
HERE = Path(__file__).parent


def main():
    errors = []
    with sync_playwright() as p:
        # Playwright's own Chromium unless CHROMIUM_EXECUTABLE points at another.
        executable = os.environ.get("CHROMIUM_EXECUTABLE")
        browser = p.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console",
            lambda m: (
                errors.append(m.text) if m.type == "error" and "favicon" not in m.text else None
            ),
        )
        page.goto(f"{BASE}/web/login")
        page.fill("input[name=login]", LOGIN)
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url("**/odoo**", timeout=60000)
        # outside Discuss, so the chat opens as a window bottom right
        page.goto(f"{BASE}/odoo/settings")
        page.wait_for_selector(".pan-ai-systray", timeout=60000)
        page.click(".pan-ai-systray button")
        page.wait_for_selector(".o-mail-ChatWindow .o-mail-Composer-input", timeout=30000)
        # the bus runs in a shared worker; give its websocket a moment, or the
        # first batches of a fast answer are sent before anybody listens
        page.wait_for_timeout(1500)
        page.fill(".o-mail-ChatWindow .o-mail-Composer-input", PROMPT)
        before = page.evaluate(
            "document.querySelectorAll('.o-mail-ChatWindow .o-mail-Message').length"
        )
        t0 = time.time()
        page.press(".o-mail-ChatWindow .o-mail-Composer-input", "Enter")
        # the agent's message: a stream div while it runs, a rich body when done
        page.wait_for_function(
            f"() => document.querySelectorAll('.o-mail-ChatWindow .o-mail-Message').length >= {before} + 2",
            timeout=30000,
        )
        first = round(time.time() - t0, 2)
        try:
            page.wait_for_function(
                "() => {"
                " const w = window.panAi;"
                " const all = Array.from(document.querySelectorAll('.o-mail-ChatWindow .o-mail-Message'));"
                " const last = all[all.length - 1];"
                f" const settled = all.length >= {before} + 2 && last && !last.innerText.includes('Thinking') && !last.querySelector('.pan-ai-stream');"
                " return w && Object.keys(w.live).length === 0 && settled; }",
                timeout=120000,
            )
        except Exception:  # noqa: BLE001 - a run that never streamed still has a message to show
            pass
        page.wait_for_timeout(600)
        done = round(time.time() - t0, 2)
        metrics = page.evaluate("window.panAi ? window.panAi.metrics : null")
        messages = page.evaluate(
            "Array.from(document.querySelectorAll('.o-mail-ChatWindow .o-mail-Message')).map(m => m.innerText.trim().slice(0, 300))"
        )
        page.screenshot(path=str(HERE / "shot_desktop.png"))
        phone = browser.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True
        ).new_page()
        phone.goto(f"{BASE}/web/login")
        phone.fill("input[name=login]", LOGIN)
        phone.fill("input[name=password]", PASSWORD)
        phone.click("button[type=submit]")
        phone.wait_for_url("**/odoo**", timeout=60000)
        phone.goto(f"{BASE}/odoo/discuss")
        phone.wait_for_timeout(2500)
        phone.screenshot(path=str(HERE / "shot_phone.png"))
        browser.close()
    out = {
        "first_message_s": first,
        "done_s": done,
        "metrics": metrics,
        "messages": messages,
        "js_errors": errors,
    }
    print(json.dumps(out, indent=1))
    answered = (
        len(messages) >= 2
        and "Thinking" not in (messages[-1] or "")
        and PROMPT not in (messages[-1] or "")
    )
    sys.exit(0 if answered and not errors else 1)


if __name__ == "__main__":
    main()
