# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Enterprise's AI field button runs on AI Pro, never on Odoo's LLM."""

from unittest.mock import patch

from odoo.addons.pan_ai_pro.tests.common import AiProCase
from odoo.exceptions import UserError
from odoo.tests import tagged

# Where Odoo's AI fields call Odoo's LLM from, on 19 and 20 alike.
NATIVE = "odoo.addons.ai_fields.models.models.get_ai_value"


def _native(*args, **kwargs):
    raise AssertionError("Odoo's own LLM path was called")


# A custom field: the registry is reloaded, so after every module is installed.
@tagged("post_install", "-at_install")
class TestEnterpriseAiFields(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.ir_field = cls.env["ir.model.fields"].create(
            {
                "name": "x_pan_note",
                "field_description": "Note",
                "model_id": cls.env["ir.model"]._get("res.partner").id,
                "ttype": "char",
                "ai": True,
                "system_prompt": "<p>A one-line note about {{ object.name }}.</p>",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Ada"})

    def _answer(self, value, unresolved=None):
        self.fake(
            [
                [
                    (
                        "final_result",
                        {
                            "value": value,
                            "could_not_resolve": bool(unresolved),
                            "unresolved_cause": unresolved,
                        },
                    )
                ]
            ]
        )

    def test_the_ai_button_fills_through_ai_pro(self):
        self._answer("Ada, a pioneer.")
        with patch(NATIVE, side_effect=_native):
            value = self.partner.with_user(self.admin).get_ai_field_value("x_pan_note", {})
        self.assertEqual(value, "Ada, a pioneer.")
        self.assertEqual(self.partner.x_pan_note, "Ada, a pioneer.")
        self.assertIn("{{ object.name }}", self.ir_field.pan_ai_prompt)
        run = self.env["pan_ai.run"].search([("thread_id.res_id", "=", self.partner.id)], limit=1)
        self.assertEqual(run.status, "ok")
        # the form saves the value it was given: not a person's edit
        self.partner.with_user(self.admin).write({"x_pan_note": value})
        state = self.env["pan_ai.field.metadata"].search(
            [("res_id", "=", self.partner.id), ("field_name", "=", "x_pan_note")]
        )
        self.assertFalse(state.human_edited)
        # Odoo's cron reaches AI Pro too
        self._answer("Ada, again.")
        with patch(NATIVE, side_effect=_native):
            self.partner._fill_ai_field(self.partner._fields["x_pan_note"])
        self.assertEqual(self.partner.x_pan_note, "Ada, again.")

    def test_a_failure_reaches_the_person(self):
        self._answer(None, unresolved="Nothing about Ada here")
        with patch(NATIVE, side_effect=_native), self.assertRaises(UserError) as caught:
            self.partner.with_user(self.admin).get_ai_field_value("x_pan_note", {})
        self.assertIn("Nothing about Ada here", str(caught.exception))
        self.assertFalse(self.partner.x_pan_note)
        # a record not saved yet has nothing for AI Pro to read
        with patch(NATIVE, side_effect=_native), self.assertRaises(UserError):
            self.env["res.partner"].with_user(self.admin).get_ai_field_value("x_pan_note", {})
