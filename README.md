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

| Desktop | Phone |
|---|---|
| Channels left · conversation centre · Team with live status right | One column. ☰ opens channels, the people icon opens Team (badge = how many are working) |

Unused agentchattr features (jobs, rules, sessions, schedules, help tour, update checks) are hidden, not deleted, so upstream fixes can still be merged.

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
| `./scranton.sh start [agent]` | start the server and all agents (or one) |
| `./scranton.sh status` | what's running |
| `./scranton.sh attach claude` | see / type into Claude's terminal. Leave with `Ctrl+B` then `D` |
| `./scranton.sh stop` | stop everything |

Logs: `data/logs/`. If a teammate's CLI exits, Scranton restarts it, waiting longer each time; after 5 exits within a minute of starting it stops and says so in `data/logs/<name>.log` (usually a login or quota problem). API keys in your environment are removed before anyone starts.

## First-run test (do this once)

1. Open Scranton.app. The autostart teammates should appear under **Team** as *Available*.
2. In #lu-portfolio: `@pm 你好，说一下你是谁、用的什么模型`. 项目经理 should turn *Working*, then reply.
3. Try `@visual` (Codex) the same way.
4. Hand-off test: `@pm 让 @dev 列出项目里的文件，然后总结给我`.
5. The first time a Claude teammate starts in full-permission mode it shows a one-time warning about bypassing permissions. Run `./scranton.sh attach pm` (and each Claude teammate) once and accept it, or that teammate waits on the warning.

If someone doesn't reply: `./scranton.sh attach pm` (or their handle) and look at their terminal. Cursor support is new in Scranton and hasn't been tested on a real Mac yet (see Known gaps).

## Phone access with Tailscale

The server only listens on `127.0.0.1`. Tailscale Serve puts HTTPS in front of it, reachable only from devices on your tailnet.

```bash
tailscale serve --bg 8300
tailscale serve status        # shows https://<mac-name>.<tailnet>.ts.net
```

Put that address in `config.local.toml` (your Mac's own settings; copy `config.local.toml.example`), then restart. Keep personal changes out of `config.toml`, so **Update now** keeps working:

```toml
[server]
allowed_origins = ["https://mac-mini.tail1234.ts.net"]
```

On the phone, open the address in Safari → Share → **Add to Home Screen**.

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
- **role** (one line) is added to every wake-up as `ROLE: …`. A role picked in the Team panel (⋯) is added in front; it doesn't replace the card.
- **[team].brief** (称呼 Lu, 简洁中文, report format, merge rule) is added on the first wake-up and every 10th after. Merge rule: **code PRs** are merged by QA with `scripts/merge-pr.sh` after review; **`design` PRs** are merged only by Lu; publishing and deleting still need Lu's OK.
- **[team].channels** are created on the first start (`lu-portfolio`, `scranton-feedback`). Delete or rename one and it stays that way.
- **Direct messages** use channels named `dm-<handle>`. That prefix is reserved: you can't create or rename other channels to it.
- **avatar**: the 14 portraits from the handover package are in `static/avatars/` (resized to 256 px). Alternates weren't copied.
- **cwd**: the lu-portfolio team works in `../LuJin-Portfolio`, i.e. clone that repo next to Scranton.

## Known gaps

- **First start:** Claude and Codex may ask "trust this folder?" the first time they open `LuJin-Portfolio`. Run `./scranton.sh attach pm` (and the others) once and answer it, or the first message waits on that prompt.

- **Cursor** is configured (MCP via `.cursor/mcp.json`, started with `--approve-mcps`) but not yet verified with a real Cursor login.
- **Nine teammates share one folder** (`../LuJin-Portfolio`). Two agents editing the same files at once will clash. Ask them to work on separate branches, or give coding roles their own git worktree as `cwd`.
- **Nine always-on CLIs** share your Claude and ChatGPT limits. Start fewer if you hit limits: set `autostart = false` on roles you don't need today.
- The system prompts of the Buzz agents weren't in the notes, so each role is one line. Add more detail to `role`, or to `CLAUDE.md` / `AGENTS.md` in the project.
- **Subscription limits:** a busy team uses your plan faster than working by hand. When a CLI hits its limit it says so in its terminal; Scranton doesn't show that in the Team panel yet.
- **Your own settings** go in `config.local.toml`: `[server] allowed_origins`, `[team] owner/permissions`, and per teammate `autostart`, `cwd`, `permissions`. If `config.toml` itself has local edits, Update refuses to run.
- **Updates:** Update now pulls, installs packages and restarts the server. If the new version won't start, Scranton goes back to the previous one and shows a card. Running teammates keep the old wrapper until they're restarted.
- No push notifications on the phone yet.

## Updating from agentchattr

Scranton keeps upstream's code and file names so fixes can be pulled in:

```bash
git remote add upstream https://github.com/bcurts/agentchattr.git
git fetch upstream && git merge upstream/main   # resolve conflicts in static/index.html, config.toml
```

Scranton's own changes live mainly in `static/scranton.css`, `static/scranton.js`, `scranton.sh`, `install-mac.sh`, `tools/spawn.py`, `config.toml`, `roles/`, and lines marked "Scranton" in `app.py`, `wrapper.py` and `wrapper_unix.py`.

## Licence

MIT. agentchattr © 2026 Ben Curtis. See `LICENSE`. The upstream README is kept as `UPSTREAM_README.md`. Bundled `static/vendor/marked.min.js` is MIT (see `static/vendor/marked.LICENSE.md`).
