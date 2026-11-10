"""Mac/Linux agent injection — pastes the prompt into the agent CLI via tmux.

Called by wrapper.py on Mac and Linux. Requires tmux to be installed.
  - Mac:   brew install tmux
  - Linux: apt install tmux  (or yum, pacman, etc.)

How it works:
  1. Creates a tmux session running the agent CLI
  2. Queue watcher delivers the prompt as one bracketed paste
     ('tmux load-buffer' + 'tmux paste-buffer -p'), then presses Enter
  3. Wrapper attaches to the session so you see the full TUI
  4. Ctrl+B, D to detach (agent keeps running in background)
"""

import os
import shlex
import shutil
import re
import subprocess
import sys
import time
import uuid

TMUX_COMMAND_TIMEOUT = 5.0


def _exact(session_name: str) -> str:
    """tmux target that matches this session name exactly.

    A bare `-t name` falls back to prefix matching, so `agentchattr-visual`
    would hit `agentchattr-visualqa` when the former isn't running.
    """
    return f"={session_name}"


def _exact_pane(session_name: str) -> str:
    """Exact-match target for pane commands (session's active window/pane)."""
    return f"={session_name}:"


def _session_exists(session_name: str) -> bool:
    """Return True while the tmux session is still alive."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", _exact(session_name)],
        capture_output=True,
    )
    return result.returncode == 0


def _check_tmux():
    """Verify tmux is installed, exit with helpful message if not."""
    if shutil.which("tmux"):
        return
    print("\n  Error: tmux is required for auto-trigger on Mac/Linux.")
    if sys.platform == "darwin":
        print("  Install: brew install tmux")
    else:
        print("  Install: apt install tmux  (or yum/pacman equivalent)")
    sys.exit(1)


def _pane_id(tmux_session: str) -> str | None:
    """Resolve the session's active pane once, so paste and Enter hit the same pane."""
    result = subprocess.run(
        ["tmux", "display-message", "-p", "-t", _exact_pane(tmux_session), "#{pane_id}"],
        capture_output=True, timeout=TMUX_COMMAND_TIMEOUT,
    )
    if result.returncode != 0:
        return None
    pane = result.stdout.decode(errors="replace").strip()
    return pane or None


def _drop_buffer(name: str) -> None:
    subprocess.run(["tmux", "delete-buffer", "-b", name],
                   capture_output=True, timeout=TMUX_COMMAND_TIMEOUT)


# A first-run or sign-in question on the agent's screen. Typing the prompt into
# it would answer the question (Enter picks the highlighted choice), so wait.
_QUESTION_RE = re.compile(
    r"Do you trust|trust the files|Yes, I trust|Yes, I accept|No, exit|Enter to confirm"
    r"|Press Enter to continue|Select login method|Sign in with ChatGPT|Log in with|Choose the text style"
    r"|Allow this|Do you want to proceed|Approve\?|\(y/n\)|\[Y/n\]",
    re.I,
)

# Codex's "Approaching rate limits · switch to a cheaper model?" is a choice, not a limit: the plan
# still has room. It mentions "rate limit", so the limit check used to post "I stopped: … usage limit"
# every 30 min while it sat waiting (visualqa, 11-10 16:43–18:13, with 7% of the week left).
# wrapper.py turns it off at launch; if it shows anyway it counts as a question. Only the box itself
# (its title and its "Press enter to confirm" line together): a teammate writing about it is not the box.
_CODEX_NUDGE = re.compile(r"Approaching rate limits", re.I)
_CODEX_NUDGE_CONFIRM = re.compile(r"to confirm", re.I)
_CODEX_NUDGE_LINE = re.compile(r"Approaching rate limits|rate limit reminders", re.I)


def pane_text(tmux_session: str, lines: int = 40) -> str:
    try:
        r = subprocess.run(["tmux", "capture-pane", "-p", "-J", "-t", _exact_pane(tmux_session), "-S", f"-{lines}"],
                           capture_output=True, timeout=TMUX_COMMAND_TIMEOUT)
        return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""
    except Exception:
        return ""


def _bottom(text: str, n: int) -> str:
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def waiting_on_question(tmux_session: str) -> bool:
    # Only the bottom of the screen: a question in old transcript output must not stall the agent.
    return bool(_QUESTION_RE.search(_bottom(pane_text(tmux_session, 30), 6)))


_BOX = re.compile(r"^[\s│|╭╮╰╯─━┃>❯›•·*]+|[\s│|╭╮╰╯─━┃]+$")


def question_text(tmux_session: str) -> str:
    """The question the screen is asking, in one line, so the chat can say what it is.
    The last line in the bottom 14 that ends with "?", else the line that matched."""
    lines = [_BOX.sub("", l).strip() for l in pane_text(tmux_session, 40).splitlines()]
    lines = [l for l in lines if l][-14:]
    asked = [l for l in lines if l.endswith(("?", "？")) and len(l) > 6]
    hit = asked[-1] if asked else next((l for l in reversed(lines) if _QUESTION_RE.search(l)), "")
    # "Do you want to proceed?" alone says little: add what it's about (the line above, e.g. the command)
    if hit and len(hit) < 40 and hit in lines:
        i = lines.index(hit)
        about = next((l for l in reversed(lines[max(0, i - 3):i]) if not l.lower().endswith("command")), "")
        if about:
            hit = f"{hit} ({about})"
    return hit[:160]


_INPUT_LINE = re.compile(r"^\s*[│|]?\s*[>❯›]\s?(.*)$")


def _still_in_input(tmux_session: str, head: str) -> bool:
    """True only when the CLI's input line still holds our text (Enter was swallowed),
    not when the submitted prompt is merely echoed in the transcript."""
    for line in reversed(_bottom(pane_text(tmux_session, 30), 8).splitlines()):
        m = _INPUT_LINE.match(line)
        if m:
            rest = m.group(1).strip()
            return bool(rest) and (rest.startswith(head[:20]) or rest.startswith("[Pasted text"))
    return False


# Antigravity's one-time "trust this folder" question, with "Yes" highlighted. Scranton made that
# folder (the teammate's own worktree of Lu's project), so it answers Yes itself (Lu, 11-10: she
# couldn't answer it from Scranton). Nothing else is ever answered automatically.
_AGY_TRUST = re.compile(r"Do you trust the contents of this project\?")
_AGY_TRUST_YES = re.compile(r"^\s*>\s*Yes, I trust this folder\s*$", re.M)


def _answer_agy_trust(tmux_session: str) -> bool:
    screen = _bottom(pane_text(tmux_session, 30), 14)
    if not (_AGY_TRUST.search(screen) and _AGY_TRUST_YES.search(screen)):
        return False
    subprocess.run(["tmux", "send-keys", "-t", _exact_pane(tmux_session), "-H", "0d"],
                   capture_output=True, timeout=TMUX_COMMAND_TIMEOUT)
    print("  TRUST: answered Antigravity's \"trust this folder\" with Yes (its own worktree)", flush=True)
    for _ in range(10):
        time.sleep(0.5)
        if not waiting_on_question(tmux_session):
            return True
    return False


_AGY_SURVEY = re.compile(r"Help us improve[\s\S]*\[0\] Skip")


def _skip_agy_survey(tmux_session: str) -> None:
    """Antigravity's "How's the CLI experience so far?" takes number keys, so a message typed into
    it would be eaten. Skip it (0) before typing."""
    if _AGY_SURVEY.search(_bottom(pane_text(tmux_session, 20), 8)):
        subprocess.run(["tmux", "send-keys", "-t", _exact_pane(tmux_session), "-l", "0"],
                       capture_output=True, timeout=TMUX_COMMAND_TIMEOUT)
        print("  SURVEY: skipped Antigravity's feedback question", flush=True)
        time.sleep(0.8)


def inject(text: str, *, tmux_session: str, delay: float = 0.3):
    """Returns True when delivered, "question" when the agent's screen shows a
    question (nothing was typed), False when tmux failed."""
    _skip_agy_survey(tmux_session)
    if waiting_on_question(tmux_session):
        _answer_agy_trust(tmux_session)
    if waiting_on_question(tmux_session):
        print(f"  WAITING: {tmux_session} shows a question; not typing into it", flush=True)
        return "question"
    ok = _inject(text, tmux_session=tmux_session, delay=delay)
    _LAST_INJECTED[tmux_session] = _norm(text)
    if ok:
        # The prompt still sitting in the input box means Enter was swallowed
        # (e.g. the CLI was still drawing). Press it once more.
        time.sleep(1.5)
        if not waiting_on_question(tmux_session) and _still_in_input(tmux_session, text[:30]):
            subprocess.run(["tmux", "send-keys", "-t", _exact_pane(tmux_session), "-H", "0d"],
                           capture_output=True, timeout=TMUX_COMMAND_TIMEOUT)
            print("  INJECT: pressed Enter again (prompt was still in the input box)", flush=True)
    return ok


def _inject(text: str, *, tmux_session: str, delay: float = 0.3) -> bool:
    """Deliver text to the agent CLI as ONE bracketed paste, then press Enter.

    Why a paste and not send-keys: a pty's raw input queue is finite (1024
    bytes on macOS), so a single long `send-keys -l` can reach the CLI as
    several reads. Claude Code treats a large read as a paste and, when typed
    text follows a paste before Enter, submits only the typed text: measured on
    macOS, a 1204-byte prompt arrived as its last 182 characters. With
    `paste-buffer -p`, tmux wraps the text in ESC[200~ / ESC[201~ when the CLI
    has enabled bracketed paste mode, and those delimiters let the CLI
    reassemble one paste across split reads. A CLI that never asked for
    bracketed paste gets the plain bytes, exactly as before.

    Returns True only when tmux accepted both the paste and Enter. On any
    failure, a non-zero exit, timeout or an exception launching tmux, it prints a
    diagnostic, cleans up its buffer on a best-effort basis, sends nothing
    further, and returns False (the queue watcher swallows exceptions, so a
    raise alone would be invisible). Each delivery and cleanup command has a
    time limit so a stuck tmux cannot block the queue watcher indefinitely.
    Failure does not imply that retrying is safe: a paste may have arrived.
    """
    buffer_name = f"agentchattr-inject-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    try:
        return _deliver(text, tmux_session, buffer_name, delay)
    except Exception as exc:  # launching tmux itself failed, not a non-zero exit
        print(f"  INJECT FAILED: {type(exc).__name__}: {exc}")
        try:
            _drop_buffer(buffer_name)
        except Exception:
            pass
        return False


def _deliver(text: str, tmux_session: str, buffer_name: str, delay: float) -> bool:
    """The paste-then-Enter sequence; every tmux exit status is checked."""
    pane = _pane_id(tmux_session)
    if pane is None:
        print(f"  INJECT FAILED: no pane for tmux session {tmux_session!r}")
        return False

    loaded = subprocess.run(
        ["tmux", "load-buffer", "-b", buffer_name, "-"],
        input=text.encode("utf-8"),
        capture_output=True, timeout=TMUX_COMMAND_TIMEOUT,
    )
    if loaded.returncode != 0:
        print(f"  INJECT FAILED: load-buffer exit {loaded.returncode}: "
              f"{loaded.stderr.decode(errors='replace').strip()}")
        _drop_buffer(buffer_name)
        return False

    # -p: bracket the paste if the pane asked for it; -d: drop the buffer after.
    pasted = subprocess.run(
        ["tmux", "paste-buffer", "-p", "-d", "-b", buffer_name, "-t", pane],
        capture_output=True, timeout=TMUX_COMMAND_TIMEOUT,
    )
    if pasted.returncode != 0:
        print(f"  INJECT FAILED: paste-buffer exit {pasted.returncode}: "
              f"{pasted.stderr.decode(errors='replace').strip()}")
        _drop_buffer(buffer_name)
        return False

    # Scale delay with text length so longer prompts get more processing time
    time.sleep(max(delay, len(text) * 0.001))
    entered = subprocess.run(
        ["tmux", "send-keys", "-t", pane, "-H", "0d"],   # raw CR: agy ignores tmux's named Enter
        capture_output=True, timeout=TMUX_COMMAND_TIMEOUT,
    )
    if entered.returncode != 0:
        print(f"  INJECT FAILED: Enter exit {entered.returncode}: "
              f"{entered.stderr.decode(errors='replace').strip()}")
        return False
    return True


def _without_codex_input_animation(output: bytes) -> bytes:
    """Ignore Codex's single-dot particles in and immediately around its prompt.

    Keep output above the composer intact, including real Braille output and
    progress spinners. Replacing particles with spaces preserves text columns.
    """
    dots = "⠁⠂⠄⠈⠐⠠⡀⢀"
    lines = output.decode("utf-8", errors="replace").splitlines()
    prompt = next((i for i in range(len(lines) - 1, -1, -1)
                   if lines[i].lstrip(" " + dots).startswith("›")), None)
    if prompt is None:
        return output
    translation = str.maketrans({dot: " " for dot in dots})
    lines[prompt] = lines[prompt].translate(translation).rstrip()
    for index in (prompt - 1, prompt + 1):
        if 0 <= index < len(lines) and not lines[index].strip(" \t" + dots):
            lines[index] = ""
    return "\n".join(lines).encode("utf-8")


# ---- what the agent is doing / why it stopped, read from its screen ----------
_SPINNER = re.compile(r"^\s*[✻✶✳✢✽✺*·•◦⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s+([A-Z][A-Za-z ]{2,30})(?:…|\.\.\.)")
_ACTION = re.compile(r"^\s*[⏺●•]\s+(?:[\w.-]+ - )?([A-Za-z_][\w.:-]*)(?: \(MCP\))?\((.{0,120})")
_NICE = {
    "read": "Reading {}", "write": "Writing {}", "edit": "Editing {}", "update": "Editing {}", "multiedit": "Editing {}",
    "bash": "Running {}", "grep": "Searching", "glob": "Looking for files", "search": "Searching",
    "webfetch": "Reading a web page", "websearch": "Searching the web", "task": "Handing part of it to a helper",
    "todowrite": "Planning", "notebookedit": "Editing a notebook",
}
_PROBLEMS = [
    ("limit", re.compile(r"usage limit|limit reached|hit your limit|rate.?limit|quota (?:exceeded|reached)|out of (?:credits|messages)", re.I),
     "I stopped: my {app} plan has hit its usage limit. @ me again after it resets, or switch me to another app: Settings → Agents → me → Runs on."),
    ("login", re.compile(r"please (?:run )?/login|not logged in|log ?in again|invalid api key|authentication (?:failed|error)|token (?:has )?expired", re.I),
     "I stopped: {app} needs you to sign in again. Settings → Connections → Switch account."),
    ("question", re.compile(r"(?!x)x"),
     "I stopped: my terminal is waiting on a question. Answer it here."),
    ("error", re.compile(r"\bAPI Error\b|Internal server error|overloaded_error|Connection error", re.I),
     "I hit an error from {app} and stopped. Open my terminal to see it, or restart me."),
]


_CODEX = re.compile(r"^\s*[•●]\s+(Running|Reading|Editing|Searching|Exploring|Updating|Thinking|Working)\b\s*(.{0,60})")


def _short(path: str) -> str:
    path = path.strip().strip('"\'').split(",")[0].strip()
    return path.rsplit("/", 1)[-1][:48] if "/" in path else path[:48]


_LAST_INJECTED: dict[str, str] = {}   # tmux session -> what we last typed (normalised)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def _echoes_prompt(line: str, injected: str) -> bool:
    """True when a screen line is just part of the prompt we typed (the brief mentions
    'usage limit', so its echo must never count as the app saying it)."""
    core = _norm(re.sub(r"^[\s│|>❯›⏵·•●⏺]+", "", line))
    return len(core) >= 12 and bool(injected) and core[:60] in injected


def is_working(tmux_session: str) -> bool:
    """A spinner near the bottom of the screen: the agent is in the middle of something."""
    text = pane_text(tmux_session, 30)
    return any(_SPINNER.match(l) for l in [l for l in text.splitlines() if l.strip()][-8:])


def describe_screen(tmux_session: str) -> tuple[str, str | None]:
    """(what it's doing in a few words, problem key or None) from the bottom of the screen.
    A problem only counts when no spinner is showing and the line isn't our own prompt."""
    text = pane_text(tmux_session, 60)
    if not text:
        return "", None
    lines = [l for l in text.splitlines() if l.strip()]
    injected = _LAST_INJECTED.get(tmux_session, "")
    bottom = "\n".join(l for l in lines[-10:] if not _echoes_prompt(l, injected))
    nudge = bool(_CODEX_NUDGE.search(bottom) and _CODEX_NUDGE_CONFIRM.search(bottom))
    if nudge:   # the box's own lines say "rate limit"; a real limit elsewhere on screen still counts
        bottom = "\n".join(l for l in bottom.splitlines() if not _CODEX_NUDGE_LINE.search(l))
    problem = next((key for key, rx, _ in _PROBLEMS if rx.search(bottom)), None)
    if nudge and not problem:
        problem = "question"   # Codex asking whether to switch models: not a usage limit
    if problem and any(_SPINNER.match(l) for l in lines[-8:]):
        problem = None   # still working: whatever it printed isn't where it stopped
    if not problem and waiting_on_question(tmux_session):
        problem = "question"   # e.g. a permission prompt in the middle of a task
    doing = ""
    for l in reversed(lines[-40:]):
        m = _ACTION.match(l)
        if m:
            name = m.group(1).split("__")[-1].lower()
            arg = m.group(2).rstrip(")")
            if name in ("chat_send", "send"):
                doing = "Writing a reply"
            elif name in ("chat_read", "read_messages", "chat_messages"):
                doing = "Reading the chat"
            else:
                tpl = _NICE.get(name)
                doing = tpl.format(_short(arg) if "{}" in tpl else "") if tpl else name.replace("_", " ").capitalize()
            break
        c = _CODEX.match(l)
        if c:
            doing = f"{c.group(1)} {c.group(2).strip()}".strip()
            break
    for l in reversed(lines[-8:]):
        m = _SPINNER.match(l)
        if m:
            phase = m.group(1).strip()
            doing = f"{phase} · {doing}" if doing and phase.lower() not in doing.lower() else (doing or phase)
            break
    return doing[:80], problem


def problem_text(key: str, app: str) -> str:
    for k, _, msg in _PROBLEMS:
        if k == key:
            return msg.format(app=app or "the app")
    return ""


def get_activity_checker(session_name, trigger_flag=None, *, provider=""):
    """Return a callable that detects tmux pane output by hashing content."""
    last_hash = [None]

    def check():
        # External trigger: queue watcher injected a message
        if trigger_flag is not None and trigger_flag[0]:
            trigger_flag[0] = False
            return True
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", _exact_pane(session_name), "-p"],
                capture_output=True, timeout=2,
            )
            output = result.stdout
            if provider == "codex":
                output = _without_codex_input_animation(output)
            h = hash(output)
            changed = last_hash[0] is not None and h != last_hash[0]
            last_hash[0] = h
            return changed
        except Exception:
            return False

    return check


def run_agent(
    command,
    extra_args,
    cwd,
    env,
    queue_file,
    agent,
    no_restart,
    start_watcher,
    strip_env=None,
    pid_holder=None,
    session_name=None,
    inject_env=None,
    inject_delay: float = 0.3,
):
    """Run agent inside a tmux session, inject via tmux send-keys."""
    _check_tmux()

    session_name = session_name or f"agentchattr-{agent}"
    agent_cmd = " ".join(
        [shlex.quote(command)] + [shlex.quote(a) for a in extra_args]
    )

    # Build env(1) prefix for the command INSIDE the tmux session.
    # subprocess.run(env=...) only affects the tmux client binary — the
    # session shell inherits from the tmux server instead.  Use env(1)
    # to set (-u to unset, VAR=val to inject) vars in the actual session.
    env_parts = []
    if strip_env:
        env_parts.extend(f"-u {shlex.quote(v)}" for v in strip_env)
    if inject_env:
        env_parts.extend(
            f"{shlex.quote(k)}={shlex.quote(v)}"
            for k, v in inject_env.items()
        )
    if env_parts:
        agent_cmd = f"env {' '.join(env_parts)} {agent_cmd}"

    # Resolve cwd to absolute path (tmux -c needs it)
    from pathlib import Path
    abs_cwd = str(Path(cwd).resolve())

    # Wire up injection with the tmux session name
    inject_fn = lambda text: inject(text, tmux_session=session_name, delay=inject_delay)
    start_watcher(inject_fn)

    print(f"  Using tmux session: {session_name}")
    print(f"  Detach: Ctrl+B, D  (agent keeps running)")
    print(f"  Reattach: tmux attach -t {session_name}\n")

    # Scranton: back off when the CLI keeps exiting right away (logged out,
    # out of quota, bad flag) and give up after a few fast exits.
    quick_exits = 0
    started_at = time.monotonic()

    def _restart_delay() -> float | None:
        nonlocal quick_exits
        ran_for = time.monotonic() - started_at
        quick_exits = quick_exits + 1 if ran_for < 60 else 0
        if quick_exits >= 5:
            return None
        return min(10 * (2 ** quick_exits), 300) if quick_exits else 10

    while True:
        started_at = time.monotonic()
        try:
            # Clean up stale session from a previous crash
            subprocess.run(
                ["tmux", "kill-session", "-t", _exact(session_name)],
                capture_output=True,
            )

            # Create tmux session running the agent CLI
            result = subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name,
                 "-c", abs_cwd, agent_cmd],
                env=env,
            )
            if result.returncode != 0:
                print(f"  Error: failed to create tmux session (exit {result.returncode})")
                break

            # Attach — blocks until agent exits or user detaches (Ctrl+B, D)
            subprocess.run(["tmux", "attach-session", "-t", _exact(session_name)])

            # Check: did the agent exit, or did the user just detach?
            if _session_exists(session_name):
                # Session still alive — user detached, agent running in background.
                # Keep the wrapper alive so the local proxy and heartbeats survive.
                print(f"\n  Detached. {agent.capitalize()} still running in tmux.")
                print(f"  Reattach: tmux attach -t {session_name}")
                while _session_exists(session_name):
                    time.sleep(1)
                # Scranton runs wrappers headless (no terminal to attach to),
                # so "detached" is the normal state. If the agent CLI later
                # exits, bring it back instead of silently leaving the team.
                if no_restart:
                    break
                delay = _restart_delay()
                if delay is None:
                    print(f"\n  {agent.capitalize()} exited 5 times within a minute of starting. "
                          f"Not restarting. Check its login with ./scranton.sh attach, then start it again.")
                    break
                print(f"\n  {agent.capitalize()} exited. Restarting in {delay:.0f}s...")
                time.sleep(delay)
                continue

            # Session gone — agent exited
            if no_restart:
                break

            delay = _restart_delay()
            if delay is None:
                print(f"\n  {agent.capitalize()} exited 5 times within a minute of starting. "
                      f"Not restarting. Check its login with ./scranton.sh attach, then start it again.")
                break
            print(f"\n  {agent.capitalize()} exited. Restarting in {delay:.0f}s... (Ctrl+C to quit)")
            time.sleep(delay)
        except KeyboardInterrupt:
            # Kill the tmux session on Ctrl+C
            subprocess.run(
                ["tmux", "kill-session", "-t", _exact(session_name)],
                capture_output=True,
            )
            break
