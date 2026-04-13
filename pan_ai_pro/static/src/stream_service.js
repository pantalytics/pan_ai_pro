/** @odoo-module */

import { registry } from "@web/core/registry";

/**
 * Listens for ai_pro.stream_token bus events and incrementally appends
 * text to the message DOM element, creating a smooth typewriter effect.
 * The final formatted message is written to DB server-side after streaming.
 */
const streamService = {
    dependencies: ["bus_service"],

    start(env, { bus_service }) {
        bus_service.subscribe("ai_pro.stream_token", ({ message_id, delta }) => {
            // Find the message DOM element directly
            const el = document.querySelector(
                `.o-mail-Message[data-message-id="${message_id}"] .o-mail-Message-richBody`
            );
            if (!el) return;

            // On first token, clear the placeholder
            if (el.textContent.trim() === "…") {
                el.textContent = "";
            }

            // Append delta text, converting newlines to <br>
            const parts = delta.split("\n");
            for (let i = 0; i < parts.length; i++) {
                if (i > 0) {
                    el.appendChild(document.createElement("br"));
                }
                if (parts[i]) {
                    el.appendChild(document.createTextNode(parts[i]));
                }
            }

            // Scroll to bottom
            const thread = el.closest(".o-mail-Thread");
            if (thread) {
                thread.scrollTop = thread.scrollHeight;
            }
        });
    },
};

registry.category("services").add("ai_pro.stream", streamService);
