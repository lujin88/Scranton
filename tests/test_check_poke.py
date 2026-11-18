import time
import app, scranton_board


def test_waiting_for_check_wakes_the_checker_twice_at_most(tmp_path, monkeypatch):
    b = scranton_board.Board(tmp_path / "b.json")
    monkeypatch.setattr(app, "_quiet_channel", lambda ch: False)
    monkeypatch.setitem(app.config, "agents", {"visualqa": {}, "legal": {}, "dev": {}})
    now = time.time()
    b.upsert("p", "pm", ask="Time per case", state="waiting_qa", who="dev", note="dev 已改，待 visualqa", now=now - 5 * 3600)
    b.upsert("p", "pm", ask="Deck repo", state="waiting_qa", who="legal", now=now - 600)
    got = app._sc_check_pokes(b, now)
    assert [(g[0], g[1]) for g in got] == [("p", "visualqa")] and "行 1" in got[0][3]
    assert app._sc_check_pokes(b, now + 600) == []                 # not again within the hour
    assert len(app._sc_check_pokes(b, now + 3700)) == 2            # second and last for row 1; first for the legal row
    assert [g[1] for g in app._sc_check_pokes(b, now + 7400)] == ["legal"]
    assert app._row_checker({"who": "webdev", "note": "webdev 封面；等 legal 法务通过"}) == "legal"
