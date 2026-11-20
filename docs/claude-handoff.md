# Handoff for Claude (the chat assistant that develops Scranton with Lu)

Read this first in a new chat. Lu writes "继续 Scranton" and nothing else.
Updated: 2026-11-19 22:25. Last commit when written: `8be6041`.

## How we work

- Reply to Lu in Chinese, plain and concrete. She picks options A/B/C. Bottom line first.
- Code lives in `lujin88/Scranton`, branch `main`. Run the full `pytest` before every push.
- Scranton runs on her Mac mini (port 8300). Deploy: push, then in the built-in browser on
  `http://localhost:8300/` call `POST /api/scranton/update/check` and `/api/scranton/update/apply`
  with `X-Session-Token: window.SESSION_TOKEN`; wait about 40 s; verify through the API.
- The remote shell on the mini has not worked since 11-18. Use the browser and the API.
- Look at the result (screenshots) before handing design work over. Icons: Remix only.
- When something fails, find the cause in the record first. Prefer a mechanical check or a tool
  result over another rule in a brief.
- Never read or use Agent Monitor's `token.txt`; never enter credentials; never repeat tokens.

## State on 2026-11-19, 22:25

Shipped today, none of it yet proven in real work:

- Activity: tiles, "Done, to check" (her words next to the result; Right / Not right; answers in
  the chat clear a card), stuck notices that clear after a restart, one row per repeated notice.
- Verification: `check` on board rows, `tools/page-walk.mjs` (widths, touch, slow 3G), JTBD
  walk-through in the QA role card, first-time-right rate in Report (shows after 5 checks).
- Design process: the visual designer asks Lu directly with a card (`[team] asks_owner`), one row
  at a time (`one_at_a_time`), second send-back means redo, picture-like references are made with
  image generation, the project manager cannot retell what Lu told a teammate herself.
- Sessions: a recap from the record at the start of every session (`/api/scranton/recap/{name}`);
  a new session only when the session is actually big (150k tokens; 8 h / 100 messages when the
  size is unknown).
- Quota: Cursor's "out of usage" is recognised and falls back to Auto; `chat_team(runs_on)` lets
  the project manager move a teammate to another app on Lu's say-so; a moved teammate gets the new
  app's chat tools.
- Models: webdev on Claude Sonnet 5.5 (not moved back to Cursor automatically); interns on
  Gemini 4 Argon; Claude default Sonnet 5.5; Cursor default Auto.

## Added on 2026-11-20

- A promised time on a board row wakes whoever holds it once it has passed, at night too; a
  restarted teammate is handed its row back after 40 s (seen working with dev at 10:12).
- `asks_owner = [visual, dev, motion]`, `one_at_a_time = [visual, dev]`. In Lu's DM with the visual
  designer the two work alone (her test of whether fewer hands gives better first drafts).
- Activity: a delivery links only the row it opens with; an acknowledgement is not a delivery; a
  result answers the instructions it opens with; several instructions get a pair of buttons each.
- Numbers on 11-20, 07:00–16:40, two channels: project manager 183 messages, 60 of them to Lu;
  Lu 125 messages; "no record of the last round" 3 times (10 the day before); right the first
  time 6 of 27 (partly judged from keywords, so rough).
- All teammates were restarted on the new wrapper by 10:15.

## Open

1. After her presentation on 11-20: restart pm, dev, qa and the others so they get the recap and
   the new session rule. visual, visualqa and motion were restarted on 11-19 at 22:20.
2. Check with real work whether design got better. If not, ask for the conversation and trace
   that one case; do not add rules from inference.
3. Count the project manager's cards to Lu again (21 in 11 hours on 11-19).
4. In about a week: how many deliveries missed "Done, to check", and whether the first-time-right
   number can be trusted.
5. Not started: a check at start-up that a teammate has its chat tools; clearing 7 stale mentions
   of Buzz in the rules; whether `@grok` is an outside bot (needs Lu); renaming 视觉校正 so it is
   not confused with 视觉设计师 (needs Lu); a monthly read-only audit of the rules.
6. Lu's side: mini prevent-sleep, Cursor app login, `gh auth login` for `lujinixdbot88`, delete
   `lu-migrate.tgz` on both machines after checking, Tailscale Serve if the ts.net address fails.
