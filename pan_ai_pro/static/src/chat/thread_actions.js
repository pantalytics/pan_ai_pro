/** @odoo-module */
import { registerThreadAction, threadActionsRegistry } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";
import { AgentPicker } from "@pan_ai_pro/chat/agent_picker";
import { actionIcon, channelType, threadModel } from "@pan_ai_pro/chat/compat";

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
    icon: actionIcon("add", "fa fa-fw fa-plus"),
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
    icon: actionIcon("swap_horiz", "fa fa-fw fa-exchange"),
    name: _t("Switch agent"),
    onSelected: async ({ thread, store }) => {
        const orm = store.env.services.orm;
        const agents = await orm.call("discuss.channel", "pan_ai_agents", []);
        store.env.services.dialog.add(AgentPicker, {
            agents,
            onPick: async (agentId) => {
                const id = await orm.call("discuss.channel", "pan_ai_open", [agentId]);
                await openChannel(store, id);
            },
        });
    },
    sequence: 16,
    sequenceGroup: 20,
});

// A chat with an agent is one person and one agent: the channel actions
// about other people, calls and notifications say nothing here. What stays:
// New chat, Switch agent, Search Messages, Attachments, Open in Discuss, Close.
const NOT_ON_AI = [
    "add-to-favorites",
    "advanced-settings",
    "copy-invite-link",
    "delete-thread",
    "hide",
    "invite-people",
    "leave",
    "mark-read",
    "meeting-chat",
    "member-list",
    "meeting-to-chat",
    "notification-settings",
    "pinned-messages",
    "remove-from-favorites",
    "rename-thread",
    "view-recordings",
];
for (const id of NOT_ON_AI) {
    const definition = threadActionsRegistry.get(id, null);
    if (!definition) {
        continue;
    }
    const condition = definition.condition;
    definition.condition = function (params) {
        if (channelType(params.thread) === "ai") {
            return false;
        }
        return typeof condition === "function" ? condition.call(this, params) : condition ?? true;
    };
}
