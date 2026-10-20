"""Until this Odoo is connected, AI Pro is Settings and nothing else; the
chat shows once the key is saved too; the checklist says where setup stands."""

from ..compat import params
from .common import AiProCase


class TestOnboarding(AiProCase):
    def menus(self, user):
        menus = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        return {m["xmlid"] for m in menus.values() if m.get("xmlid", "").startswith("pan_ai_pro.")}

    def disconnect(self):
        self.license.write({"status": "not_connected", "key": False, "plan": False})

    def test_connected_shows_the_app(self):
        self.assertIn("pan_ai_pro.menu_agents", self.menus(self.user))
        self.assertIn("pan_ai_pro.menu_toolsets", self.menus(self.env.ref("base.user_admin")))

    def test_not_connected_admin_sees_settings_only(self):
        self.disconnect()
        self.assertEqual(
            self.menus(self.env.ref("base.user_admin")),
            {"pan_ai_pro.menu_root", "pan_ai_pro.menu_configuration", "pan_ai_pro.menu_settings"},
        )

    def test_not_connected_user_sees_no_app(self):
        self.disconnect()
        self.assertEqual(self.menus(self.user), set())

    def test_reconnecting_brings_the_menu_back(self):
        self.disconnect()
        self.menus(self.user)  # cached as hidden
        self.license.write({"status": "active", "key": "mp_test", "plan": "beta"})
        self.assertIn("pan_ai_pro.menu_agents", self.menus(self.user))

    def ready(self, user):
        return self.env["ir.http"].with_user(user)._pan_ai_chat_ready()

    def test_chat_needs_the_connection_and_the_key(self):
        self.assertTrue(self.ready(self.user))
        params(self.env).set_str("pan_ai.openrouter_key", "")
        self.assertFalse(self.ready(self.user))
        params(self.env).set_str("pan_ai.openrouter_key", "sk-or-test")
        self.disconnect()
        self.assertFalse(self.ready(self.user))

    def test_checklist(self):
        settings = self.env["res.config.settings"].create({})
        self.assertTrue(settings.pan_ai_entitled)
        self.assertTrue(settings.pan_ai_has_key)
        self.assertFalse(settings.pan_ai_has_chatted)
        self.fake(["Hi."])
        self.chat()
        self.env["pan_ai.run"]._cron_run_slices()
        self.assertTrue(self.env["res.config.settings"].create({}).pan_ai_has_chatted)

    def test_connected_without_plan_says_why(self):
        self.license.write({"plan": False})
        settings = self.env["res.config.settings"].create({})
        self.assertFalse(settings.pan_ai_entitled)
        self.assertEqual(settings.pan_ai_state, "connected")
        self.assertIn("no AI Pro plan", settings.pan_ai_why_not)

    def test_open_chat(self):
        action = self.env["res.config.settings"].create({}).action_pan_ai_open_chat()
        self.assertEqual(action["tag"], "pan_ai_pro.open_chat")
        self.assertTrue(action["params"]["channel_id"])
