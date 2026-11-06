# Analysis: whose identity and rights an agent uses

2026-11-06. Question: how should an AI Pro agent be identified and
authorised in Odoo, so that five agents cost no extra Odoo users and nobody
sees data they should not? Thirteen sources were read: Microsoft (four),
the OpenID Foundation, the IETF, Okta/Auth0, WorkOS, OWASP, Anthropic, two
research papers and an independent security review. Salesforce is covered
through secondary sources only (its own pages refused the fetch). The list
is at the end.

## 1. Conclusion first

1. **By default an agent acts on behalf of a person, never as itself.** Its
   reach is that person's rights, narrowed by the agent's own tool scope.
   The person is accountable and approves writes. This needs no Odoo user
   per agent. It is what every source recommends for interactive agents.
2. **In a shared channel the agent answers with what every member may
   read**: the intersection of the members' read rights, not the asker's.
   Writes stay the asker's, with their Allow. This is the OpenID
   Foundation's answer to the "CFO in a channel" problem and needs no Odoo
   user either.
3. **An agent's own identity (a dedicated Odoo user) is only for work with
   no person behind it**: watches and schedules. In Odoo that is a paid
   user on Enterprise. Odoo has no free agent licence like Salesforce's.
4. **Every action names both the agent and the person.** In OAuth terms the
   person is the subject and the agent is the actor. In AI Pro that is the
   run log, plus "via Ava" where Odoo's chatter shows the change.

Dropped: running in a channel with the asker's rights (my earlier
proposal). Section 3 explains why.

## 2. What the field agrees on

**Three modes, named the same way everywhere.** Microsoft's Agent 365 has
three execution modes [2]:

- S2S: "the agent runs without a user context and acts as its own agent
  identity".
- OBO: "the user is the token subject and the agent identity is the actor".
- Agentic user: the agent "runs with its own Microsoft Entra user account".

The account is optional: "Add a user account only when the agent requires
one" [2]. It is for a mailbox, Teams presence or a directory profile, and
it is still in preview. The Entra SDK maps the same split onto "autonomous"
and "interactive" agents [1]. Okta ships both: "Agent as Principal" for
identities "distinct from the users they serve", and On-Behalf-Of token
exchange for "correctly scoped downstream tokens" [9].

**Delegation, not impersonation.** The OpenID Foundation: "User
impersonation by agents should be replaced by delegated authority", and
agents must "prove their delegated scope while remaining identifiable as
distinct from the user they represent" [6]. The IETF draft gives the
mechanism: an `act` claim that names the agent next to the user's `sub` [7].
WorkOS adds the principle that "Authority reduces, not amplifies": a
delegated agent never gets more than the user has [8]. South et al. design
the same thing with a delegation token signed by the human [11].

**Borrowed or shared credentials are the risk.** For Copilot Studio,
Microsoft warns that tools on the maker's credentials "could lead to
oversharing of data or capabilities". With end-user credentials, "each end
user only has access to what their own account allows" [3]. OWASP lists
identity and privilege abuse as ASI03. Its mitigations are distinct agent
identities, "permissions granted per task, not as standing access", and
tracing every action to "the agent, the requesting user, and the task"
[10]. A security review of Entra Agent ID found that a shared blueprint
credential is a single point of compromise. It advises preferring
"delegated over application permissions" [5].

**Approval does not scale per action.** The OpenID Foundation: users "will
face thousands of authorization requests", and "per-action authorization
must be replaced by a more robust model of pre-authorized, policy-based
controls" within "a clearly defined operational envelope" [6]. South et al.
also warn of "prompt fatigue" [11].

**Accountability needs a named person.** Agent 365 requires a sponsor for
every agent: "the business representative accountable for the agent's
purpose and lifecycle" [2].

**Agents are not licensed like people, except where the platform needs a
user.** Microsoft licenses Agent 365 per human user: "no additional
per-agent or per-instance charges" [4]. Salesforce runs autonomous agents
as an "Agent User" on a separate Einstein Agent licence. Secondary sources
say it does not take a paid seat and cannot log in [14]. Its employee
agents run as the logged-in user and follow "the same permissions" [14].

## 3. The shared channel: the one hard case

The OpenID Foundation describes our exact question [6]:

> "you could imagine a CFO having an agent answer questions in a chat
> channel. While the CFO may have access to salary data, not every member
> of the channel does. As a result, the agent may disclose confidential
> salaries because it can act under the CFO's permission. It lacks a
> standardized method for respecting the subset of permissions that
> overlap for all users in the channel."

It adds that "no popular protocol exists to support shared agents" [6].

That rules out the asker's rights in a channel. There are two answers
that hold:

| | Claude in Slack [12] | Intersection [6] |
|---|---|---|
| Whose reach | The channel's: connectors an admin sets per channel, on service accounts, "everyone in a given channel works with the same capability" | What every member of the channel may read |
| In Odoo | A user per agent or per channel: a seat | Run as the asker, and drop from every tool result what not every member may read: no seat |
| Admin work | Configure each channel | None: Odoo's own groups and record rules decide |
| Weak spot | The reach is wider than some members' | Aggregates and tools we cannot filter |

**The recommendation is the intersection**, because Odoo already knows
every member's rights.

- **Reads.** `search_records` and `read_records` keep a record only when
  every member of the channel may read it, and a field only when every
  member's groups allow it. `read_group` aggregates only over those
  records.
- **Writes.** The asker makes them, with their Allow. They are accountable,
  as they are for what they paste in a channel.
- **Tools we cannot filter** (server actions, MCP tools) are off in a
  shared channel. The answer says so.
- **Large channels.** A channel with all employees ends at what every
  employee may read, which is the right answer there.
- **Cost.** One access check per member per tool call. That is fine up to
  a few hundred members. Beyond a cap the agent says the channel is too
  large.

This replaces decision 1 of plans/agent-in-discuss.md (a channel needs a
dedicated user) for agents without one. An agent that has a dedicated user
keeps that user's reach in channels.

## 4. What this means for AI Pro

| Where | Mode | Reach | Approves | Seat |
|---|---|---|---|---|
| AI chat, a to-do ("Done by agent"), a person's automation | Delegated (OBO) | The person's rights ∩ the agent's tool groups | The person | No |
| Team channel, group chat | Delegated, attenuated | The asker's rights ∩ what every member may read | The asker | No |
| Watch or schedule with nobody behind it | Own identity | The dedicated user's rights | Its sponsor | Yes, on Enterprise |

Next to that:

- **Sponsor.** Every agent gets a responsible person [2]. That person hears
  about failures and approves for runs with nobody behind them. This also
  closes #58.
- **Envelope instead of a click per write** [6]. Per agent and per tool
  group, the administrator can allow named changes without asking, for
  example "update phone and email on contacts". Approval cards stay for
  everything else.
- **Actor and subject in the trail** [7]. The run log already records the
  agent, the person and every call. A write made for a person gets "via
  Ava" in the chatter.
- **No archived users** to dodge seats. Odoo counts active users and treats
  archived ones as gone (plans/ai-colleague.md, section 5). The point of
  delegation is that no extra account is needed at all.

## 5. Sources

1. Microsoft Learn, *Agent identities: autonomous and interactive agent patterns* (Entra ID Auth SDK). https://learn.microsoft.com/en-us/entra/msidweb/agent-id-sdk/agent-identities
2. Microsoft Learn, *Agent 365 identity*. https://learn.microsoft.com/en-us/microsoft-agent-365/developer/identity
3. Microsoft Learn, *Control maker-provided credentials for authentication* (Copilot Studio). https://learn.microsoft.com/en-us/microsoft-copilot-studio/configure-no-maker-authentication
4. Microsoft Licensing FAQ, *Agent 365*. https://www.microsoft.com/licensing/faqs/122
5. Compass Security, *Entra Agent ID from a security perspective* (June 2026). https://blog.compass-security.com/2026/06/entra-agent-id-from-a-security-perspective/
6. OpenID Foundation, *Identity Management for Agentic AI*, v1.1 (October 2025). https://openid.net/wp-content/uploads/2025/10/Identity-Management-for-Agentic-AI.pdf
7. IETF Internet-Draft, *OAuth 2.0 Extension: On-Behalf-Of User Authorization for AI Agents*, draft-02 (expired, not adopted). https://datatracker.ietf.org/doc/html/draft-oauth-ai-agents-on-behalf-of-user-02
8. WorkOS, *OAuth on-behalf-of for AI agents*. https://workos.com/blog/oauth-on-behalf-of-ai-agents
9. Okta, *Auth0 gives developers the identity layer to securely ship agentic apps* (May 2026). https://www.okta.com/newsroom/articles/auth0-may-2026-product-innovations/
10. Adversa AI, *OWASP ASI03: Identity & Privilege Abuse in AI Agents*. https://adversa.ai/blog/owasp-asi03-identity-privilege-abuse-in-ai-agents/
11. South et al., *Authenticated Delegation and Authorized AI Agents*, arXiv 2501.09674. https://arxiv.org/html/2501.09674
12. Anthropic, *Claude Tag: how it works*. https://www.claude.com/docs/claude-tag/concepts/how-it-works
13. *AI Identity: Standards, Gaps, and Research Directions for AI Agents*, arXiv 2604.23280 (abstract only): the gaps include "recursive delegation accountability", and "these gaps are structural". https://arxiv.org/abs/2604.23280
14. Salesforce, secondary only: Salesforce Ben, *Agentforce permissions explained*, https://www.salesforceben.com/agentforce-permissions-explained-agent-users-access-and-security/, and Trailhead, *Get started with Agentforce for employees*, https://trailhead.salesforce.com/content/learn/modules/agentforce-for-employees-quick-look/get-started-with-agentforce-for-employees (search excerpts; the pages refused the fetch).
