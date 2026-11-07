"""Start a command fully detached from the caller and record its pid.

Used by scranton.sh. `nohup cmd &` keeps the child in the caller's process
group, and launchd (login item / Dock app) can kill that group when the
launcher exits. A new session (setsid) survives that.

usage: python tools/spawn.py <pidfile> <logfile> -- <command> [args...]
"""
import os
import subprocess
import sys

if len(sys.argv) < 5 or sys.argv[3] != "--":
    sys.exit("usage: spawn.py <pidfile> <logfile> -- <command> [args...]")
pidfile, logfile, cmd = sys.argv[1], sys.argv[2], sys.argv[4:]

env = dict(os.environ)
for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "CURSOR_API_KEY"):  # = config_loader.PAID_API_ENV
    env.pop(key, None)  # subscriptions only

os.makedirs(os.path.dirname(pidfile) or ".", exist_ok=True)
os.makedirs(os.path.dirname(logfile) or ".", exist_ok=True)
with open(logfile, "ab") as log, open(os.devnull, "rb") as null:
    proc = subprocess.Popen(cmd, stdin=null, stdout=log, stderr=subprocess.STDOUT,
                            env=env, start_new_session=True)
with open(pidfile, "w") as f:
    f.write(str(proc.pid))
print(proc.pid)
