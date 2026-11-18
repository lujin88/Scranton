import scranton_team as t

RAW = """auto | Auto
gpt-5.3-codex-low | Codex 5.3 Low
gpt-5.3-codex | Codex 5.3
gpt-5.3-codex-xhigh-fast | Codex 5.3 Extra High Fast
gpt-5.2 | GPT-5.2
composer-2.5 | Composer 2.5
claude-opus-5-thinking-high | Claude Opus 5 1M Thinking
gpt-5.6-sol-high | GPT-5.6 Sol 1M High
claude-fable-5-thinking-high | Claude Fable 5 1M Thinking (NO ZDR)
cursor-grok-4.5-high | Grok 4.5
grok-4.7-low | Grok 4.7  Low
grok-4.7-medium | Grok 4.7  Medium
grok-4.7-high-fast | Grok 4.7  High Fast​​
cursor-grok-4.6-low | Grok 4.6 Low
cursor-grok-4.6-high | Grok 4.6
composer-2.5-fast | Composer 2.5 Fast
claude-opus-5-5-low | Claude Opus 5.5 1M Low
claude-opus-5-5-medium | Claude Opus 5.5 1M
claude-opus-5-5-max-fast | Claude Opus 5.5 1M Max Fast
claude-opus-4-8-high | Claude Opus 4.8 1M
gemini-4-neon-low | Gemini 4 Neon Low
gemini-4-neon-medium | Gemini 4 Neon Medium
gemini-3.8-flash-low | Gemini 3.8 Flash Low
gpt-5.6-sol-medium | GPT-5.6 Sol 1M
gpt-5.5-medium | GPT-5.5 1M
claude-fable-5-2-high | Claude Fable 5.2 1M (NO ZDR)
claude-haiku-5-5-thinking-low | Claude Haiku 5.5  Low
kimi-k3-max | Kimi K3"""
MODELS = [[a, b, "Your Cursor plan"] for a, b in (l.split(" | ") for l in RAW.splitlines())]


def test_one_line_per_model_newest_version_cursors_own_effort():
    got = {m[1]: m[0] for m in t.cursor_short(MODELS)}
    assert got["Auto"] == "auto"
    assert got["Claude Opus 5.5"] == "claude-opus-5-5-medium"      # the bare name, not Low or Max Fast
    assert "Claude Opus 5" not in got and "Claude Opus 4.8" not in got
    assert got["Grok 4.7"] == "grok-4.7-medium"                    # no bare variant: medium
    assert "Grok 4.6" not in got and "Grok 4.5" not in got
    assert got["Composer 2.5"] == "composer-2.5"
    assert got["GPT-5.6 Sol"] == "gpt-5.6-sol-medium"
    assert got["Claude Fable 5.2"] == "claude-fable-5-2-high"
    assert len(got) < len(MODELS) / 2


def test_model_in_use_stays_selectable(monkeypatch):
    monkeypatch.setattr(t, "cursor_models", lambda: MODELS)
    ids = [m[0] for m in t.models_for("cursor", "cursor-grok-4.6-low")]
    assert ids[0] == "" and "cursor-grok-4.6-low" in ids
    assert len(t.models_for("cursor", full=True)) == len(MODELS) + 1
