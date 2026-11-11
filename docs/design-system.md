# Scranton design system (v2)

Code: `static/design-system.css` (tokens + components, loaded last). Icons: Remix Icon only, through `scIcon(name, size)` in `static/scranton-icons.js`. Never draw an icon by hand.

## Principles

1. **The page belongs to the conversation.** No top bar. Sidebar tools (hide sidebar, search) sit at the top of the sidebar. The channel or agent name floats top-left as a pill; clicking it opens the details panel on the right.
2. **Separate by tone, not by lines.** Areas are told apart by different blacks. A line only appears where two areas of the same tone meet (details panel), and it uses the next tone up (`#1f1f1f`), so it reads as a seam.
3. **Greys carry the hierarchy, one accent for action.** Darker = further back (sidebar), lighter = closer to you (your bubbles). Blue only for actions, unread and on-states.
4. **Soft corners, not round.** Controls 8, rows 10, cards and popovers 14, bubbles 18. Full pills only for tags, counts and the floating name pill.
5. **Little text.** Labels say what a thing is in one or two words; hints only where a choice isn't obvious.

## Blacks (sampled from Grok Bot)

| Token | Value | Used for |
|---|---|---|
| `--ds-canvas` | `#0e0e0e` | Sidebar |
| `--ds-surface` | `#121212` | Conversation, details panel, settings |
| `--ds-raised` / `--ds-field` | `#1f1f1f` | Composer, cards, grouped lists, inputs, seams |
| `--ds-selected` | `#202020` | Selected sidebar row |
| `--ds-bubble` | `#212121` | Agent message bubbles |
| `--ds-overlay` | `#2c2c2c` | Menus, popovers, floating pills, secondary buttons |
| `--ds-accent-soft` | `#3c3c3c` | Your message bubbles (lightest grey) |

Text: `#f5f5f5` primary, `#a7a7a7` secondary, `#8a8a8a` tertiary (timestamps, section labels; 5:1 on the surface, WCAG AA).
Accent: `#4c8df6` (hover `#6aa1f8`) for links, icons and on-states. Filled buttons use `#2f6fde` (hover `#3b7ae8`) so white text passes AA. Status: online `#3fb950`, away `#e3b341`, danger `#f47067`.

## Spacing, type, layout

- Spacing: 4 · 8 · 12 · 16 · 24 · 32 · 48.
- Type: 12 (meta) · 13 (secondary) · 14 (body, rows) · 15 (titles in pills) · 20 (panel titles). Weight 400 / 500 / 600 only.
- Sidebar 256 px, details panel 340 px, conversation column max 820 px, centred.
- Only floating layers (menus, popovers, dialogs) get a shadow: `0 12px 32px rgba(0,0,0,.45)`.

## Components

- **Buttons:** secondary = `--ds-overlay` fill, no border; primary = accent fill. Height 32–36, radius 8. Icon buttons 36×36, transparent until hover.
- **Rows** (sidebar, menus, lists): min 32–36 px high, radius 10, hover `rgba(255,255,255,.05)`, selected `--ds-selected`.
- **Menus:** flat list; a row with a value and › opens a submenu to the right (Status, Support).
- **Composer:** `--ds-field`, radius 14, no border until focus (hairline). + and ↵ are plain icon buttons; ↵ turns blue when there is something to send. Up to 3 quick @ chips: the people you @ most here, then overall.
- **@ list:** 300 px popover above the composer, search hint on top, people you @ most first.
- **Bubbles:** agents `#212121`, you `#3c3c3c`; no borders. Thread replies ("N replies") sit under the bubble, outside it. "X is working…" is the last item in the conversation.
- **Date divider:** calendar icon + "Today", no rules.
- **Details panel:** big avatar, name, status, Start/Restart + Settings, tabs Activity / Terminal. For channels: members and Add people.

## Rules added after the v2.1 review

- People are always circles; only app logos are squares.
- Offline is shown by the status dot only; avatars keep their colour.
- No row band on hover: the floating toolbar is the signal.
- Popovers start at the edge of what opened them (the @ list at the composer's left edge).
- Pages that read like documents (Activity, Report) use the same centred 820px column.
- Tabs are pills (`--ds-overlay` when selected), never underlines.
- Neutral states (not signed in, not installed) are grey; red is only for real failures.
- Search opens centred, without key hints.

## Terminal (live xterm view, 11-11)

- Background `#f5f5f5` light / `#161616` dark, radius `--ds-r-card`, 8 px inner padding on `.xterm`, never on the box (the fit addon would cut the last row).
- Selection is the accent at reading strength: light `rgba(47,111,222,.32)`, dark `rgba(76,141,246,.5)`; it stays (a bit lighter) when focus leaves, so you can still see what you copied.
- A plain left drag always selects text, even when the agent or tmux has turned on mouse reporting. The wheel still scrolls the agent. ⌘C copies.
- No tmux status bar in Scranton (the tab already says who it is); the green bar was tmux's default, not ours.
- The note above the terminal says what you can do in one line: "Live. Click inside to type. Drag to select, ⌘C to copy."

## Inline create / rename in the sidebar (11-11)

- The row turns into the field in place: same 32 px height, padding and `#` as a channel row, `--ds-field` fill with a 1 px accent ring, check and × as 28 px plain icon buttons.
- The channel being renamed is hidden behind it and stays hidden through re-renders (rows are `display:flex !important`, so hide with `setProperty('display','none','important')`).
