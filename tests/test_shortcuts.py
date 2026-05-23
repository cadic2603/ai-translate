"""Tests for the central shortcut registry and the Shortcuts settings tab."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow

from src.constants.shortcuts import (
    GROUP_APP,
    GROUP_COMMON,
    GROUP_LIVE,
    GROUP_OVERLAY,
    SHORTCUTS,
    UNBIND_SENTINEL,
    Shortcut,
    find_conflicts,
    get_default,
    get_shortcut,
    is_shortcut_supported,
    is_wayland_platform,
    iter_display_shortcuts,
    lookup,
    reset_all_shortcuts,
    reset_shortcut,
    set_shortcut,
    shortcuts_changed,
    unbind_shortcut,
)


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Wipes any user overrides so each test starts from defaults."""
    reset_all_shortcuts()
    yield
    reset_all_shortcuts()


class TestRegistry:
    """Core registry behaviour — default/override/reset/conflict detection."""

    def test_registry_has_expected_shortcuts(self) -> None:
        """At least the known shortcut IDs are present in the registry."""
        ids = {s.id for s in SHORTCUTS}
        expected = {
            "app.quit",
            "translate_text.translate",
            "translate_text.swap_languages",
            "translate_text.cancel_edit",
            "subtitle.generate",
            "voice.generate",
            "dubbing.start",
            "live.start_stop",
            "live.clear_log",
            "glossary.new_set",
            "glossary.focus_search",
        }
        assert expected.issubset(ids)

    def test_get_shortcut_returns_default_without_override(self) -> None:
        """With no override stored, get_shortcut returns the registry default."""
        for shortcut in SHORTCUTS:
            assert get_shortcut(shortcut.id) == shortcut.default

    def test_set_shortcut_persists_override(self) -> None:
        """set_shortcut writes through to settings and is read back by get_shortcut."""
        set_shortcut("translate_text.translate", "Ctrl+Shift+T")
        assert get_shortcut("translate_text.translate") == "Ctrl+Shift+T"

    def test_set_shortcut_equal_to_default_clears_override(self) -> None:
        """Assigning the default is stored as an empty override (keeps ini tidy)."""
        set_shortcut("translate_text.translate", "Ctrl+Shift+T")
        # Re-assign the default — override should be cleared.
        set_shortcut(
            "translate_text.translate",
            get_default("translate_text.translate"),
        )
        assert get_shortcut("translate_text.translate") == get_default(
            "translate_text.translate",
        )

    def test_reset_shortcut_restores_default(self) -> None:
        """reset_shortcut drops the override."""
        set_shortcut("translate_text.translate", "Ctrl+Shift+T")
        reset_shortcut("translate_text.translate")
        assert get_shortcut("translate_text.translate") == get_default(
            "translate_text.translate",
        )

    def test_reset_all_shortcuts_clears_every_override(self) -> None:
        """reset_all_shortcuts restores all bindings to their defaults."""
        set_shortcut("translate_text.translate", "Ctrl+Shift+T")
        set_shortcut("live.clear_log", "Ctrl+Shift+K")
        reset_all_shortcuts()
        for shortcut in SHORTCUTS:
            assert get_shortcut(shortcut.id) == shortcut.default

    def test_section_order_app_common_pages_overlay(self) -> None:
        """Displayed sections appear in source order: App → Common → pages → Overlay.

        The Shortcuts table renders rows in declaration order (no sort),
        so the registry's group sequence is what the user sees.  Pages
        whose only entry is a follower (Translate Document, Subtitle,
        Voice, Dubbing, Extract Text — all shadow ``common.primary_action``)
        have no displayed rows and so don't appear as sections in the
        table; ``iter_display_shortcuts`` filters them out.
        """
        from src.constants.shortcuts import iter_display_shortcuts

        seen_groups: list[str] = []
        for s in iter_display_shortcuts():
            if not seen_groups or seen_groups[-1] != s.group_key:
                seen_groups.append(s.group_key)

        expected = [
            GROUP_APP,
            GROUP_COMMON,
            "shortcut_group.translate_text",
            GROUP_LIVE,
            "shortcut_group.glossary",
            GROUP_OVERLAY,
        ]
        assert seen_groups == expected, (
            f"Section order changed.\n"
            f"  expected: {expected}\n"
            f"  actual:   {seen_groups}"
        )

    def test_overlay_shortcuts_grouped_separately(self) -> None:
        """All overlay shortcuts live in their own group, not in Common or Live.

        Lifting them into GROUP_OVERLAY is what makes them appear as a
        sequential block in the Shortcuts table — the table sorts by
        ``Group · Action`` so same-group entries naturally cluster.
        """
        overlay_ids = {s.id for s in SHORTCUTS if s.group_key == GROUP_OVERLAY}
        # 4 move + 2 resize + 2 opacity + 2 font = 10.
        expected = {
            "common.overlay_move_up",
            "common.overlay_move_down",
            "common.overlay_move_left",
            "common.overlay_move_right",
            "common.overlay_resize_grow",
            "common.overlay_resize_shrink",
            "common.overlay_opacity_up",
            "common.overlay_opacity_down",
            "common.overlay_font_bigger",
            "common.overlay_font_smaller",
        }
        assert overlay_ids == expected, (
            f"GROUP_OVERLAY contents mismatch.\n"
            f"  expected: {sorted(expected)}\n"
            f"  actual:   {sorted(overlay_ids)}"
        )
        # Common must not carry any overlay-prefixed action.
        common_overlay_leak = [
            s.id
            for s in SHORTCUTS
            if s.group_key == GROUP_COMMON and s.id.startswith("common.overlay_")
        ]
        assert common_overlay_leak == [], (
            f"overlay shortcuts leaked into GROUP_COMMON: {common_overlay_leak}"
        )
        # Live must not carry any overlay font-size action either.
        live_overlay_leak = [
            s.id
            for s in SHORTCUTS
            if s.group_key == GROUP_LIVE and "overlay_font" in s.id
        ]
        assert live_overlay_leak == [], (
            f"overlay font shortcuts leaked into GROUP_LIVE: {live_overlay_leak}"
        )

    def test_translate_text_cancel_edit_resolves_via_common_cancel(self) -> None:
        """``translate_text.cancel_edit`` follows the ``common.cancel`` group.

        Rebinding ``common.cancel`` must propagate to every member of
        the shared group so the user-visible "Cancel / dismiss" row
        rebinds them all at once (matches the existing
        ``common.primary_action`` pattern used by the per-page
        primary-action shortcuts).
        """
        original = get_shortcut("common.cancel")
        try:
            assert get_shortcut("translate_text.cancel_edit") == original
            set_shortcut("common.cancel", "Ctrl+.")
            assert get_shortcut("translate_text.cancel_edit") == "Ctrl+."
            assert get_shortcut("common.cancel") == "Ctrl+."
        finally:
            set_shortcut("common.cancel", original)

    def test_set_shortcut_emits_changed_signal(self) -> None:
        """shortcuts_changed fires so pages can re-bind live."""
        cb = MagicMock()
        shortcuts_changed.connect(cb)
        try:
            set_shortcut("translate_text.translate", "Ctrl+Shift+T")
            assert cb.called
        finally:
            shortcuts_changed.disconnect(cb)

    def test_find_conflicts_flags_same_group_duplicates(self) -> None:
        """Two non-follower shortcuts in the same group colliding is flagged."""
        # Force a same-group collision within "glossary" between two non-followers.
        set_shortcut("glossary.new_set", "Ctrl+L")
        set_shortcut("glossary.focus_new_pair", "Ctrl+L")
        conflicts = find_conflicts()
        assert "Ctrl+L" in conflicts
        assert "glossary.new_set" in conflicts["Ctrl+L"]
        assert "glossary.focus_new_pair" in conflicts["Ctrl+L"]

    def test_find_conflicts_flags_global_vs_page(self) -> None:
        """A global (app.*) binding colliding with any page binding is flagged."""
        # Force a global/page collision: rebind glossary.new_set to match
        # app.browse_files (defaults to Ctrl+O).
        set_shortcut("glossary.new_set", "Ctrl+O")
        conflicts = find_conflicts()
        assert "Ctrl+O" in conflicts
        assert "app.browse_files" in conflicts["Ctrl+O"]
        assert "glossary.new_set" in conflicts["Ctrl+O"]

    def test_find_conflicts_ignores_cross_page_duplicates(self) -> None:
        """Page-scoped shortcuts in different groups don't collide at runtime."""
        # Defaults: Ctrl+Return is the primary action on 5 different pages,
        # which is by design — only one page is active at a time.
        conflicts = find_conflicts()
        ids_for_return = conflicts.get("Ctrl+Return", [])
        # No entries because every Ctrl+Return binding is in a different
        # page group and none is app.*.
        assert ids_for_return == []

    def test_find_conflicts_skips_unbound_shortcuts(self) -> None:
        """Unbound shortcuts (sequence == "") never appear in conflicts.

        Regression: two shortcuts the user explicitly unbound used to
        bucket together on the empty key and surface as a fake conflict
        in the warning banner.
        """
        # Unbind two non-follower shortcuts in the same group.
        unbind_shortcut("glossary.new_set")
        unbind_shortcut("glossary.focus_new_pair")

        conflicts = find_conflicts()
        # Empty key must NOT appear; neither shortcut should be flagged.
        assert "" not in conflicts
        flat = {sid for ids in conflicts.values() for sid in ids}
        assert "glossary.new_set" not in flat
        assert "glossary.focus_new_pair" not in flat

    def test_lookup_unknown_raises(self) -> None:
        """Lookup raises KeyError for unknown IDs."""
        with pytest.raises(KeyError):
            lookup("does.not.exist")


class TestLivePageRebind:
    """End-to-end: set_shortcut should rebind live QShortcut instances."""

    @pytest.fixture
    def translate_text_page(self, qapp: QApplication):
        from src.ui.pages.translate_text import TranslateTextPage

        window = QMainWindow()
        with patch(
            "src.ui.pages.translate_text.check_llm_setup",
            return_value=True,
        ):
            page = TranslateTextPage(window)
        window.setCentralWidget(page)
        yield page
        page.deleteLater()
        window.deleteLater()
        qapp.processEvents()

    def test_rebinding_translate_shortcut_updates_page(
        self,
        translate_text_page,
    ) -> None:
        """Changing the setting updates the page's QShortcut.key() immediately."""
        before = translate_text_page._translate_shortcut.key().toString(
            QKeySequence.SequenceFormat.PortableText,
        )
        assert before == "Ctrl+Return"

        set_shortcut("translate_text.translate", "Ctrl+Shift+T")
        after = translate_text_page._translate_shortcut.key().toString(
            QKeySequence.SequenceFormat.PortableText,
        )
        assert after == "Ctrl+Shift+T"

    def test_reset_restores_page_binding(self, translate_text_page) -> None:
        """Reset propagates back to the page instance."""
        set_shortcut("translate_text.translate", "Ctrl+Shift+T")
        reset_shortcut("translate_text.translate")
        final = translate_text_page._translate_shortcut.key().toString(
            QKeySequence.SequenceFormat.PortableText,
        )
        assert final == get_default("translate_text.translate")


class TestShortcutsSettingsTab:
    """UI rendering / interaction on the Shortcuts tab."""

    @pytest.fixture
    def tab(self, qapp: QApplication):
        from src.ui.pages.settings import create_shortcuts_settings

        widget = create_shortcuts_settings()
        yield widget
        widget.deleteLater()
        qapp.processEvents()

    def test_tab_renders_without_error(self, tab) -> None:
        """The factory produces a widget with the expected refresh hook."""
        assert hasattr(tab, "_refresh_shortcuts")
        assert callable(tab._refresh_shortcuts)

    def test_refresh_hook_syncs_edits_from_registry(self, tab) -> None:
        """External set_shortcut updates the table cell via shortcuts_changed."""
        from PySide6.QtCore import Qt

        table = tab._shortcut_table
        assert table.rowCount() > 0, "expected table to be populated"

        # translate_text.swap_languages is a stand-alone (non-follower)
        # shortcut that always appears in the table. Mutating via
        # set_shortcut should propagate automatically through
        # shortcuts_changed — no need to explicitly call _refresh_shortcuts.
        set_shortcut("translate_text.swap_languages", "Ctrl+Alt+L")

        target_row = None
        for r in range(table.rowCount()):
            item = table.item(r, 0)
            if (
                item
                and item.data(Qt.ItemDataRole.UserRole)
                == "translate_text.swap_languages"
            ):
                target_row = r
                break
        assert target_row is not None, "row for swap_languages not found"

        seq_item = table.item(target_row, 0)
        assert seq_item.text() == "Ctrl+Alt+L"

    def test_capture_rejects_bare_letter(self, tab) -> None:
        """Pressing a bare letter on a selected row must NOT bind it."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        table = tab._shortcut_table
        # Select the first row.
        target_sid = table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        table.selectRow(0)
        original = get_shortcut(target_sid)

        # Press bare 'A' (no modifiers).
        evt = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.NoModifier,
        )
        consumed = tab._shortcut_capture_filter.eventFilter(table, evt)

        assert consumed is False
        assert get_shortcut(target_sid) == original

    def test_capture_accepts_function_key_without_modifier(self, tab) -> None:
        """F1 alone is a valid bare-key shortcut and binds successfully."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        table = tab._shortcut_table
        target_sid = table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        table.selectRow(0)

        evt = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_F1,
            Qt.KeyboardModifier.NoModifier,
        )
        consumed = tab._shortcut_capture_filter.eventFilter(table, evt)

        assert consumed is True
        assert get_shortcut(target_sid) == "F1"

    def test_capture_accepts_modifier_combination(self, tab) -> None:
        """Ctrl+B captures and binds correctly."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        table = tab._shortcut_table
        target_sid = table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        table.selectRow(0)

        evt = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_B,
            Qt.KeyboardModifier.ControlModifier,
        )
        consumed = tab._shortcut_capture_filter.eventFilter(table, evt)

        assert consumed is True
        assert get_shortcut(target_sid) == "Ctrl+B"

    def test_capture_escape_clears_selection_without_binding(self, tab) -> None:
        """Esc cancels capture mode — no write to the registry."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        table = tab._shortcut_table
        target_sid = table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        table.selectRow(0)
        original = get_shortcut(target_sid)

        evt = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        consumed = tab._shortcut_capture_filter.eventFilter(table, evt)

        assert consumed is True
        assert get_shortcut(target_sid) == original
        # Selection should be cleared.
        assert not table.selectionModel().selectedRows()

    def test_capture_delete_unbinds_shortcut(self, tab) -> None:
        """Delete on a selected row unbinds the shortcut entirely."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        table = tab._shortcut_table
        target_sid = table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        table.selectRow(0)
        assert get_shortcut(target_sid) != ""

        evt = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Delete,
            Qt.KeyboardModifier.NoModifier,
        )
        consumed = tab._shortcut_capture_filter.eventFilter(table, evt)

        assert consumed is True
        assert get_shortcut(target_sid) == ""

    def test_conflict_banner_appears_when_two_actions_collide(
        self, tab
    ) -> None:
        """Assigning the same sequence to two same-group actions shows the banner."""
        # Find two non-follower shortcuts in the same group.
        from src.constants.shortcuts import iter_display_shortcuts

        by_group: dict[str, list] = {}
        for s in iter_display_shortcuts():
            by_group.setdefault(s.group_key, []).append(s)
        pair = next(
            (group for group in by_group.values() if len(group) >= 2),  # noqa: PLR2004
            None,
        )
        if pair is None:
            pytest.skip("registry has no group with two collidable shortcuts")

        a, b = pair[0], pair[1]
        set_shortcut(a.id, "Ctrl+Shift+Alt+F10")
        set_shortcut(b.id, "Ctrl+Shift+Alt+F10")  # Conflict!

        # Use isHidden() which reflects explicit setVisible state regardless
        # of parent show/hide (the test never shows the tab).
        from PySide6.QtWidgets import QFrame

        banners = [c for c in tab.findChildren(QFrame) if c.objectName() == "Banner"]
        assert any(not b.isHidden() for b in banners), (
            "expected conflict banner to be shown after introducing a collision"
        )

    def test_no_conflict_banner_when_bindings_unique(self, tab) -> None:
        """With only default bindings the conflict banner stays hidden."""
        from PySide6.QtWidgets import QFrame

        banners = [c for c in tab.findChildren(QFrame) if c.objectName() == "Banner"]
        for banner in banners:
            assert banner.isHidden()

    def test_capture_hint_visible_only_during_row_selection(self, tab) -> None:
        """Hint label is hidden until a row is selected, then shown."""
        from PySide6.QtWidgets import QLabel

        table = tab._shortcut_table
        # Find the capture-mode hint by its style sheet — there's exactly one
        # QLabel in the tab whose stylesheet sets ``font-size: 12px``.  Use
        # ``isHidden()`` rather than ``isVisible()`` because the tab itself
        # is never ``show()``-n in tests (offscreen + parent-hidden), so
        # ``isVisible()`` would always return False regardless of state.
        hint_candidates = [
            label
            for label in tab.findChildren(QLabel)
            if "font-size: 12px" in (label.styleSheet() or "")
        ]
        assert len(hint_candidates) == 1, "expected exactly one capture-hint label"
        hint_label = hint_candidates[0]
        assert hint_label.isHidden(), "hint must start hidden"

        table.selectRow(0)
        assert not hint_label.isHidden(), "hint must appear when a row is selected"

        table.clearSelection()
        assert hint_label.isHidden(), "hint must hide when selection cleared"

    def test_reset_all_button_wipes_overrides(self, tab, monkeypatch) -> None:
        """Clicking "Reset all" (after confirm) clears every per-action override.

        Surfaces the previously-orphaned ``reset_all_shortcuts()``
        registry function via a footer button, gated by the existing
        confirm dialog.
        """
        from PySide6.QtWidgets import QPushButton

        # Seed two per-action overrides we expect to be wiped.
        sid_a = "translate_text.swap_languages"
        sid_b = "app.browse_files"
        original_a = get_shortcut(sid_a)
        original_b = get_shortcut(sid_b)
        set_shortcut(sid_a, "Ctrl+Alt+Shift+L")
        set_shortcut(sid_b, "Ctrl+Alt+Shift+O")
        assert get_shortcut(sid_a) == "Ctrl+Alt+Shift+L"
        assert get_shortcut(sid_b) == "Ctrl+Alt+Shift+O"

        # Stub the confirm dialog to "yes".
        monkeypatch.setattr(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            staticmethod(lambda *args, **kwargs: True),
        )

        # Find the Reset all button (the only QPushButton on the tab
        # itself; per-row Reset buttons live inside table cells).
        reset_buttons = [
            b
            for b in tab.findChildren(QPushButton)
            if b.parentWidget() is tab
        ]
        assert len(reset_buttons) == 1, "expected exactly one Reset all button"
        reset_buttons[0].click()

        assert get_shortcut(sid_a) == original_a
        assert get_shortcut(sid_b) == original_b

    def test_per_row_reset_button_fits_text(self, tab) -> None:
        """Each row's inline Reset button must be sized to render its text.

        The base secondary-button style uses 10px+10px padding and a
        14px font, so a too-small ``setFixedSize`` would clip the text
        and leave an empty pill in the column.  The override drops
        padding to 4px+12px and font-size to 12px so the button fits
        in a compact table row.

        Verified against the actual user-visible text ("Reset" in
        en-US, "Đặt lại" in vi) rather than ``btn.text()`` because the
        test environment may have translations cleared and would
        otherwise check against the long raw tr-key fallback.
        """
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtWidgets import QPushButton

        table = tab._shortcut_table
        btn = table.cellWidget(0, 2)
        assert isinstance(btn, QPushButton), "expected a QPushButton in column 2"

        # Worst-case localised text the button must render.
        worst_case_text = "Đặt lại"
        fm = QFontMetrics(btn.font())
        text_w = fm.horizontalAdvance(worst_case_text)
        text_h = fm.height()
        actual = btn.size()
        assert actual.height() >= text_h, (
            f"Reset button height {actual.height()}px clips {text_h}px text"
        )
        assert actual.width() >= text_w, (
            f"Reset button width {actual.width()}px clips "
            f"{text_w}px ('{worst_case_text}')"
        )

    def test_reset_all_button_keeps_natural_width(self, tab) -> None:
        """The button must not balloon full-width when the hint is hidden.

        The hint and the button share a single horizontal row.  When
        the hint is visible it claims the row's stretch; when it
        disappears the button must stay at its natural sizeHint width
        rather than absorbing the freed space.
        """
        from PySide6.QtWidgets import QPushButton

        tab.resize(1200, 600)

        buttons = [
            b for b in tab.findChildren(QPushButton) if b.parentWidget() is tab
        ]
        assert len(buttons) == 1
        btn = buttons[0]
        natural = btn.sizeHint().width()

        # Hint hidden by default — button must stay near natural width,
        # not stretch to fill the 1200px row.
        tab.show()
        QApplication.processEvents()
        assert btn.width() <= natural + 50, (
            f"button ballooned to {btn.width()}px when hint was hidden "
            f"(natural width {natural}px)"
        )

        # Same after the hint appears.
        tab._shortcut_table.selectRow(0)
        QApplication.processEvents()
        assert btn.width() <= natural + 50, (
            f"button ballooned to {btn.width()}px when hint was visible "
            f"(natural width {natural}px)"
        )

    def test_reset_all_button_cancel_keeps_overrides(
        self, tab, monkeypatch,
    ) -> None:
        """Cancelling the confirm dialog leaves the overrides intact."""
        from PySide6.QtWidgets import QPushButton

        sid = "translate_text.swap_languages"
        set_shortcut(sid, "Ctrl+Alt+Shift+L")

        monkeypatch.setattr(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            staticmethod(lambda *args, **kwargs: False),
        )

        reset_buttons = [
            b
            for b in tab.findChildren(QPushButton)
            if b.parentWidget() is tab
        ]
        reset_buttons[0].click()

        assert get_shortcut(sid) == "Ctrl+Alt+Shift+L"

    def test_display_substitutes_del_to_delete(self, tab) -> None:
        """The ``Del`` key renders as ``Delete`` in the table.

        Qt's native-text format outputs the abbreviated ``"Del"`` but
        the keycap label is ``"Delete"`` — match what the user sees.
        Same readability substitution as ``Return`` → ``Enter``.
        """
        from PySide6.QtCore import Qt

        table = tab._shortcut_table
        for r in range(table.rowCount()):
            sid = table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            if sid == "common.delete_selected":
                cell_text = table.item(r, 0).text()
                assert cell_text == "Delete", (
                    f"expected 'Delete' (substituted from Qt's 'Del'), "
                    f"got {cell_text!r}"
                )
                return
        pytest.fail("row for common.delete_selected not found")

    def test_display_substitutes_return_to_enter(self, tab) -> None:
        """``Ctrl+Return`` renders as ``Ctrl+Enter`` in the table.

        Pre-existing readability substitution; this regression test
        guards against accidentally breaking it while editing
        ``_display_sequence``.
        """
        from PySide6.QtCore import Qt

        table = tab._shortcut_table
        for r in range(table.rowCount()):
            sid = table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            if sid == "common.primary_action":
                cell_text = table.item(r, 0).text()
                assert "Enter" in cell_text, (
                    f"expected 'Enter' (substituted from Qt's 'Return'), "
                    f"got {cell_text!r}"
                )
                assert "Return" not in cell_text, (
                    f"raw 'Return' leaked into display: {cell_text!r}"
                )
                return
        pytest.fail("row for common.primary_action not found")

    def test_unbound_displays_placeholder_text(self, tab) -> None:
        """A row with an unbound shortcut shows the (none) placeholder."""
        from PySide6.QtCore import Qt

        table = tab._shortcut_table
        target_sid = table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        unbind_shortcut(target_sid)

        # Find the row again (could be re-sorted but ID-stable).
        for r in range(table.rowCount()):
            if table.item(r, 0).data(Qt.ItemDataRole.UserRole) == target_sid:
                cell_text = table.item(r, 0).text()
                # tr() returns the key when no translation loaded, or "(none)"
                # when en-US is loaded — accept either.
                assert cell_text in (
                    "settings.shortcuts.unbound",
                    "(none)",
                )
                return
        pytest.fail("row for unbound shortcut not found")


# ---------------------------------------------------------------------------
# Platform detection — ``is_wayland_platform`` / ``is_shortcut_supported``
# ---------------------------------------------------------------------------


class TestPlatformDetection:
    """Wayland-aware filtering for skip_on_wayland shortcuts."""

    def test_is_wayland_platform_false_on_xcb(self) -> None:
        """X11 / xcb platform name should NOT trigger Wayland filtering."""
        with patch(
            "PySide6.QtWidgets.QApplication.platformName",
            return_value="xcb",
        ):
            assert is_wayland_platform() is False

    def test_is_wayland_platform_true_on_wayland(self) -> None:
        """``platformName == 'wayland'`` triggers Wayland mode."""
        with patch(
            "PySide6.QtWidgets.QApplication.platformName",
            return_value="wayland",
        ):
            assert is_wayland_platform() is True

    def test_is_wayland_platform_handles_wayland_egl(self) -> None:
        """Wayland-EGL backend (compositor variant) is still Wayland.

        ``startswith('wayland')`` covers ``wayland``, ``wayland-egl``
        and other compositor-specific suffixes.
        """
        with patch(
            "PySide6.QtWidgets.QApplication.platformName",
            return_value="wayland-egl",
        ):
            assert is_wayland_platform() is True

    def test_is_wayland_platform_swallows_qt_exception(self) -> None:
        """If Qt raises during platform detection, return False (safe default)."""
        with patch(
            "PySide6.QtWidgets.QApplication.platformName",
            side_effect=RuntimeError("no QApplication"),
        ):
            assert is_wayland_platform() is False

    def test_is_shortcut_supported_filters_skip_on_wayland(self) -> None:
        """``skip_on_wayland=True`` shortcuts hide on Wayland, show elsewhere."""
        wl_shortcut = Shortcut(
            id="test.wayland_skip",
            default="Ctrl+Shift+W",
            label_key="x",
            group_key=GROUP_APP,
            skip_on_wayland=True,
        )
        normal = Shortcut(
            id="test.normal",
            default="Ctrl+Shift+N",
            label_key="x",
            group_key=GROUP_APP,
        )
        with patch(
            "src.constants.shortcuts.is_wayland_platform",
            return_value=True,
        ):
            assert is_shortcut_supported(wl_shortcut) is False
            assert is_shortcut_supported(normal) is True
        with patch(
            "src.constants.shortcuts.is_wayland_platform",
            return_value=False,
        ):
            assert is_shortcut_supported(wl_shortcut) is True
            assert is_shortcut_supported(normal) is True


# ---------------------------------------------------------------------------
# ``iter_display_shortcuts`` — UI-facing filtered view
# ---------------------------------------------------------------------------


class TestIterDisplayShortcuts:
    """Followers of shared groups are collapsed; Wayland-incompatible hidden."""

    def test_followers_are_collapsed(self) -> None:
        """Shortcuts with ``shared_group`` set never appear in the displayed list."""
        displayed = iter_display_shortcuts()
        for s in displayed:
            assert s.shared_group is None, f"follower {s.id!r} leaked into display list"

    def test_group_owners_are_present(self) -> None:
        """Every non-follower, platform-supported shortcut is in the list."""
        with patch(
            "src.constants.shortcuts.is_wayland_platform",
            return_value=False,
        ):
            displayed = iter_display_shortcuts()
            displayed_ids = {s.id for s in displayed}
            for s in SHORTCUTS:
                if s.shared_group is None and not s.skip_on_wayland:
                    assert s.id in displayed_ids

    def test_wayland_hides_skip_on_wayland_entries(self) -> None:
        """On Wayland, ``skip_on_wayland`` entries drop out of the display set.

        We don't assert on a specific shortcut id (defensive against
        registry edits) — only that the Wayland-true call is a strict
        subset of the Wayland-false call.
        """
        with patch(
            "src.constants.shortcuts.is_wayland_platform",
            return_value=False,
        ):
            without_wayland = {s.id for s in iter_display_shortcuts()}
        with patch(
            "src.constants.shortcuts.is_wayland_platform",
            return_value=True,
        ):
            with_wayland = {s.id for s in iter_display_shortcuts()}
        assert with_wayland.issubset(without_wayland)


# ---------------------------------------------------------------------------
# ``find_conflicts`` — collision detection
# ---------------------------------------------------------------------------


class TestFindConflicts:
    """Same-group, app-vs-page, and shared-group exclusion rules."""

    def test_no_conflicts_at_defaults(self) -> None:
        """The shipped defaults must not collide with each other.

        If the registry ever ships overlapping bindings, this test
        catches the regression before users hit it.
        """
        assert find_conflicts() == {}

    def test_same_group_collision_reported(self) -> None:
        """Two shortcuts in the same page-group sharing a sequence collide.

        Both shortcuts must be group-owned (``shared_group is None``) —
        followers are deliberately skipped by ``find_conflicts``.
        """
        # Pick two non-follower shortcuts from the same group.
        live_owned = [
            s for s in SHORTCUTS if s.group_key == GROUP_LIVE and s.shared_group is None
        ]
        if len(live_owned) < 2:  # noqa: PLR2004
            pytest.skip("registry has fewer than 2 non-follower Live shortcuts")
        # Force the second onto the first's sequence.
        seq = get_shortcut(live_owned[0].id)
        set_shortcut(live_owned[1].id, seq)

        conflicts = find_conflicts()
        assert seq in conflicts, f"collision on {seq!r} not reported"
        ids = set(conflicts[seq])
        assert live_owned[0].id in ids
        assert live_owned[1].id in ids

    def test_global_app_shortcut_shadows_page_shortcut(self) -> None:
        """An ``app.*`` shortcut sharing a sequence with a page binding collides.

        Globals fire window-wide and shadow page bindings, so a match
        between ``GROUP_APP`` and any non-common group is reported even
        though they're in different groups.
        """
        app_candidates = [s for s in SHORTCUTS if s.group_key == GROUP_APP]
        page_candidates = [
            s
            for s in SHORTCUTS
            if s.group_key not in (GROUP_APP, GROUP_COMMON) and s.shared_group is None
        ]
        if not app_candidates or not page_candidates:
            pytest.skip("registry missing app or page shortcuts")
        app_s = app_candidates[0]
        page_s = page_candidates[0]
        # Force the page binding onto the app binding's sequence.
        app_seq = get_shortcut(app_s.id)
        set_shortcut(page_s.id, app_seq)

        conflicts = find_conflicts()
        assert app_seq in conflicts
        ids = set(conflicts[app_seq])
        assert app_s.id in ids
        assert page_s.id in ids

    def test_shared_group_followers_skipped(self) -> None:
        """Follower entries (``shared_group != None``) never appear in conflicts.

        By construction, every follower shares its sequence with the
        group owner — that's intentional and would generate false
        positives if not filtered.
        """
        followers = [s for s in SHORTCUTS if s.shared_group is not None]
        if not followers:
            pytest.skip("registry has no shared-group followers")
        conflicts = find_conflicts()
        flat_ids = {sid for ids in conflicts.values() for sid in ids}
        for f in followers:
            assert f.id not in flat_ids, (
                f"follower {f.id!r} was incorrectly reported as a conflict"
            )


class TestUnbindAndNoOpEmission:
    """Explicit unbind sentinel + no-op suppression on set_shortcut."""

    def test_unbind_shortcut_returns_empty_string(self) -> None:
        """unbind_shortcut writes a sentinel; get_shortcut returns ''."""
        sid = SHORTCUTS[0].id
        assert get_shortcut(sid) == get_default(sid)

        unbind_shortcut(sid)

        assert get_shortcut(sid) == ""
        # Stored value is the sentinel, not an empty string.
        from src.constants.shortcuts import _setting_key  # noqa: PLC0415
        from src.utils.config_manager import load_setting  # noqa: PLC0415

        assert load_setting(_setting_key(sid), "") == UNBIND_SENTINEL

    def test_unbind_distinct_from_reset(self) -> None:
        """reset_shortcut restores the default; unbind clears it."""
        sid = SHORTCUTS[0].id
        default = get_default(sid)

        unbind_shortcut(sid)
        assert get_shortcut(sid) == ""

        reset_shortcut(sid)
        assert get_shortcut(sid) == default

    def test_set_shortcut_no_op_skips_signal(self) -> None:
        """Setting the same value twice emits the change signal once."""
        sid = SHORTCUTS[0].id
        new_seq = "Ctrl+Shift+Alt+F12"

        emissions: list[None] = []

        def _record() -> None:
            emissions.append(None)

        shortcuts_changed.connect(_record)
        try:
            set_shortcut(sid, new_seq)
            set_shortcut(sid, new_seq)  # No-op — same value
            set_shortcut(sid, new_seq)  # No-op — same value
        finally:
            shortcuts_changed.disconnect(_record)

        assert len(emissions) == 1, (
            f"expected single emission, got {len(emissions)} — no-op writes "
            "should be suppressed"
        )

    def test_set_shortcut_to_default_clears_override(self) -> None:
        """Setting back to the default value removes the settings.ini entry."""
        sid = SHORTCUTS[0].id
        default = get_default(sid)

        set_shortcut(sid, "Ctrl+Shift+Alt+F11")
        # Now reset by setting to default explicitly.
        set_shortcut(sid, default)

        from src.constants.shortcuts import _setting_key  # noqa: PLC0415
        from src.utils.config_manager import load_setting  # noqa: PLC0415

        assert load_setting(_setting_key(sid), "") == ""
        assert get_shortcut(sid) == default
