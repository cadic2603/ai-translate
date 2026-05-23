"""Static coverage check: every palette key referenced is defined.

The theme engine at :mod:`src.constants.theme` exposes the
``color(name)`` lookup against a per-theme dict (``light`` / ``dark``).
A missing key returns an empty string and the QSS rule that
referenced it renders blank — invisible borders, transparent
backgrounds, illegible text.  No exception, no log, just silent
breakage on whichever theme is missing the key.

This scanner extracts every ``color("name")`` call site across the
codebase and asserts each name is present in BOTH the light and
dark palettes.  Runs in milliseconds — no heavy imports needed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.constants.theme import _PALETTES

_SRC_ROOT = Path(__file__).parent.parent / "src"
_SCAN_DIRS = (_SRC_ROOT,)  # everywhere

# Match ``color("key")`` / ``color('key')``.  Restrict the key to
# lowercase letters / digits / underscores so log strings or
# comments containing ``color("...")``-shaped text don't false-
# positive.  The ``(?<![A-Za-z_])`` look-behind keeps the substring
# match from triggering on method names ending in ``color`` (e.g.
# ``set_color(``).
_COLOR_CALL_RE = re.compile(
    r"""(?<![A-Za-z_])color\(\s*['"]([a-z][a-z0-9_]*)['"]""",
)


def _collect_referenced_palette_keys() -> set[str]:
    """Returns the set of palette keys referenced via ``color()``."""
    keys: set[str] = set()
    for root in _SCAN_DIRS:
        for path in root.rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            keys.update(_COLOR_CALL_RE.findall(content))
    return keys


def test_every_color_key_exists_in_both_palettes() -> None:
    """Every ``color("name")`` reference is defined in light + dark.

    Regression for the silent-breakage failure mode: a typo or a
    new key added to only one palette renders blank in the other
    (and only the other) theme — bug surfaces only when a user
    toggles the theme.
    """
    referenced = _collect_referenced_palette_keys()
    assert referenced, "scanner regressed: zero color() calls found in src/"

    light_keys = set(_PALETTES["light"].keys())
    dark_keys = set(_PALETTES["dark"].keys())

    missing_light = sorted(referenced - light_keys)
    missing_dark = sorted(referenced - dark_keys)

    msg_lines: list[str] = []
    if missing_light:
        msg_lines.append(
            "Keys referenced via color() but missing from LIGHT palette: "
            f"{missing_light}",
        )
    if missing_dark:
        msg_lines.append(
            "Keys referenced via color() but missing from DARK palette: "
            f"{missing_dark}",
        )
    if msg_lines:
        msg_lines.append(
            "Add the missing keys to src/constants/theme.py _PALETTES "
            "so the QSS rule renders the same on both themes.",
        )
        pytest.fail("\n".join(msg_lines))


def test_light_and_dark_palettes_have_identical_key_sets() -> None:
    """The two palettes have the same key set.

    Catches the asymmetric-palette failure mode where a fork adds a
    key to one theme and forgets the other.  This is a stricter
    check than ``test_every_color_key_exists_in_both_palettes`` —
    it catches palette-only drift even when no code references the
    new key yet.
    """
    light = set(_PALETTES["light"].keys())
    dark = set(_PALETTES["dark"].keys())
    only_in_light = sorted(light - dark)
    only_in_dark = sorted(dark - light)
    msg: list[str] = []
    if only_in_light:
        msg.append(f"keys in light only: {only_in_light}")
    if only_in_dark:
        msg.append(f"keys in dark only: {only_in_dark}")
    if msg:
        pytest.fail("Light/dark palette drift: " + "; ".join(msg))
