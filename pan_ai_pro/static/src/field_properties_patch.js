/** @odoo-module */
import { SelectMenu } from "@web/core/select_menu/select_menu";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FieldProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/field_properties/field_properties";

import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

Object.assign(FieldProperties.components, { SelectMenu });

patch(FieldProperties.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.agentState = useState({
            agents: [],
            loaded: false,
            currentAgentId: false,
        });

        onWillStart(async () => {
            await this._loadAiAgents();
            await this._loadFieldAiAgent(this.props);
        });

        onWillUpdateProps(async (nextProps) => {
            await this._loadFieldAiAgent(nextProps);
        });
    },

    async _loadAiAgents() {
        if (this.agentState.loaded) return;
        try {
            const agents = await this.orm.searchRead(
                "ai.agent", [], ["id", "name", "llm_model"]
            );
            this.agentState.agents = agents;
        } catch {
            this.agentState.agents = [];
        }
        this.agentState.loaded = true;
    },

    async _loadFieldAiAgent(props) {
        const field = props.node.field;
        const isAi = !!field.ai || field.ai === "";
        if (!isAi) {
            this.agentState.currentAgentId = false;
            return;
        }
        try {
            const modelName = this.env.viewEditorModel.resModel;
            const fields = await this.orm.searchRead(
                "ir.model.fields",
                [["model", "=", modelName], ["name", "=", field.name]],
                ["x_ai_agent_id"],
                { limit: 1 }
            );
            this.agentState.currentAgentId =
                fields.length && fields[0].x_ai_agent_id
                    ? fields[0].x_ai_agent_id[0]
                    : false;
        } catch {
            this.agentState.currentAgentId = false;
        }
    },

    get aiAgentChoices() {
        return [
            { value: false, label: "Default (global setting)" },
            ...this.agentState.agents.map((a) => ({
                value: a.id,
                label: `${a.name} (${a.llm_model})`,
            })),
        ];
    },

    get currentAiAgentId() {
        return this.agentState.currentAgentId;
    },

    async onChangeAiAgent(agentId) {
        await rpc("/web_studio/edit_field", {
            model_name: this.env.viewEditorModel.resModel,
            field_name: this.props.node.field.name,
            values: { x_ai_agent_id: agentId || false },
        });
        this.agentState.currentAgentId = agentId || false;
    },
});
