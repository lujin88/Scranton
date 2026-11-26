# Handoff for Claude (the chat assistant that develops Scranton with Lu)

Read this first in a new chat. Lu writes "继续 Scranton" and nothing else.
Updated: 2026-11-26 23:15. Last commit when written: `111a190`. Older sections below are history.

## Handover to Claude Code, 2026-11-26 23:15

Lu is moving this work from the claude.ai chat to Claude Code. Everything below this section is
the record up to now; this section is what you need to carry on.

### If you run on the Mac mini itself

- Do not edit `~/Scranton` in place: it is the running install and updates itself with `git pull`.
  Work in a separate clone (for example `~/Scranton-dev`), run the full `pytest`, push to `main`,
  then update the running copy: `POST /api/scranton/update/check` and `/update/apply` on
  `http://localhost:8300` with header `X-Session-Token` (the token is `window.SESSION_TOKEN` in the
  page), wait about 45 s, and check `/api/scranton/status` shows `update.behind == 0`.
- To look at a design change, run `python3 run.py` in the clone on another port and take
  screenshots with Playwright; stop it afterwards. Never take port 8300 or 3000.
- Posting in Scranton for Lu: send through the page's websocket with `via: "claude"` and start the
  text with 「（Claude 代 Lu 发）」. Check the channel exists first.
- Still off limits: Agent Monitor's `token.txt`, `data/keys`, `data/grok-token`, `preview.key`,
  `~/.codex/auth.json`; entering any password; repeating any token; installing software updates
  (the Codex CLI "Update now" prompt: choose Skip); changing `~/.claude/settings.json` hooks.
  File cleanup means moving to `_to_delete`, never deleting. Vault: append to
  `~/Documents/lu-vault/03-side-projects/scranton/scranton-handoff.md` only; a nightly script
  pushes it, never commit or push the vault by hand.
- A PR that changes `.claude/`, `AGENTS.md`, `CLAUDE.md`, `.github/workflows/`, `.design-paths` in
  the team's repos is Lu's to merge. Do not tell teammates you will merge one for her.

### What shipped on 11-26 (none of it proven in real work yet)

- Low-priority projects (`[team.low_priority]`): lumin-sotry-telling, ai-pet, agent-monitor,
  contour-slide. Gemini teammates first, reviewers unchanged, only the PM takes things to Lu,
  once a day at 18:00.
- Model limit: a restart no longer loses the job (`_AUTO_NOTE`); `[team.model_limit] hold =
  ["gemdev"]` waits for the quota instead of moving to Flash.
- 接回: the Catch up button and `/接回` (`scranton_catchup.py`).
- 探索 work starts with two lines to whoever handed it out (`_restate_first`).
- `review`, first code review before QA, on Claude Sonnet (`[team.first_review]`,
  `_first_review_gate`, `roles/first-review.md`). Started once and answered correctly; has not
  reviewed a real PR.
- Role cards: QA and visual QA do not hold a PR for problems already on main; PM splits designers
  by project (visual: portfolio and interview work; visual2: Gratula, man-screen, the rest;
  visintern: low-priority projects).
- Effort set to high for dev, webdev, qa, review. Takes effect at their next restart. Lu agreed to
  a restart on the morning of 11-27.
- harness-core #116 media-check, #117 match-final, #118 ledger file names: merged by the team.
- LuJin-Portfolio #246 (AGENTS.md says the 11-13 merge rule): merged with Lu's say-so.

### Due on Friday 11-27 (two reminders are set in the claude.ai chat; do them here if Lu has moved)

1. 09:00 Count per PR for 11-25 to 11-27: Gemini (gemdev; Argon and Flash apart) against Claude
   (dev, webdev). Passed, returned, merged. A rough count on 11-26 evening from message headers:
   webdev 10 merged / 8 returned, dev 2 / 5, gemdev 3 / 6, and 2 of gemdev's 6 were problems
   already on main. visintern had 28 messages and no verdict from visual QA; scout and
   motionintern one message each. Lu asked whether Gemini is worth paying for; the answer so far
   is "not for the team", pending this count.
2. In the same count: for each PR, time from opened to merged, split into waiting for review,
   waiting for a fix, waiting for Lu. Lu says the team is slow; nothing has been measured.
3. `data/stop-check/log.jsonl`: webdev passed once, was sent back twice, then let through five
   times with the same 8 findings. Find out whether the 8 are real or false, then either fix the
   check or drop the "two send-backs, then let through" rule.
4. 09:10 First weekly spot check: 5 random 「视觉通过」 for Lu to judge. Blind: do not show her
   visual QA's verdict or reasons until she has judged.
5. Restart dev, webdev, qa so the effort change applies; check each gets its row back.
6. Append the evening's changes to the vault note (first review, pre-existing problems, designers
   by project, effort). The note is current up to the 接回 and 探索 changes.

### Waiting for Lu

- 「装」 under #25295 in #general for the two pstack verification skills, and which project
  (PM pointed out Lumi is Gemini-first, so the Claude-only skill may never run there; Gratula was
  suggested). She said "你可以装" in chat but has not posted it; the PR touching `.claude/` is hers
  to merge.
- Row 91 (font size and spacing table, portfolio). Once approved the PM schedules the design-system
  linter: hard-coded colours and one-off values first, portfolio first, CI PR for Lu to merge.
- Second visual QA or a third designer: she asked twice; the advice was a second visual QA first
  (options A to D, unanswered).
- Harness changes that only she can merge, offered and not yet asked for: merge conclusions are
  on an honour system because all teammates share one GitHub account; the "returned twice, no
  auto-merge" rule blocked a PR she had already approved; AGENTS.md carries sources and dates
  inline and has stale temporary clauses.
- Cursor comes back on 11-29: webdev stays on Claude or returns to Cursor (PM row 77).
- Ten of the fourteen test-set tasks.

### Numbers on 11-26 22:44

Claude week 42% (resets Sat 11-28 about 13:00), ChatGPT 18% (resets Tue 12-01 evening), Grok 82%
(Lu's own use, résumé and search), Cursor 100% (resets 11-29). Lu wants Claude used more before
the reset and ChatGPT kept for her own work this week; the PM was told to keep Claude teammates
busy with work that needs no decision from her, and not to produce more for her to look at.

### What to watch

- The first review adds a step. If QA rarely writes 「初审漏了」 and PRs take longer, send docs and
  few-line PRs straight to QA again.
- 探索 restating wakes the PM (Opus) every time. Drop it if it catches nothing in a week.
- motionintern still moves down to Flash at the limit although its motion code goes into PRs.
- Phones cannot put channels into groups (hover only). Claude and Gemini model lists are still
  written by hand; only Codex reads the live list.

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

## 2026-11-26 晚 代码初审、既有问题不挡 PR、设计师按项目分

- 新队友 `review`「代码初审」（Claude Sonnet；Lu 当晚说 ChatGPT 她自己要用、Claude 要多用，所以没放 ChatGPT）。`[team.first_review] agent = "review", final = "qa"`；`mcp_bridge._first_review_gate`：QA、初审、PM、Lu 以外的人把带 PR 链接的消息发给 @qa，而初审没贴过「初审通过」、QA 也没在这个 PR 上说过话，就 Not sent，让它先发 @review。QA 打回后的修复直接回 QA。角色卡 `roles/first-review.md`；QA 卡加「初审先过」。
- QA 和视觉校正角色卡各加一句：main 上本来就有的问题不挡当前 PR，列出来交 PM 另开行。
- PM 角色卡：设计师按项目分（visual：portfolio 和面试相关；visual2：Gratula、man-screen 等；低优先级先 visintern）。
- 测试：`tests/test_first_review.py`。
