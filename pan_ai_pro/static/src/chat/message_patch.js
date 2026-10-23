/** @odoo-module */
// Copyright 2025-2026 Pantalytics B.V. All rights reserved.
// SPDX-License-Identifier: Elastic-2.0
import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
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
    /** Allow and Skip are the asker's; the rest of a channel sees who it waits for. */
    get panAiMayDecide() {
        const s = this.panAiStream;
        return !s?.askerUid || s.askerUid === user.userId;
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
