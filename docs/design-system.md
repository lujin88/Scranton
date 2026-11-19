# Scranton design system (v3)

Code: `static/design-system.css` (tokens and components, loaded last). Icons: Remix Icon only, through `scIcon(name, size)` in `static/scranton-icons.js`; never draw one by hand.

v3 (2026-11-19) is the same system, reorganised. v2 had grown by one dated section per feature, so the rule for a button sat on line 37 and nine features later nobody read it: the Activity answer box shipped with its own font size, its own bordered field and its own outlined buttons. This version is ordered by what you are about to build.

## Before you add anything to the interface

Answer these with something that already exists. If none fits, extend the component here first, then use it.

| You need | Use | Never |
|---|---|---|
| Text | 14 body · 13 secondary · 12 meta (`--ds-fs-md/sm/xs`), weight 400 / 500 / 600 | 16px on desktop, 700, a size of your own |
| A button | `.sc-btn` (quiet) or `.sc-btn.primary` (one per group); `.sm` = 32px | an outlined button, a second primary |
| A place to type | `.sc-typebox` (the composer) | a bordered `<input>` or `<textarea>`, a button that says "Send" |
| A box around related things | a card: `--ds-raised`, `--ds-r-card`, no border | a 1px border, a shadow |
| A count | a pill: `--ds-accent-fill`, white, `--ds-fs-xs` 600 | a number in a coloured circle of your own |
| A choice between views | `.sc-tabs` pills, or `.sc-ov-tile` when each view has a number | underlined tabs, a `<select>` |
| An icon | `scIcon('name')` from the set in `scranton-icons.js` | an emoji, an SVG you drew, an icon from another set |
| A colour | a `--ds-*` token | a hex value in a component rule |

Then: look at the result next to an existing screen at 1440 and 390 wide, in the dark and the light theme, before anyone else sees it. `python -m pytest tests/test_design_tokens.py` must pass.

## Principles

1. **The page belongs to the conversation.** No top bar. Sidebar tools sit at the top of the sidebar. The channel or agent name floats top-left as a pill; clicking it opens the details panel.
2. **Separate by tone, not by lines.** Areas are told apart by different blacks. A line appears only where two areas of the same tone meet, in the next tone up, so it reads as a seam.
3. **Greys carry the hierarchy, one accent for action.** Darker is further back (sidebar), lighter is closer (your bubbles). Blue only for actions, unread and on-states. Red only for a real failure or the last step of something that removes.
4. **Soft corners, not round.** Controls 8, rows 10, cards and popovers 14, bubbles 18. Full pills only for tags, counts and the floating name pill.
5. **Little text.** A label says what a thing is in one or two words. A hint appears only where a choice is not obvious, and once per group, not once per item.
6. **One thing per row of attention.** A card is a few rows read top to bottom: what it is, the content, the actions on one line. If it needs seven separate pieces it is two cards or it is too much.

## Tokens

| Token | Dark value | Used for |
|---|---|---|
| `--ds-canvas` | `#0e0e0e` | Sidebar |
| `--ds-surface` | `#121212` | Conversation, details panel, settings, full pages |
| `--ds-raised`, `--ds-field` | `#1f1f1f` | Cards, grouped lists, the type box, seams |
| `--ds-selected` | `#202020` | Selected sidebar row |
| `--ds-bubble` | `#212121` | Agent message bubbles |
| `--ds-overlay` | `#2c2c2c` | Menus, popovers, floating pills, quiet buttons |
| `--ds-accent-soft` | accent at 16% | Your bubbles, on-state tint, the message you came for |
| `--ds-hover` | white at 5% | Hover on rows and quiet controls |
| `--ds-line`, `--ds-line-strong` | | Seams; the ring a type box gets on focus |

- Text: `--ds-text` `#f5f5f5`, `--ds-text-2` `#a7a7a7`, `--ds-text-3` `#8a8a8a` (timestamps, section labels; 5:1 on the surface).
- Accent: `--ds-accent` `#4c8df6` for links, icons and on-states; `--ds-accent-fill` `#2f6fde` under white text (passes AA). `--ds-danger` `#f47067`. Status: online `#3fb950`, away `#e3b341`.
- Type: `--ds-fs-xs` 12 · `sm` 13 · `md` 14 · `lg` 15 (titles in pills) · `xl` 20 (page and panel titles). On phones every field is 16px so iOS does not zoom; that is the only 16.
- Spacing: 4 · 8 · 12 · 16 · 24 · 32 · 48. Radius: `--ds-r-control` 8 · `--ds-r-row` 10 · `--ds-r-card` 14 · `--ds-r-pill`.
- Layout: sidebar 256, details panel 340, reading column `--ds-read-w` (820) centred. Pages that read like documents (Activity, Report) use that same column.
- Shadow only on floating layers (menus, popovers, dialogs): `0 12px 32px rgba(0,0,0,.45)`.
- There is no `--ds-border`. A token that is not defined in `design-system.css` draws nothing; the test catches it.

## Components

**Button** `.sc-btn`. Quiet: `--ds-overlay` fill, no border. `.primary`: accent fill, one per group, on the right. `.sm`: 32px high, 13px, weight 500. `.danger` only on the step that removes something, and that step asks for a second click. Buttons that sit together are the same height.

**Icon button.** 32 or 36px square, transparent until hover (`--ds-hover`), a `data-tip` and an `aria-label`.

**Type box** `.sc-typebox`. Wherever the owner types more than a name: `--ds-field`, radius 14, no border until focus (then a `--ds-line-strong` ring), 14px text, one line high and growing to 160px. An Enter icon at the right, grey when empty and accent when there is something to send. Enter sends, Shift+Enter is a new line. Used by: the message composer, the thread reply, answering a board row in Activity, asking about a rule. (`.sc-field` is taken: it is the labelled form field in Settings.)

**Text edited in place.** The text looks like text; hover gives it the `--ds-hover` fill, focus an accent ring, and a pencil icon button at its right says it can be changed. Used by the rule line and by rename.

**Card.** `--ds-raised`, `--ds-r-card`, padding 12–16, no border. Rows inside it read top to bottom: a 12px kicker saying what it is, the content, then the actions on one line with links at the left and buttons at the right.

**Row** (sidebar, menus, lists). 32–36px high, radius 10, hover `--ds-hover`, selected `--ds-selected`. No band on hover in the conversation: the floating toolbar is the signal there.

**Tile** `.sc-ov-tile`. A number over a two-word label; pressing it filters the list under it and pressing again clears. 等你 / Needs your answer is blue, 卡住 / Stuck is red, the rest neutral. Used on the board overview and at the top of Activity.

**Pill.** Counts and tags: `--ds-r-pill`, 12px 600. A count that means "yours to act on" is `--ds-accent-fill` with white text, in every row state.

**Tabs** `.sc-tabs` + `.sc-tab`. Pills, `--ds-overlay` when selected. Never underlines.

**Menu.** A flat list in a `--ds-overlay` popover that starts at the edge of what opened it. A row with a value and › opens a submenu to the right.

**Bubbles.** Agents `--ds-bubble`, you `--ds-accent-soft`; no borders. "N replies" sits under the bubble. "X is working…" is the last item in the conversation. Date divider: calendar icon and "Today", no rules.

**People and apps.** People are circles, app logos are squares. Offline is shown by the status dot only; avatars keep their colour. Neutral states (not signed in, not installed) are grey.

**Page head** `.sc-page-head`. Every full page (Activity, Report): 24px icon box, `h1` at `--ds-fs-xl` / 600, actions at the right, a 36px round close button last, in the reading column. Switching pages must not move the title. Use a `div`, not `header` (the legacy styles catch `header`).

**Details panel.** Big avatar, name, status, Start/Restart and Settings, tabs Activity / Terminal. For channels: members and Add people. Side panels start their title at the content edge (32px in).

**Inline create / rename in the sidebar.** The row turns into the field in place: same 32px height, padding and `#`, `--ds-field` fill with a 1px accent ring, check and × as 28px icon buttons.

**Pasted text chip.** A paste of 1200+ characters or 16+ lines becomes a chip in the attachment row instead of filling the box: 200 × 132, `--ds-overlay`, up to 4 lines of the text in 13px, a `PASTED` tag and a pencil button that puts the text back.

**Picture viewer.** Pinch or scroll zooms at the pointer (100–800%), drag moves, double-click toggles fit and 250%, keys `+` `-` `0`. A dark pill at the bottom centre: `subtract`, the percentage (click = fit), `add`.

**Terminal.** Background `#f5f5f5` light / `#161616` dark, `--ds-r-card`, 8px padding on `.xterm` (not on the box). A left drag always selects, ⌘C copies. One line above it says what you can do.

## Screens

**Sidebar.** A channel row shows one number, and only when something there is the owner's to act on (`.sc-need-pill`): questions and finished work addressed to her. How much the team said among themselves is not shown. Direct messages keep their unread count. Closed projects are one quiet line under the channel list, "Closed projects · N", each with Reopen.

**Activity.** Only what needs her. From the top:
1. Tiles: "Needs your answer", "Stuck", then "Done, to check" and "Rules to confirm" when there are any.
2. One row per project (`.sc-inbox-proj`: chevron, name, count pills). Six items or fewer: every project starts open. Under it, the questions put to her and the board rows that wait for her.
3. A board row opens in place: the teammate's own message with its pictures (click to enlarge), the row's link, and a type box to answer. The answer goes to the project's channel as "@teammate 行 N：…" and the row leaves 等你.
4. "Done, to check": one card per result (`.sc-check`), two columns (her words 2 : the result 3; stacked under 760px). Left: every instruction the result answers, in her words, with "sent back N times" when it has been. Right: who made it, their message, the pictures (click to enlarge). Foot: "Open in #channel" at the left, Not right / Right at the right. Not right opens one `.sc-typebox` for what is wrong; sending it posts her words back to the maker. Only Right finishes an instruction.
5. "Rules to confirm": its own section with two sentences saying what it is, then one card per rule (`.sc-lesson`): project, the rule (edit in place), "You said" with her own words and pictures (each opens the message), then "Ask about it" at the left and Drop / Keep at the right. A rule without her words beside it is never shown.
5. Stuck: teammates that stopped, board rows in 卡住, and rows with no update for four hours. Older than a day: behind one line.
6. One folded line: "Everything else that mentions you · N".

**Coming from Activity into a channel.** The message she came for keeps a 2px accent frame, `--ds-accent-soft` fill and an "Asked here" pill, in the channel and in the thread panel, until she answers, reacts, presses Esc, or 45 seconds pass. Only that message is marked.

**Channel.** At the top, when something waits for her: a `--ds-raised` strip, "Waiting for your answer", up to six rows, each with a check button meaning "seen, nothing more from me". Her reaction on a message counts as seen everywhere.

**Channel overview.** "Who's on what": tiles per state (等你, 卡住, 在做, 在 PR, 等 QA, 排队, 以后做), then rows by teammate. 以后做 is work put aside on purpose and is never counted as stuck. Next to the title: Pause project, Close project. "Your preferences for this project · N" opens the kept rules (Remove), the proposed ones (Drop / Keep) and a field to add one. Closing a project shows one card with three numbered steps that tick themselves, then the buttons; the last one is `.danger` and needs two clicks.

**Preview.** On a device other than the Scranton computer, a localhost link or a path in a message opens in a new tab through `/preview/…`. No element of its own.

## Checks

- `tests/test_design_tokens.py` runs with the test suite: every `var(--ds-…)` used without a fallback is defined; no raw pixel font size, no weight outside 400 / 500 / 600 and no outlined button is added beyond what is already there (the counts may only go down).
- `tools/ds-check.mjs` measures a deck or page in a browser and holds every slide to the project's `design-system/tokens.json` (fonts, type sizes, weights, title size and position). It does not read Scranton's own screens; those are checked by eye against this page.
- What no check sees: whether it looks good. Take the screenshot and look.

## Known debt

- About 600 `!important` in `design-system.css`, from layering over the legacy styles. New rules should win by being the right component, not by `!important`.
- Class names from features that were restyled still exist in the markup (`.sc-inbox-item`, `.sc-inbox-row`). Do not copy their one-off rules; use the components above.

### Widths and touch (checked 2026-11-19)

Every screen is walked at 1024, 768, 390 and 320 wide, the last three as touch screens, and the home page once on a slow 3G line (`tools/page-walk.mjs --slow`). Rules that came out of it:

- Two columns inside a page become one under 760px. A desktop rule with `!important` needs its own phone rule.
- A page title never shrinks to make room for tabs: under 420px the tabs go on their own row.
- A name and its buttons share a row only when both fit; under 420px the buttons go under the name.
- Chips are one line each and shorten with …; they never wrap.
- On a phone, status cards show on the home list and in a conversation, not over a full page.
- Static files are sent compressed and kept by the browser; first content on slow 3G went from 19.7 s to 3.9 s.
