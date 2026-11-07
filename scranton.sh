#!/usr/bin/env sh
# Scranton - start, stop and check the whole team on this Mac.
#
#   ./scranton.sh start            server + every autostart teammate in config.toml
#   ./scranton.sh start growth     server + one teammate
#   ./scranton.sh stop             stop teammates and server
#   ./scranton.sh status           what is running
#   ./scranton.sh attach pm        watch / type into a teammate's terminal (Ctrl+B, D to leave)
#   ./scranton.sh check            are the CLIs installed and logged in?
#
# Teammates run in background tmux sessions, so they keep working when you
# close the terminal. Logs: data/logs/. Pids: data/run/.

set -e
cd "$(dirname "$0")"
PORT=8300
LOG_DIR="data/logs"
RUN_DIR="data/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"

# Subscriptions only: never let an API key reach the CLIs.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN OPENAI_API_KEY CURSOR_API_KEY

PY=".venv/bin/python"

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

cfg() {  # cfg <agent> <key> <default>
    "$PY" -c "import tomllib,sys;a=tomllib.load(open('config.toml','rb')).get('agents',{}).get(sys.argv[1]);print('' if a is None else a.get(sys.argv[2],sys.argv[3]))" "$1" "$2" "$3"
}

autostart_names() {
    "$PY" -c "import tomllib;c=tomllib.load(open('config.toml','rb'));print(' '.join(n for n,a in c.get('agents',{}).items() if a.get('type')!='api' and a.get('autostart',True)))"
}

all_names() {
    "$PY" -c "import tomllib;print(' '.join(tomllib.load(open('config.toml','rb')).get('agents',{})))"
}

pid_alive() {  # pid_alive <pidfile>
    [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null
}

server_running() { pid_alive "$RUN_DIR/server.pid" || lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; }

start_server() {
    if server_running; then echo "Server already running on http://localhost:$PORT"; return; fi
    "$PY" tools/spawn.py "$RUN_DIR/server.pid" "$LOG_DIR/server.log" -- "$PY" run.py >/dev/null
    i=0
    while [ "$i" -lt 40 ] && ! lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do sleep 0.5; i=$((i + 1)); done
    if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "Server running on http://localhost:$PORT"
    else echo "Server did not start. See $LOG_DIR/server.log"; exit 1; fi
}

start_agent() {
    name="$1"
    if pid_alive "$RUN_DIR/$name.pid"; then echo "  $name already running"; return; fi
    cmd=$(cfg "$name" command "")
    [ -n "$cmd" ] || { echo "  $name is not in config.toml"; return; }
    if ! command -v "$cmd" >/dev/null 2>&1; then echo "  $name skipped: '$cmd' is not installed"; return; fi
    dir=$(cfg "$name" cwd ".")
    if [ ! -d "$dir" ]; then echo "  $name skipped: folder $dir doesn't exist (clone the project next to Scranton, or change cwd in config.toml)"; return; fi
    case "$cmd" in
        agent|cursor-agent)
            # Cursor reads its MCP settings (with a local token) from the project.
            # Keep that file out of git so it can't be committed by accident.
            if [ -d "$dir/.git" ]; then
                ex="$dir/.git/info/exclude"; mkdir -p "$dir/.git/info"; touch "$ex"
                grep -qxF ".cursor/mcp.json" "$ex" || echo ".cursor/mcp.json" >> "$ex"
            fi
            "$PY" tools/spawn.py "$RUN_DIR/$name.pid" "$LOG_DIR/$name.log" -- "$PY" wrapper.py "$name" -- --approve-mcps >/dev/null ;;
        *)
            "$PY" tools/spawn.py "$RUN_DIR/$name.pid" "$LOG_DIR/$name.log" -- "$PY" wrapper.py "$name" >/dev/null ;;
    esac
    echo "  started $name  (terminal: ./scranton.sh attach $name)"
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
        start_server
        if [ -n "${2:-}" ]; then start_agent "$2"
        else for a in $(autostart_names); do start_agent "$a"; done; fi
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
