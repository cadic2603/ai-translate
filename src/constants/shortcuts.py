"""Central registry of user-editable keyboard shortcuts.

Defines the list of customisable shortcuts, their default key sequences,
and the i18n label keys used in the Settings → Shortcuts tab.  Pages read
their current binding via :func:`get_shortcut` and subscribe to the module
level :data:`shortcuts_changed` signal to re-apply updates without a restart.

**Shared bindings.** A shortcut can opt into a ``shared_group`` — a logical
binding used by several actions that should always move together (e.g. the
"primary action" on every page is ``Ctrl+Return``).  Pages still look up
their own action ID; the registry transparently resolves it to the shared
group's stored value.  In the Shortcuts UI the shared group is represented
by a single row in the dedicated "Common" section, and individual entries
belonging to a group are hidden.

F-keys (F1..F35) are not bound by default to avoid clashing with
universal OS conventions (F1=Help, F5=Refresh, F11=Fullscreen).  The
capture UI accepts them, so a user who wants function-key bindings can
wire them through this registry with full conflict detection.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.constants._signal import CallbackSignal

# ── Groupings used as section headers in the Shortcuts tab ─────────────
GROUP_COMMON = "shortcut_group.common"
GROUP_APP = "shortcut_group.app"
GROUP_TRANSLATE_TEXT = "shortcut_group.translate_text"
GROUP_TRANSLATE_DOCUMENT = "shortcut_group.translate_document"
GROUP_SUBTITLE = "shortcut_group.subtitle"
GROUP_VOICE = "shortcut_group.voice"
GROUP_DUBBING = "shortcut_group.dubbing"
GROUP_LIVE = "shortcut_group.live"
GROUP_EXTRACT_TEXT = "shortcut_group.extract_text"
GROUP_OVERLAY = "shortcut_group.overlay"
GROUP_GLOSSARY = "shortcut_group.glossary"


@dataclass(frozen=True)
class Shortcut:
    """Metadata for a single user-editable shortcut."""

    id: str
    """Stable identifier used as the settings key and lookup token."""

    default: str
    """Default key sequence in ``QKeySequence`` portable string form."""

    label_key: str
    """i18n key for the human-readable action label."""

    group_key: str
    """i18n key for the section header this shortcut belongs to."""

    shared_group: str | None = None
    """Optional ID of a ``GROUP_COMMON`` shortcut whose binding this action
    follows.  When set, :func:`get_shortcut` / :func:`set_shortcut` resolve
    via that shared ID instead, so one override updates every member."""

    skip_on_wayland: bool = False
    """When True, the shortcut is hidden from the Shortcuts tab and not
    wired at runtime under Mutter/GNOME Wayland because the compositor
    refuses programmatic repositioning for xdg_toplevel windows.  Used
    by the ``common.overlay_move_*`` entries."""


# Source order drives display order in the Shortcuts tab.  Sections
# follow the user's mental model: app-global first, cross-cutting
# Common bindings next, page-specific groups in sidebar order, and
# the contextual Overlay shortcuts last.
SHORTCUTS: tuple[Shortcut, ...] = (
    # ── App-global ─────────────────────────────────────────────────────
    Shortcut("app.quit", "Ctrl+Q", "shortcut.app.quit", GROUP_APP),
    Shortcut("app.browse_files", "Ctrl+O", "shortcut.app.browse_files", GROUP_APP),
    # ── Common shared bindings ─────────────────────────────────────────
    # The "primary action" on every page (Translate, Generate, Start…).
    Shortcut(
        "common.primary_action",
        "Ctrl+Return",
        "shortcut.common.primary_action",
        GROUP_COMMON,
    ),
    # Focus the search input on pages that have one (history tables,
    # glossary entries).  No-op on pages without a search field.
    Shortcut(
        "common.focus_search",
        "Ctrl+F",
        "shortcut.common.focus_search",
        GROUP_COMMON,
    ),
    # App-wide cancel / dismiss key.  Page-specific cancel actions
    # (e.g. ``translate_text.cancel_edit``) opt into this binding via
    # ``shared_group`` so the user sees a single "Common" row that
    # rebinds them all at once.  Note: in-place uses inside the
    # shortcut-capture filter (Settings → Shortcuts) intentionally stay
    # hardcoded to ``Key_Escape`` — otherwise rebinding Esc would
    # leave capture mode with no way out.
    Shortcut(
        "common.cancel",
        "Esc",
        "shortcut.common.cancel",
        GROUP_COMMON,
    ),
    # Delete selected items in any history table or glossary list.
    # Wired on the main window; pages opt in by exposing an
    # ``on_delete_selected`` method.  Like ``common.cancel``, this is a
    # cross-cutting binding rather than a true app-global.
    Shortcut(
        "common.delete_selected",
        "Del",
        "shortcut.common.delete_selected",
        GROUP_COMMON,
    ),
    # Pause / continue the active process (Translate Document + Dubbing
    # history pages).  Wired on the main window; pages opt in by
    # exposing ``on_pause`` / ``on_continue`` methods.  Same dispatch
    # pattern as ``common.delete_selected`` — no-op on pages that don't
    # have a process to control.
    Shortcut(
        "common.pause",
        "Ctrl+P",
        "shortcut.common.pause",
        GROUP_COMMON,
    ),
    Shortcut(
        "common.continue",
        "Ctrl+G",
        "shortcut.common.continue",
        GROUP_COMMON,
    ),
    # ── Translate Text ─────────────────────────────────────────────────
    Shortcut(
        "translate_text.translate",
        "Ctrl+Return",
        "shortcut.translate_text.translate",
        GROUP_TRANSLATE_TEXT,
        shared_group="common.primary_action",
    ),
    Shortcut(
        "translate_text.swap_languages",
        "Ctrl+L",
        "shortcut.translate_text.swap_languages",
        GROUP_TRANSLATE_TEXT,
    ),
    Shortcut(
        "translate_text.edit",
        "Ctrl+E",
        "shortcut.translate_text.edit",
        GROUP_TRANSLATE_TEXT,
    ),
    Shortcut(
        "translate_text.save_edit",
        "Ctrl+S",
        "shortcut.translate_text.save_edit",
        GROUP_TRANSLATE_TEXT,
    ),
    Shortcut(
        "translate_text.cancel_edit",
        "Esc",
        "shortcut.translate_text.cancel_edit",
        GROUP_TRANSLATE_TEXT,
        shared_group="common.cancel",
    ),
    Shortcut(
        "translate_text.toggle_history",
        "Ctrl+H",
        "shortcut.translate_text.toggle_history",
        GROUP_TRANSLATE_TEXT,
    ),
    # ── Translate Document ─────────────────────────────────────────────
    Shortcut(
        "translate_document.translate",
        "Ctrl+Return",
        "shortcut.translate_document.translate",
        GROUP_TRANSLATE_DOCUMENT,
        shared_group="common.primary_action",
    ),
    # ── Subtitle ───────────────────────────────────────────────────────
    Shortcut(
        "subtitle.generate",
        "Ctrl+Return",
        "shortcut.subtitle.generate",
        GROUP_SUBTITLE,
        shared_group="common.primary_action",
    ),
    # ── Voice ──────────────────────────────────────────────────────────
    Shortcut(
        "voice.generate",
        "Ctrl+Return",
        "shortcut.voice.generate",
        GROUP_VOICE,
        shared_group="common.primary_action",
    ),
    # ── Dubbing ────────────────────────────────────────────────────────
    Shortcut(
        "dubbing.start",
        "Ctrl+Return",
        "shortcut.dubbing.start",
        GROUP_DUBBING,
        shared_group="common.primary_action",
    ),
    # ── Live ───────────────────────────────────────────────────────────
    Shortcut(
        "live.start_stop",
        "Ctrl+Return",
        "shortcut.live.start_stop",
        GROUP_LIVE,
        shared_group="common.primary_action",
    ),
    Shortcut(
        "live.clear_log",
        "Ctrl+K",
        "shortcut.live.clear_log",
        GROUP_LIVE,
    ),
    # ── Extract Text ───────────────────────────────────────────────────
    Shortcut(
        "extract_text.extract",
        "Ctrl+Return",
        "shortcut.extract_text.extract",
        GROUP_EXTRACT_TEXT,
        shared_group="common.primary_action",
    ),
    # ── Glossary ───────────────────────────────────────────────────────
    Shortcut(
        "glossary.new_set",
        "Ctrl+N",
        "shortcut.glossary.new_set",
        GROUP_GLOSSARY,
    ),
    Shortcut(
        "glossary.rename_set",
        "Ctrl+R",
        "shortcut.glossary.rename_set",
        GROUP_GLOSSARY,
    ),
    Shortcut(
        "glossary.focus_new_pair",
        "Ctrl+T",
        "shortcut.glossary.focus_new_pair",
        GROUP_GLOSSARY,
    ),
    Shortcut(
        "glossary.focus_search",
        "Ctrl+F",
        "shortcut.glossary.focus_search",
        GROUP_GLOSSARY,
        shared_group="common.focus_search",
    ),
    # ── Overlay (Live Translation) ─────────────────────────────────────
    # Only fire while an overlay is visible.  Move + resize keys are
    # skipped on Mutter/GNOME Wayland because the compositor refuses
    # client-requested repositioning / size changes on frameless Tool
    # windows; opacity + font-size work everywhere.
    Shortcut(
        "common.overlay_move_up",
        "Ctrl+Up",
        "shortcut.common.overlay_move_up",
        GROUP_OVERLAY,
        skip_on_wayland=True,
    ),
    Shortcut(
        "common.overlay_move_down",
        "Ctrl+Down",
        "shortcut.common.overlay_move_down",
        GROUP_OVERLAY,
        skip_on_wayland=True,
    ),
    Shortcut(
        "common.overlay_move_left",
        "Ctrl+Left",
        "shortcut.common.overlay_move_left",
        GROUP_OVERLAY,
        skip_on_wayland=True,
    ),
    Shortcut(
        "common.overlay_move_right",
        "Ctrl+Right",
        "shortcut.common.overlay_move_right",
        GROUP_OVERLAY,
        skip_on_wayland=True,
    ),
    Shortcut(
        "common.overlay_resize_grow",
        "Ctrl+0",
        "shortcut.common.overlay_resize_grow",
        GROUP_OVERLAY,
        skip_on_wayland=True,
    ),
    Shortcut(
        "common.overlay_resize_shrink",
        "Ctrl+9",
        "shortcut.common.overlay_resize_shrink",
        GROUP_OVERLAY,
        skip_on_wayland=True,
    ),
    Shortcut(
        "common.overlay_opacity_up",
        "Ctrl+]",
        "shortcut.common.overlay_opacity_up",
        GROUP_OVERLAY,
    ),
    Shortcut(
        "common.overlay_opacity_down",
        "Ctrl+[",
        "shortcut.common.overlay_opacity_down",
        GROUP_OVERLAY,
    ),
    Shortcut(
        "common.overlay_font_bigger",
        "Ctrl+=",
        "shortcut.common.overlay_font_bigger",
        GROUP_OVERLAY,
    ),
    Shortcut(
        "common.overlay_font_smaller",
        "Ctrl+-",
        "shortcut.common.overlay_font_smaller",
        GROUP_OVERLAY,
    ),
)

_BY_ID: dict[str, Shortcut] = {s.id: s for s in SHORTCUTS}


# ── Settings key prefix ────────────────────────────────────────────────

_SETTING_PREFIX = "shortcut/"


def _setting_key(shortcut_id: str) -> str:
    """Returns the ``settings.ini`` key used to persist a shortcut override."""
    return f"{_SETTING_PREFIX}{shortcut_id}"


def _resolve_storage_id(shortcut_id: str) -> str:
    """Returns the effective storage ID for reads/writes.

    If *shortcut_id* declares a ``shared_group``, that group's ID is used so
    the binding is shared across every member.  Otherwise the ID is
    returned unchanged.
    """
    shortcut = _BY_ID.get(shortcut_id)
    if shortcut is None:
        return shortcut_id
    return shortcut.shared_group or shortcut_id


# Sentinel written to settings.ini when the user has explicitly unbound
# a shortcut.  Distinguished from an empty/missing override (which means
# "use default") so a deliberately-disabled shortcut survives reads
# without falling back to the default.
UNBIND_SENTINEL = "__unbound__"


# ── Change signal ──────────────────────────────────────────────────────

shortcuts_changed = CallbackSignal()
"""Emitted after any shortcut is set, reset, or bulk-reset.

Subscribers receive no arguments and should re-read all bindings they care
about via :func:`get_shortcut`.
"""


# ── Public API ─────────────────────────────────────────────────────────


def lookup(shortcut_id: str) -> Shortcut:
    """Returns the registry entry for *shortcut_id* or raises ``KeyError``."""
    return _BY_ID[shortcut_id]


def get_default(shortcut_id: str) -> str:
    """Returns the built-in default key sequence for *shortcut_id*.

    Shared shortcuts fall back to the shared entry's default — individual
    follower defaults are ignored at read time.
    """
    storage_id = _resolve_storage_id(shortcut_id)
    return _BY_ID[storage_id].default


def get_shortcut(shortcut_id: str) -> str:
    """Returns the currently active key sequence for *shortcut_id*.

    Shared shortcuts resolve via their ``shared_group`` ID so every follower
    reads the same stored value.  Returns ``""`` when the user has
    explicitly unbound the shortcut via :func:`unbind_shortcut`; runtime
    code building ``QShortcut(QKeySequence(""), …)`` then becomes inert.
    """
    # Local import avoids a circular dependency: config_manager imports from
    # src.constants, and we live in src.constants.
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    storage_id = _resolve_storage_id(shortcut_id)
    override = load_setting(_setting_key(storage_id), "").strip()
    if override == UNBIND_SENTINEL:
        return ""
    if override:
        return override
    return _BY_ID[storage_id].default


def set_shortcut(shortcut_id: str, key_sequence: str) -> None:
    """Persists *key_sequence* as the user override for *shortcut_id*.

    For shortcuts with a ``shared_group``, the override is written against
    the group's ID — so editing any follower updates every member of the
    shared binding.  No-op when the new value matches what's already
    stored — avoids redundant ``shortcuts_changed`` emissions that would
    re-render every subscriber for nothing.
    """
    from src.utils.config_manager import load_setting, save_setting  # noqa: PLC0415

    if shortcut_id not in _BY_ID:
        raise KeyError(shortcut_id)

    storage_id = _resolve_storage_id(shortcut_id)
    stripped = key_sequence.strip()
    default = _BY_ID[storage_id].default
    # Empty / matches default → clear override (keeps settings.ini tidy);
    # the explicit unbind sentinel is preserved as-is so it survives reads.
    if stripped == UNBIND_SENTINEL:
        value = UNBIND_SENTINEL
    elif stripped in ("", default):
        value = ""
    else:
        value = stripped

    setting_key = _setting_key(storage_id)
    if load_setting(setting_key, "").strip() == value:
        return  # No change — skip the write and the signal emission.

    save_setting(setting_key, value)
    shortcuts_changed.emit()


def reset_shortcut(shortcut_id: str) -> None:
    """Clears the user override for *shortcut_id*, restoring the default."""
    set_shortcut(shortcut_id, "")


def unbind_shortcut(shortcut_id: str) -> None:
    """Marks *shortcut_id* as explicitly disabled (no key sequence).

    ``get_shortcut`` then returns ``""`` and the runtime ``QShortcut``
    becomes inert.  Different from :func:`reset_shortcut`, which restores
    the built-in default.
    """
    set_shortcut(shortcut_id, UNBIND_SENTINEL)


def reset_all_shortcuts() -> None:
    """Clears every user override, restoring each shortcut to its default."""
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    # Clear each unique storage ID exactly once — followers all alias to
    # the same key, so we'd otherwise save_setting() several times per key.
    seen: set[str] = set()
    for shortcut in SHORTCUTS:
        storage_id = shortcut.shared_group or shortcut.id
        if storage_id in seen:
            continue
        seen.add(storage_id)
        save_setting(_setting_key(storage_id), "")
    shortcuts_changed.emit()


def is_wayland_platform() -> bool:
    """Returns True when Qt is running on a Wayland compositor.

    Kept here (not in a UI module) so the registry itself can consult
    the runtime platform when deciding what to hide.  Returns False if
    ``QApplication`` hasn't been created yet, which is the safe default.
    """
    try:
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415

        name = QApplication.platformName() or ""
    except Exception:  # noqa: BLE001 - platform detection is best-effort
        return False
    return name.lower().startswith("wayland")


def is_shortcut_supported(shortcut: Shortcut) -> bool:
    """Returns True when *shortcut* is usable on the current platform.

    Wayland-incompatible entries (``skip_on_wayland=True``) are filtered
    out here, so both the Shortcuts tab and runtime wiring can share a
    single source of truth.
    """
    return not (shortcut.skip_on_wayland and is_wayland_platform())


def iter_display_shortcuts() -> tuple[Shortcut, ...]:
    """Returns the subset of shortcuts to render in the Shortcuts tab.

    Followers of a ``shared_group`` are collapsed into their group entry,
    so the UI shows one row per editable binding.  Platform-incompatible
    entries are hidden so users don't see non-functional rows.
    """
    return tuple(
        s for s in SHORTCUTS if s.shared_group is None and is_shortcut_supported(s)
    )


def find_conflicts() -> dict[str, list[str]]:
    """Returns only real collisions — ones that would actually misfire.

    A binding is reported as a conflict when either:

    * ≥2 shortcuts **in the same group** share a key sequence (same page can
      only dispatch one of them), or
    * a global (``app.*``) shortcut shares a sequence with any other
      shortcut (the global binding fires window-wide and shadows page
      bindings).

    Followers of a shared group are skipped — they by construction share a
    sequence with every other member, and that is intentional.  Shortcuts
    in *different* page groups that share a sequence (e.g. ``Ctrl+O`` on
    ``app.browse_files`` and ``live.toggle_overlay``) are compared via the
    global-vs-page rule above.
    """
    # Bucket by (group, sequence).
    by_group_seq: dict[tuple[str, str], list[str]] = {}
    app_seqs: dict[str, list[str]] = {}
    other_seqs: dict[str, list[str]] = {}

    for shortcut in SHORTCUTS:
        if shortcut.shared_group is not None:
            continue  # Followers inherit the group binding by design.
        seq = get_shortcut(shortcut.id)
        if not seq:
            continue  # Explicitly unbound — never fires, can't conflict.
        by_group_seq.setdefault((shortcut.group_key, seq), []).append(shortcut.id)
        if shortcut.group_key == GROUP_APP:
            app_seqs.setdefault(seq, []).append(shortcut.id)
        elif shortcut.group_key != GROUP_COMMON:
            other_seqs.setdefault(seq, []).append(shortcut.id)

    result: dict[str, list[str]] = {}
    for (_group, seq), ids in by_group_seq.items():
        if len(ids) >= 2:  # noqa: PLR2004
            result.setdefault(seq, []).extend(ids)
    for seq in set(app_seqs) & set(other_seqs):
        combined = app_seqs[seq] + other_seqs[seq]
        seen: set[str] = set()
        for sid in combined:
            if sid not in seen:
                result.setdefault(seq, []).append(sid)
                seen.add(sid)
    return result
