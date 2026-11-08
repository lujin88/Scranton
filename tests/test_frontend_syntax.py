"""Every page script must parse. One stray brace stops the whole page from loading,
and the Python tests can't see that."""
import shutil
import subprocess
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class FrontendSyntaxTests(unittest.TestCase):
    def test_every_script_parses(self):
        bad = []
        for f in sorted(STATIC.glob("*.js")):
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                bad.append(f"{f.name}: {r.stderr.strip().splitlines()[0] if r.stderr.strip() else 'error'}")
        self.assertEqual(bad, [], "scripts that don't parse:\n" + "\n".join(bad))

    def test_index_only_loads_scripts_that_exist(self):
        import re
        html = (STATIC / "index.html").read_text("utf-8")
        missing = [m for m in re.findall(r'src="/static/([^"?]+)', html) if not (STATIC / m).exists()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
