# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The module's access rows, created for whichever access model this Odoo has.

Odoo 20 keeps rights and record rules in one model, `ir.access`, with a
domain per row. Odoo 19 keeps them apart: `ir.model.access` for the rights
and `ir.rule` for the domains. A CSV is read for the model its file name
says, so one CSV cannot serve both; `security/access.xml` calls `install`
instead and the rows below are the one source. The xml ids are the ones
the 20.0 CSV used, so an upgrade updates rows instead of adding them.
"""

from odoo import models

# (xml id, name, model, group xml id, operations, domain)
ACCESS = [
    (
        "access_agent_user",
        "agent: user reads the agents open to them",
        "pan_ai.agent",
        "pan_ai_pro.group_user",
        "r",
        "['|', ('group_ids', '=', False), ('group_ids', 'in', user.all_group_ids.ids)]",
    ),
    (
        "access_agent_manager",
        "agent: manager",
        "pan_ai.agent",
        "pan_ai_pro.group_manager",
        "crud",
        "",
    ),
    (
        "access_toolset_user",
        "toolset: user reads",
        "pan_ai.toolset",
        "pan_ai_pro.group_user",
        "r",
        "",
    ),
    (
        "access_toolset_manager",
        "toolset: manager",
        "pan_ai.toolset",
        "pan_ai_pro.group_manager",
        "crud",
        "",
    ),
    ("access_tool_user", "tool: user reads", "pan_ai.tool", "pan_ai_pro.group_user", "r", ""),
    ("access_tool_manager", "tool: manager", "pan_ai.tool", "pan_ai_pro.group_manager", "crud", ""),
    (
        "access_thread_own",
        "thread: own, read only (the conversation is the runtime's to write)",
        "pan_ai.thread",
        "pan_ai_pro.group_user",
        "r",
        "[('user_id', '=', user.id)]",
    ),
    (
        "access_thread_manager",
        "thread: manager",
        "pan_ai.thread",
        "pan_ai_pro.group_manager",
        "crud",
        "",
    ),
    (
        "access_run_own",
        "run: own reads",
        "pan_ai.run",
        "pan_ai_pro.group_user",
        "r",
        "[('user_id', '=', user.id)]",
    ),
    ("access_run_manager", "run: manager", "pan_ai.run", "pan_ai_pro.group_manager", "crud", ""),
    (
        "access_license_manager",
        "license: system",
        "pan_ai.license",
        "base.group_system",
        "crud",
        "",
    ),
    ("access_llm_user", "model list: user reads", "pan_ai.llm", "base.group_user", "r", ""),
    ("access_llm_system", "model list: system", "pan_ai.llm", "base.group_system", "crud", ""),
    (
        "access_field_metadata_user",
        "field state: user reads",
        "pan_ai.field.metadata",
        "pan_ai_pro.group_user",
        "r",
        "",
    ),
    (
        "access_field_metadata_manager",
        "field state: manager",
        "pan_ai.field.metadata",
        "pan_ai_pro.group_manager",
        "crud",
        "",
    ),
]

ALL = "[(1, '=', 1)]"


class Access(models.AbstractModel):
    _name = "pan_ai.access"
    _description = "AI Pro access rows, loaded per Odoo version"

    def install(self):
        """Called from security/access.xml on install and update."""
        if "ir.access" in self.env:
            self._install_ir_access()
        else:
            self._install_ir_model_access()

    def _model_id(self, model):
        return self.env["ir.model"]._get_id(model)

    def _group_id(self, xml_id):
        return self.env.ref(xml_id).id

    def _load(self, model, rows):
        self.env[model]._load_records(
            [
                {"xml_id": f"pan_ai_pro.{xml_id}", "values": values, "noupdate": False}
                for xml_id, values in rows
            ],
            update=True,
        )

    def _install_ir_access(self):
        rows = []
        for xml_id, name, model, group, operation, domain in ACCESS:
            values = {
                "name": name,
                "model_id": self._model_id(model),
                "group_id": self._group_id(group),
                "operation": operation,
                "domain": domain or False,
            }
            rows.append((xml_id, values))
        self._load("ir.access", rows)

    def _install_ir_model_access(self):
        rights, rules = [], []
        for xml_id, name, model, group, operation, domain in ACCESS:
            rights.append(
                (
                    xml_id,
                    {
                        "name": name,
                        "model_id": self._model_id(model),
                        "group_id": self._group_id(group),
                        "perm_read": "r" in operation,
                        "perm_write": "u" in operation,
                        "perm_create": "c" in operation,
                        "perm_unlink": "d" in operation,
                    },
                )
            )
            if domain:
                rules.append((xml_id.replace("access_", "rule_", 1), name, model, group, domain))
        self._load("ir.model.access", rights)
        # A rule for one group narrows every member, managers included (they are
        # users too): the manager gets an explicit rule that opens the model up.
        managers_all = {
            (model, "pan_ai_pro.group_manager") for _xml_id, _name, model, _group, _domain in rules
        }
        for model, group in sorted(managers_all):
            rules.append(
                (
                    f"rule_{model.replace('.', '_')}_manager_all",
                    f"{model}: manager",
                    model,
                    group,
                    ALL,
                )
            )
        self._load(
            "ir.rule",
            [
                (
                    xml_id,
                    {
                        "name": name,
                        "model_id": self._model_id(model),
                        "groups": [(6, 0, [self._group_id(group)])],
                        "domain_force": domain,
                    },
                )
                for xml_id, name, model, group, domain in rules
            ],
        )
