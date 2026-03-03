/** @odoo-module */
import { SelectMenu } from "@web/core/select_menu/select_menu";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
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
        this.dialogService = useService("dialog");
        this.notification = useService("notification");
        this.agentState = useState({
            agents: [],
            loaded: false,
            currentAgentId: false,
            autoFill: false,
            autoUpdate: false,
            regenerating: false,
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
            this.agentState.autoFill = false;
            this.agentState.autoUpdate = false;
            return;
        }
        try {
            const modelName = this.env.viewEditorModel.resModel;
            const fields = await this.orm.searchRead(
                "ir.model.fields",
                [["model", "=", modelName], ["name", "=", field.name]],
                ["x_ai_agent_id", "x_ai_auto_fill", "x_ai_auto_update"],
                { limit: 1 }
            );
            this.agentState.currentAgentId =
                fields.length && fields[0].x_ai_agent_id
                    ? fields[0].x_ai_agent_id[0]
                    : false;
            this.agentState.autoFill =
                fields.length ? fields[0].x_ai_auto_fill : false;
            this.agentState.autoUpdate =
                fields.length ? fields[0].x_ai_auto_update : false;
        } catch {
            this.agentState.currentAgentId = false;
            this.agentState.autoFill = false;
            this.agentState.autoUpdate = false;
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

    get autoFillEnabled() {
        return this.agentState.autoFill;
    },

    get autoUpdateEnabled() {
        return this.agentState.autoUpdate;
    },

    async onChangeAutoFill(ev) {
        const enabled = ev.target.checked;
        await rpc("/web_studio/edit_field", {
            model_name: this.env.viewEditorModel.resModel,
            field_name: this.props.node.field.name,
            values: { x_ai_auto_fill: enabled },
        });
        this.agentState.autoFill = enabled;
    },

    async onChangeAutoUpdate(ev) {
        const enabled = ev.target.checked;
        await rpc("/web_studio/edit_field", {
            model_name: this.env.viewEditorModel.resModel,
            field_name: this.props.node.field.name,
            values: { x_ai_auto_update: enabled },
        });
        this.agentState.autoUpdate = enabled;
    },

    async onRegenerateAll() {
        const modelName = this.env.viewEditorModel.resModel;
        const fieldName = this.props.node.field.name;
        const fieldLabel = this.props.node.field.string || fieldName;

        this.dialogService.add(ConfirmationDialog, {
            title: "Regenerate all values",
            body: `This will regenerate "${fieldLabel}" for all records. Existing values will be overwritten.`,
            confirmLabel: "Regenerate",
            cancelLabel: "Cancel",
            confirm: async () => {
                this.agentState.regenerating = true;
                try {
                    await this.orm.call(
                        "ir.model.fields", "action_regenerate_ai_field",
                        [modelName, fieldName]
                    );
                    this.notification.add("Regeneration started in the background.", {
                        type: "success",
                    });
                } finally {
                    this.agentState.regenerating = false;
                }
            },
        });
    },

    async updateSystemPrompt(value) {
        await rpc("/web_studio/edit_field", {
            model_name: this.env.viewEditorModel.resModel,
            field_name: this.props.node.field.name,
            values: { system_prompt: value },
        });
        this.props.node.field.ai = value;
    },
});
