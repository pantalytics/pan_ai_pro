/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Record } from "@web/model/relational_model/record";

// --- Patch Record: bypass mutex, silent RPC, show notification ---

patch(Record.prototype, {
    computeAiField(fieldName) {
        // Don't hold the model mutex — let the user keep editing
        return this._computeAiField(fieldName);
    },

    async _computeAiField(fieldName) {
        const field = this.fields[fieldName];
        if (!field?.ai) {
            throw new Error("Cannot compute a non-AI field using AI");
        }
        let value;
        try {
            // Use silent RPC — no loading indicator at the bottom
            value = await this.model.orm.silent.call(
                this.resModel, "get_ai_field_value",
                [this.resId || [], fieldName, this._getChanges()],
            );
        } catch (e) {
            if (e.exceptionName === "odoo.addons.ai_fields.tools.UnresolvedQuery") {
                this.model.notification.add(e.data.message, {
                    autocloseDelay: 7000,
                    title: "\uD83E\uDD16 Hmm\u2026",
                    type: "warning",
                });
                return;
            }
            throw e;
        }
        if (field.type === "many2many") {
            await this._update({ [fieldName]: value });
            return;
        }
        await this._update(
            this._parseServerValues({ [fieldName]: value }, { currentValues: this.data }),
        );
    },

    computeAiProperty(fullName) {
        return this._computeAiProperty(fullName);
    },

    async _computeAiProperty(fullName) {
        const property = this.fields[fullName];
        if (!property?.ai) {
            throw new Error("Cannot compute a non-AI property using AI");
        }
        let value;
        try {
            value = await this.model.orm.silent.call(
                this.resModel, "get_ai_property_value",
                [this.resId || [], fullName, this._getChanges()],
            );
        } catch (e) {
            if (e.exceptionName === "odoo.addons.ai_fields.tools.UnresolvedQuery") {
                this.model.notification.add(e.data.message, {
                    autocloseDelay: 7000,
                    title: "\uD83E\uDD16 Hmm\u2026",
                    type: "warning",
                });
                return false;
            }
            throw e;
        }
        return value;
    },
});

// --- Patch all AI field widgets: spinner via OWL useState ---

const AI_WIDGETS = [
    "ai_boolean", "ai_char", "ai_date", "ai_datetime", "ai_float",
    "ai_html", "ai_integer", "ai_many2many_tags_avatar", "ai_many2many_tags",
    "ai_many2one_avatar", "ai_many2one", "ai_monetary", "ai_selection", "ai_text",
];

for (const widgetName of AI_WIDGETS) {
    const def = registry.category("fields").get(widgetName, null);
    if (!def?.component) continue;
    patch(def.component.prototype, {
        setup() {
            super.setup(...arguments);
            this.aiState = useState({ computing: false });
        },
        get isAiComputing() {
            return this.aiState.computing;
        },
        async onAiClick() {
            this.aiState.computing = true;
            try {
                await this.props.record.computeAiField(this.props.name);
            } finally {
                this.aiState.computing = false;
            }
        },
    });
}
