# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""An agent without a user of its own in a team channel: added by an
administrator, mentioned like a colleague, and it answers with what every
reader of the channel may read (docs/plans/agent-identity.md, section 3)."""

from odoo.release import version_info

from .common import AiProCase

UUID_QUERY = [
    (
        "search_records",
        {
            "model": "ir.config_parameter",
            "domain": [["key", "=", "database.uuid"]],
            "fields": ["value"],
        },
    )
]


class TestChannelShared(AiProCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user.group_ids = [
            (4, cls.env.ref("base.group_system").id),
            (4, cls.env.ref("base.group_partner_manager").id),
        ]
        cls.bob = cls.env["res.users"].create(
            {
                "name": "Bob",
                "login": "bob",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.sales = cls.env["discuss.channel"].create({"name": "sales", "channel_type": "channel"})
        cls.sales._add_members(users=cls.user | cls.bob, post_joined_message=False)
        cls.agent.channel_ids = [(4, cls.sales.id)]

    def mention(self, text="@agent what is our database id?"):
        message = self.sales.with_user(self.user).message_post(
            body=text,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            partner_ids=[self.agent.partner_id.id],
        )
        sub = self.sales.sudo().sub_channel_ids.filtered(lambda c: c.from_message_id == message)
        return message, sub, sub.pan_ai_thread_ids[:1]

    def tool_results(self, thread):
        return thread.conversation

    def test_the_agent_is_a_member_and_answers_as_its_character(self):
        self.fake(["Hello."])
        message, sub, thread = self.mention("@agent hi")
        self.assertIn(self.agent.partner_id, message.partner_ids, "the mention is kept")
        run = thread.run_ids
        self.assertEqual((run.caller_id, run.user_id), (self.user, self.user), "for the asker")
        said = sub.sudo().message_ids.filtered(lambda m: m.author_id == self.agent.partner_id)
        self.assertIn("Hello", said.body)

    def test_it_reads_only_what_every_reader_may_read(self):
        self.fake([UUID_QUERY, "done"])
        _message, _sub, thread = self.mention()
        self.assertIn('"count": 0', self.tool_results(thread), "Bob may not read settings")
        # The same question in Sam's own chat: his rights, the value is there.
        self.fake([UUID_QUERY, "done"])
        chat = self.env["discuss.channel"].with_user(self.user).pan_ai_chat(self.agent.id)
        chat.message_post(body="db id?", message_type="comment", subtype_xmlid="mail.mt_comment")
        self.assertIn('"count": 1', chat.sudo().pan_ai_thread_ids.conversation)

    def test_an_agent_not_added_to_the_channel_stays_quiet(self):
        self.agent.channel_ids = [(3, self.sales.id)]
        self.fake(["never"])
        _message, sub, thread = self.mention("@agent hi")
        self.assertFalse(thread)

    def test_it_shows_in_the_channels_mention_suggestions(self):
        Partner = self.env["res.partner"].with_user(self.user)
        search = self.agent.name[:4]
        found = Partner.with_context(pan_ai_agents=True).search(
            Partner.with_context(pan_ai_agents=True)._get_mention_suggestions_domain(search)
        )
        self.assertIn(self.agent.partner_id, found, "suggested inside a channel")
        self.assertNotIn(
            self.agent.partner_id,
            Partner.search(Partner._get_mention_suggestions_domain(search)),
            "not in the chatter's suggestions elsewhere",
        )
        # The channel's own suggestions run through the same domain.
        Partner.get_mention_suggestions_from_channel(self.sales.id, search)

    def test_it_is_invited_from_the_channel_and_takes_no_seat(self):
        self.agent.channel_ids = [(3, self.sales.id)]
        Users = self.env["res.users"].with_context(active_test=False)
        users = Users.search_count([("share", "=", False)])
        Partner = self.env["res.partner"].with_user(self.user)
        found = Partner.search_for_channel_invite(self.agent.name[:4], self.sales.id)
        if version_info[0] >= 20:
            self.assertNotIn(self.agent.partner_id.id, found["partner_ids"], "20 would drop it")
            return
        self.assertIn(self.agent.partner_id.id, found["partner_ids"], "found in Invite")
        self.sales.with_user(self.user).add_members(partner_ids=found["partner_ids"][:1])
        self.assertIn(self.sales, self.agent.channel_ids)
        self.assertFalse(self.agent.partner_id.with_context(active_test=False).user_ids)
        self.assertEqual(Users.search_count([("share", "=", False)]), users, "no seat")
        self.assertEqual(self.agent.partner_id.im_status, "online", "always there")
        again = Partner.search_for_channel_invite(self.agent.name[:4], self.sales.id)
        self.assertNotIn(self.agent.partner_id.id, again["partner_ids"], "already a member")

    def test_a_change_in_a_channel_hides_the_old_value(self):
        acme = self.env["res.partner"].create({"name": "Acme", "phone": "111"})
        self.fake(
            [
                [
                    (
                        "write_record",
                        {"model": "res.partner", "id": acme.id, "values": {"phone": "222"}},
                    )
                ],
                "ok",
            ]
        )
        _message, _sub, thread = self.mention("@agent fix the phone of Acme")
        effect = thread.pending()[0]["effect"]
        self.assertEqual(effect, 'Change Contact "Acme": Phone: 222')
