# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Who reads an answer, and what all of them may read
(docs/plans/agent-identity.md, section 3).

In a team channel or a group chat everybody in it reads the agent's answer.
An agent without a user of its own works with the asker's rights, so what
it reads is narrowed to what every reader may read: the intersection of
their read rights, the OpenID Foundation's answer to the CFO who asks about
salaries in a channel. Records, fields and the names behind many2one values
pass only when every reader may read them. Writes stay the asker's, with
their Allow. An agent with a dedicated user keeps that user's reach
(plans/agent-in-discuss.md, decision 1).
"""

from odoo.exceptions import UserError

# A channel read by more people than this is answered by an agent with its
# own user, or not at all: one access check per reader per tool call.
READERS_MAX = 300
# Records a total in a shared channel may cover.
GROUP_MAX = 5000


def readers(thread, run_user):
    """The other users who read this thread's answers, or None when the
    thread is private (an AI chat, a direct chat) or the agent has its own
    user. Raises when there are too many to check."""
    channel = thread.channel_id.sudo()
    if not channel or channel.channel_type not in ("channel", "group"):
        return None
    if thread.agent_id.run_as == "user":
        return None
    root = channel.parent_channel_id or channel
    users = root.channel_member_ids.partner_id.user_ids
    if root.channel_type == "channel":
        Users = channel.env["res.users"]
        users |= (
            root.group_public_id.all_user_ids
            if root.group_public_id
            else Users.search([], limit=READERS_MAX + 1)
        )
    users = (users - run_user).filtered("active")
    if len(users) > READERS_MAX:
        raise UserError(
            f"This channel has more than {READERS_MAX} readers. Ask me in a smaller channel, "
            "or in your own chat with me."
        )
    return users.sudo(False)


def records(deps, recs):
    """`recs` narrowed to what every reader may read."""
    for user in deps.audience or ():
        recs = recs.with_user(user)._filtered_access("read")
    return recs.with_env(deps.env)


def field_names(deps, Model, names):
    """The fields every reader's groups allow."""
    if not deps.audience:
        return names
    return [
        n
        for n in names
        if not Model._fields[n].groups
        or all(u.with_user(u).has_groups(Model._fields[n].groups) for u in deps.audience)
    ]


def scrub(deps, Model, rows):
    """Many2one values whose record not every reader may read lose their
    name: the id stays, the name says it is hidden."""
    if not deps.audience:
        return rows
    for name, field in Model._fields.items():
        if field.type != "many2one" or not rows or name not in rows[0]:
            continue
        ids = {r[name][0] for r in rows if r.get(name)}
        if not ids:
            continue
        visible = set(records(deps, deps.env[field.comodel_name].browse(ids)).ids)
        for row in rows:
            if row.get(name) and row[name][0] not in visible:
                row[name] = [row[name][0], "(hidden in this channel)"]
    return rows


def group_domain(deps, Model, domain):
    """For a total in a shared channel: only the records every reader may read."""
    found = Model.search(domain, limit=GROUP_MAX + 1)
    if len(found) > GROUP_MAX:
        raise UserError(
            f"More than {GROUP_MAX} records to total in a shared channel. Narrow the filter."
        )
    return [("id", "in", records(deps, found).ids)]
