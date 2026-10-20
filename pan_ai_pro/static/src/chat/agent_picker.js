/** @odoo-module */
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { declareProps } from "@pan_ai_pro/chat/compat";

export class AgentPicker extends Component {
    static template = "pan_ai_pro.AgentPicker";
    static components = { Dialog };

    setup() {
        declareProps(this, (t) => ({
            agents: t.array(t.object()),
            onPick: t.function(),
            close: t.function(),
        }));
    }

    pick(agent) {
        this.props.onPick(agent.id);
        this.props.close();
    }
}
