/** @odoo-module */
import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

/** Open a channel in the chat window, bottom right. */
export async function openChannel(store, channelId) {
    const thread = await store["mail.thread"].getOrFetch({ model: "discuss.channel", id: channelId });
    if (thread) {
        await thread.openChatWindow({ focus: true });
    }
    return thread;
}

const onAiChannel = ({ thread }) => thread?.channel?.channel_type === "ai";

// A fresh thread with the same agent: the old chat stays in Threads.
registerThreadAction("pan-ai-new-chat", {
    condition: onAiChannel,
    icon: "add",
    name: _t("New chat"),
    onSelected: async ({ thread, store }) => {
        const orm = store.env.services.orm;
        const id = await orm.call("discuss.channel", "pan_ai_open", [], { new: true, channel_id: thread.id });
        await openChannel(store, id);
    },
    sequence: 15,
    sequenceQuick: 30,
});

// Switch agent: the picker lists the agents open to this person.
registerThreadAction("pan-ai-pick-agent", {
    condition: onAiChannel,
    icon: "swap_horiz",
    name: _t("Switch agent"),
    onSelected: async ({ thread, store }) => {
        const orm = store.env.services.orm;
        const agents = await orm.call("discuss.channel", "pan_ai_agents", []);
        store.env.services.dialog.add(
            (await import("@pan_ai_pro/chat/agent_picker")).AgentPicker,
            {
                agents,
                onPick: async (agentId) => {
                    const id = await orm.call("discuss.channel", "pan_ai_open", [agentId]);
                    await openChannel(store, id);
                },
            }
        );
    },
    sequence: 16,
    sequenceGroup: 20,
});
