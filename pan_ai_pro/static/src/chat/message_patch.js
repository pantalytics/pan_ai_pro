/** @odoo-module */
import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        this.panAi = useService("pan_ai_pro.run_events");
    },
    get panAiStream() {
        return this.panAi.streams[this.message.id];
    },
    get panAiChannelId() {
        return this.message.thread?.id;
    },
    panAiApprove(call, ok) {
        const s = this.panAiStream;
        const approvals = {};
        for (const c of s.pending) {
            approvals[c.id] = c.id === call.id ? ok : null;
        }
        // One click decides one call; the others keep waiting until decided.
        const decided = Object.fromEntries(Object.entries(approvals).filter(([, v]) => v !== null));
        s.decided = Object.assign(s.decided || {}, decided);
        if (Object.keys(s.decided).length === s.pending.length) {
            this.panAi.decide(this.panAiChannelId, this.message.id, s.runId, s.decided);
        }
    },
    panAiIsDecided(call) {
        const s = this.panAiStream;
        return s?.decided && call.id in s.decided;
    },
});
