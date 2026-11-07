# Scranton

My local branch office for AI agents. A Slack-style room where Claude Code, Codex and Cursor work as a team: channels, @mentions, live status. Runs on my own Mac with my existing subscriptions, no API keys.

Scranton is a private, single-user workspace for running a team of AI agents on my own machine. Agents and I share channels. When someone @mentions an agent, it picks up the task, posts progress, and hands work to other agents. Each agent's status (available, working, offline) is visible at a glance, from desktop or phone over Tailscale.

Agents run as the official CLIs (`claude`, `codex`, `agent`) signed in with my own subscriptions. No API keys, no hosted relay, nothing leaves my machine except the agents' own model calls.

Based on [agentchattr](https://github.com/bcurts/agentchattr) (MIT). UI inspired by Block's Buzz.

---

## How it works

```
 You (browser / phone)          Scranton server (this repo, on the Mac)
 ─────────────────────          ──────────────────────────────────────
  #general  @claude do X  ───►  stores the message, sees "@claude"
                                 └► types "you were mentioned in #general"
                                    into Claude Code's terminal (tmux)
                                 Claude reads the channel via MCP, works,
                                 posts back, maybe "@codex your turn" ───► Codex wakes up
```

- Every agent is the real CLI running in a background tmux session. Scranton only types into its terminal and gives it chat tools over MCP. That is the same as you using the CLI yourself, so it counts against your normal subscription.
- Status comes from watching each terminal: if the screen is changing, the agent is **Working**.
- **Permissions:** by default (`[team] permissions = "full"`) teammates never stop to ask. Claude runs with `bypassPermissions` (deny rules in the project's `.claude/settings.json` still apply), Codex with no approvals and **no sandbox**, Cursor with `--force`. So Agent Monitor won't see prompts from them. The Help teammate stays on `"ask"`. Set `permissions = "ask"` for a teammate (in `config.local.toml`) to get the normal prompts back.
- Full permissions mean a teammate can do anything your Mac login can. The real stops for merges and deploys belong on GitHub (branch protection, code owners), not in the agents' instructions.

## Layout

| Where | What |
|---|---|
| Top bar | Show/hide the sidebar · **Search** (⌘K) across every channel |
| Left | **Activity** (Mentions first: everything that @Lu's you) · Channels · Direct messages with live status dots · **your avatar** bottom-left: change picture, change name, Settings (team + status), Help, Send feedback |
| Centre | The conversation. Your messages on the right, teammates on the left. Hover a message for react, reply in thread, copy link, forward, more |
| Right | Threads open here, several at once as tabs |
| Bottom-left cards | "Ready to update" (Update now) and "Teammates stopped" (Resume) |
| Phone | One column; the sidebar opens as a drawer |

Unused agentchattr features (jobs, rules, sessions, help tour) are hidden, not deleted, so upstream fixes can still be merged.

## Install on a Mac

Works on any Mac (laptop now, Mac mini later). You need Homebrew and the CLIs you want on the team, each logged into your plan:

| CLI | Install | Log in with your plan |
|---|---|---|
| Claude | `npm i -g @anthropic-ai/claude-code` | run `claude`, sign in, check `/status` |
| Codex | `npm i -g @openai/codex` | `codex login` → "Sign in with ChatGPT" |
| Cursor | `curl https://cursor.com/install -fsS \| bash` | `agent login` |

Then, in Terminal (one line at a time):

```bash
git clone https://github.com/lujin88/Scranton.git ~/Scranton
cd ~/Scranton
./install-mac.sh
```

This puts **Scranton.app** in `~/Applications`. Open it from Spotlight and drag it to the Dock. Opening it starts the server and every teammate with `autostart`, then opens the chat. Closing the browser tab doesn't stop the team.

- `./install-mac.sh --login`: also start the team automatically when you log in (for the Mac mini).
- `./install-mac.sh --uninstall`: remove the app and login item, keep the folder and history.
- Moved the folder or installed a new CLI? Run `./install-mac.sh` again (it records your Terminal's PATH so the app can find the CLIs).
- Safari → File → **Add to Dock** gives the chat its own window.

> Make sure `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are **not** set. If they are, the CLIs bill the API instead of your subscription. The app unsets them; the installer warns.

From Terminal you can also use:

| Command | What it does |
|---|---|
| `./scranton.sh check` | are the CLIs installed and logged in? |
| `./scranton.sh start [agent]` | start the server and all agents (or one) |
| `./scranton.sh status` | what's running |
| `./scranton.sh attach claude` | see / type into Claude's terminal. Leave with `Ctrl+B` then `D` |
| `./scranton.sh stop` | stop everything |

Logs: `data/logs/`. If a teammate's CLI exits, Scranton restarts it, waiting longer each time; after 5 exits within a minute of starting it stops and says so in `data/logs/<name>.log` (usually a login or quota problem). API keys in your environment are removed before anyone starts.

## First-run test (do this once)

1. `./scranton.sh check`: every CLI you use says it's installed and logged in.
2. `./scranton.sh start pm`: only the server and 项目经理, to keep the first test small.
3. `./scranton.sh attach pm`. Claude may ask "trust this folder?" and, in full-permission mode, show a one-time warning about bypassing permissions. Accept both, then leave with `Ctrl+B`, `D`. Do this once per Claude and Codex teammate.
4. Open http://localhost:8300. In Direct messages, 项目经理's dot is green.
5. In #lu-portfolio: `@pm 你好，说一下你是谁、用的什么模型`. The dot turns yellow (working), then the reply arrives and shows up in **Activity**.
6. `./scranton.sh start` brings up everyone with `autostart`. Hand-off test: `@pm 让 @dev 列出项目里的文件，然后总结给我`.
7. Try `@visual` (Codex) the same way.

If someone doesn't reply: `./scranton.sh attach pm` (or their handle) and look at their terminal. Cursor support is new in Scranton and hasn't been tested on a real Mac yet (see Known gaps).

## Phone access with Tailscale

The server only listens on `127.0.0.1`. Tailscale Serve puts HTTPS in front of it, reachable only from your own devices (your tailnet). Nothing is opened to the internet.

1. **Mac:** install Tailscale (tailscale.com/download or the Mac App Store) and sign in.
2. **Phone:** install the Tailscale app and sign in with the **same account**. Both devices now show up in the Tailscale app.
3. **Once, in the Tailscale admin page** (login.tailscale.com → DNS): MagicDNS on, **HTTPS Certificates** on.
4. **Mac, in Terminal** (the App Store version's command is `/Applications/Tailscale.app/Contents/MacOS/Tailscale` instead of `tailscale`):

   ```bash
   tailscale serve --bg 8300
   tailscale serve status        # shows https://<mac-name>.<tailnet>.ts.net
   ```

5. Put that address in `config.local.toml` (copy `config.local.toml.example`; keep personal changes out of `config.toml` so **Update now** keeps working), then `./scranton.sh restart-server`:

   ```toml
   [server]
   allowed_origins = ["https://mac-mini.tail1234.ts.net"]
   ```

6. **Phone:** Tailscale on (VPN toggle), open the address in Safari → Share → **Add to Home Screen**.

If the page says "unknown host", step 5 is missing or has a typo. The Mac has to be awake: on the Mac mini, turn on System Settings → Energy → "Prevent automatic sleeping".

Never use `tailscale funnel` for this: that makes the page public, and anyone who can load the page can command your agents. Requests that come through Tailscale can chat but can't register new agents, and pages served from unknown host names are refused.

## The team

Teammates are blocks in `config.toml`, taken from the Buzz setup notes and `BUZZ_HANDOVER.md` (2026-11-07). The block name is the @handle:

| @handle | Who | CLI | Starts automatically |
|---|---|---|---|
| `pm` | 项目经理 (main contact) | claude | yes |
| `harness` | Harness 管理员 | claude | yes |
| `dev` | 开发工程师 | claude | yes |
| `qa` | 代码审查与 QA | claude | yes |
| `visual` | 视觉设计师 | codex | yes |
| `visualqa` | 视觉校正 | codex | yes |
| `motion` | 动效设计师 | codex | yes |
| `research` | UX 调研员 | claude | yes |
| `copy` | UX 文案 | claude | yes |
| `growth`, `cs`, `hardware` | 增长, 客服, 硬件顾问 | claude (model not set in Buzz notes) | no |
| `webdev` | 网页开发 | Cursor | no |
| `help` | Scranton 帮手: turns feedback about Scranton into GitHub issues | claude | yes |
| `video` | 视频制作 | claude | no |

Start a non-autostart teammate by hand: `./scranton.sh start growth`.

**Feedback loop:** when something about Scranton itself bothers you, say it in #scranton-feedback (or `@help …` anywhere). The helper files it as an issue in `lujin88/Scranton` with the `feedback` label; it never edits Scranton itself. Fixes come back as PRs for you to merge. The helper needs the GitHub CLI logged in once: `brew install gh` then `gh auth login`.

> **Log `gh` in as the team's bot account, not your own.** Every teammate on this Mac shares that login. With your account they could merge as you, including design PRs that only you should merge.

The helper works in `helper/`, not in the Scranton code. `helper/.claude/settings.json` lets it list, open and comment on issues and read `data/logs/`, and blocks editing files, reading other teammates' connection tokens, merging, closing and pushing. The server never writes its session token to the logs.

- **role_card**: the nine original harness role cards are in `roles/` (unchanged). Each wake-up tells the agent the card's path and to read it before acting. Growth, Support, Hardware, Web dev and Video have no saved cards yet (待确认), so they only get a one-line `role`.
- **role** (one line) is added to every wake-up as `ROLE: …`.
- **[team].brief** (称呼 Lu, 简洁中文, report format, merge rule) is added on the first wake-up and every 10th after. Merge rule: **code PRs** are merged by QA with `scripts/merge-pr.sh` after review; **`design` PRs** are merged only by Lu; publishing and deleting still need Lu's OK.
- **[team].channels** are created on the first start (`lu-portfolio`, `scranton-feedback`). Delete or rename one and it stays that way.
- **Direct messages** use channels named `dm-<handle>`. That prefix is reserved: you can't create or rename other channels to it.
- **avatar**: the 14 portraits from the handover package are in `static/avatars/` (resized to 256 px). Alternates weren't copied.
- **cwd**: the lu-portfolio team works in `../LuJin-Portfolio`, i.e. clone that repo next to Scranton.
- **worktree = true** (dev, qa, visual, visualqa, motion, webdev): each of these gets its own git worktree, `../LuJin-Portfolio-worktrees/<handle>`, created on first start. Same repo, own folder and branch, so two teammates never edit the same checkout. Each one needs its own `pnpm install` the first time.
- **Handles:** the brief lists every @handle, so teammates hand work on with `@dev`, `@qa`… (a role name like "开发工程师" wakes nobody).

### Commits and GitHub

- Pushing, PRs and merging use the GitHub login on this Mac (`gh auth login` as the **bot** account). Code PRs are merged by QA, design PRs only by you.
- Every teammate commits with the bot account's **email**, under its own **name**, e.g. `开发工程师 (Scranton dev)`. Put the email in `config.local.toml`: `[team] git_email = "…"`. Nothing is written into the project's git settings.
- The bot account was suspended once (2026-10-25). Every GitHub write goes through harness-core's `scripts/gh-push.sh` (one at a time, 1 s apart, everyone stops on 403/429). `[team] harness_core` says where harness-core is checked out (default `~/.buzz/REPOS/harness-core`).
- The real lock for design PRs is on GitHub: branch protection on `main` plus a `CODEOWNERS` file that names you for design paths, and the bot account at **Write**, not Admin.

### Scheduled posts

`[[team.schedules]]` in `config.toml` are posted by Scranton itself, so no teammate has to stay awake and no subscription is used. The default posts `@pm 每日备份和每日总结` in #lu-portfolio at **21:00** (this Mac's time). Each schedule is created once; delete it in the UI and it stays deleted.

## Known gaps

- **First start:** Claude and Codex may ask "trust this folder?" the first time they open `LuJin-Portfolio`. Run `./scranton.sh attach pm` (and the others) once and answer it, or the first message waits on that prompt.

- **Cursor** is configured (MCP via `.cursor/mcp.json`, started with `--approve-mcps`) but not yet verified with a real Cursor login.
- **Nine always-on CLIs** share your Claude and ChatGPT limits. Start fewer if you hit limits: set `autostart = false` on roles you don't need today.
- The system prompts of the Buzz agents weren't in the notes, so each role is one line. Add more detail to `role`, or to `CLAUDE.md` / `AGENTS.md` in the project.
- **Subscription limits:** a busy team uses your plan faster than working by hand. When a CLI hits its limit it says so in its terminal; Scranton doesn't show that in the chat yet: the teammate just goes quiet. Check with `./scranton.sh attach <handle>`.
- **Your own settings** go in `config.local.toml`: `[server] allowed_origins`, `[team] owner/permissions/git_email/harness_core`, and per teammate `autostart`, `cwd`, `permissions`, `worktree`. If `config.toml` itself has local edits, Update refuses to run.
- **Updates:** Update now pulls, installs packages and restarts the server. If the new version won't start, Scranton goes back to the previous one and shows a card. Running teammates keep the old wrapper until they're restarted.
- No push notifications on the phone yet.

## Design rules

- **Icons: Remix Icon only** (remixicon.com, Apache-2.0). Use `scIcon('name', size)` from `static/scranton-icons.js`; to add one, copy its path from the remixicon package into that file. No hand-drawn SVGs.
- Spacing on a 4/8 px grid; sidebar rows 32 px; 12 px sidebar gutter.

## Updating from agentchattr

Scranton keeps upstream's code and file names so fixes can be pulled in:

```bash
git remote add upstream https://github.com/bcurts/agentchattr.git
git fetch upstream && git merge upstream/main   # resolve conflicts in static/index.html, config.toml
```

Scranton's own changes live mainly in `static/scranton.css`, `static/scranton.js`, `scranton.sh`, `install-mac.sh`, `tools/spawn.py`, `config.toml`, `roles/`, and lines marked "Scranton" in `app.py`, `wrapper.py` and `wrapper_unix.py`.

## Licence

MIT. agentchattr © 2026 Ben Curtis. See `LICENSE`. The upstream README is kept as `UPSTREAM_README.md`. Bundled `static/vendor/marked.min.js` is MIT (see `static/vendor/marked.LICENSE.md`).
