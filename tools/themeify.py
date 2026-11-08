"""One-off: replace hard-coded dark colours in our CSS with theme tokens.

Each grey becomes var(--tone-XX) (XX = its dark hex byte); white tints become
rgba(var(--ink), a); pastel status text becomes a named token. design-system.css
defines what each token is in dark and in light. Run from the repo root:
    python3 tools/themeify.py static/scranton.css static/design-system.css
Safe to re-run: already-converted values are left alone.
"""
import re
import sys

GREYS = {
    "0e0e0e": "0e", "121212": "12", "1a1a1a": "1a", "1c1c1c": "1c", "1f1f1f": "1f",
    "202020": "20", "212121": "21", "222222": "22", "222": "22", "232323": "23",
    "242424": "24", "262626": "26", "2a2a2a": "2a", "2c2c2c": "2c", "2e2e2e": "2e",
    "333333": "33", "333": "33", "3a3a3a": "3a", "3c3c3c": "3c", "404040": "40",
    "4a4a4a": "4a", "555555": "55", "555": "55", "5a5a5a": "5a", "6e6e6e": "6e",
    "707070": "70", "8a8a8a": "8a", "8c8c8c": "8c", "a4a4a4": "a4", "a7a7a7": "a7",
    "c7c7c7": "c7", "f5f5f5": "f5", "101010": "10",
    "7a7a7a": "70", "7d7d7d": "70", "191919": "1a", "111": "10", "111111": "10", "171717": "1a",
    "0f0f0f": "0e", "141414": "12", "282828": "26", "2f2f2f": "2e", "383838": "3a", "bdbdbd": "c7",
    "d4d4d4": "c7", "d6d6d6": "c7",
}
NAMED = {
    "8ce99a": "--ds-ok-text", "7ee08f": "--ds-ok-text", "7ee2a8": "--ds-ok-text",
    "f8a39d": "--ds-err-text", "f28b82": "--ds-err-text",
    "f0cb6b": "--ds-warn-text",
    "9cc0fa": "--ds-link-text", "9cc0ff": "--ds-link-text", "8ab4f8": "--ds-link-text",
    "e3edff": "--ds-link-text",
    "3a3f22": "--ds-pic-bg",
}
HEX = re.compile(r"#([0-9a-fA-F]{3,6})\b")
WHITE = re.compile(r"rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*([0-9.]+)\s*\)")
FLOAT = re.compile(r"rgba\(\s*(?:38\s*,\s*38\s*,\s*38|44\s*,\s*44\s*,\s*44)\s*,\s*([0-9.]+)\s*\)")
SKIP_START, SKIP_END = "/* theme-tokens:start */", "/* theme-tokens:end */"


def convert_line(line):
    def hexsub(m):
        h = m.group(1).lower()
        if h in GREYS:
            return f"var(--tone-{GREYS[h]})"
        if h in NAMED:
            return f"var({NAMED[h]})"
        return m.group(0)
    line = HEX.sub(hexsub, line)
    line = WHITE.sub(lambda m: f"rgba(var(--ink), {m.group(1)})", line)
    line = FLOAT.sub(lambda m: f"rgba(var(--float), {m.group(1)})", line)
    return line


def convert(text):
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        if SKIP_START in line:
            skipping = True
        if skipping:
            out.append(line)
        else:
            out.append(convert_line(line))
        if SKIP_END in line:
            skipping = False
    return "".join(out)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        new = convert(src)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        print(path, "changed lines:", sum(a != b for a, b in zip(src.splitlines(), new.splitlines())))
