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
- Permission prompts appear in the agent's terminal. Scranton does not handle approvals; Agent Monitor does that separately.

## Layout

| Desktop | Phone |
|---|---|
| Channels left · conversation centre · Team with live status right | One column. ☰ opens channels, the people icon opens Team (badge = how many are working) |

Unused agentchattr features (jobs, rules, sessions, schedules, help tour, update checks) are hidden, not deleted, so upstream fixes can still be merged.

## Set up on the Mac mini

You need: Homebrew, Python 3.11+, tmux, and the CLIs you want on the team.

```bash
brew install python tmux
git clone https://github.com/lujin88/Scranton.git ~/Scranton
cd ~/Scranton
./scranton.sh check        # which CLIs are installed + login hints
```

**Log each CLI into your subscription once, by hand, before starting the team:**

| Agent | Install | Log in with your plan |
|---|---|---|
| Claude | `npm i -g @anthropic-ai/claude-code` | run `claude`, sign in with your Claude account, check `/status` |
| Codex | `npm i -g @openai/codex` | `codex login` → "Sign in with ChatGPT" |
| Cursor | `curl https://cursor.com/install -fsS \| bash` | `agent login` |

> Make sure `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are **not** set in your shell. If they are, the CLIs bill the API instead of your subscription. `./scranton.sh check` warns about this.

Then:

```bash
./scranton.sh start          # server + every agent in config.toml
open http://localhost:8300
```

| Command | What it does |
|---|---|
| `./scranton.sh start [agent]` | start the server and all agents (or one) |
| `./scranton.sh status` | what's running |
| `./scranton.sh attach claude` | see / type into Claude's terminal. Leave with `Ctrl+B` then `D` |
| `./scranton.sh stop` | stop everything |

Logs: `data/logs/`. If an agent's CLI exits, Scranton restarts it after 10 s.

## First-run test (do this once)

1. `./scranton.sh start`, open the page. Claude, Codex and Cursor should appear under **Team** as *Available*.
2. In #general: `@claude say hi and tell me which model you are`. Claude should turn *Working*, then reply.
3. Repeat for `@codex` and `@cursor`.
4. Hand-off test: `@claude ask @codex to list the files in this folder, then summarise`.
5. Trigger a permission prompt (e.g. ask an agent to create a file) and confirm Agent Monitor still catches it.

If Cursor doesn't reply: `./scranton.sh attach cursor` and look. Cursor support is new in Scranton and hasn't been tested on a real Mac yet (see Known gaps).

## Phone access with Tailscale

The server only listens on `127.0.0.1`. Tailscale Serve puts HTTPS in front of it, reachable only from devices on your tailnet.

```bash
tailscale serve --bg 8300
tailscale serve status        # shows https://<mac-name>.<tailnet>.ts.net
```

Put that address in `config.toml`, then restart:

```toml
[server]
allowed_origins = ["https://mac-mini.tail1234.ts.net"]
```

On the phone, open the address in Safari → Share → **Add to Home Screen**.

Never use `tailscale funnel` for this: that makes the page public, and anyone who can load the page can command your agents.

## The team

Teammates are blocks in `config.toml`. Several teammates can use the same CLI:

```toml
[agents.michael]          # project manager
command = "claude"
cwd = "../Party-Planner"
color = "#d97757"
label = "Michael"

[agents.pam]              # visual designer
command = "claude"
cwd = "../Party-Planner"
color = "#e5c890"
label = "Pam"
```

**Roles:** each agent reads `CLAUDE.md` / `AGENTS.md` in its `cwd`, so keep pointing those at your harness-core role cards like today. Clicking a name under Team also sets a short role label that's added to every wake-up message.

## Known gaps

- **Cursor** is configured (MCP via `.cursor/mcp.json`, started with `--approve-mcps`) but not yet verified with a real Cursor login.
- **Subscription limits:** a busy team uses your plan faster than working by hand. When a CLI hits its limit it says so in its terminal; Scranton doesn't show that in the Team panel yet.
- **Approvals** are out of scope (Agent Monitor).
- No push notifications on the phone yet.

## Updating from agentchattr

Scranton keeps upstream's code and file names so fixes can be pulled in:

```bash
git remote add upstream https://github.com/bcurts/agentchattr.git
git fetch upstream && git merge upstream/main   # resolve conflicts in static/index.html, config.toml
```

Scranton's own changes live mainly in `static/scranton.css`, `static/scranton.js`, `scranton.sh`, `config.toml`, and a few marked lines in `app.py` and `wrapper_unix.py`.

## Licence

MIT. agentchattr © 2026 Ben Curtis. See `LICENSE`. The upstream README is kept as `UPSTREAM_README.md`. Bundled `static/vendor/marked.min.js` is MIT (see `static/vendor/marked.LICENSE.md`).
