"""AI fields: a prompt on a field, a value from the agent, the state rows."""

from .common import AiProCase


class TestFields(AiProCase):
    def _ai_field(self, name="comment", prompt="A one-line note about {{ object.name }}.", **vals):
        field = (
            self.env["ir.model.fields"]
            .sudo()
            .search([("model", "=", "res.partner"), ("name", "=", name)])
        )
        field.write({"pan_ai_prompt": prompt, **vals})
        return field

    def _value(self, text):
        return [
            [
                (
                    "final_result",
                    {"value": text, "could_not_resolve": False, "unresolved_cause": None},
                )
            ]
        ]

    def test_a_value_is_written_and_the_state_is_clean(self):
        field = self._ai_field(name="comment")
        self.fake(self._value("Sam, a tester."))
        partner = self.user.partner_id
        n = partner.with_user(self.env.ref("base.user_admin")).pan_ai_fill("comment")
        self.assertEqual(n, 1)
        self.assertIn("Sam, a tester.", partner.comment)
        state = self.env["pan_ai.field.metadata"].search(
            [("model_name", "=", "res.partner"), ("res_id", "=", partner.id)]
        )
        self.assertFalse(state.is_stale)
        self.assertFalse(state.human_edited)
        run = self.env["pan_ai.run"].search([("thread_id.res_id", "=", partner.id)], limit=1)
        self.assertEqual(run.status, "ok")
        self.assertEqual(field.pan_ai_inputs(), {"name"})

    def test_an_input_change_marks_stale_and_a_human_edit_protects(self):
        self._ai_field(name="comment")
        partner = self.user.partner_id
        partner.write({"name": "Sam Two"})
        state = self.env["pan_ai.field.metadata"].search(
            [
                ("model_name", "=", "res.partner"),
                ("res_id", "=", partner.id),
                ("field_name", "=", "comment"),
            ]
        )
        self.assertTrue(state.is_stale)
        partner.write({"comment": "my own words"})
        self.assertTrue(state.human_edited)
        self.assertFalse(state.is_stale)
        self.assertEqual(partner.pan_ai_stale_fields(partner.id), {"stale": [], "auto": []})

    def test_could_not_resolve_writes_nothing(self):
        self._ai_field(name="comment")
        self.fake(
            [
                [
                    (
                        "final_result",
                        {"value": None, "could_not_resolve": True, "unresolved_cause": "No data"},
                    )
                ]
            ]
        )
        partner = self.user.partner_id
        n = partner.with_user(self.env.ref("base.user_admin")).pan_ai_fill("comment")
        self.assertEqual(n, 0)
        self.assertFalse(partner.comment)
        state = self.env["pan_ai.field.metadata"].search(
            [("res_id", "=", partner.id), ("field_name", "=", "comment")]
        )
        self.assertEqual(state.last_error, "No data")

    def test_fill_missing_skips_human_edited(self):
        field = self._ai_field(name="comment", pan_ai_auto_fill=True)
        partner = self.user.partner_id
        partner.write({"comment": "mine"})
        partner.write({"comment": False})
        self.fake(self._value("generated"))
        from ..runtime import field as field_runtime

        field_runtime.fill_missing(field, self.env.ref("base.user_admin"), limit=50)
        self.assertFalse(partner.comment)

    def test_only_stored_fillable_fields(self):
        from odoo.exceptions import UserError

        with self.assertRaises(UserError):
            self._ai_field(name="image_128")
