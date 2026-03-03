/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { EventBus, onWillStart, useState } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { Record } from "@web/model/relational_model/record";

// Shared bus — guarantees all widgets and the _save patch use the same instance.
const AI_BUS = new EventBus();

// --- Patch Record: bypass mutex, silent RPC, show notification ---

patch(Record.prototype, {
    async _save() {
        const result = await super._save(...arguments);
        if (result !== false) {
            AI_BUS.trigger("AI_STALE_CHECK");
        }
        return result;
    },

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

// --- Patch all AI field widgets: spinner + stale indicator via OWL useState ---

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
            this.orm = useService("orm");
            this.aiState = useState({ computing: false, stale: false });

            onWillStart(async () => {
                await this._loadStaleStatus();
            });

            // AI field widgets don't re-render when only context fields change,
            // so OWL lifecycle hooks won't fire. Listen on a module-level bus
            // that's guaranteed to be the same instance for all widgets.
            useBus(AI_BUS, "AI_STALE_CHECK", () => {
                this._loadStaleStatus();
            });
        },

        async _loadStaleStatus() {
            const field = this.props.record.fields[this.props.name];
            if (!field?.ai || !this.props.record.resId) {
                this.aiState.stale = false;
                return;
            }
            try {
                const result = await this.orm.silent.call(
                    "ir.model.fields", "get_ai_stale_fields",
                    [this.props.record.resModel, this.props.record.resId],
                );
                const isStale = result.stale.includes(this.props.name);
                const autoRegenerate = result.auto_regenerate.includes(this.props.name);

                if (isStale && autoRegenerate && !this.aiState.computing) {
                    // Auto-update: trigger regeneration immediately (like clicking the button)
                    this.onAiClick();
                    return;
                }
                this.aiState.stale = isStale;
            } catch {
                this.aiState.stale = false;
            }
        },

        get isAiComputing() {
            return this.aiState.computing;
        },

        get isStale() {
            return this.aiState.stale && !this.aiState.computing;
        },

        async onAiClick() {
            this.aiState.computing = true;
            try {
                await this.props.record.computeAiField(this.props.name);
                // After regeneration, clear stale flag
                this.aiState.stale = false;
            } finally {
                this.aiState.computing = false;
            }
        },
    });
}
