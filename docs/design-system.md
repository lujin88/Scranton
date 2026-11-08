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

Text: `#f5f5f5` primary, `#a7a7a7` secondary, `#707070` tertiary (timestamps, section labels).
Accent: `#4c8df6` (hover `#6aa1f8`), text on accent white. Status: online `#3fb950`, away `#e3b341`, danger `#f47067`.

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
