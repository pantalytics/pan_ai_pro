/** @odoo-module */
import { registerComposerAction } from "@mail/core/common/composer_actions";
import { _t } from "@web/core/l10n/translation";

// Stop: on an AI channel while a run is live. The run stops at its next
// event; the message keeps what was streamed and says "Stopped."
registerComposerAction("pan-ai-stop", {
    condition: ({ composer, store }) => {
        const thread = composer.thread;
        if (!thread || thread.channel?.channel_type !== "ai") {
            return false;
        }
        const live = store.env.services["pan_ai_pro.run_events"].live;
        return Boolean(live[thread.id]);
    },
    icon: "stop",
    name: _t("Stop"),
    onSelected: ({ composer, store }) =>
        store.env.services["pan_ai_pro.run_events"].stop(composer.thread.id),
    sequence: 5,
    sequenceQuick: 5,
});
