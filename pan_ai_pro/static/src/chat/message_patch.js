/** @odoo-module */
import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useLive } from "@pan_ai_pro/chat/compat";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        this.panAi = useService("pan_ai_pro.run_events");
        this.panAiStreams = useLive(this.panAi.streams);
    },
    get panAiStream() {
        return this.panAiStreams[this.message.id];
    },
    get panAiChannelId() {
        return this.message.thread?.id;
    },
    panAiApprove(call, ok) {
        const s = this.panAiStream;
        // One click decides one call; the others keep waiting until decided.
        s.decided = { ...(s.decided || {}), [call.id]: ok };
        if (Object.keys(s.decided).length === s.pending.length) {
            this.panAi.decide(this.panAiChannelId, this.message.id, s.runId, s.decided);
        }
    },
    panAiIsDecided(call) {
        const s = this.panAiStream;
        return s?.decided && call.id in s.decided;
    },
});
