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
#   ./scranton.sh grok …           for Grok Bot: post / read as 幕僚长 (Grok) (docs/grok-bot.md)
#   ./scranton.sh install-service  let macOS keep the server running (restarts it if it stops, starts at login)
#   ./scranton.sh uninstall-service
#   ./scranton.sh install-app      build Scranton.app (own window + Dock icon) into /Applications
#
# Teammates run in background tmux sessions, so they keep working when you
# close the terminal. Logs: data/logs/. Pids: data/run/.

set -e
cd "$(dirname "$0")"

LOG_DIR="data/logs"
RUN_DIR="data/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"

# Subscriptions only: never let an API key reach the CLIs.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX OPENAI_API_KEY OPENAI_BASE_URL CODEX_API_KEY CURSOR_API_KEY   # = config_loader.PAID_API_ENV

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

# The server as a macOS login service (launchd): if anything stops it, macOS starts it
# again within seconds, and it starts when you log in. Installed only by install-service.
LABEL="com.scranton.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
service_installed() { [ -f "$PLIST" ] && command -v launchctl >/dev/null 2>&1; }
service_loaded() { launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; }
wait_port() {  # wait_port <up|down> <tries of 0.5 s>
    i=0
    while [ "$i" -lt "$2" ]; do
        if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then [ "$1" = up ] && return 0
        else [ "$1" = down ] && return 0; fi
        sleep 0.5; i=$((i + 1))
    done
    return 1
}

server_running() { PORT=${PORT:-$(port)}; pid_alive "$RUN_DIR/server.pid" || lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; }

start_server() {
    PORT=$(port)
    if service_installed; then
        service_loaded || launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null || true
        server_running || launchctl kickstart "$DOMAIN/$LABEL" 2>/dev/null || true
        if wait_port up 40; then echo "Server running on http://localhost:$PORT (kept running by macOS)"
        else echo "Server did not start. See $LOG_DIR/server.log"; return 1; fi
        return
    fi
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
    if [ ! -d "$dir" ]; then
        # A known project ([team.projects] in config.toml)? Get it from GitHub once.
        url=$("$PY" -c "$LOADCFG;import os,sys;p=c.get('team',{}).get('projects',{});print(next((u for k,u in p.items() if os.path.expanduser(k)==sys.argv[1]),''))" "$dir")
        if [ -n "$url" ]; then
            mkdir -p "$(dirname "$dir")"
            # Several teammates may start at once: only one clones, the others wait for it.
            if mkdir "$dir.cloning" 2>/dev/null; then
                echo "  $name: getting $(basename "$dir") from GitHub (first time only)..."
                git clone --quiet "$url" "$dir" 2>&1 | tail -2 || true
                rmdir "$dir.cloning"
            else
                i=0; while [ -d "$dir.cloning" ] && [ "$i" -lt 600 ]; do sleep 1; i=$((i + 1)); done
            fi
        fi
    fi
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
        full:agy)                 pflags="--dangerously-skip-permissions" ;;
        *)                        pflags="" ;;
    esac
    # Claude Code can block reading outside the working folder (blockReadsOutsideWorkingDirectories),
    # and each teammate's role card is in Scranton/roles. Lu, 11-09: @help sat on that question.
    if [ "$cmd" = "claude" ]; then pflags="$pflags --add-dir $(pwd)/roles"; fi
    model=$(cfg "$name" model "")
    if [ -n "$model" ] && printf '%s' "$model" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'; then
        case "$cmd" in
            codex) pflags="$pflags -m $model" ;;
            *)     pflags="$pflags --model $model" ;;
        esac
    fi
    effort=$(cfg "$name" effort "")
    case "$cmd:$effort" in
        codex:low|codex:medium|codex:high|codex:xhigh) pflags="$pflags -c model_reasoning_effort=$effort" ;;
        claude:low|claude:medium|claude:high|claude:xhigh|claude:max) pflags="$pflags --effort $effort" ;;
        agy:low|agy:medium|agy:high) pflags="$pflags --effort $effort" ;;
    esac
    # No wrapper is running for this teammate (checked above), so any terminal it left
    # behind (agentchattr-<name> or <name>-2 after a crash/sleep) has nobody reading it:
    # close those, or the old one keeps waiting on a question next to the new one.
    for s in $(tmux ls -F '#S' 2>/dev/null | grep -E "^agentchattr-$name(-[0-9]+)?\$" || true); do
        tmux kill-session -t "=$s" 2>/dev/null || true
    done
    case "$cmd" in
        agent|cursor-agent)
            # Cursor reads its MCP settings (with a local token) from the project.
            # Keep that file out of git so it can't be committed by accident.
            if [ -d "$dir/.git" ]; then
                ex="$dir/.git/info/exclude"; mkdir -p "$dir/.git/info"; touch "$ex"
                grep -qxF ".cursor/mcp.json" "$ex" || echo ".cursor/mcp.json" >> "$ex"
            fi
            # shellcheck disable=SC2086
            "$PY" tools/spawn.py "$RUN_DIR/$name.pid" "$LOG_DIR/$name.log" -- "$PY" -u wrapper.py "$name" -- --approve-mcps $pflags >/dev/null ;;
        *)
            if [ -n "$pflags" ]; then
                # shellcheck disable=SC2086
                "$PY" tools/spawn.py "$RUN_DIR/$name.pid" "$LOG_DIR/$name.log" -- "$PY" -u wrapper.py "$name" -- $pflags >/dev/null
            else
                "$PY" tools/spawn.py "$RUN_DIR/$name.pid" "$LOG_DIR/$name.log" -- "$PY" -u wrapper.py "$name" >/dev/null
            fi ;;
    esac
    echo "  started $name  (permissions: $perm${model:+, model: $model}, terminal: ./scranton.sh attach $name)"
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
        # The Mac app is a window around this page, so it shows every update right away. Only when
        # the app's own code (mac/) changed is it rebuilt; the new one is used from its next launch.
        rebuild_app() {
            [ -f "$RUN_DIR/prev_head" ] && { [ -d /Applications/Scranton.app ] || [ -d "$HOME/Applications/Scranton.app" ]; } || return 0
            git diff --quiet "$(cat "$RUN_DIR/prev_head")" HEAD -- mac/ 2>/dev/null && return 0
            echo "mac/ changed: rebuilding Scranton.app"
            "$0" install-app || echo "Rebuilding Scranton.app failed; run ./scranton.sh install-app"
        }
        healthy() {
            curl -fs -o /dev/null --max-time 5 "http://127.0.0.1:$PORT/" || return 1
            sleep 10
            curl -fs -o /dev/null --max-time 5 "http://127.0.0.1:$PORT/"
        }
        if service_installed && service_loaded; then
            # launchd restarts it (-k: stop the running one first); same health check and rollback.
            launchctl kickstart -k "$DOMAIN/$LABEL"
            sleep 1
            if wait_port up 40 && healthy; then rebuild_app; rm -f "$RUN_DIR/prev_head" "$RUN_DIR/prev_requirements.txt"; exit 0; fi
            if [ -f "$RUN_DIR/prev_head" ]; then
                prev=$(cat "$RUN_DIR/prev_head")
                echo "New version didn't start - going back to $prev"
                git reset --hard --quiet "$prev"
                if [ -f "$RUN_DIR/prev_requirements.txt" ]; then "$PY" -m pip install -q -r "$RUN_DIR/prev_requirements.txt" || true
                else "$PY" -m pip install -q -r requirements.txt || true; fi
                rm -f "$RUN_DIR/prev_requirements.txt" "$RUN_DIR/prev_head"
                echo "The update didn't start, so Scranton went back to the previous version. Details: data/logs/server.log" > "$RUN_DIR/update_failed"
                launchctl kickstart -k "$DOMAIN/$LABEL"
                wait_port up 40 || exit 1
                exit 0
            fi
            exit 1
        fi
        stop_pidfile "$RUN_DIR/server.pid"
        # No (or a stale) pid file: stop whatever Scranton server holds the port, so the
        # restart really happens instead of "already running" with the old code.
        for pid in $(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null); do
            case "$(ps -o command= -p "$pid" 2>/dev/null)" in *run.py*) kill "$pid" 2>/dev/null || true ;; esac
        done
        i=0; while [ "$i" -lt 20 ] && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do sleep 0.5; i=$((i + 1)); done
        if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "Port $PORT is still in use by another program, so Scranton couldn't restart."
            rm -f "$RUN_DIR/prev_head"; exit 1
        fi
        # Healthy = it started AND still answers 10 s later (a crash right after binding the
        # port must roll back too). Only then is the rollback point dropped.
        healthy() {
            curl -fs -o /dev/null --max-time 5 "http://127.0.0.1:$PORT/" || return 1
            sleep 10
            curl -fs -o /dev/null --max-time 5 "http://127.0.0.1:$PORT/"
        }
        if start_server && healthy; then rebuild_app; rm -f "$RUN_DIR/prev_head" "$RUN_DIR/prev_requirements.txt"; exit 0; fi
        if [ -f "$RUN_DIR/prev_head" ]; then
            prev=$(cat "$RUN_DIR/prev_head")
            echo "New version didn't start - going back to $prev"
            stop_pidfile "$RUN_DIR/server.pid"
            git reset --hard --quiet "$prev"
            # Put back the exact packages from before the update (requirements use >=).
            if [ -f "$RUN_DIR/prev_requirements.txt" ]; then
                "$PY" -m pip install -q -r "$RUN_DIR/prev_requirements.txt" || true
            else
                "$PY" -m pip install -q -r requirements.txt || true
            fi
            rm -f "$RUN_DIR/prev_requirements.txt"
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
        # Under launchd, unload it first, or macOS would just start it again.
        if service_installed && service_loaded; then launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true; fi
        stop_pidfile "$RUN_DIR/server.pid"
        echo "Stopped."
        ;;
    install-service)
        ensure_venv
        command -v launchctl >/dev/null 2>&1 || { echo "This is for macOS only."; exit 1; }
        PORT=$(port)
        here=$(pwd)
        mkdir -p "$HOME/Library/LaunchAgents"
        # launchd starts with an almost empty PATH: keep the one from this terminal, so the
        # Resume button can still find claude / codex / agent / tmux.
        cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$here/$PY</string><string>run.py</string></array>
  <key>WorkingDirectory</key><string>$here</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$PATH</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>AbandonProcessGroup</key><true/>
  <key>StandardOutPath</key><string>$here/$LOG_DIR/server.log</string>
  <key>StandardErrorPath</key><string>$here/$LOG_DIR/server.log</string>
</dict>
</plist>
PL
        # Hand over: stop the server started by this script, then let launchd run it.
        if service_loaded; then launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true; fi
        stop_pidfile "$RUN_DIR/server.pid"
        for pid in $(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null); do
            case "$(ps -o command= -p "$pid" 2>/dev/null)" in *run.py*) kill "$pid" 2>/dev/null || true ;; esac
        done
        wait_port down 20 || { echo "Port $PORT is used by another program."; exit 1; }
        launchctl bootstrap "$DOMAIN" "$PLIST"
        if wait_port up 40; then
            echo "Done. macOS now keeps the server running: it comes back by itself if it stops, and starts when you log in."
            echo "Teammates keep running and reconnect by themselves. Undo with: ./scranton.sh uninstall-service"
        else echo "Installed, but the server didn't answer yet. See $LOG_DIR/server.log"; exit 1; fi
        ;;
    install-app)
        # Scranton.app in /Applications, next to your other apps (~/Applications if that isn't
        # writable): its own window and Dock icon (badge = what needs you).
        # Built here with swiftc (Xcode Command Line Tools), so nothing downloaded runs.
        command -v xcrun >/dev/null 2>&1 && xcrun --find swiftc >/dev/null 2>&1 || {
            echo "Needs the Xcode Command Line Tools. Run: xcode-select --install   then try again."; exit 1; }
        PORT=$(port)
        here=$(pwd)
        # Lu, 11-09: she looked in Finder > Applications and it wasn't there (it was in ~/Applications).
        if [ -w /Applications ]; then APP_DIR=/Applications; else APP_DIR="$HOME/Applications"; fi
        APP="$APP_DIR/Scranton.app"
        tmp=$(mktemp -d)
        mkdir -p "$tmp/Scranton.app/Contents/MacOS" "$tmp/Scranton.app/Contents/Resources"
        echo "Building Scranton.app..."
        xcrun swiftc -O -o "$tmp/Scranton.app/Contents/MacOS/Scranton" mac/Scranton.swift -framework Cocoa -framework WebKit || { rm -r "$tmp"; exit 1; }
        # Icon: every size macOS wants, from mac/AppIcon.png (1024 px).
        mkdir -p "$tmp/AppIcon.iconset"
        for s in 16 32 128 256 512; do
            sips -z $s $s mac/AppIcon.png --out "$tmp/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
            d=$((s * 2)); sips -z $d $d mac/AppIcon.png --out "$tmp/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
        done
        iconutil -c icns "$tmp/AppIcon.iconset" -o "$tmp/Scranton.app/Contents/Resources/AppIcon.icns"
        cat > "$tmp/Scranton.app/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Scranton</string>
  <key>CFBundleDisplayName</key><string>Scranton</string>
  <key>CFBundleIdentifier</key><string>com.scranton.app</string>
  <key>CFBundleExecutable</key><string>Scranton</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$(git rev-parse --short HEAD 2>/dev/null || echo 1)</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>ScrantonDir</key><string>$here</string>
  <key>ScrantonPort</key><integer>$PORT</integer>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PL
        codesign --force --deep -s - "$tmp/Scranton.app" >/dev/null 2>&1 || true   # ad-hoc: built on this Mac
        mkdir -p "$APP_DIR"
        # The previous build goes to the Trash (recoverable), not deleted. So does an older copy in
        # ~/Applications, so there's only one Scranton in Spotlight.
        stamp=$(date "+%Y-%m-%d %H.%M.%S")
        if [ -d "$APP" ]; then mv "$APP" "$HOME/.Trash/Scranton $stamp.app"; fi
        old="$HOME/Applications/Scranton.app"
        if [ "$APP" != "$old" ] && [ -d "$old" ]; then mv "$old" "$HOME/.Trash/Scranton (old place) $stamp.app"; fi
        mv "$tmp/Scranton.app" "$APP"
        rm -r "$tmp"
        echo "Installed: $APP"
        echo "Open it from Finder > Applications or Spotlight (Cmd+Space, Scranton). Drag it to the Dock to keep it there."
        ;;
    uninstall-service)
        if service_installed && service_loaded; then launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true; fi
        rm -f "$PLIST"
        echo "Removed. The server is stopped; start it again with ./scranton.sh start"
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
    grok)
        # Grok Bot (幕僚长) runs this on your Mac: post and read only. See docs/grok-bot.md
        shift
        SCRANTON_PORT=$(port) exec "$PY" tools/grok_cli.py "$@"
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
        sed -n '2,14p' "$0"
        ;;
esac
