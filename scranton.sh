#!/usr/bin/env sh
# Scranton - start, stop and check the whole team on this Mac.
#
#   ./scranton.sh start            server + every agent in config.toml
#   ./scranton.sh start claude     server + one agent
#   ./scranton.sh stop             stop agents and server
#   ./scranton.sh status           what is running
#   ./scranton.sh attach claude    watch / type into an agent's terminal (Ctrl+B, D to leave)
#   ./scranton.sh check            are the CLIs installed and logged in?
#
# Agents run in background tmux sessions, so they keep working when you
# close the terminal. Logs go to data/logs/.

set -e
cd "$(dirname "$0")"
PORT=8300
LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1 ($2)"; exit 1; }; }

ensure_venv() {
    need python3 "install with: brew install python"
    need tmux "install with: brew install tmux"
    if [ ! -x ".venv/bin/python" ]; then
        echo "First run: creating .venv and installing dependencies..."
        python3 -m venv .venv
        .venv/bin/python -m pip install -q -r requirements.txt
    fi
}

server_running() { lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; }

agent_names() {
    .venv/bin/python -c "import tomllib;c=tomllib.load(open('config.toml','rb'));print(' '.join(n for n,a in c.get('agents',{}).items() if a.get('type')!='api' and a.get('autostart',True)))"
}

wrapper_running() { pgrep -f "wrapper.py $1( |$)" >/dev/null 2>&1; }

start_server() {
    if server_running; then echo "Server already running on http://localhost:$PORT"; return; fi
    nohup .venv/bin/python run.py > "$LOG_DIR/server.log" 2>&1 &
    i=0
    while [ "$i" -lt 40 ] && ! server_running; do sleep 0.5; i=$((i + 1)); done
    if server_running; then echo "Server running on http://localhost:$PORT"
    else echo "Server did not start. See $LOG_DIR/server.log"; exit 1; fi
}

start_agent() {
    name="$1"
    if wrapper_running "$name"; then echo "  $name already running"; return; fi
    extra=""
    cmd=$(.venv/bin/python -c "import tomllib,sys;print(tomllib.load(open('config.toml','rb')).get('agents',{}).get(sys.argv[1],{}).get('command',''))" "$name")
    [ -n "$cmd" ] || { echo "  $name is not in config.toml"; return; }
    if ! command -v "$cmd" >/dev/null 2>&1; then echo "  $name skipped: '$cmd' is not installed"; return; fi
    dir=$(.venv/bin/python -c "import tomllib,sys;print(tomllib.load(open('config.toml','rb')).get('agents',{}).get(sys.argv[1],{}).get('cwd','.'))" "$name")
    if [ ! -d "$dir" ]; then echo "  $name skipped: folder $dir doesn't exist (clone the project next to Scranton, or change cwd in config.toml)"; return; fi
    case "$cmd" in agent|cursor-agent) extra="-- --approve-mcps" ;; esac
    # shellcheck disable=SC2086
    nohup .venv/bin/python wrapper.py "$name" $extra > "$LOG_DIR/$name.log" 2>&1 &
    echo "  started $name  (log: $LOG_DIR/$name.log, terminal: ./scranton.sh attach $name)"
}

case "${1:-}" in
    start)
        ensure_venv
        start_server
        if [ -n "${2:-}" ]; then start_agent "$2"
        else for a in $(agent_names); do start_agent "$a"; done; fi
        ;;
    stop)
        pkill -f "wrapper.py" 2>/dev/null || true
        for s in $(tmux ls -F '#S' 2>/dev/null | grep '^agentchattr-' || true); do tmux kill-session -t "$s"; done
        pkill -f "run.py" 2>/dev/null || true
        echo "Stopped."
        ;;
    status)
        ensure_venv
        if server_running; then echo "Server: running (http://localhost:$PORT)"; else echo "Server: stopped"; fi
        for a in $(.venv/bin/python -c "import tomllib;print(' '.join(tomllib.load(open('config.toml','rb')).get('agents',{})))"); do
            if wrapper_running "$a"; then echo "  $a: running"; else echo "  $a: stopped"; fi
        done
        ;;
    attach)
        [ -n "${2:-}" ] || { echo "Usage: ./scranton.sh attach <agent>"; exit 1; }
        # Instance names can get a suffix (claude-2) when two share a CLI.
        s=$(tmux ls -F '#S' 2>/dev/null | grep "^agentchattr-$2" | head -1)
        [ -n "$s" ] || { echo "No running terminal for $2. Running: $(tmux ls -F '#S' 2>/dev/null | sed 's/^agentchattr-//' | tr '\n' ' ')"; exit 1; }
        tmux attach -t "$s"
        ;;
    check)
        for c in claude codex agent; do
            if command -v "$c" >/dev/null 2>&1; then echo "$c: installed ($(command -v "$c"))"; else echo "$c: NOT installed"; fi
        done
        echo
        echo "Login checks (each should show your subscription account, not an API key):"
        command -v claude >/dev/null 2>&1 && { echo "- claude: run 'claude' once and type /status"; }
        command -v codex >/dev/null 2>&1 && { codex login status 2>&1 | sed 's/^/- codex: /' || true; }
        command -v agent >/dev/null 2>&1 && { agent status 2>&1 | sed 's/^/- cursor: /' || true; }
        [ -n "${ANTHROPIC_API_KEY:-}" ] && echo "WARNING: ANTHROPIC_API_KEY is set. Claude Code will bill the API instead of your subscription. Unset it."
        [ -n "${OPENAI_API_KEY:-}" ] && echo "WARNING: OPENAI_API_KEY is set. Codex may use the API instead of your ChatGPT plan. Unset it."
        [ -n "${CURSOR_API_KEY:-}" ] && echo "Note: CURSOR_API_KEY is set."
        true
        ;;
    *)
        sed -n '2,10p' "$0"
        ;;
esac
