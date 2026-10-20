/** @odoo-module */
// Copyright 2025-2026 Pantalytics B.V. All rights reserved.
// SPDX-License-Identifier: Elastic-2.0
import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

// Owl 3: a `proxy` read during render is tracked; no useState needed.
patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        this.panAi = useService("pan_ai_s2.run_events");
    },
    get panAiStream() {
        return this.panAi.streams[this.message.id];
    },
});
