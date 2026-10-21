# A setup with choices, as a list of rows

What the design systems say about a form that walks a person through a few
choices (an agent: model, instructions, tools, access), and what AI Pro does
with it. Checked 2026-10-21. The brand's own rules are on
[brand.pantalytics.com/en/product-ui](https://brand.pantalytics.com/en/product-ui)
and [design-philosophy](https://brand.pantalytics.com/en/design-philosophy).

## What they advise

| Source | The rule | Where it lands here |
|---|---|---|
| [Apple HIG, Lists and tables](https://developer.apple.com/design/human-interface-guidelines/lists-and-tables) | "iOS Settings uses a hierarchy of lists to help people choose options." A row that drills into a subview gets a disclosure indicator (the chevron); an info button never navigates. "Keep item text succinct." | One agent is a list of rows; a row shows its value and ends in an arrow; the dialog is the subview |
| [Apple HIG, Settings](https://developer.apple.com/design/human-interface-guidelines/settings) | "Aim to provide default settings that give the best experience to the largest number of people." "Minimize the number of settings you offer." "Avoid using settings to ask for setup information you can get in other ways." | Model, instructions and access are filled on arrival; only Tools is open on a new agent; Advanced exists in developer mode only |
| [GOV.UK, Task list](https://design-system.service.gov.uk/components/task-list/) | A status per task, in colour and a short word; "The whole row is linked"; the list is done when every task is Completed. Not for showing answers. | The dot and the word (No tools, Not yet); the whole row opens its dialog |
| [GOV.UK, Check answers](https://design-system.service.gov.uk/patterns/check-answers/) | Each row: key, value, a Change link; after a change the person returns to the list, pre-filled, and repeats nothing. | The row's value is the answer; Save in the dialog returns to the list with the row updated |
| [GOV.UK, Question pages](https://design-system.service.gov.uk/patterns/question-pages/) | "Start by asking one question per page." Hint "a single short sentence, without any full stops"; "Do not use links in hint text." Radios and checkboxes show every option. | One dialog asks one thing; its help is one line; the model is a radio list, tool groups are checkboxes |
| [NN/g, Wizards](https://www.nngroup.com/articles/wizards/) | For novices and infrequent setup; show the steps and the current one; sensible defaults; let people leave midway. Wrong when people need to move between steps freely or repeat it often. | A list of rows, not a wizard: an administrator comes back to one row (Tools, Access) more often than to all five in order |
| [Polaris, Setup guide](https://shopify.dev/docs/api/app-home/patterns/compositions/setup-guide) | A checklist with progress, one action per step, marked complete when done, on the home page. "Give merchants the option to complete the onboarding at a later time." | Settings > AI Pro's three steps; the agent's five rows; a half-done agent is saved as it is |
| Brand, Product UI | A dialog suits one short step; a flow with checks gets its own page; a switch only for on/off with immediate effect, a checkbox for a choice saved later; no explainer copy; one primary action. | Dialogs with Save; web search is a checkbox; Chat is the one primary button, in row 5 |

## The shape, in one line

A list of rows (dot, name, value, arrow), the whole row opens one dialog
that asks one thing with every option in sight, Save returns to the list.
A wizard would force an order nobody needs; tabs hide the state.

## What we did not take

- A progress bar or step counter (Polaris, NN/g): five rows with dots show
  the same thing without a second element.
- "Continue" buttons and one question per page as pages (GOV.UK): the
  questions are short and independent, so a dialog each is the smaller shape.
- Inline controls on the row (Apple's toggles): a row's value is saved with
  the record, not applied at once, and the brand reserves a switch for
  immediate effect.
