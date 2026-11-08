import wrapper_unix as w


def _with(monkeypatch, text):
    monkeypatch.setattr(w, "pane_text", lambda s, n=40: text)
    return w.question_text("x")


def test_permission_prompt_names_the_command(monkeypatch):
    t = """⏺ Bash(git push origin feat)
╭──────────────────╮
│ Bash command      │
│   git push origin feat │
│ Do you want to proceed? │
│ ❯ 1. Yes          │
│   2. No           │
╰──────────────────╯"""
    assert _with(monkeypatch, t) == "Do you want to proceed? (git push origin feat)"


def test_trust_prompt(monkeypatch):
    t = "Do you trust the files in this folder?\n /Users/lu/x\n❯ 1. Yes, proceed\n  2. No, exit\nEnter to confirm"
    assert _with(monkeypatch, t) == "Do you trust the files in this folder?"


def test_nothing_on_screen(monkeypatch):
    assert _with(monkeypatch, "") == ""
