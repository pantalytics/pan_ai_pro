/** @odoo-module */
import { registry } from "@web/core/registry";
import { proxy } from "@odoo/owl";

/**
 * Holds the live state of a streaming agent message, keyed by message id,
 * fed by `pan_ai.run_event` on the bus. The patched Message renders it.
 */
export const runEventsService = {
    dependencies: ["bus_service"],
    start(env, { bus_service }) {
        const streams = proxy({});
        const metrics = { first_delta_latency_ms: null, first_delta_at: null, batches: 0, events: 0, max_batch_latency_ms: 0, final_latency_ms: null, server_stats: null };
        window.panAiS2 = metrics;
        window.panAiS2Streams = streams;
        bus_service.subscribe("pan_ai.run_event", ({ message_id, events, sent_at, final }) => {
            const now = Date.now();
            const latency = now - sent_at * 1000;
            metrics.batches += 1;
            metrics.events += events.length;
            metrics.max_batch_latency_ms = Math.max(metrics.max_batch_latency_ms, latency);
            const s = streams[message_id] || (streams[message_id] = { text: "", tools: [], done: false });
            for (const ev of events) {
                if (ev.type === "delta") {
                    if (metrics.first_delta_at === null) {
                        metrics.first_delta_at = now;
                        metrics.first_delta_latency_ms = latency;
                    }
                    s.text += ev.text;
                } else if (ev.type === "tool_call") {
                    s.tools.push({ id: ev.id, name: ev.name, args: ev.args, summary: null });
                } else if (ev.type === "tool_result") {
                    const row = s.tools.find((t) => t.id === ev.id);
                    if (row) row.summary = ev.summary;
                } else if (ev.type === "run_finished") {
                    metrics.server_stats = ev.stats;
                    metrics.final_latency_ms = latency;
                }
            }
            if (final) {
                s.done = true;
                // The final body arrives through mail.record/insert; give it a tick, then let it show.
                setTimeout(() => delete streams[message_id], 300);
            }
        });
        return { streams, metrics };
    },
};
registry.category("services").add("pan_ai_s2.run_events", runEventsService);
