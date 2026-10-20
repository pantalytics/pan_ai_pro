# brand.pantalytics.com, applied

What the brand's Product UI page asks, and where this module does it.
Checked 2026-10-19 against https://brand.pantalytics.com/en/product-ui.

| The rule | Here |
|---|---|
| Odoo-native where possible; no custom chrome where a standard widget does | The chat is Odoo's own chat window and Discuss pane; agents, toolsets, tools, threads and runs are standard list and form views; settings use Odoo's settings markup. The only CSS of ours: the stream, the tool rows, the approval card, tables in an answer (`static/src/chat/chat.scss`) |
| One primary action per screen; outline for the rest; destructive last, under a danger zone, with a confirmation | Agent form: Chat. Settings: Connect to Pantalytics first; Remove key, Delete all threads and Disconnect in a Danger zone block, each with a confirmation that names the thing and the consequence |
| Colour means status; purple only for the primary action and links, never a status | Connected in green, broken in red, waiting in amber (Odoo's text classes), the approval card's border included: it waits for the person, so it is a status. The accent is on Allow, the one primary action, and nowhere else |
| Page types: list, overview, settings, flow, empty | Agents, Threads, Runs, Toolsets, Tools, AI fields are lists; one agent is a form; Settings is a settings page; the empty states say one line and one action |
| Say each fact once; silent when healthy | The settings connection row shows one state. A healthy chat shows nothing but the messages; tool rows and the approval card appear only while something is happening |
| Speed: a click answers within 100 ms, the next frame within 200 ms, motion only on transform and opacity, none with reduced motion | Measured in a real browser: first token 27 ms after the server sent it, slowest batch 31 ms (`scripts/browser/check_chat.py`). The only motion is the tool row pulse, opacity only, off under `prefers-reduced-motion` |
| Writing: sentence case, verb and thing on buttons, short help, status words, errors say what happened and what to do, no em dashes, read back for AI tells | "Connect to Pantalytics", "Remove key", "Fill empty records now"; "Connected", "Not connected", "Waiting for approval"; "Could not reach Pantalytics. Check that this server can make outgoing HTTPS requests."; `scripts/checks/no_em_dash.py` in CI; the copy was read against the humanizer checklist before shipping |
| Fixed terms: workspace, member, Administrator, Odoo instance, key | "Administrator" for who may configure; "key" for the OpenRouter key and the installation key; "Pantalytics account" for the connection |
| Icons: one ring, one object, one accent; AI Pro is the sparkles | `static/description/icon.png` is the brand's rendered `ai-pro.png` (brand repo, `public/images/app-icons/`), used by the Apps page, the menu and the systray button |
| Tone: quiet, human; no explainer copy on screen | Help lines are one sentence. Nothing on a screen explains how the product works; the docs do |

What the brand page does not cover and we decided: the agent's streamed
text stays plain while it streams and is rendered once at the end (the
final body), so nothing jumps; an approval card is a bordered block inside
the message, not a dialog, because the person is in the middle of reading.
