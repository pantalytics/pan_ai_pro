/** @odoo-module */
import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";
import { channelType, threadModel } from "@pan_ai_pro/chat/compat";

/** Open a channel: the chat window bottom right, or the pane when inside Discuss. */
export async function openChannel(store, channelId) {
    const thread = await threadModel(store).getOrFetch({ model: "discuss.channel", id: channelId });
    if (thread) {
        await thread.open({ focus: true });
    }
    return thread;
}

const onAiChannel = ({ thread }) => channelType(thread) === "ai";

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
