"""Lu, 11-26: a restart for a model change must not lose the job, and code that goes into a PR
waits for the quota instead of moving to a weaker model."""
import asyncio, json, time
import wrapper


def test_scrantons_own_notice_is_not_the_teammates_reply():
    at = time.time() - 30
    notice = {"sender": "visintern", "timestamp": at + 14, "metadata": {"auto": True},
              "text": "Gemini 4 Argon has used up its quota, but the plan still has room on other models"}
    assert not wrapper._replied_since([notice], "visintern", at)
    real = {"sender": "visintern", "timestamp": at + 20, "text": "两版在这里"}
    assert wrapper._replied_since([notice, real], "visintern", at)


def test_job_handed_just_before_the_limit_is_picked_up_again(tmp_path, monkeypatch):
    """The 11-25 13:11 case: asked at :06, limit notice at :20, restart. The request is handed back."""
    import io, urllib.request
    q = tmp_path / "visintern_queue.jsonl"
    (tmp_path / "run").mkdir()
    at = time.time() - 60
    (tmp_path / "run" / "visintern.work.json").write_text(json.dumps({"channel": "lu-portfolio", "thread": 24880, "at": at}))
    msgs = [{"sender": "pm", "text": "@visintern 探索｜行 88", "timestamp": at - 1},
            {"sender": "visintern", "timestamp": at + 14, "metadata": {"auto": True}, "text": "Gemini 4 Argon has used up its quota"}]
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=5: io.BytesIO(json.dumps(msgs).encode()))
    wrapper._resume_unfinished(q, "visintern", 8300, lambda: "tok", delay=0)
    line = json.loads(q.read_text().strip())
    assert line["channel"] == "lu-portfolio" and line["thread"] == 24880


def test_every_notice_scranton_posts_for_a_teammate_is_marked():
    import re
    from pathlib import Path
    src = Path(__file__).parent.parent.joinpath("app.py").read_text("utf-8")
    start = src.index("_AUTO_NOTE = ")
    calls = re.findall(r'store\.add\((?:inst\["name"\]|base),.*?\n(?:.*?\n){0,3}?', src[start:])
    blocks = [src[m.start():src.index("\n    ", src.index(")\n", m.start())) ] for m in re.finditer(r'store\.add\((?:inst\["name"\]|base), ', src)]
    assert len(blocks) >= 5
    for b in blocks:
        assert "_AUTO_NOTE" in b, b[:120]


class _Req:
    def __init__(self, body): self._b, self.headers = body, {"authorization": "Bearer t"}
    async def json(self): return self._b


def _setup(monkeypatch, tmp_path, hold):
    import app
    posted, restarted, overrides = [], [], []
    monkeypatch.setattr(app, "config", {"agents": {"gemdev": {"command": "agy", "model": "gemini-4-argon"},
                                                   "scout": {"command": "agy", "model": "gemini-4-argon"}},
                                        "team": {"model_limit": {"hold": hold}}, "server": {"data_dir": str(tmp_path)}})
    monkeypatch.setattr(app, "_MODEL_FB", tmp_path / "fb.json")
    class _Reg:
        def resolve_token(self, t): return {"name": app._who, "base": app._who}
    monkeypatch.setattr(app, "registry", _Reg())
    class _Store:
        def add(self, sender, text, **k): posted.append((sender, text, k))
    monkeypatch.setattr(app, "store", _Store())
    monkeypatch.setattr(app._sc_team, "load_overrides", lambda: {})
    monkeypatch.setattr(app._sc_team, "set_override", lambda *a, **k: overrides.append(a[:3]))
    monkeypatch.setattr(app, "_sc_resume_text", lambda n: ("lumin-sotry-telling", f"@{n} 你刚被重启，手上的活没有丢：接着做行 2「Lumi 动画超亮一帧」。", None))
    async def _r(n): restarted.append(n)
    async def _b(): pass
    monkeypatch.setattr(app, "_sc_restart_quiet", _r)
    monkeypatch.setattr(app, "broadcast_team_changed", _b)
    return app, posted, restarted, overrides


def _check(app, who):
    app._who = who
    r = asyncio.run(app.scranton_limit_check(_Req({"problem": "model_limit", "text": "Individual quota reached. Resets in 3h47m", "channel": "lumin-sotry-telling"})))
    return json.loads(r.body)


def test_pr_coder_waits_and_pm_is_told_once(monkeypatch, tmp_path):
    app, posted, restarted, overrides = _setup(monkeypatch, tmp_path, ["gemdev"])
    out = _check(app, "gemdev")
    assert out == {"action": "switched", "held": True}
    assert overrides == [] and restarted == []                     # no weaker model, no restart
    assert len(posted) == 1 and posted[0][0] == "Scranton"
    assert posted[0][1].startswith("@pm gemdev") and "行 2「Lumi 动画超亮一帧」" in posted[0][1]
    _check(app, "gemdev")
    assert len(posted) == 1                                         # said once
    # After the reset it is started again on the same model and gets its row back.
    back = asyncio.run(app._sc_model_back_once(now=time.time() + 5 * 3600))
    assert back == ["gemdev"] and overrides == []
    assert json.loads((tmp_path / "fb.json").read_text()) == {}


def test_other_gemini_teammates_still_move_down(monkeypatch, tmp_path):
    app, posted, restarted, overrides = _setup(monkeypatch, tmp_path, ["gemdev"])
    out = _check(app, "scout")
    assert out["action"] == "switched" and out["model"] == "gemini-3.8-flash"
    assert overrides == [("scout", "model", "gemini-3.8-flash")]
    assert posted[0][0] == "scout" and posted[0][2]["metadata"] == {"auto": True}
