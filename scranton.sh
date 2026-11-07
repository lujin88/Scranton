#!/usr/bin/env sh
# Scranton - start, stop and check the whole team on this Mac.
#
#   ./scranton.sh start            server + every autostart teammate in config.toml
#   ./scranton.sh start growth     server + one teammate
#   ./scranton.sh stop             stop teammates and server
#   ./scranton.sh status           what is running
#   ./scranton.sh attach pm        watch / type into a teammate's terminal (Ctrl+B, D to leave)
#   ./scranton.sh check            are the CLIs installed and logged in?
#   ./scranton.sh restart-server   restart only the server (teammates keep working)
#
# Teammates run in background tmux sessions, so they keep working when you
# close the terminal. Logs: data/logs/. Pids: data/run/.

set -e
cd "$(dirname "$0")"

LOG_DIR="data/logs"
RUN_DIR="data/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"

# Subscriptions only: never let an API key reach the CLIs.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN OPENAI_API_KEY CURSOR_API_KEY

PY=".venv/bin/python"
port() { "$PY" -c "$LOADCFG;print(c.get('server',{}).get('port',8300))" 2>/dev/null || echo 8300; }

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1 ($2)"; exit 1; }; }

ensure_venv() {
    need python3 "install with: brew install python"
    need tmux "install with: brew install tmux"
    if [ ! -x "$PY" ]; then
        echo "First run: creating .venv and installing dependencies..."
        python3 -m venv .venv
        "$PY" -m pip install -q -r requirements.txt
    fi
}

# config.toml merged with this Mac's config.local.toml (see config_loader.py)
LOADCFG="from config_loader import load_config as L;c=L()"
cfg() {  # cfg <agent> <key> <default>
    "$PY" -c "$LOADCFG;import sys;a=c.get('agents',{}).get(sys.argv[1]);print('' if a is None else a.get(sys.argv[2],sys.argv[3]))" "$1" "$2" "$3"
}

autostart_names() {
    "$PY" -c "$LOADCFG;print(' '.join(n for n,a in c.get('agents',{}).items() if a.get('type')!='api' and a.get('autostart',True)))"
}

all_names() {
    "$PY" -c "$LOADCFG;print(' '.join(c.get('agents',{})))"
}

pid_alive() {  # pid_alive <pidfile>: alive AND really ours (pids get reused after a reboot)
    [ -f "$1" ] || return 1
    p=$(cat "$1" 2>/dev/null)
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null || return 1
    ps -p "$p" -o command= 2>/dev/null | grep -Eq '(wrapper|run)\.py'
}

server_running() { PORT=${PORT:-$(port)}; pid_alive "$RUN_DIR/server.pid" || lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; }

start_server() {
    PORT=$(port)
    if server_running; then echo "Server already running on http://localhost:$PORT"; return; fi
    "$PY" tools/spawn.py "$RUN_DIR/server.pid" "$LOG_DIR/server.log" -- "$PY" run.py >/dev/null
    i=0
    while [ "$i" -lt 40 ] && ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do sleep 0.5; i=$((i + 1)); done
    if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "Server running on http://localhost:$PORT"
    else echo "Server did not start. See $LOG_DIR/server.log"; return 1; fi
}

start_agent() {
    name="$1"
    if pid_alive "$RUN_DIR/$name.pid"; then echo "  $name already running"; return; fi
    cmd=$(cfg "$name" command "")
    [ -n "$cmd" ] || { echo "  $name is not in config.toml"; return; }
    if ! command -v "$cmd" >/dev/null 2>&1; then echo "  $name skipped: '$cmd' is not installed"; return; fi
    dir=$(cfg "$name" cwd ".")
    if [ ! -d "$dir" ]; then echo "  $name skipped: folder $dir doesn't exist (clone the project next to Scranton, or change cwd in config.toml)"; return; fi
    # Teammates that change code get their own git worktree (same repo, own folder and
    # branch), so two of them never edit the same checkout. Created once, kept afterwards.
    SCRANTON_CWD=""
    if [ "$(cfg "$name" worktree "")" = "True" ] && git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
        wdir="$(cd "$dir/.." && pwd)/$(basename "$dir")-worktrees/$name"
        if [ ! -d "$wdir" ]; then
            if git -C "$dir" worktree add --quiet --detach "$wdir" >/dev/null 2>&1; then
                echo "  $name: own working copy at $wdir"
            else
                echo "  $name: couldn't create its own working copy, sharing $dir"; wdir=""
            fi
        fi
        SCRANTON_CWD="$wdir"
    fi
    export SCRANTON_CWD
    # Permission level: [team].permissions, overridable per teammate ("full" or "ask").
    perm=$("$PY" -c "$LOADCFG;import sys;a=c.get('agents',{}).get(sys.argv[1],{});print(a.get('permissions', c.get('team',{}).get('permissions','ask')))" "$name")
    # Answer the CLI's one-time questions (trust this folder? / full-permission warning)
    # so the teammate doesn't sit on a prompt in a terminal nobody is looking at.
    "$PY" tools/first_run.py "$cmd" "${SCRANTON_CWD:-$dir}" "$perm" || true
    case "$perm:$cmd" in
        full:claude)              pflags="--permission-mode bypassPermissions" ;;
        full:codex)               pflags="--dangerously-bypass-approvals-and-sandbox" ;;
        full:agent|full:cursor-agent) pflags="--force" ;;
        *)                        pflags="" ;;
    esac
    case "$cmd" in
        agent|cursor-agent)
            # Cursor reads its MCP settings (with a local token) from the project.
            # Keep that file out of git so it can't be committed by accident.
            if [ -d "$dir/.git" ]; then
                ex="$dir/.git/info/exclude"; mkdir -p "$dir/.git/info"; touch "$ex"
                grep -qxF ".cursor/mcp.json" "$ex" || echo ".cursor/mcp.json" >> "$ex"
            fi
            # shellcheck disable=SC2086
            "$PY" tools/spawn.py "$RUN_DIR/$name.pid" "$LOG_DIR/$name.log" -- "$PY" wrapper.py "$name" -- --approve-mcps $pflags >/dev/null ;;
        *)
            if [ -n "$pflags" ]; then
                # shellcheck disable=SC2086
                "$PY" tools/spawn.py "$RUN_DIR/$name.pid" "$LOG_DIR/$name.log" -- "$PY" wrapper.py "$name" -- $pflags >/dev/null
            else
                "$PY" tools/spawn.py "$RUN_DIR/$name.pid" "$LOG_DIR/$name.log" -- "$PY" wrapper.py "$name" >/dev/null
            fi ;;
    esac
    echo "  started $name  (permissions: $perm, terminal: ./scranton.sh attach $name)"
    sleep 2  # stagger: several CLIs writing their settings at once can clash
}

stop_pidfile() {
    f="$1"
    if pid_alive "$f"; then
        pid=$(cat "$f")
        kill "$pid" 2>/dev/null || true
        i=0; while [ "$i" -lt 10 ] && kill -0 "$pid" 2>/dev/null; do sleep 0.3; i=$((i + 1)); done
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$f"
}

case "${1:-}" in
    start)
        ensure_venv
        start_server || exit 1
        if [ -n "${2:-}" ]; then start_agent "$2"
        else for a in $(autostart_names); do start_agent "$a"; done; fi
        ;;
    start-agent)
        # used by the web page's "Resume" button: one teammate, server already running
        ensure_venv
        [ -n "${2:-}" ] || { echo "Usage: ./scranton.sh start-agent <name>"; exit 1; }
        start_agent "$2"
        ;;
    restart-server)
        # used by "Update now": teammates keep running and re-register by themselves.
        # If the new version won't start, go back to the version before the update.
        ensure_venv
        PORT=$(port)
        stop_pidfile "$RUN_DIR/server.pid"
        i=0; while [ "$i" -lt 20 ] && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do sleep 0.5; i=$((i + 1)); done
        if start_server; then rm -f "$RUN_DIR/prev_head"; exit 0; fi
        if [ -f "$RUN_DIR/prev_head" ]; then
            prev=$(cat "$RUN_DIR/prev_head")
            echo "New version didn't start - going back to $prev"
            git reset --hard --quiet "$prev"
            "$PY" -m pip install -q -r requirements.txt || true
            rm -f "$RUN_DIR/prev_head"
            echo "The update didn't start, so Scranton went back to the previous version. Details: data/logs/server.log" > "$RUN_DIR/update_failed"
            start_server || exit 1
        else
            exit 1
        fi
        ;;
    stop)
        for f in "$RUN_DIR"/*.pid; do
            [ -e "$f" ] || continue
            [ "$(basename "$f")" = "server.pid" ] && continue
            stop_pidfile "$f"
        done
        for s in $(tmux ls -F '#S' 2>/dev/null | grep '^agentchattr-' || true); do tmux kill-session -t "=$s"; done
        stop_pidfile "$RUN_DIR/server.pid"
        echo "Stopped."
        ;;
    status)
        ensure_venv
        if server_running; then echo "Server: running (http://localhost:$PORT)"; else echo "Server: stopped"; fi
        for a in $(all_names); do
            if pid_alive "$RUN_DIR/$a.pid"; then echo "  $a: running"
            elif [ "$(cfg "$a" autostart True)" = "False" ]; then echo "  $a: off (start with ./scranton.sh start $a)"
            else echo "  $a: stopped"; fi
        done
        ;;
    attach)
        [ -n "${2:-}" ] || { echo "Usage: ./scranton.sh attach <name>"; exit 1; }
        # Exact name, or name-2 etc. when two instances share a handle.
        s=$(tmux ls -F '#S' 2>/dev/null | grep -E "^agentchattr-$2(-[0-9]+)?\$" | head -1 || true)
        [ -n "$s" ] || { echo "No running terminal for $2. Running: $(tmux ls -F '#S' 2>/dev/null | sed 's/^agentchattr-//' | tr '\n' ' ')"; exit 1; }
        tmux attach -t "=$s"
        ;;
    check)
        for c in claude codex agent; do
            if command -v "$c" >/dev/null 2>&1; then echo "$c: installed ($(command -v "$c"))"; else echo "$c: NOT installed"; fi
        done
        echo
        echo "Login checks (each should show your subscription account, not an API key):"
        if command -v claude >/dev/null 2>&1; then echo "- claude: run 'claude' once and type /status"; fi
        if command -v codex >/dev/null 2>&1; then codex login status 2>&1 | sed 's/^/- codex: /' || true; fi
        if command -v agent >/dev/null 2>&1; then agent status 2>&1 | sed 's/^/- cursor: /' || true; fi
        echo
        echo "Scranton removes ANTHROPIC_API_KEY / OPENAI_API_KEY / CURSOR_API_KEY before starting anyone."
        ;;
    *)
        sed -n '2,10p' "$0"
        ;;
esac
