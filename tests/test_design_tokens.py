"""The design system checks itself (docs/design-system.md, "Checks").

Lu, 2026-11-19: the Activity answer box shipped with its own font size, a bordered field and
outlined buttons, and she was the one who noticed. What can be counted is counted here; the
numbers may only go down."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
CSS = (STATIC / "design-system.css").read_text("utf-8")

# What was already there on 2026-11-19. Lower these when you remove one; never raise them.
RAW_FONT_SIZES = 20      # pixel sizes outside the tokens (16px on phones, a few display numbers)
HEAVY_WEIGHTS = 2        # font-weight 700 (the avatar initial, the toast link)
OUTLINED_BUTTONS = 0     # a button rule with its own "border: 1px solid"


def test_every_token_used_is_defined():
    defined = set()
    for f in STATIC.glob("*.css"):
        defined |= set(re.findall(r"(--ds-[a-z0-9-]+)\s*:", f.read_text("utf-8")))
    used = re.findall(r"var\((--ds-[a-z0-9-]+)\s*(,[^)]*)?\)", CSS)
    missing = sorted({name for name, fallback in used if name not in defined and not fallback})
    assert missing == [], f"used but never defined (they draw nothing): {missing}"


def test_no_new_sizes_weights_or_outlined_buttons():
    raw = re.findall(r"font-size:\s*\d+(?:\.\d+)?px", CSS)
    assert len(raw) <= RAW_FONT_SIZES, f"{len(raw)} raw pixel font sizes; use --ds-fs-xs/sm/md/lg/xl"
    heavy = re.findall(r"font-weight:\s*(?:[789]00|bold)", CSS)
    assert len(heavy) <= HEAVY_WEIGHTS, f"{len(heavy)} weights above 600; the system has 400, 500, 600"
    outlined = re.findall(r"[^\n{}]*button[^{]*\{[^}]*border:\s*1px solid[^}]*\}", CSS)
    assert len(outlined) <= OUTLINED_BUTTONS, f"outlined button: {outlined[0][:80]} … use .sc-btn"


def test_type_box_is_not_the_settings_field():
    # .sc-field is the labelled form field in Settings (scranton.css); the composer-style box is .sc-typebox
    js = "".join(p.read_text("utf-8") for p in STATIC.glob("scranton-nav.js"))
    assert "sc-typebox" in js and 'class="sc-field' not in js
