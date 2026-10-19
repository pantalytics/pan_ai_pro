/** @odoo-module */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { openChannel } from "@pan_ai_pro/chat/thread_actions";

/** The sparkle top right: one click opens the chat with the default agent. */
export class AiProSystray extends Component {
    static template = "pan_ai_pro.Systray";

    setup() {
        this.orm = useService("orm");
        this.store = useService("mail.store");
    }

    async onClick() {
        const id = await this.orm.call("discuss.channel", "pan_ai_open", []);
        await openChannel(this.store, id);
    }
}

registry.category("systray").add(
    "pan_ai_pro.systray",
    { Component: AiProSystray, isDisplayed: () => user.isInternalUser },
    { sequence: 26 }
);

// Ctrl+K: "Ask AI".
registry.category("command_provider").add("pan_ai_pro", {
    provide(env) {
        return [
            {
                name: _t("Ask AI"),
                category: "app",
                async action() {
                    const id = await env.services.orm.call("discuss.channel", "pan_ai_open", []);
                    await openChannel(env.services["mail.store"], id);
                },
            },
        ];
    },
});

// The client action the server returns from "Chat" buttons.
registry.category("actions").add("pan_ai_pro.open_chat", async (env, action) => {
    await openChannel(env.services["mail.store"], action.params.channel_id);
});
