/** @odoo-module */
// Copyright 2025-2026 Pantalytics B.V. All rights reserved.
// SPDX-License-Identifier: Elastic-2.0
import { registry } from "@web/core/registry";

// Enterprise ships its own AI button and Ctrl+K entries: `ai.systray_action`
// and `ask_ai` (module `ai`), `chat_with_agent` (`ai_app` on 19,
// `ai_agentic` on 20). One agent button top right is enough: AI Pro's.
// `ai_app` and `ai_agentic` are no dependency of this module, so their file
// may load after this one: an entry is removed now and whenever it is added.
function hide(category, ids) {
    const entries = registry.category(category);
    const remove = () => {
        for (const id of ids) {
            if (entries.contains(id)) {
                entries.remove(id);
            }
        }
    };
    remove();
    entries.addEventListener("UPDATE", ({ detail }) => {
        if (detail.operation === "add" && ids.includes(detail.key)) {
            remove();
        }
    });
}

hide("systray", ["ai.systray_action"]);
hide("command_provider", ["ask_ai", "chat_with_agent"]);
