/** @odoo-module */
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class AgentPicker extends Component {
    static template = "pan_ai_pro.AgentPicker";
    static components = { Dialog };

    pick(agent) {
        this.props.onPick(agent.id);
        this.props.close();
    }
}
