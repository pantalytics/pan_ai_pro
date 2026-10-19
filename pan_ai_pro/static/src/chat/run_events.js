/** @odoo-module */
import { registry } from "@web/core/registry";
import { proxy } from "@odoo/owl";

/**
 * The live state of every streaming agent message, keyed by mail.message id,
 * fed by `pan_ai.run_event` on the bus (runtime/stream.py). The patched
 * Message renders it; the Composer's Stop reads `live` by channel.
 *
 * Owl 3: reads of a `proxy` during render are tracked, so no useState.
 */
export const runEventsService = {
    dependencies: ["bus_service", "action", "orm"],
    start(env, { bus_service, action, orm }) {
        const streams = proxy({});
        // channel id -> run id while a run is live on that channel
        const live = proxy({});
        const metrics = { first_delta_latency_ms: null, batches: 0, max_batch_latency_ms: 0 };
        window.panAi = { streams, live, metrics };

        function streamFor(messageId, runId) {
            return (
                streams[messageId] ||
                (streams[messageId] = {
                    runId,
                    text: "",
                    tools: [],
                    pending: [],
                    status: "running",
                    error: null,
                    opened: [],
                })
            );
        }

        bus_service.subscribe("pan_ai.run_event", ({ message_id, run_id, channel_id, events, sent_at, final }) => {
            const latency = Date.now() - sent_at * 1000;
            if (channel_id && !final) {
                live[channel_id] = run_id;
            }
            metrics.batches += 1;
            metrics.max_batch_latency_ms = Math.max(metrics.max_batch_latency_ms, latency);
            const s = streamFor(message_id, run_id);
            for (const ev of events) {
                if (ev.type === "delta") {
                    if (metrics.first_delta_latency_ms === null) {
                        metrics.first_delta_latency_ms = latency;
                    }
                    s.text += ev.text;
                } else if (ev.type === "tool_call") {
                    s.tools.push({ id: ev.id, name: ev.name, args: ev.args, summary: null });
                } else if (ev.type === "tool_result") {
                    const row = s.tools.find((t) => t.id === ev.id);
                    if (row) {
                        row.summary = ev.summary;
                    }
                } else if (ev.type === "open") {
                    s.opened.push(ev);
                    openInOdoo(ev);
                } else if (ev.type === "run_finished") {
                    s.status = ev.status;
                    s.error = ev.error;
                    s.pending = ev.pending || [];
                }
            }
            if (final) {
                if (s.status === "interrupted") {
                    // Waiting for the person: the card stays until they decide.
                    return;
                }
                for (const channelId of Object.keys(live)) {
                    if (live[channelId] === run_id) {
                        delete live[channelId];
                    }
                }
                // The final body arrives through the store; give it a tick.
                setTimeout(() => delete streams[message_id], 400);
            }
        });

        function openInOdoo(ev) {
            if (ev.id) {
                action.doAction({
                    type: "ir.actions.act_window",
                    res_model: ev.model,
                    res_id: ev.id,
                    views: [[false, "form"]],
                    target: "current",
                });
            } else {
                action.doAction({
                    type: "ir.actions.act_window",
                    name: ev.name,
                    res_model: ev.model,
                    domain: ev.domain || [],
                    views: [
                        [false, "list"],
                        [false, "form"],
                    ],
                    target: "current",
                });
            }
        }

        async function decide(channelId, messageId, runId, approvals) {
            const s = streams[messageId];
            if (s) {
                s.pending = [];
                s.status = "running";
            }
            await orm.call("discuss.channel", "pan_ai_decide", [[channelId], runId, approvals]);
        }

        async function stop(channelId) {
            await orm.call("discuss.channel", "pan_ai_stop", [[channelId]]);
        }

        function markLive(channelId, runId) {
            live[channelId] = runId;
        }

        return { streams, live, metrics, decide, stop, markLive, streamFor };
    },
};
registry.category("services").add("pan_ai_pro.run_events", runEventsService);
