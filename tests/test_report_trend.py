import json, time
import scranton_tokens as st


def test_daily_counts_wakes_per_day(tmp_path):
    now = time.time()
    msgs = [{"id": 1, "sender": "pm", "text": "@visualqa @dev 看一下", "timestamp": now - 60, "type": "chat"},
            {"id": 2, "sender": "dev", "text": "做完了 visualqa 验", "timestamp": now - 30, "type": "chat"},
            {"id": 3, "sender": "Lu", "text": "@pm 好", "timestamp": now - 10, "type": "chat"}]
    team = {"pm": {}, "dev": {}, "visualqa": {}}
    days = st.daily(msgs, team, days=3, home=tmp_path)
    today = days[-1]
    assert today["wakes"] == 3 and today["pm_wakes"] == 2
    assert today["calls"] == 0 and today["ctx_k"] is None
