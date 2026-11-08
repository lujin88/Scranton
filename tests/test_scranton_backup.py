import io, json, tempfile, unittest, zipfile
from datetime import date, timedelta
from pathlib import Path

import scranton_backup as bk


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data, self.up, self.dest = root / "data", root / "uploads", root / "dest"
        self.data.mkdir(); self.up.mkdir()
        (self.data / "agentchattr_log.jsonl").write_text('{"id":1,"text":"hi"}\n')
        (self.data / "registry.json").write_text('{"secret":"token"}')
        (self.data / "pm_queue.jsonl").write_text("x")
        (self.data / "run").mkdir(); (self.data / "run" / "pm.pid").write_text("1")
        (self.up / "a.png").write_bytes(b"png")
        (self.data / "provider-config").mkdir()
        (self.data / "provider-config" / "pm.json").write_text('{"headers": {"Authorization": "Bearer abc"}}')
        (self.data / "other.json").write_text('{"token": "abc"}')
        (self.data / "schedules.json").write_text('[{"prompt": "never use an API key or a token"}]')
        bk.setup(self.data, self.up)
        bk.set_settings(folder=str(self.dest))

    def tearDown(self):
        self.tmp.cleanup()

    def names(self, raw):
        return set(zipfile.ZipFile(io.BytesIO(raw)).namelist())

    def test_export_has_history_not_tokens(self):
        n = self.names(bk.export_bytes())
        self.assertIn("data/agentchattr_log.jsonl", n)
        self.assertIn("uploads/a.png", n)
        self.assertIn("README.txt", n)
        self.assertIn("data/schedules.json", n)  # mentioning the words is fine
        for bad in ("data/provider-config/pm.json", "data/other.json", "data/registry.json", "data/pm_queue.jsonl", "data/run/pm.pid", "data/backup.json"):
            self.assertNotIn(bad, n)

    def test_backup_now_and_keep_14(self):
        self.dest.mkdir()
        for i in range(20):
            (self.dest / bk.file_name(date(2026, 1, 1) + timedelta(days=i))).write_bytes(b"x")
        (self.dest / "mine.zip").write_bytes(b"keep")
        s = bk.backup_now()
        self.assertFalse(s["error"])
        ours = [p for p in self.dest.iterdir() if bk.NAME_RE.match(p.name)]
        self.assertEqual(len(ours), 14)
        today = self.names((self.dest / bk.file_name()).read_bytes())
        self.assertNotIn("uploads/a.png", today)            # pictures aren't in every daily zip…
        self.assertTrue((self.dest / "Scranton files" / "a.png").exists())   # …they're kept once
        self.assertTrue((self.dest / bk.file_name()).exists())
        self.assertTrue((self.dest / "mine.zip").exists())
        self.assertFalse(bk.due())

    def test_relative_folder_refused(self):
        with self.assertRaises(ValueError):
            bk.set_settings(folder="backups")

    def test_import_roundtrip(self):
        raw = bk.export_bytes()
        (self.data / "agentchattr_log.jsonl").write_text('{"id":9,"text":"new"}\n')
        bk.stage_import(raw)
        self.assertTrue(bk.settings()["pending_import"])
        self.assertTrue((self.dest / bk.file_name()).exists())  # what was here got backed up first
        moved = bk.apply_pending(self.data, self.up)
        self.assertGreater(moved, 0)
        self.assertIn('"hi"', (self.data / "agentchattr_log.jsonl").read_text())
        olds = list((self.data / "import-old").rglob("agentchattr_log.jsonl"))
        self.assertIn('"new"', olds[0].read_text())
        self.assertEqual((self.data / "registry.json").read_text(), '{"secret":"token"}')

    def zipwith(self, name):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("data/agentchattr_log.jsonl", "{}")
            z.writestr(name, "x")
        return buf.getvalue()

    def test_import_refuses_escape_and_junk(self):
        for name in ("../evil.txt", "data/../../evil", "/abs", "other/x"):
            with self.assertRaises(ValueError):
                bk.stage_import(self.zipwith(name))
        with self.assertRaises(ValueError):
            bk.stage_import(b"not a zip")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("data/x.json", "{}")
        with self.assertRaises(ValueError):
            bk.stage_import(buf.getvalue())

    def test_import_skips_tokens(self):
        bk.stage_import(self.zipwith("data/registry.json"))
        self.assertFalse((self.data / "import-pending" / "data" / "registry.json").exists())


if __name__ == "__main__":
    unittest.main()
