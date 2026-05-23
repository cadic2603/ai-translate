"""Static coverage check: every raised error tag must be displayable.

When the production code raises ``ValueError("SOME_TAG")`` /
``RuntimeError("SOME_TAG")``, the UI surfaces the tag through
:func:`src.constants.errors.display_error_message`.  If the tag isn't
in ``_TAG_TO_CODE`` OR ``_TAG_TO_TR_KEY``, the user sees the raw
English tag (``"AUTH_ERROR"``) instead of a localised message.

This test scans ``src/core/`` + ``src/ui/`` for every raised
all-uppercase-with-underscores string sentinel and asserts each maps
through ``display_error_message`` to a friendly string.  A single
failure indicates a missing entry in ``src/constants/errors.py`` —
add the tag to ``_TAG_TO_CODE`` (with an ``ERR_*`` constant) or
``_TAG_TO_TR_KEY`` (with an ``error_msg.*`` translation key).

The scan is intentionally regex-based — we don't import the modules
because doing so would trigger their heavy-import chains (PyMuPDF,
genai SDK, etc.).  This is a fast, side-effect-free check that runs
in milliseconds.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.constants.errors import (
    _TAG_TO_CODE,
    _TAG_TO_TR_KEY,
    ERR_UNKNOWN,
    display_error_message,
    map_tag_to_code,
)

_SRC_ROOT = Path(__file__).parent.parent / "src"
_SCAN_DIRS = (_SRC_ROOT / "core", _SRC_ROOT / "ui")

# Match raise ValueError("ALL_CAPS_TAG") or raise RuntimeError("...").
# Whitespace before / inside the parens is tolerated; the tag has to be
# all uppercase letters / digits / underscores so log messages like
# ``raise ValueError("Bad input")`` aren't false-positives.
_RAISE_TAG_RE = re.compile(
    r"""raise\s+(?:Value|Runtime)Error\(\s*['"]([A-Z][A-Z0-9_]+)['"]\s*[),]""",
)


def _collect_tags() -> set[str]:
    """Scans ``src/core`` and ``src/ui`` for raised error tags."""
    tags: set[str] = set()
    for root in _SCAN_DIRS:
        for path in root.rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            tags.update(_RAISE_TAG_RE.findall(content))
    return tags


# Tags raised by the production code but intentionally NOT mapped to a
# friendly message — these are sentinels consumed by internal callers
# and never surface in the UI (the call site catches and re-raises a
# different tag, or the value is structural rather than user-facing).
#
# Add a tag here with a one-line justification rather than silently
# masking the coverage failure.  Empty for now.
_INTERNAL_ONLY_TAGS: frozenset[str] = frozenset({
    # STT_UNKNOWN is a fall-through for unrecognised Soniox exceptions
    # and IS mapped in _TAG_TO_TR_KEY — listed here for completeness.
})


def test_every_raised_tag_is_displayable() -> None:
    """Every ``raise (Value|Runtime)Error("TAG")`` sentinel maps to UI copy.

    Prevents the failure mode where a new engine adds
    ``raise ValueError("FOO_BAR")`` but forgets the
    ``_TAG_TO_CODE`` / ``_TAG_TO_TR_KEY`` entry, causing the UI to
    display the raw English tag (``"FOO_BAR"``) to the user.
    """
    raised_tags = _collect_tags() - _INTERNAL_ONLY_TAGS
    assert raised_tags, "scanner regressed: zero tags found in src/"

    missing: list[str] = []
    for tag in sorted(raised_tags):
        in_code = tag in _TAG_TO_CODE
        in_tr_key = tag in _TAG_TO_TR_KEY
        if not (in_code or in_tr_key):
            missing.append(tag)

    if missing:
        pytest.fail(
            "These error tags are raised in src/ but have no entry in "
            "src/constants/errors.py — the UI would show the raw "
            "English tag to the user instead of a localised message. "
            "Add each tag to _TAG_TO_CODE (with a numeric ERR_* code) "
            "or _TAG_TO_TR_KEY (with a code-less translation key):\n  "
            + "\n  ".join(missing),
        )


def test_known_tags_round_trip_through_display() -> None:
    """Every tag in the mapping dicts produces a non-tag display string.

    Catches the reverse failure: a tag IS mapped but its translation
    key is missing or the localised text is the tag itself.
    """
    for tag in (*_TAG_TO_CODE, *_TAG_TO_TR_KEY):
        msg = display_error_message(tag)
        # Tag should resolve to localised user-facing copy, not echo
        # the raw tag back.  The localised text in en-US is always
        # different from the tag (lowercase, sentence-cased, etc.).
        assert msg, f"display_error_message({tag!r}) returned empty"
        # An exact echo of the tag means the lookup fell through.
        assert msg != tag, (
            f"display_error_message({tag!r}) returned the raw tag — "
            f"the localised translation key is probably missing"
        )


def test_unknown_tag_maps_to_err_unknown() -> None:
    """A tag with no mapping must fall through to ERR_UNKNOWN, not crash."""
    # Using a deliberately-bogus tag here exercises the warning-log
    # fallback in ``map_tag_to_code``.
    assert map_tag_to_code("NOT_A_REAL_TAG_99") == ERR_UNKNOWN
