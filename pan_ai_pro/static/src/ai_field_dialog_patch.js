/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { AiFieldConfigurationDialog } from "@web_studio_ai_fields/client_action/view_editor/interactive_editor/field_configuration/ai_field_configuration_dialog";
import { randomName } from "@web_studio/client_action/view_editor/editors/utils";

import { onWillStart, useState } from "@odoo/owl";

patch(AiFieldConfigurationDialog.prototype, {
    setup() {
        super.setup(...arguments);
        this.aiAgentState = useState({
            agents: [],
            loaded: false,
            selectedAgentId: false,
        });

        onWillStart(async () => {
            try {
                const agents = await this.orm.searchRead(
                    "ai.agent", [], ["id", "name", "llm_model"]
                );
                this.aiAgentState.agents = agents;
            } catch {
                this.aiAgentState.agents = [];
            }
            this.aiAgentState.loaded = true;
        });
    },

    get aiDialogAgentChoices() {
        return [
            { value: false, label: "Default (global setting)" },
            ...this.aiAgentState.agents.map((a) => ({
                value: a.id,
                label: `${a.name} (${a.llm_model})`,
            })),
        ];
    },

    async onConfirm() {
        if (["m2o", "m2m"].includes(this.state.fieldType) && !this.state.relationId) {
            this.state.showMissingRelationWarning = true;
            return;
        }
        const newNode = {
            field_description: {
                field_description: this.selectedField.description,
                model_name: this.props.propertiesModel,
                name: randomName(`x_studio_${this.selectedField.type}_field`),
                type: this.selectedField.type,
                ai: true,
                system_prompt: this.state.prompt,
            },
            tag: "field",
            attrs: { widget: this.selectedField.widget },
        };
        if (this.state.fieldType === "selection") {
            newNode.field_description.selection = this.state.selection;
        }
        if (["m2o", "m2m"].includes(this.state.fieldType)) {
            newNode.field_description.relation_id = this.state.relationId;
        }
        if (this.aiAgentState.selectedAgentId) {
            newNode.field_description.x_ai_agent_id = this.aiAgentState.selectedAgentId;
        }
        this.props.confirm(newNode);
        this.props.close();
    },
});
