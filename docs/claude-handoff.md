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

## 11-21 skills
- Skill limit by role is live (`[team.skills]` in config.toml, `scranton_skills.py`); all teammates restarted on it, pm and visual last (about 16:00).
- Composer shows the skills of whoever the message @mentions (`static/scranton-skills.js`), commit 8018a51.
- Open: plugin/account skills (figma, product-management, design, critique, pdf-viewer on Claude; figma, google-drive, documents, presentations, sites, spreadsheets on Codex) still load for everyone; waiting for Lu to say which role keeps which plugin. How to switch a plugin off per teammate is not verified yet.

## 11-24 stop check
- `tools/stop_check.py` runs as a Claude Code Stop hook for `[team.stop_checks] agents` (dev, webdev), written into each teammate's own settings file by `scranton_skills.launch_args`. Checks the branch's change: tsc errors in touched files, font sizes new to that top-level folder. Sent back at most twice per change. Log: `data/stop-check/log.jsonl`.
- Not yet seen working in a real Claude Code session on the mini: after Update + restart of dev and webdev, look at the log.

## 2026-11-26 模型额度用完：不丢活、写 PR 代码的不降级

- 原因（11-25 13:11 visintern）：PM 派活 14 秒后撞 Argon 额度，Scranton 以它的名字发了「…has used up its quota…」并重启。重启后的两条接活路径都落空：wrapper `_resume_unfinished` 把这条通知当成它的回复；`_sc_resume_text` 只认看板上它名下「在做」的行，而这行刚派还没改到它名下。
- 修：Scranton 代队友发的 5 种额度通知都带 `metadata={"auto": True}`（`app._AUTO_NOTE`），`wrapper._replied_since` 不算它们。
- `[team.model_limit] hold = ["gemdev"]`：名单里的人撞模型额度不换低一档，记进 `data/model_fallback.json`（`held: true`），以 Scranton 名义 @pm 一次（带手上的行），恢复时间到了由 `_sc_model_back_once` 原模型重启。其他人照旧降到 Flash。
- 测试：`tests/test_model_limit_hold.py`。

## 2026-11-26 接回、探索先复述目标（Lauren Tan 的两句提示词）

- **接回**：频道名旁的「Catch up」按钮（`static/scranton-catchup.js`），或输入 `/接回`、`/catchup`。`POST /api/scranton/catch-up {channel}` → `scranton_catchup.py` 从聊天和看板取事实：Lu 在这个频道上一次自己打字的消息（最近 15 分钟的、代发的、斜杠命令不算），之后的消息数、上线的行、在动的行、所有「等你」的行。没有任何变化就由 Scranton 直接回一句，不叫人；否则以 Scranton 名义 @pm（DM 里 @ 那位队友）写一条：做完了什么 + 等她定的（每项两句背景 + A/B/C，最多 5 项）。同一频道 2 分钟内只问一次。
- **探索先复述目标**：`mcp_bridge._restate_first`。6 小时内被「@某人 探索｜」派活的人，在这个频道发的第一条消息里要有一行「目标：…」（之前说过就放行），否则 Not sent。两行发给派活的人；派活的是 Lu 就发给 PM，不 @Lu。发完接着做，不等回复。「照做｜」不受影响。
- 测试：`tests/test_catchup.py`、`tests/test_restate_first.py`。
