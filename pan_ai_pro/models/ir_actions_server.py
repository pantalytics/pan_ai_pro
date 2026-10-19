"""Server actions and the agent.

Two directions. A server action as a tool: `pan_ai.tool` rows point at an
action the administrator exposed with a name, a description and a schema;
the runtime runs it as the run's user with the model's arguments in the
context as `pan_ai_args`. And the action type "Run AI agent": an automation
rule or a scheduled action starts a run with a prompt rendered from the
record. The run carries the rule's or the scheduled action's user, never
the superuser: a scheduled action set to run as OdooBot refuses.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..tools import commit


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[("pan_ai_run", "Run AI agent")], ondelete={"pan_ai_run": "cascade"}
    )
    pan_ai_agent_id = fields.Many2one("pan_ai.agent", string="Agent", ondelete="restrict")
    pan_ai_prompt = fields.Text(
        string="Prompt",
        help="Inline template: {{ object.name }}, {{ object.partner_id.email }}. Without a record, plain text.",
    )
    pan_ai_post = fields.Boolean(string="Post the answer on the record", default=True)
    pan_ai_activity = fields.Boolean(string="Create an activity with the answer")
    pan_ai_tool_ids = fields.One2many("pan_ai.tool", "action_id", string="AI tools")
    pan_ai_tool_count = fields.Integer(compute="_compute_pan_ai_tool_count")

    def _compute_pan_ai_tool_count(self):
        for action in self:
            action.pan_ai_tool_count = len(action.pan_ai_tool_ids)

    @api.constrains("state", "pan_ai_agent_id", "pan_ai_prompt")
    def _check_pan_ai(self):
        for action in self.filtered(lambda a: a.state == "pan_ai_run"):
            if not action.pan_ai_agent_id or not action.pan_ai_prompt:
                raise UserError(_("Run AI agent needs an agent and a prompt."))

    def _can_execute_action_on_records(self, records):
        # Odoo asks write access on the model for any server action. An AI run
        # reads the records and posts on them as the person who asked, so it
        # asks what it uses: AI Pro access and read on the records.
        self.ensure_one()
        if self.sudo().state != "pan_ai_run":
            return super()._can_execute_action_on_records(records)
        if not self.env.user.has_group("pan_ai_pro.group_user"):
            raise AccessError(_("You don't have enough access rights to run this action."))
        if records.ids:
            records.check_access("read")

    def _run_action_pan_ai_run_multi(self, eval_context=None):
        """One run per record, or one run without a record. The first slice
        runs here; the rest on the worker crons."""
        from ..runtime import slices

        self.ensure_one()
        if self.env.uid == self.env.ref("base.user_root").id or self.env.su and self.env.uid == 1:
            raise UserError(
                _(
                    "Run AI agent must run as a real user, not as OdooBot. Pick a user on the action."
                )
            )
        caller = self.env.user
        records = (
            eval_context.get("records") or eval_context.get("record") if eval_context else None
        )
        if (
            records is None
            and self.env.context.get("active_model")
            and self.env.context.get("active_ids")
        ):
            records = self.env[self.env.context["active_model"]].browse(
                self.env.context["active_ids"]
            )
        kind = "triggered" if records else "scheduled"
        targets = list(records) if records else [None]
        Thread = self.env["pan_ai.thread"]
        for record in targets:
            prompt = self._pan_ai_render(record)
            thread = Thread.sudo().create(
                {
                    "name": (prompt[:60] + ("..." if len(prompt) > 60 else ""))
                    if prompt
                    else self.name,
                    "kind": kind,
                    "user_id": caller.id,
                    "agent_id": self.pan_ai_agent_id.id,
                    "res_model": record._name if record is not None else False,
                    "res_id": record.id if record is not None else 0,
                    "post_answer": self.pan_ai_post and record is not None,
                    "activity": self.pan_ai_activity and record is not None,
                }
            )
            run = self.env["pan_ai.run"].start(thread, prompt, kind=kind, caller=caller)
            commit(self.env)
            token = run._claim()
            if token:
                slices.run_slice(
                    run, token, where="inline" if self.env.context.get("pan_ai_inline") else "cron"
                )
        return False

    def _pan_ai_render(self, record):
        template = self.pan_ai_prompt or ""
        if record is None or "{{" not in template:
            return template
        rendered = self.env["mail.render.mixin"]._render_template(
            template, record._name, record.ids, engine="inline_template"
        )
        return rendered.get(record.id, template)
