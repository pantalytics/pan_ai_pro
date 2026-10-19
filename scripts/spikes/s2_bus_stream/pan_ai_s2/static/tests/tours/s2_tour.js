/** @odoo-module */
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

registry.category("web_tour.tours").add("pan_ai_s2", {
    steps: () => [
        { trigger: ".o-mail-Composer-input", run: "edit How many open sales orders are there?" },
        {
            trigger: ".o-mail-Composer-input",
            run() {
                window.panAiS2.sent_at = Date.now();
            },
        },
        { trigger: ".o-mail-Composer-input", run: "press Enter" },
        { trigger: ".o-mail-Message .pan-ai-tool:contains('12 found')" },
        {
            trigger: ".o-mail-Message .pan-ai-text:contains('twelve')",
            run() {
                window.panAiS2.first_visible_after_send_ms = Date.now() - window.panAiS2.sent_at;
            },
        },
        // The final body replaces the stream: a real table, rendered from markdown.
        { trigger: ".o-mail-Message .o-mail-Message-richBody table td:contains('Azure Interior')" },
        {
            trigger: "body",
            async run() {
                const m = window.panAiS2;
                m.final_visible_after_send_ms = Date.now() - m.sent_at;
                m.stream_divs_left = document.querySelectorAll(".pan-ai-stream").length;
                await rpc("/web/dataset/call_kw/discuss.channel/pan_ai_s2_report", {
                    model: "discuss.channel", method: "pan_ai_s2_report", args: [m], kwargs: {},
                });
            },
        },
    ],
});
