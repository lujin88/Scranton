#!/usr/bin/env python3
"""scranton.sh grok — for Grok Bot (幕僚长) running commands on this Mac.

  ./scranton.sh grok status                         channels and who's working
  ./scranton.sh grok read <channel> [--since ID] [--limit N]
  ./scranton.sh grok mentions [--since ID]          what @s you (grok) or Lu, any channel
  ./scranton.sh grok say <channel> "<text>" [--reply-to ID]

Posts appear as 幕僚长 (Grok). Write @项目经理 / @pm to give someone work; a message without an @
reaches nobody. Read output: [id] #channel HH:MM who ↳reply_to: text
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("SCRANTON_PORT", "8300"))


def token() -> str:
    p = ROOT / "data" / "grok-token"
    if not p.exists():
        sys.exit("Scranton hasn't made the Grok token yet. Start the server once: ./scranton.sh start")
    return p.read_text("utf-8").strip()


def call(method: str, path: str, body=None, query=None):
    url = f"http://127.0.0.1:{PORT}/api/scranton/grok/{path}"
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Grok-Token": token(), "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except Exception:
            msg = None
        sys.exit(f"Scranton said no: {msg or e}")
    except urllib.error.URLError:
        sys.exit("Scranton isn't running on this Mac. Start it with ./scranton.sh start")


def main():
    ap = argparse.ArgumentParser(prog="scranton.sh grok", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("read"); r.add_argument("channel"); r.add_argument("--since", type=int, default=-1); r.add_argument("--limit", type=int, default=30)
    m = sub.add_parser("mentions"); m.add_argument("--since", type=int, default=-1); m.add_argument("--limit", type=int, default=30)
    s = sub.add_parser("say"); s.add_argument("channel"); s.add_argument("text"); s.add_argument("--reply-to", type=int)
    a = ap.parse_args()

    if a.cmd == "status":
        d = call("GET", "status")
        print(f"Owner: {d.get('owner')}")
        print("Channels: " + ", ".join("#" + c for c in d.get("channels", [])))
        for h, t in d.get("team", {}).items():
            extra = f" · {t['doing']}" if t.get("doing") else ""
            print(f"  @{h} {t['label']}: {t['state']}{extra}")
    elif a.cmd in ("read", "mentions"):
        d = call("GET", "read", query={"channel": getattr(a, "channel", None), "since": a.since, "limit": a.limit,
                                       "mentions": "true" if a.cmd == "mentions" else None})
        print("\n".join(d.get("lines") or ["(nothing new)"]))
        print(f"-- last id: {d.get('last_id')} (pass --since {d.get('last_id')} next time for only newer messages)")
    elif a.cmd == "say":
        d = call("POST", "say", body={"channel": a.channel, "text": a.text, "reply_to": a.reply_to})
        print(f"Posted as 幕僚长 (Grok), message {d.get('id')}.")


if __name__ == "__main__":
    main()
