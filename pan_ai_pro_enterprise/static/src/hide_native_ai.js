/** @odoo-module */
import { registry } from "@web/core/registry";

// Enterprise 20 ships its own AI button and Ctrl+K entries (S1: registry
// names `ai.systray_action`, `ask_ai`, `chat_with_agent`). One agent button
// top right is enough: AI Pro's.
for (const id of ["ai.systray_action"]) {
    if (registry.category("systray").contains(id)) {
        registry.category("systray").remove(id);
    }
}
for (const id of ["ask_ai", "chat_with_agent"]) {
    if (registry.category("command_provider").contains(id)) {
        registry.category("command_provider").remove(id);
    }
}
