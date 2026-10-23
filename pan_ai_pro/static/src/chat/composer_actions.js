/** @odoo-module */
// Copyright 2025-2026 Pantalytics B.V. All rights reserved.
// SPDX-License-Identifier: Elastic-2.0
import { registerComposerAction } from "@mail/core/common/composer_actions";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { actionIcon, channelType, parentChannel } from "@pan_ai_pro/chat/compat";

// Stop: while a run is live, for the person who asked: on an AI channel, or
// in a thread of a team channel. The run stops at its next event; the
// message keeps what was streamed and says "Stopped."
registerComposerAction("pan-ai-stop", {
    condition: ({ composer, store }) => {
        const thread = composer.thread;
        if (!thread || (channelType(thread) !== "ai" && !parentChannel(thread))) {
            return false;
        }
        const { live, liveAsker } = store.env.services["pan_ai_pro.run_events"];
        return Boolean(live[thread.id]) && liveAsker[thread.id] === user.userId;
    },
    icon: actionIcon("stop", "fa fa-fw fa-stop"),
    name: _t("Stop"),
    onSelected: ({ composer, store }) =>
        store.env.services["pan_ai_pro.run_events"].stop(composer.thread.id),
    sequence: 5,
    sequenceQuick: 5,
});
