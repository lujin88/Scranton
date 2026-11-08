import importlib, tempfile, unittest
from pathlib import Path

import app
from schedules import ScheduleStore

OLD = app._OLD_SCHEDULE_TEXTS["daily-summary"]
CFG = {"team": {"schedules": [{"id": "daily-summary", "daily_at": "21:05", "to": ["pm"],
                               "channel": "general", "text": "NEW TEXT"}]}}


class ScheduleTextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ScheduleStore(str(Path(self.tmp.name) / "s.json"))
        self._old = (app.schedules, app.room_settings, app._save_settings)
        app.schedules, app.room_settings, app._save_settings = self.store, {}, lambda: None

    def tearDown(self):
        app.schedules, app.room_settings, app._save_settings = self._old
        self.tmp.cleanup()

    def _seed_old(self, prompt):
        s = self.store.create(prompt=prompt, targets=["pm"], channel="general",
                              interval_seconds=86400, daily_at="21:05", created_by="Scranton")
        app.room_settings.update(seeded_schedules=["daily-summary"],
                                 seeded_schedule_ids={"daily-summary": s["id"]})
        return s["id"]

    def test_old_install_gets_new_text(self):
        sid = self._seed_old(OLD)
        app._seed_team_schedules(CFG)
        self.assertEqual(self.store.get(sid)["prompt"], "NEW TEXT")

    def test_lu_edit_is_kept(self):
        sid = self._seed_old("Lu wrote this")
        app._seed_team_schedules(CFG)
        self.assertEqual(self.store.get(sid)["prompt"], "Lu wrote this")

    def test_fresh_install_then_config_change(self):
        app._seed_team_schedules(CFG)
        sid = app.room_settings["seeded_schedule_ids"]["daily-summary"]
        cfg2 = {"team": {"schedules": [dict(CFG["team"]["schedules"][0], text="NEWER")]}}
        app._seed_team_schedules(cfg2)
        self.assertEqual(self.store.get(sid)["prompt"], "NEWER")


if __name__ == "__main__":
    unittest.main()
