# AI colleagues: the recipe

Five minutes to put an agent to work like a colleague. No Odoo user per
agent, so no extra licence. The why is in
[plans/ai-colleague.md](plans/ai-colleague.md) and
[plans/agent-identity.md](plans/agent-identity.md).

## 1. Give it a face and a role

AI Pro > Agents > New. Name it like a colleague ("Sanne"), and put its role
on the line under the name ("Sales: leads, quotes and follow-ups"). It gets
a portrait. Click the portrait to upload your own. Write the role into
Instructions too: what it works on, and what it must never do ("Never send
anything to a customer").

Under Access, **Sponsor** is you. You are the one who allows the changes of
runs that nobody started by hand.

## 2. Hand it a to-do

On any record, schedule an activity as usual. Set **Done by agent** to
Sanne. The to-do stays yours; Sanne does it for you, in your chat with her,
one to-do at a time. When she is done she leaves a note on the record and
marks the activity done.

## 3. Put it in a channel

In the channel, click **Invite a User** and type her name, the way you add a
colleague (Odoo 19; on Odoo 20 use the agent's Access, **Channels**). She
joins as a contact, not as a user, so she takes no seat. Type `@Sanne` and
your question. She answers in a thread under your message.

In a channel she only shows what *everybody* in it may see, even when you
may see more. Ask in your own chat when you need your full view.

## 4. Changes wait for you

Odoo has no undo. So before Sanne creates or changes anything, you see what
will change ("Contact "Acme": Phone: 111 → 222") and press Allow or Skip.
An Allow on a record somebody changed in the meantime does not run; she
reads it again. A question nobody answers stops after a day.

## What it costs

Nothing per agent: an agent is not an Odoo user. It works with the rights of
the person it works for. An agent can get a user of its own (Access, Runs
as: a dedicated user) when it needs rights of its own; on Odoo Enterprise
that is a paid user.
