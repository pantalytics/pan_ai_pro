/** @odoo-module */
import { Thread } from "@mail/core/common/thread";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onWillUpdateProps } from "@odoo/owl";
import { channelType } from "@pan_ai_pro/chat/compat";

// The thread of an AI channel on screen: rebuild the live state the bus
// sent before this page loaded (run_events.hydrate).
patch(Thread.prototype, {
    setup() {
        super.setup(...arguments);
        const runEvents = useService("pan_ai_pro.run_events");
        const hydrate = (thread) => {
            if (thread && channelType(thread) === "ai") {
                runEvents.hydrate(thread.id);
            }
        };
        hydrate(this.props.thread);
        onWillUpdateProps((next) => hydrate(next.thread));
    },
});
