import tempfile, unittest

import scranton_presence as pr


class PresenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        pr.setup(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_visit_is_not_a_return(self):
        self.assertIsNone(pr.seen(1000))

    def test_back_after_two_hours(self):
        pr.seen(1000)
        self.assertIsNone(pr.seen(1000 + 3600))          # 1 h: not away long enough
        self.assertEqual(pr.seen(1000 + 3600 + 7200), 7200)
        self.assertIsNone(pr.seen(1000 + 3600 + 7300))   # only once

    def test_off_means_no_catch_up(self):
        pr.seen(1000)
        pr.set_enabled(False)
        self.assertIsNone(pr.seen(1000 + 9 * 3600))

    def test_text_names_owner_and_hours(self):
        t = pr.catch_up_text("Lu", 5 * 3600 + 100)
        self.assertTrue(t.startswith("@pm Lu 回来了（离开了 5 小时）"))
        self.assertIn("@Lu", t)
        self.assertIn("离开了 3 天", pr.catch_up_text("Lu", 3 * 86400))


if __name__ == "__main__":
    unittest.main()


class ShortcutsTest(unittest.TestCase):
    def test_defaults_then_save_drops_empty(self):
        import scranton_shortcuts as sc
        with tempfile.TemporaryDirectory() as d:
            sc.setup(d)
            self.assertEqual([i["label"] for i in sc.load()], ["What needs me", "Clean up my Mac"])
            self.assertIn("_to_delete", sc.load()[1]["text"])   # never deletes directly
            saved = sc.save([{"label": "A", "text": "@pm hi"}, {"label": "", "text": "x"}, {"label": "B", "text": " "}])
            self.assertEqual(saved, [{"label": "A", "text": "@pm hi"}])
            self.assertEqual(sc.load(), saved)
            with self.assertRaises(ValueError):
                sc.save("nope")
