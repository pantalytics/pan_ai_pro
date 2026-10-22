/** @odoo-module */
// Copyright 2025-2026 Pantalytics B.V. All rights reserved.
// SPDX-License-Identifier: Elastic-2.0
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";

/**
 * The agent's Model row: Odoo's own record picker over the Models list, the
 * dialog every many2one opens from "Search More", opened on the Recommended
 * filter so the shortlist is what shows first and the rest is one filter
 * click away. The pick is written to the agent and the form reloads through
 * the button's own onClose, the way a dialog action closes.
 */
async function pickModel(env, action, options = {}) {
    const agentId = action.params.agent_id;
    await new Promise((resolve) => {
        env.services.dialog.add(
            SelectCreateDialog,
            {
                resModel: "pan_ai.model",
                title: _t("Model"),
                multiSelect: false,
                noCreate: true,
                context: { search_default_recommended: 1 },
                onSelected: async (ids) => {
                    await env.services.orm.write("pan_ai.agent", [agentId], { model_id: ids[0] });
                },
            },
            { onClose: resolve }
        );
    });
    await options.onClose?.();
}

registry.category("actions").add("pan_ai_pro.pick_model", pickModel);
