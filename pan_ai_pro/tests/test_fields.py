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

    def test_the_fill_rpc_is_for_internal_users_who_may_write(self):
        from odoo.exceptions import AccessError, UserError

        from ..models.base import FILL_MAX

        self._ai_field(name="comment")
        self.fake(self._value("never"))
        partner = self.user.partner_id
        portal = self.env["res.users"].create(
            {
                "name": "Pat",
                "login": "pat",
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        with self.assertRaises(AccessError):
            partner.with_user(portal).pan_ai_fill("comment")
        # Sam has no write access on other contacts
        other = self.env["res.partner"].sudo().create({"name": "Someone else"})
        with self.assertRaises(AccessError):
            other.with_user(self.user).pan_ai_fill("comment")
        many = (
            self.env["res.partner"].sudo().create([{"name": f"p{i}"} for i in range(FILL_MAX + 1)])
        )
        with self.assertRaises(UserError):
            many.with_user(self.env.ref("base.user_admin")).pan_ai_fill("comment")

    def test_fill_now_queues_the_cron_and_a_failed_record_waits_a_day(self):
        from ..models.ir_model_fields import FILL_NOW_PARAM
        from ..runtime import field as field_runtime

        field = self._ai_field(name="comment")
        self.fake(self._value("filled"))
        from ..compat import params

        partner = self.user.partner_id
        # emptied by a program, not a person: a person's edit would protect it
        partner.with_context(pan_ai_filling=True).write({"comment": False})

        field.with_user(self.env.ref("base.user_admin")).action_pan_ai_fill_all()
        self.assertIn(str(field.id), params(self.env).get_str(FILL_NOW_PARAM, ""))
        self.env["ir.model.fields"]._cron_fill_ai_fields(batch_size=1000)
        self.assertEqual(params(self.env).get_str(FILL_NOW_PARAM, ""), "")
        self.assertEqual(partner.comment and "filled" in partner.comment, True)
        # a record that failed is left alone by the next batch
        Metadata = self.env["pan_ai.field.metadata"]
        Metadata._set("res.partner", [partner.id], "comment", last_error="bad", is_stale=True)
        self.assertNotIn(partner.id, field_runtime.missing_records(field, self.env.user).ids)
        self.assertEqual(field_runtime.fill_stale(field, self.env.ref("base.user_admin")), 0)

    def test_the_column_guard_answers_false_before_the_upgrade(self):
        from unittest.mock import patch

        from ..models import ir_model_fields as module

        Fields = self.env["ir.model.fields"]
        self.assertTrue(Fields._pan_ai_column_ready())
        self.env.registry._pan_ai_column_ready = False
        with patch.object(module, "column_exists", return_value=False):
            self.assertFalse(Fields._pan_ai_column_ready())
            self.assertFalse(Fields.pan_ai_fields_of("res.partner"))
        self.assertTrue(Fields._pan_ai_column_ready())

    def test_a_pull_before_the_upgrade_gets_its_columns_at_registry_load(self):
        from odoo.tools.sql import column_exists

        cr = self.env.cr
        self.env.flush_all()
        self.env.invalidate_all()
        cr.execute("ALTER TABLE ir_model_fields DROP COLUMN pan_ai_prompt")
        cr.execute("ALTER TABLE ir_model_fields DROP COLUMN pan_ai_use_tools")
        actions = self.env["ir.actions.server"]._table
        cr.execute(f"ALTER TABLE {actions} DROP COLUMN pan_ai_post")
        self.assertFalse(column_exists(cr, "ir_model_fields", "pan_ai_prompt"))
        added = self.env["ir.model.fields"]._pan_ai_add_missing_columns()
        self.assertEqual(
            sorted(added),
            [
                (actions, "pan_ai_post"),
                ("ir_model_fields", "pan_ai_prompt"),
                ("ir_model_fields", "pan_ai_use_tools"),
            ],
        )
        self.assertTrue(column_exists(cr, "ir_model_fields", "pan_ai_prompt"))
        # what every /web request does: read ir.model.fields whole
        cr.execute("SELECT pan_ai_prompt, pan_ai_use_tools FROM ir_model_fields LIMIT 1")
        self.assertEqual(cr.fetchone(), (None, False))
        # a second load adds nothing
        self.assertEqual(self.env["ir.model.fields"]._pan_ai_add_missing_columns(), [])

    def test_an_empty_or_invented_value_is_unresolved(self):
        partner = self.user.partner_id
        self._ai_field(name="comment")
        self.fake(self._value(None))
        n = partner.with_user(self.env.ref("base.user_admin")).pan_ai_fill("comment")
        self.assertEqual(n, 0)
        state = self.env["pan_ai.field.metadata"].search(
            [("model_name", "=", "res.partner"), ("res_id", "=", partner.id)]
        )
        self.assertIn("no value", state.last_error)
        run = self.env["pan_ai.run"].search([("thread_id.res_id", "=", partner.id)], limit=1)
        self.assertEqual(run.error_code, "unresolved")
        # a many2one id the model invented never reaches the database
        self._ai_field(name="comment", pan_ai_prompt=False)
        field = self._ai_field(name="country_id", prompt="The country of {{ object.name }}.")
        self.assertEqual(field.ttype, "many2one")
        partner.with_context(pan_ai_filling=True).write({"country_id": False})
        self.fake(self._value(999999999))
        n = partner.with_user(self.env.ref("base.user_admin")).pan_ai_fill("country_id")
        self.assertEqual(n, 0)
        self.assertFalse(partner.country_id)
        self._ai_field(name="country_id", pan_ai_prompt=False)
