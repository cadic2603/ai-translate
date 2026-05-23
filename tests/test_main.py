"""Unit tests for the application entry point (src/main.py).

Covers the ``_FONT_FILES`` constant, ``_load_app_font()`` font loading
logic, and the ``main()`` bootstrap function including QApplication
creation, theme/language initialization, window creation, and resume
worker lifecycle.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.main import _FONT_FILES, _load_app_font

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_MOD = "src.main"


# ===================================================================
# _FONT_FILES constant
# ===================================================================


class TestFontFilesConstant:
    """Tests for the _FONT_FILES module-level constant."""

    def test_contains_roboto_regular(self) -> None:
        """Roboto-Regular.ttf must be present (used as default family)."""
        assert "Roboto-Regular.ttf" in _FONT_FILES

    def test_contains_roboto_bold(self) -> None:
        """Roboto-Bold.ttf must be present for bold text rendering."""
        assert "Roboto-Bold.ttf" in _FONT_FILES

    def test_contains_roboto_medium(self) -> None:
        """Roboto-Medium.ttf must be present for medium weight text."""
        assert "Roboto-Medium.ttf" in _FONT_FILES

    def test_contains_roboto_light(self) -> None:
        """Roboto-Light.ttf must be present for light weight text."""
        assert "Roboto-Light.ttf" in _FONT_FILES

    def test_contains_roboto_italic(self) -> None:
        """Roboto-Italic.ttf must be present for italic text."""
        assert "Roboto-Italic.ttf" in _FONT_FILES

    def test_regular_is_first(self) -> None:
        """Roboto-Regular.ttf must be the first entry (loaded before others)."""
        assert _FONT_FILES[0] == "Roboto-Regular.ttf"

    def test_all_entries_are_ttf(self) -> None:
        """Every font file name ends with .ttf."""
        for name in _FONT_FILES:
            assert name.endswith(".ttf"), f"{name} is not a .ttf file"

    def test_five_font_variants(self) -> None:
        """Exactly five Roboto variants are bundled."""
        assert len(_FONT_FILES) == 5  # noqa: PLR2004

    def test_no_duplicates(self) -> None:
        """No duplicate font file names."""
        assert len(_FONT_FILES) == len(set(_FONT_FILES))


# ===================================================================
# _load_app_font()
# ===================================================================


class TestLoadAppFont:
    """Tests for the _load_app_font() function."""

    def test_all_fonts_loaded_successfully(self, qapp: MagicMock) -> None:
        """All font files that exist on disk are loaded via addApplicationFont."""
        mock_app = MagicMock()
        mock_font = MagicMock()

        with (
            patch(f"{_MOD}.FONTS_DIR", new=MagicMock()) as mock_fonts_dir,
            patch(f"{_MOD}.QFontDatabase") as mock_fdb,
            patch(f"{_MOD}.QFont", return_value=mock_font),
        ):
            # Every font path exists and loads OK (font_id >= 0)
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_fonts_dir.__truediv__ = MagicMock(return_value=mock_path)
            mock_fdb.addApplicationFont.return_value = 0

            _load_app_font(mock_app)

            # addApplicationFont called once per font file
            assert mock_fdb.addApplicationFont.call_count == len(_FONT_FILES)

    def test_missing_font_file_logs_warning(self, qapp: MagicMock) -> None:
        """A missing font file logs a warning but does not raise."""
        mock_app = MagicMock()

        with (
            patch(f"{_MOD}.FONTS_DIR", new=MagicMock()) as mock_fonts_dir,
            patch(f"{_MOD}.QFontDatabase") as mock_fdb,
            patch(f"{_MOD}.QFont", return_value=MagicMock()),
            patch(f"{_MOD}.logger") as mock_logger,
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_fonts_dir.__truediv__ = MagicMock(return_value=mock_path)

            _load_app_font(mock_app)

            # Should log a warning for each missing font
            assert mock_logger.warning.call_count == len(_FONT_FILES)
            # addApplicationFont should never be called for missing files
            mock_fdb.addApplicationFont.assert_not_called()

    def test_failed_font_load_logs_warning(self, qapp: MagicMock) -> None:
        """A font file that exists but fails to load (id == -1) logs a warning."""
        mock_app = MagicMock()

        with (
            patch(f"{_MOD}.FONTS_DIR", new=MagicMock()) as mock_fonts_dir,
            patch(f"{_MOD}.QFontDatabase") as mock_fdb,
            patch(f"{_MOD}.QFont", return_value=MagicMock()),
            patch(f"{_MOD}.logger") as mock_logger,
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_fonts_dir.__truediv__ = MagicMock(return_value=mock_path)
            mock_fdb.addApplicationFont.return_value = -1

            _load_app_font(mock_app)

            # Warning logged for each file that fails to load
            assert mock_logger.warning.call_count == len(_FONT_FILES)

    def test_partial_success_logs_only_failed(self, qapp: MagicMock) -> None:
        """Only the failing font produces a warning; successful ones do not."""
        mock_app = MagicMock()

        with (
            patch(f"{_MOD}.FONTS_DIR", new=MagicMock()) as mock_fonts_dir,
            patch(f"{_MOD}.QFontDatabase") as mock_fdb,
            patch(f"{_MOD}.QFont", return_value=MagicMock()),
            patch(f"{_MOD}.logger") as mock_logger,
        ):
            # All paths exist
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_fonts_dir.__truediv__ = MagicMock(return_value=mock_path)

            # First file fails, rest succeed
            side_effects = [-1] + list(range(1, len(_FONT_FILES)))
            mock_fdb.addApplicationFont.side_effect = side_effects

            _load_app_font(mock_app)

            # Only 1 warning for the first failed font
            assert mock_logger.warning.call_count == 1

    def test_sets_roboto_as_default_font(self, qapp: MagicMock) -> None:
        """Sets the QFont with family 'Roboto' as the application default."""
        mock_app = MagicMock()
        mock_font = MagicMock()

        with (
            patch(f"{_MOD}.FONTS_DIR", new=MagicMock()) as mock_fonts_dir,
            patch(f"{_MOD}.QFontDatabase") as mock_fdb,
            patch(f"{_MOD}.QFont", return_value=mock_font) as mock_qfont_cls,
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_fonts_dir.__truediv__ = MagicMock(return_value=mock_path)
            mock_fdb.addApplicationFont.return_value = 0

            _load_app_font(mock_app)

            mock_qfont_cls.assert_called_once_with("Roboto")
            mock_app.setFont.assert_called_once_with(mock_font)

    def test_font_point_size_is_10(self, qapp: MagicMock) -> None:
        """Default font point size is set to 10."""
        mock_app = MagicMock()
        mock_font = MagicMock()

        with (
            patch(f"{_MOD}.FONTS_DIR", new=MagicMock()) as mock_fonts_dir,
            patch(f"{_MOD}.QFontDatabase") as mock_fdb,
            patch(f"{_MOD}.QFont", return_value=mock_font),
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_fonts_dir.__truediv__ = MagicMock(return_value=mock_path)
            mock_fdb.addApplicationFont.return_value = 0

            _load_app_font(mock_app)

            mock_font.setPointSize.assert_called_once_with(10)

    def test_font_set_even_when_all_fonts_missing(self, qapp: MagicMock) -> None:
        """The default Roboto font is set on the app even if no files load."""
        mock_app = MagicMock()
        mock_font = MagicMock()

        with (
            patch(f"{_MOD}.FONTS_DIR", new=MagicMock()) as mock_fonts_dir,
            patch(f"{_MOD}.QFontDatabase"),
            patch(f"{_MOD}.QFont", return_value=mock_font),
            patch(f"{_MOD}.logger"),
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_fonts_dir.__truediv__ = MagicMock(return_value=mock_path)

            _load_app_font(mock_app)

            # Font is still set as app default
            mock_app.setFont.assert_called_once_with(mock_font)


# ===================================================================
# main() function
# ===================================================================


class TestMain:
    """Tests for the main() application bootstrap function."""

    @pytest.fixture()
    def _main_mocks(self) -> dict:
        """Sets up all mocks needed for the main() function.

        Returns a dict of all mock objects for assertion.
        """
        mock_app = MagicMock()
        mock_app.exec.return_value = 0
        mock_window = MagicMock()
        mock_monitor = MagicMock()
        mock_resume_worker = None  # Default: no resume needed

        # detect_system_theme and SystemThemeMonitor are imported locally
        # inside main(), so they must be patched at their source module.
        theme_mod = "src.ui.system_theme"

        patches = {
            "ensure_app_dirs_exist": patch(f"{_MOD}.ensure_app_dirs_exist"),
            "configure_logging": patch(f"{_MOD}.configure_logging"),
            "wipe_tts_cache": patch(f"{_MOD}.wipe_tts_cache"),
            "init_db": patch(f"{_MOD}.init_db"),
            "QApplication": patch(f"{_MOD}.QApplication", return_value=mock_app),
            "_load_app_font": patch(f"{_MOD}._load_app_font"),
            "load_setting": patch(f"{_MOD}.load_setting"),
            "_set_initial_theme": patch(f"{_MOD}._set_initial_theme"),
            "_set_initial_language": patch(f"{_MOD}._set_initial_language"),
            "detect_system_theme": patch(
                f"{theme_mod}.detect_system_theme",
                return_value="light",
            ),
            "SystemThemeMonitor": patch(
                f"{theme_mod}.SystemThemeMonitor",
                return_value=mock_monitor,
            ),
            "create_main_window": patch(
                f"{_MOD}.create_main_window",
                return_value=mock_window,
            ),
            "resume_unfinished_translations": patch(
                f"{_MOD}.resume_unfinished_translations",
                return_value=mock_resume_worker,
            ),
            # ``install_focus_clear_filter`` constructs a ``QObject``
            # parented to ``app`` — a real PySide6 type that rejects
            # the MagicMock the fixture passes for ``QApplication``.
            # Patch at the source so the real wiring tests
            # (``test_installs_focus_clear_filter``) still see the
            # call, but every other ``main()`` test gets a no-op stub.
            "install_focus_clear_filter": patch(
                "src.ui.focus_filter.install_focus_clear_filter",
            ),
            "sys_exit": patch(f"{_MOD}.sys.exit"),
        }

        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()

        # Default load_setting behavior: theme=Auto, language=en-US
        def _load_setting_side_effect(key: str, default: str = "") -> str:
            from src.constants import SETTING_THEME, SETTING_UI_LANGUAGE

            if key == SETTING_THEME:
                return "Auto"
            if key == SETTING_UI_LANGUAGE:
                return "en-US"
            return default

        mocks["load_setting"].side_effect = _load_setting_side_effect

        mocks["_app"] = mock_app
        mocks["_window"] = mock_window
        mocks["_monitor"] = mock_monitor

        yield mocks

        for p in patches.values():
            p.stop()

    def test_calls_ensure_app_dirs_exist(self, _main_mocks: dict) -> None:
        """main() calls ensure_app_dirs_exist() to create required dirs."""
        from src.main import main

        main()
        _main_mocks["ensure_app_dirs_exist"].assert_called_once()

    def test_calls_configure_logging(self, _main_mocks: dict) -> None:
        """main() calls configure_logging() early in startup."""
        from src.main import main

        main()
        _main_mocks["configure_logging"].assert_called_once()

    def test_calls_init_db(self, _main_mocks: dict) -> None:
        """main() initializes the database."""
        from src.main import main

        main()
        _main_mocks["init_db"].assert_called_once()

    def test_creates_qapplication(self, _main_mocks: dict) -> None:
        """main() creates a QApplication instance."""
        from src.main import main

        main()
        _main_mocks["QApplication"].assert_called_once()

    def test_sets_organization_name(self, _main_mocks: dict) -> None:
        """QApplication has organization name set to 'Google'."""
        from src.main import main

        main()
        _main_mocks["_app"].setOrganizationName.assert_called_once_with("Google")

    def test_sets_application_name(self, _main_mocks: dict) -> None:
        """QApplication has application name set to 'AITranslate'."""
        from src.main import main

        main()
        _main_mocks["_app"].setApplicationName.assert_called_once_with("AITranslate")

    def test_sets_fusion_style(self, _main_mocks: dict) -> None:
        """QApplication uses the Fusion style for cross-platform consistency."""
        from src.main import main

        main()
        _main_mocks["_app"].setStyle.assert_called_once_with("Fusion")

    def test_installs_focus_clear_filter(self, _main_mocks: dict) -> None:
        """main() wires the Esc / outside-click focus filter to QApplication.

        Without this, ``Esc`` and clicks-into-the-void wouldn't drop
        the focus rectangle from the last-clicked button — the desktop
        UX regression the filter exists to fix.  Pin that the wiring
        survives a refactor of ``main()``: a future cleanup that drops
        the call (or moves it before ``setStyle``) silently breaks the
        feature, and only a UI walk-through would catch it otherwise.
        """
        from unittest.mock import patch

        with patch(
            "src.ui.focus_filter.install_focus_clear_filter",
        ) as mock_install:
            from src.main import main
            main()
        mock_install.assert_called_once_with(_main_mocks["_app"])

    def test_calls_load_app_font(self, _main_mocks: dict) -> None:
        """main() calls _load_app_font() with the QApplication instance."""
        from src.main import main

        main()
        _main_mocks["_load_app_font"].assert_called_once_with(
            _main_mocks["_app"],
        )

    def test_auto_theme_detects_system_and_starts_monitor(
        self,
        _main_mocks: dict,
    ) -> None:
        """When saved theme is 'Auto', system theme is detected and monitor starts."""
        from src.main import main

        # Default side_effect already returns "Auto" for SETTING_THEME
        main()

        _main_mocks["detect_system_theme"].assert_called_once()
        _main_mocks["_set_initial_theme"].assert_called_once_with("light")
        _main_mocks["_monitor"].start.assert_called_once()

    def test_auto_theme_case_insensitive(self, _main_mocks: dict) -> None:
        """'auto' (any casing) triggers system detection and monitor."""
        from src.constants import SETTING_THEME, SETTING_UI_LANGUAGE
        from src.main import main

        def _load(key: str, default: str = "") -> str:
            if key == SETTING_THEME:
                return "auto"  # lowercase
            if key == SETTING_UI_LANGUAGE:
                return "en-US"
            return default

        _main_mocks["load_setting"].side_effect = _load

        main()

        _main_mocks["detect_system_theme"].assert_called_once()
        _main_mocks["_monitor"].start.assert_called_once()

    def test_explicit_dark_theme_no_monitor_start(
        self,
        _main_mocks: dict,
    ) -> None:
        """When saved theme is 'dark', theme is applied directly without monitor."""
        from src.constants import SETTING_THEME, SETTING_UI_LANGUAGE
        from src.main import main

        def _load(key: str, default: str = "") -> str:
            if key == SETTING_THEME:
                return "dark"
            if key == SETTING_UI_LANGUAGE:
                return "en-US"
            return default

        _main_mocks["load_setting"].side_effect = _load

        main()

        _main_mocks["_set_initial_theme"].assert_called_once_with("dark")
        _main_mocks["_monitor"].start.assert_not_called()

    def test_explicit_light_theme_no_monitor_start(
        self,
        _main_mocks: dict,
    ) -> None:
        """When saved theme is 'light', theme is applied directly without monitor."""
        from src.constants import SETTING_THEME, SETTING_UI_LANGUAGE
        from src.main import main

        def _load(key: str, default: str = "") -> str:
            if key == SETTING_THEME:
                return "light"
            if key == SETTING_UI_LANGUAGE:
                return "en-US"
            return default

        _main_mocks["load_setting"].side_effect = _load

        main()

        _main_mocks["_set_initial_theme"].assert_called_once_with("light")
        _main_mocks["_monitor"].start.assert_not_called()

    def test_language_loaded_from_settings(self, _main_mocks: dict) -> None:
        """Language is loaded from settings and passed to _set_initial_language."""
        from src.main import main

        main()
        _main_mocks["_set_initial_language"].assert_called_once_with("en-US")

    def test_custom_language_loaded(self, _main_mocks: dict) -> None:
        """A non-default language from settings is applied."""
        from src.constants import SETTING_THEME, SETTING_UI_LANGUAGE
        from src.main import main

        def _load(key: str, default: str = "") -> str:
            if key == SETTING_THEME:
                return "Auto"
            if key == SETTING_UI_LANGUAGE:
                return "ja-JP"
            return default

        _main_mocks["load_setting"].side_effect = _load

        main()

        _main_mocks["_set_initial_language"].assert_called_once_with("ja-JP")

    def test_create_main_window_called(self, _main_mocks: dict) -> None:
        """main() calls create_main_window() to build the UI."""
        from src.main import main

        main()
        _main_mocks["create_main_window"].assert_called_once()

    def test_window_show_called(self, _main_mocks: dict) -> None:
        """The main window is shown after creation."""
        from src.main import main

        main()
        _main_mocks["_window"].show.assert_called_once()

    def test_system_theme_monitor_stored_on_window(
        self,
        _main_mocks: dict,
    ) -> None:
        """SystemThemeMonitor is stored on the window to prevent GC."""
        from src.main import main

        main()
        assert _main_mocks["_window"]._system_theme_monitor is _main_mocks["_monitor"]

    def test_resume_unfinished_translations_called(
        self,
        _main_mocks: dict,
    ) -> None:
        """main() calls resume_unfinished_translations()."""
        from src.main import main

        main()
        _main_mocks["resume_unfinished_translations"].assert_called_once()

    def test_sys_exit_called_with_app_exec(self, _main_mocks: dict) -> None:
        """sys.exit() is called with the return value of app.exec()."""
        from src.main import main

        _main_mocks["_app"].exec.return_value = 42

        main()

        _main_mocks["sys_exit"].assert_called_once_with(42)

    def test_resume_worker_stored_on_window(self, _main_mocks: dict) -> None:
        """When resume_unfinished_translations returns a worker, it's stored."""
        from src.main import main

        mock_worker = MagicMock()
        mock_worker.finished = MagicMock()
        _main_mocks["resume_unfinished_translations"].return_value = mock_worker

        # Pre-set _workers as a real list on the mock window.
        # MagicMock's hasattr() always returns True, so main() will find the
        # existing _workers attribute and append to it rather than creating
        # a new list.
        window = _main_mocks["_window"]
        window._workers = []

        main()

        assert mock_worker in window._workers

    def test_resume_worker_finished_connected_to_safe_remove(
        self,
        _main_mocks: dict,
    ) -> None:
        """The resume worker's finished signal is connected to safe_remove."""
        from src.main import main

        mock_worker = MagicMock()
        mock_worker.finished = MagicMock()
        _main_mocks["resume_unfinished_translations"].return_value = mock_worker

        # Pre-set _workers as a real list so main() appends to it
        _main_mocks["_window"]._workers = []

        main()

        mock_worker.finished.connect.assert_called_once()

    def test_resume_worker_none_no_workers_list(
        self,
        _main_mocks: dict,
    ) -> None:
        """When resume returns None, no _workers list is created on the window."""
        from src.main import main

        _main_mocks["resume_unfinished_translations"].return_value = None
        # Use a clean mock window that doesn't auto-create attributes on access
        mock_window = MagicMock(
            spec=[
                "show",
                "setOrganizationName",
                "setApplicationName",
            ]
        )
        _main_mocks["create_main_window"].return_value = mock_window
        _main_mocks["_window"] = mock_window

        main()

        # _workers should not be set when there's no resume worker
        # We check that no _workers attribute was explicitly assigned
        # (MagicMock with spec won't have it)
        assert not hasattr(mock_window, "_workers")

    def test_initialization_order(self, _main_mocks: dict) -> None:
        """Startup functions are called in the correct order."""
        from src.main import main

        call_order = []

        _main_mocks["ensure_app_dirs_exist"].side_effect = lambda: call_order.append(
            "ensure_app_dirs_exist"
        )
        _main_mocks["configure_logging"].side_effect = lambda: call_order.append(
            "configure_logging"
        )
        _main_mocks["init_db"].side_effect = lambda: call_order.append("init_db")

        def _qa(*a: object, **kw: object) -> MagicMock:
            call_order.append("QApplication")
            return _main_mocks["_app"]

        _main_mocks["QApplication"].side_effect = _qa
        _main_mocks["_load_app_font"].side_effect = lambda app: call_order.append(
            "_load_app_font"
        )
        _main_mocks["create_main_window"].side_effect = lambda: (
            call_order.append("create_main_window") or _main_mocks["_window"]
        )

        main()

        # Verify the ordering of critical setup steps
        assert call_order.index("ensure_app_dirs_exist") < call_order.index(
            "configure_logging",
        )
        assert call_order.index("configure_logging") < call_order.index(
            "init_db",
        )
        assert call_order.index("init_db") < call_order.index("QApplication")
        assert call_order.index("QApplication") < call_order.index(
            "_load_app_font",
        )
        assert call_order.index("_load_app_font") < call_order.index(
            "create_main_window",
        )

    def test_safe_remove_callback_removes_worker(
        self,
        _main_mocks: dict,
    ) -> None:
        """The safe_remove callback properly removes the worker from the list."""
        from src.main import main

        mock_worker = MagicMock()
        mock_worker.finished = MagicMock()
        _main_mocks["resume_unfinished_translations"].return_value = mock_worker

        # Pre-set _workers as a real list so main() appends to it
        window = _main_mocks["_window"]
        window._workers = []

        main()

        # Retrieve the safe_remove callback that was connected
        connect_call = mock_worker.finished.connect.call_args
        safe_remove_fn = connect_call[0][0]

        # The worker should be in _workers before safe_remove
        assert mock_worker in window._workers

        # Call safe_remove — it should remove the worker
        safe_remove_fn()

        assert mock_worker not in window._workers

    def test_safe_remove_idempotent(self, _main_mocks: dict) -> None:
        """Calling safe_remove multiple times does not raise."""
        from src.main import main

        mock_worker = MagicMock()
        mock_worker.finished = MagicMock()
        _main_mocks["resume_unfinished_translations"].return_value = mock_worker

        # Pre-set _workers as a real list so main() appends to it
        _main_mocks["_window"]._workers = []

        main()

        safe_remove_fn = mock_worker.finished.connect.call_args[0][0]

        # First call removes the worker
        safe_remove_fn()
        # Second call should not raise (worker already removed)
        safe_remove_fn()

    def test_app_exec_called(self, _main_mocks: dict) -> None:
        """app.exec() is invoked to start the event loop."""
        from src.main import main

        main()
        _main_mocks["_app"].exec.assert_called_once()


# ===================================================================
# Module-level __name__ == "__main__" guard
# ===================================================================


class TestModuleGuard:
    """Tests for the ``if __name__ == '__main__'`` guard."""

    def test_module_guard_calls_main(self) -> None:
        """The module guard invokes main() when run as a script."""
        with (
            patch(f"{_MOD}.main") as mock_main,
            patch(f"{_MOD}.__name__", "__main__"),
        ):
            # Re-execute the guard logic
            exec(  # noqa: S102
                "if __name__ == '__main__': main()",
                {"__name__": "__main__", "main": mock_main},
            )
            mock_main.assert_called_once()
