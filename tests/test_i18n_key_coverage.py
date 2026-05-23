"""Static coverage check: every ``tr("key")`` in src/ has a translation.

The app's i18n engine in :mod:`src.constants.i18n` silently falls back
to the raw key string when a translation is missing — so a typo or a
new code call that forgot to add the locale entry surfaces only when
the affected UI string is shown to a user.  This scanner catches the
mismatch at test time.

The check is **regex-based** on purpose: we don't import the modules
(doing so would trigger their heavy import chains — PyMuPDF, genai
SDK, etc.).  Fast, side-effect-free, runs in milliseconds.

If a key intentionally has no static i18n entry (built up at runtime
from a settings key prefix, etc.), add it to ``_RUNTIME_KEYS`` below
with a one-line justification.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).parent.parent / "src"
_EN_US = _SRC_ROOT / "constants" / "translations" / "en-US.json"
_SCAN_DIRS = (_SRC_ROOT / "ui", _SRC_ROOT / "core", _SRC_ROOT / "constants")

# Match ``tr("key")`` / ``tr('key')`` with optional kwargs.  Restrict
# the key to the project's namespace style (``area.sub_name`` —
# lowercase letters / digits / dots / underscores) so log-message
# false-positives like ``tr("some debug text")`` don't get scooped.
# The dot is required because every real key is namespaced.  The
# ``(?<![A-Za-z_])`` look-behind keeps the scanner from matching
# the ``tr`` substring inside method names like ``writestr(...)``.
_TR_CALL_RE = re.compile(
    r"""(?<![A-Za-z_])tr\(\s*['"]([a-z][a-z0-9_.]*\.[a-z0-9_.]+)['"]""",
)

# Match ``_bind_text(widget, "key")`` — the language-binding helper
# used in settings + components.  Same key shape as ``tr``.
_BIND_TEXT_RE = re.compile(
    r"""_bind_text\(\s*\w+\s*,\s*['"]([a-z][a-z0-9_.]*\.[a-z0-9_.]+)['"]""",
)

# Match ``tr_key="some.key"`` — the kwargs pattern used by
# create_setting_*, create_banner, etc.
_TR_KEY_KWARG_RE = re.compile(
    r"""tr_key\s*=\s*['"]([a-z][a-z0-9_.]*\.[a-z0-9_.]+)['"]""",
)

# Match ``setProperty("action_label_key", "some.key")`` /
# ``setProperty("tr_key", "...")`` — language-refresh hooks that
# rebuild the visible text by looking up the stored key.
_SET_PROPERTY_RE = re.compile(
    r"""setProperty\(\s*['"](?:action_label_key|tr_key)['"]\s*,"""
    r"""\s*['"]([a-z][a-z0-9_.]*\.[a-z0-9_.]+)['"]""",
)

# Match the per-file ``key = "literal" ... tr(key)`` pattern.  Without
# this scan, a contributor who assigns the key to a local variable
# before calling ``tr(key)`` hides it from the static checker — exactly
# how the ``settings.ocr_tesseract_install_*`` keys went undetected.
# Two-pass: first collect all ``var = "namespaced.key"`` candidates,
# then keep only those whose name is used as the FIRST arg to ``tr(...)``
# in the same file.
_KEY_LITERAL_ASSIGN_RE = re.compile(
    r'\b(\w+)\s*=\s*["\']([a-z][a-z0-9_.]*\.[a-z0-9_.]+)["\']',
)


def _collect_indirect_tr_keys(content: str) -> set[str]:
    """Returns keys referenced via ``tr(var)`` where ``var = "literal"``."""
    candidates: dict[str, str] = {}
    for m in _KEY_LITERAL_ASSIGN_RE.finditer(content):
        candidates[m.group(1)] = m.group(2)
    used: set[str] = set()
    for var_name, key_value in candidates.items():
        # Match ``tr(var_name)`` / ``tr(var_name, …)``.  Word boundary
        # prevents ``tr(var_namespace)`` from matching ``var_name``.
        if re.search(rf"\btr\(\s*{re.escape(var_name)}\s*[,)]", content):
            used.add(key_value)
    return used


# Keys constructed at runtime (string-formatted from a prefix and a
# variable) — they look like ``f"area.{value}"`` so the static
# regex can't see them.  List the full set of statically-known
# combinations here so the scanner doesn't false-positive.
_RUNTIME_KEYS: frozenset[str] = frozenset(
    {
        # Built by live.py / settings: f"live.btn_{action}_{state}"
        # already covered as static literals via _bind_text on the actual
        # button widgets, so no entry needed here for now.
    }
)


def _collect_referenced_keys() -> set[str]:
    """Scans the source tree for every static i18n key reference."""
    keys: set[str] = set()
    patterns = (
        _TR_CALL_RE,
        _BIND_TEXT_RE,
        _TR_KEY_KWARG_RE,
        _SET_PROPERTY_RE,
    )
    for root in _SCAN_DIRS:
        for path in root.rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            for pat in patterns:
                keys.update(pat.findall(content))
            # Indirect ``tr(var)`` references — scanned per-file so
            # the variable-name lookup stays scoped to its own module.
            keys.update(_collect_indirect_tr_keys(content))
    return keys - _RUNTIME_KEYS


def _load_en_us_keys() -> set[str]:
    with _EN_US.open(encoding="utf-8") as f:
        return set(json.load(f).keys())


def test_no_orphan_tr_keys() -> None:
    """Every ``tr("key")`` referenced in src/ has an entry in en-US.json.

    Regression for the silent-fallback failure mode: when ``tr()``
    can't find the key, it returns the raw key string itself
    (``"settings.live_show_speaker"`` instead of "Speaker labels:")
    so users see the namespaced identifier in the UI.  No exception
    is raised, no log entry, no test coverage — exactly the bug
    profile that hides in a codebase until a user reports it.
    """
    referenced = _collect_referenced_keys()
    assert referenced, "scanner regressed: zero tr() keys found in src/"

    available = _load_en_us_keys()
    orphans = sorted(referenced - available)

    if orphans:
        pytest.fail(
            "These i18n keys are referenced in src/ but missing from "
            "src/constants/translations/en-US.json — the UI would "
            "show the raw key string ('settings.foo') instead of "
            "the localised text.  Add an entry for each key, then "
            "propagate it to the other 19 locale files:\n  " + "\n  ".join(orphans),
        )


def test_install_hint_linux_keys_carry_placeholder() -> None:
    """Every ``*_linux`` install-hint key must include ``{linux_install}``.

    The Linux variant of each per-OS install-hint banner uses a
    runtime-substituted placeholder so the auto-detected
    ``sudo apt-get install …`` (or dnf / pacman / zypper / apk)
    command is inlined into the banner.  Code path:

        tr("settings.ffmpeg_install_linux",
           linux_install=format_install_clause(get_ffmpeg_install_hint()))

    If a translator drops the ``{linux_install}`` placeholder by
    accident, the format() call is a no-op and the user sees the
    base sentence with NO install command — defeating the whole
    point of the auto-detection.

    This scanner pins the contract across all 20 locales for every
    key matching ``*_linux`` whose en-US value carries the
    placeholder (the authoritative set).
    """
    en_us = json.loads(_EN_US.read_text(encoding="utf-8"))
    keys_requiring_placeholder = {
        k for k, v in en_us.items() if k.endswith("_linux") and "{linux_install}" in v
    }
    assert keys_requiring_placeholder, (
        "test regressed: no en-US _linux keys carry {linux_install} — "
        "either the install-hint feature was removed or the scan logic "
        "is broken."
    )

    translations_dir = _SRC_ROOT / "constants" / "translations"
    failures: list[str] = []
    for path in translations_dir.glob("*.json"):
        if path.stem == "en-US":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in keys_requiring_placeholder:
            value = data.get(key)
            if value is None:
                # Missing-key drift is caught by the sibling locale
                # parity test; don't double-report here.
                continue
            if "{linux_install}" not in value:
                failures.append(f"  {path.stem}.{key} (current: {value[:60]!r})")

    if failures:
        pytest.fail(
            "These Linux install-hint translations dropped the "
            "{linux_install} placeholder.  Without it, the runtime "
            "substitution that inlines the distro-specific install "
            "command (apt-get / dnf / pacman / ...) is a no-op and "
            "users see the bare sentence with no actionable command:\n"
            + "\n".join(failures),
        )


def test_all_locales_have_same_keys_as_en_us() -> None:
    """Every locale file has the same key set as en-US.json.

    en-US is the source of truth.  If a translator forgets to add a
    new key when the english copy gets one, the UI silently falls
    back to the raw key in their locale.  This scan is the regression
    guard — it catches drift the moment a new key is added in en-US
    without the locale files being updated.
    """
    en_us_keys = _load_en_us_keys()
    translations_dir = _SRC_ROOT / "constants" / "translations"

    drift: dict[str, dict[str, list[str]]] = {}
    for path in translations_dir.glob("*.json"):
        if path.stem == "en-US":
            continue
        with path.open(encoding="utf-8") as f:
            locale_keys = set(json.load(f).keys())
        missing = sorted(en_us_keys - locale_keys)
        extra = sorted(locale_keys - en_us_keys)
        if missing or extra:
            drift[path.stem] = {"missing": missing, "extra": extra}

    if drift:
        msg_lines = ["Locale key drift from en-US:"]
        for locale, diff in drift.items():
            if diff["missing"]:
                msg_lines.append(
                    f"  {locale}: missing {len(diff['missing'])} key(s): "
                    f"{diff['missing'][:5]}{'...' if len(diff['missing']) > 5 else ''}",
                )
            if diff["extra"]:
                msg_lines.append(
                    f"  {locale}: orphan (not in en-US) {len(diff['extra'])}: "
                    f"{diff['extra'][:5]}{'...' if len(diff['extra']) > 5 else ''}",
                )
        pytest.fail("\n".join(msg_lines))
