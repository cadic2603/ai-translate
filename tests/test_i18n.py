"""Unit tests for the i18n internationalization engine."""

import json
from pathlib import Path
from unittest.mock import patch

from src.constants._signal import CallbackSignal
from src.constants.i18n import (
    UI_LANGUAGES,
    _load_translations,
    _set_initial_language,
    current_language,
    language_changed,
    set_language,
    tr,
)

# ruff: noqa: PLW0108


# ── CallbackSignal ──────────────────────────────────────────


class TestCallbackSignal:
    """Tests for the lightweight CallbackSignal class."""

    def test_disconnect_prevents_callback(self) -> None:
        """Connect then disconnect a callback; emit should NOT invoke it."""
        signal = CallbackSignal()
        called: list[str] = []
        callback = lambda *a: called.append("hit")  # noqa: E731

        signal.connect(callback)
        # Verify callback WORKS before disconnect
        signal.emit("before")
        assert called == ["hit"]

        called.clear()
        signal.disconnect(callback)
        signal.emit("after")
        assert called == []  # Not called after disconnect

    def test_emit_calls_multiple_callbacks_in_order(self) -> None:
        """Multiple connected callbacks are called in registration order."""
        signal = CallbackSignal()
        order: list[int] = []

        signal.connect(lambda *a: order.append(1))
        signal.connect(lambda *a: order.append(2))  # noqa: PLR2004
        signal.connect(lambda *a: order.append(3))  # noqa: PLR2004

        signal.emit()

        assert order == [1, 2, 3]  # noqa: PLR2004

    def test_disconnect_nonexistent_callback_is_silent_noop(self) -> None:
        """Disconnecting a never-connected callback is a silent no-op.

        Production code suppresses the ``ValueError`` that
        ``list.remove`` would otherwise raise, because widget
        ``destroyed`` lambdas can fire AFTER the conftest's
        ``_callbacks.clear()`` has already wiped the listener
        list — making the disconnect a guaranteed no-op race.
        Raising would cascade through pytest teardown as spurious
        test failures unrelated to the actual code under test.
        """
        signal = CallbackSignal()

        # No exception — disconnect is tolerant of "never connected".
        signal.disconnect(lambda: None)
        assert signal._callbacks == []

    def test_connect_same_callback_twice_only_registered_once(self) -> None:
        """Connecting the same callback twice does not duplicate it."""
        signal = CallbackSignal()
        count: list[int] = []
        callback = lambda *a: count.append(1)  # noqa: E731

        signal.connect(callback)
        signal.connect(callback)
        signal.emit()

        assert len(count) == 1  # noqa: PLR2004

    def test_emit_passes_arguments(self) -> None:
        """Arguments passed to emit() are forwarded to callbacks."""
        signal = CallbackSignal()
        received: list[tuple] = []

        signal.connect(lambda *a: received.append(a))
        signal.emit("hello", 42)

        assert len(received) == 1  # noqa: PLR2004
        assert received[0] == ("hello", 42)

    def test_emit_no_callbacks_is_noop(self) -> None:
        """Emitting with no connected callbacks does not raise."""
        signal = CallbackSignal()
        signal.emit("whatever")  # Should not raise


# ── _load_translations ────────────────────────────────────────


class TestLoadTranslations:
    """Tests for _load_translations internal helper."""

    def test_valid_json_file(self, tmp_path: Path) -> None:
        """Valid JSON file populates the module-level _translations dict."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        translations_dir = tmp_path / "translations"
        translations_dir.mkdir()
        json_file = translations_dir / "test-lang.json"
        data = {"greeting": "Hello", "farewell": "Goodbye"}
        json_file.write_text(json.dumps(data), encoding="utf-8")

        with patch.object(i18n_mod, "_TRANSLATIONS_DIR", translations_dir):
            _load_translations("test-lang")
            assert i18n_mod._translations == data

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Missing JSON file sets _translations to empty dict."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        translations_dir = tmp_path / "translations"
        translations_dir.mkdir()

        with patch.object(i18n_mod, "_TRANSLATIONS_DIR", translations_dir):
            _load_translations("nonexistent")
            assert i18n_mod._translations == {}

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        """Invalid JSON content sets _translations to empty dict."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        translations_dir = tmp_path / "translations"
        translations_dir.mkdir()
        bad_file = translations_dir / "broken.json"
        bad_file.write_text("{not valid json!!!", encoding="utf-8")

        with patch.object(i18n_mod, "_TRANSLATIONS_DIR", translations_dir):
            _load_translations("broken")
            assert i18n_mod._translations == {}


# ── set_language / current_language ───────────────────────────


class TestSetLanguage:
    """Tests for set_language() and current_language()."""

    def _reset_language(self) -> None:
        """Restore the module to en-US after each test."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        i18n_mod._current_language = "en-US"
        _load_translations("en-US")

    def test_set_language_emits_signal(self) -> None:
        """set_language() emits the language_changed signal with the new code."""
        emitted: list[str] = []
        handler = lambda code: emitted.append(code)  # noqa: E731
        language_changed.connect(handler)

        try:
            # Switch to a different language to trigger signal
            set_language("vi")
            assert emitted == ["vi"]
        finally:
            language_changed.disconnect(handler)
            self._reset_language()

    def test_current_language_returns_last_set(self) -> None:
        """current_language() returns the code most recently set."""
        try:
            set_language("en-UK")
            assert current_language() == "en-UK"
        finally:
            self._reset_language()

    def test_set_language_invalid_code_ignored(self) -> None:
        """Setting an invalid language code is ignored; current language unchanged."""
        original = current_language()
        set_language("xx-INVALID")
        assert current_language() == original

    def test_set_same_language_does_not_emit(self) -> None:
        """Setting the already-active language does not emit the signal."""
        emitted: list[str] = []
        handler = lambda code: emitted.append(code)  # noqa: E731
        language_changed.connect(handler)

        try:
            # Ensure we're on en-US, then set en-US again
            self._reset_language()
            set_language("en-US")
            assert emitted == []
        finally:
            language_changed.disconnect(handler)


# ── tr() ──────────────────────────────────────────────────────


class TestTr:
    """Tests for the tr() translation function."""

    def test_existing_key_returns_translation(self) -> None:
        """tr() returns the translated string for a known key."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"hello": "Xin chao"}
            assert tr("hello") == "Xin chao"
        finally:
            i18n_mod._translations = original

    def test_missing_key_returns_key_itself(self) -> None:
        """tr() returns the key itself when no translation exists."""
        result = tr("this.key.does.not.exist.anywhere")
        assert result == "this.key.does.not.exist.anywhere"

    def test_tr_with_format_kwargs(self) -> None:
        """tr() supports Python format kwargs in the template."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"items": "Found {count} items"}
            assert tr("items", count=5) == "Found 5 items"  # noqa: PLR2004
        finally:
            i18n_mod._translations = original

    def test_tr_format_error_returns_template(self) -> None:
        """tr() returns the raw template when format kwargs don't match."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"msg": "Hello {name}"}
            # Pass wrong kwarg — should return the template as-is
            result = tr("msg", wrong_key="value")
            assert result == "Hello {name}"
        finally:
            i18n_mod._translations = original

    def test_tr_with_multiple_interpolation_variables(self) -> None:
        """tr() correctly replaces multiple interpolation variables."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {
                "greeting": "Hello {name}, you have {count} items in {place}"
            }
            result = tr("greeting", name="Alice", count=3, place="cart")
            assert result == "Hello Alice, you have 3 items in cart"
        finally:
            i18n_mod._translations = original

    def test_tr_with_nested_key_returns_key_if_missing(self) -> None:
        """tr() with a dotted key returns the key itself if not found."""
        result = tr("settings.general.theme.dark.label")
        assert result == "settings.general.theme.dark.label"

    def test_tr_with_nested_key_returns_value_if_present(self) -> None:
        """tr() with a dotted key returns the translation if it exists."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"app.title": "My Application"}
            result = tr("app.title")
            assert result == "My Application"
        finally:
            i18n_mod._translations = original

    def test_tr_empty_key_returns_empty_string(self) -> None:
        """tr() with empty string key returns empty string (key fallback)."""
        result = tr("")
        assert result == ""

    def test_tr_returns_string_type(self) -> None:
        """tr() always returns a string."""
        result = tr("any.random.key")
        assert isinstance(result, str)


# ── TestSetLanguage: additional coverage ──────────────────


class TestSetLanguageAdditional:
    """Additional tests for set_language()."""

    def _reset_language(self) -> None:
        """Restore the module to en-US after each test."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        i18n_mod._current_language = "en-US"
        _load_translations("en-US")

    def test_set_language_en_us(self) -> None:
        """set_language('en-US') sets the language to en-US."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        # Force a different language first so the switch is not a no-op
        i18n_mod._current_language = "vi"
        try:
            set_language("en-US")
            assert current_language() == "en-US"
        finally:
            self._reset_language()

    def test_set_language_en_uk(self) -> None:
        """set_language('en-UK') sets the language to en-UK."""
        try:
            set_language("en-UK")
            assert current_language() == "en-UK"
        finally:
            self._reset_language()

    def test_set_language_vi(self) -> None:
        """set_language('vi') sets the language to Vietnamese."""
        try:
            set_language("vi")
            assert current_language() == "vi"
        finally:
            self._reset_language()

    def test_set_language_invalid_falls_back(self) -> None:
        """set_language() with invalid code does not change the current language."""
        original = current_language()
        set_language("invalid-lang")
        assert current_language() == original

    def test_set_language_emits_language_changed_signal(self) -> None:
        """set_language() emits language_changed signal with new code."""
        emitted: list[str] = []
        handler = lambda code: emitted.append(code)  # noqa: E731
        language_changed.connect(handler)
        try:
            set_language("vi")
            assert emitted == ["vi"]
        finally:
            language_changed.disconnect(handler)
            self._reset_language()

    def test_set_language_does_not_emit_for_same_language(self) -> None:
        """set_language() with same language does not emit signal."""
        self._reset_language()
        emitted: list[str] = []
        handler = lambda code: emitted.append(code)  # noqa: E731
        language_changed.connect(handler)
        try:
            set_language("en-US")  # already en-US, no-op
            assert emitted == []
        finally:
            language_changed.disconnect(handler)

    def test_set_language_loads_translations_for_new_language(self) -> None:
        """After set_language(), translations dict is populated."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        try:
            set_language("vi")
            assert len(i18n_mod._translations) > 0
        finally:
            self._reset_language()

    def test_set_language_roundtrip(self) -> None:
        """Switching language and back restores original translations."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        # Force-load en-US translations to capture a non-empty baseline.
        # set_language("en-US") is a no-op when _current_language is already
        # "en-US", so we go through another language first.
        i18n_mod._current_language = "invalid"
        set_language("en-US")
        original_keys = set(i18n_mod._translations.keys())
        assert original_keys, "_translations should not be empty after load"
        try:
            set_language("vi")
            assert current_language() == "vi"
            vi_keys = set(i18n_mod._translations.keys())
            # Vietnamese file should have the same set of keys
            assert vi_keys == original_keys

            i18n_mod._current_language = "invalid"  # force change back
            set_language("en-US")
            assert current_language() == "en-US"
            assert set(i18n_mod._translations.keys()) == original_keys
        finally:
            self._reset_language()


# ── TestCurrentLanguage ───────────────────────────────────


class TestCurrentLanguageAdditional:
    """Tests for current_language()."""

    def test_returns_current_language_after_set(self) -> None:
        """current_language() returns the language most recently set."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        try:
            set_language("en-UK")
            assert current_language() == "en-UK"
            i18n_mod._current_language = "en-US"  # force for next switch
            set_language("vi")
            assert current_language() == "vi"
        finally:
            i18n_mod._current_language = "en-US"
            _load_translations("en-US")

    def test_returns_string_type(self) -> None:
        """current_language() always returns a string."""
        result = current_language()
        assert isinstance(result, str)

    def test_returns_valid_ui_language_code(self) -> None:
        """current_language() returns one of the valid UI language codes."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        valid = {c for c, *_ in UI_LANGUAGES}
        assert current_language() in valid


# ── TestTranslationFiles ─────────────────────────────────


class TestTranslationFiles:
    """Tests for the JSON translation files on disk."""

    def _load_json(self, locale: str) -> dict:
        """Load a translation JSON file by locale code."""
        json_path = (
            Path(__file__).parent.parent
            / "src"
            / "constants"
            / "translations"
            / f"{locale}.json"
        )
        with json_path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def test_en_us_is_valid_json(self) -> None:
        """en-US.json parses as valid JSON."""
        data = self._load_json("en-US")
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_en_uk_is_valid_json(self) -> None:
        """en-UK.json parses as valid JSON."""
        data = self._load_json("en-UK")
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_vi_is_valid_json(self) -> None:
        """vi.json parses as valid JSON."""
        data = self._load_json("vi")
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_en_us_has_all_keys(self) -> None:
        """en-US.json has a substantial number of keys."""
        data = self._load_json("en-US")
        assert len(data) >= 100  # noqa: PLR2004

    def test_en_uk_has_all_keys(self) -> None:
        """en-UK.json has a substantial number of keys."""
        data = self._load_json("en-UK")
        assert len(data) >= 100  # noqa: PLR2004

    def test_vi_has_all_keys(self) -> None:
        """vi.json has a substantial number of keys."""
        data = self._load_json("vi")
        assert len(data) >= 100  # noqa: PLR2004

    def test_all_files_have_same_keys(self) -> None:
        """All translation files contain the same set of keys."""
        en_us = set(self._load_json("en-US").keys())
        en_uk = set(self._load_json("en-UK").keys())
        vi = set(self._load_json("vi").keys())
        assert en_us == en_uk, (
            f"en-US vs en-UK diff: "
            f"only in US: {en_us - en_uk}, only in UK: {en_uk - en_us}"
        )
        assert en_us == vi, (
            f"en-US vs vi diff: only in US: {en_us - vi}, only in vi: {vi - en_us}"
        )

    def test_all_values_are_strings(self) -> None:
        """All translation values are strings."""
        for locale in ("en-US", "en-UK", "vi"):
            data = self._load_json(locale)
            for key, value in data.items():
                assert isinstance(value, str), (
                    f"{locale}/{key} value is {type(value).__name__}, expected str"
                )

    def test_no_empty_values_in_en_us(self) -> None:
        """en-US.json has no empty string values."""
        data = self._load_json("en-US")
        for key, value in data.items():
            assert len(value) > 0, f"en-US/{key} has empty value"

    def test_translation_files_exist_for_all_ui_languages(self) -> None:
        """A JSON file exists for every language in UI_LANGUAGES."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        for code, _name, _flag in UI_LANGUAGES:
            json_path = (
                Path(__file__).parent.parent
                / "src"
                / "constants"
                / "translations"
                / f"{code}.json"
            )
            assert json_path.exists(), f"Missing translation file: {json_path}"


# ── _set_initial_language ────────────────────────────────────


class TestSetInitialLanguage:
    """Tests for _set_initial_language()."""

    def _reset_language(self) -> None:
        """Restore the module to en-US after each test."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        i18n_mod._current_language = "en-US"
        _load_translations("en-US")

    def test_sets_language_without_signal(self) -> None:
        """_set_initial_language changes the language without emitting a signal."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        emitted: list[str] = []
        handler = lambda code: emitted.append(code)  # noqa: E731
        language_changed.connect(handler)
        try:
            _set_initial_language("vi")
            assert current_language() == "vi"
            assert emitted == []
        finally:
            language_changed.disconnect(handler)
            self._reset_language()

    def test_invalid_code_keeps_current(self) -> None:
        """_set_initial_language with invalid code keeps the current language."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        original = current_language()
        _set_initial_language("invalid-code")
        assert current_language() == original

    def test_loads_translations_for_valid_code(self) -> None:
        """_set_initial_language populates translations for the set language."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        try:
            _set_initial_language("vi")
            assert len(i18n_mod._translations) > 0
        finally:
            self._reset_language()

    def test_loads_translations_even_for_invalid_code(self) -> None:
        """_set_initial_language loads translations for _current_language on invalid code."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        self._reset_language()
        _set_initial_language("bad-code")
        # Should still have en-US translations loaded
        assert len(i18n_mod._translations) > 0

    def test_all_valid_codes_accepted(self) -> None:
        """_set_initial_language accepts all valid UI_LANGUAGES codes."""
        from src.constants.i18n import (  # noqa: PLC0415
            UI_LANGUAGES,
            _set_initial_language,
        )

        try:
            for code, *_ in UI_LANGUAGES:
                _set_initial_language(code)
                assert current_language() == code
        finally:
            self._reset_language()


# ── tr() edge cases ──────────────────────────────────────────


class TestTrEdgeCases:
    """Extended edge-case tests for tr()."""

    def test_tr_special_characters_in_key(self) -> None:
        """tr() with special characters in key returns the key as fallback."""
        key = "key.with <html>&amp; special chars"
        assert tr(key) == key

    def test_tr_numeric_format_kwarg(self) -> None:
        """tr() correctly formats numeric kwargs."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"progress": "{pct}% complete"}
            result = tr("progress", pct=99.5)
            assert result == "99.5% complete"
        finally:
            i18n_mod._translations = original

    def test_tr_with_index_error_returns_template(self) -> None:
        """tr() with positional placeholder and kwargs returns template on IndexError."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"msg": "Value: {0}"}
            result = tr("msg", name="test")
            # {0} can't be resolved by keyword args → KeyError or IndexError
            assert result == "Value: {0}"
        finally:
            i18n_mod._translations = original

    def test_tr_empty_template(self) -> None:
        """tr() returns empty string when the translation value is empty."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"empty_key": ""}
            assert tr("empty_key") == ""
        finally:
            i18n_mod._translations = original

    def test_tr_unicode_value(self) -> None:
        """tr() returns Unicode translations correctly."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"greeting": "こんにちは {name}"}
            result = tr("greeting", name="世界")
            assert result == "こんにちは 世界"
        finally:
            i18n_mod._translations = original

    def test_tr_with_braces_in_non_placeholder(self) -> None:
        """tr() handles templates that look like format strings but aren't."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"code": "Use {{braces}} for escaping"}
            result = tr("code")
            assert result == "Use {{braces}} for escaping"
        finally:
            i18n_mod._translations = original

    def test_tr_with_multiple_same_placeholder(self) -> None:
        """tr() replaces the same placeholder used multiple times."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"dup": "{x} and {x} again"}
            result = tr("dup", x="hello")
            assert result == "hello and hello again"
        finally:
            i18n_mod._translations = original

    def test_tr_no_kwargs_with_placeholder_returns_as_is(self) -> None:
        """tr() without kwargs returns template with placeholders unresolved."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"tmpl": "Hello {name}"}
            result = tr("tmpl")
            assert result == "Hello {name}"
        finally:
            i18n_mod._translations = original

    def test_tr_extra_kwargs_ignored(self) -> None:
        """tr() ignores extra kwargs that don't appear in the template."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = i18n_mod._translations.copy()
        try:
            i18n_mod._translations = {"simple": "Hello {name}"}
            result = tr("simple", name="Alice", extra="ignored")
            assert result == "Hello Alice"
        finally:
            i18n_mod._translations = original


# ── set_language edge cases ──────────────────────────────────


class TestSetLanguageEdgeCases:
    """Edge case tests for set_language()."""

    def _reset_language(self) -> None:
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        i18n_mod._current_language = "en-US"
        _load_translations("en-US")

    def test_set_language_empty_string_ignored(self) -> None:
        """set_language('') is ignored (not a valid code)."""
        original = current_language()
        set_language("")
        assert current_language() == original

    def test_set_language_none_like_string_ignored(self) -> None:
        """set_language with a string that looks like None is ignored."""
        original = current_language()
        set_language("None")
        assert current_language() == original

    def test_set_language_case_sensitive(self) -> None:
        """set_language is case-sensitive: 'EN-US' is not valid."""
        original = current_language()
        set_language("EN-US")
        assert current_language() == original

    def test_signal_receives_correct_code_on_each_switch(self) -> None:
        """Each language switch emits the correct code in order."""
        emitted: list[str] = []
        handler = lambda code: emitted.append(code)  # noqa: E731
        language_changed.connect(handler)
        try:
            set_language("vi")
            set_language("en-UK")
            assert emitted == ["vi", "en-UK"]
        finally:
            language_changed.disconnect(handler)
            self._reset_language()

    def test_rapid_language_switching(self) -> None:
        """Rapid switching between languages results in correct final state."""
        try:
            for _ in range(10):
                set_language("vi")
                set_language("en-UK")
            assert current_language() == "en-UK"
            set_language("vi")
            assert current_language() == "vi"
        finally:
            self._reset_language()

    def test_translations_change_on_language_switch(self) -> None:
        """Translations dict changes when switching between languages."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        try:
            set_language("en-UK")
            en_uk_keys = set(i18n_mod._translations.keys())
            i18n_mod._current_language = "invalid"  # force re-entry
            set_language("vi")
            vi_keys = set(i18n_mod._translations.keys())
            # Both should have the same keys
            assert en_uk_keys == vi_keys
        finally:
            self._reset_language()


# ── _load_translations edge cases ────────────────────────────


class TestLoadTranslationsEdgeCases:
    """Additional edge case tests for _load_translations()."""

    def test_empty_json_file(self, tmp_path: Path) -> None:
        """Empty JSON object results in empty translations dict."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        translations_dir = tmp_path / "translations"
        translations_dir.mkdir()
        json_file = translations_dir / "empty.json"
        json_file.write_text("{}", encoding="utf-8")

        with patch.object(i18n_mod, "_TRANSLATIONS_DIR", translations_dir):
            _load_translations("empty")
            assert i18n_mod._translations == {}

    def test_json_array_top_level(self, tmp_path: Path) -> None:
        """JSON array at top level (not dict) produces a non-dict result."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        translations_dir = tmp_path / "translations"
        translations_dir.mkdir()
        json_file = translations_dir / "array.json"
        json_file.write_text('["a", "b"]', encoding="utf-8")

        with patch.object(i18n_mod, "_TRANSLATIONS_DIR", translations_dir):
            _load_translations("array")
            # json.load succeeds with a list, stored as _translations
            assert isinstance(i18n_mod._translations, list)

    def test_unicode_content(self, tmp_path: Path) -> None:
        """Translation file with Unicode content loads correctly."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        translations_dir = tmp_path / "translations"
        translations_dir.mkdir()
        json_file = translations_dir / "unicode.json"
        data = {"greeting": "Привет", "farewell": "さようなら"}
        json_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        with patch.object(i18n_mod, "_TRANSLATIONS_DIR", translations_dir):
            _load_translations("unicode")
            assert i18n_mod._translations == data

    def test_large_translation_file(self, tmp_path: Path) -> None:
        """Large translation file with many keys loads correctly."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        translations_dir = tmp_path / "translations"
        translations_dir.mkdir()
        data = {f"key_{i}": f"value_{i}" for i in range(500)}
        json_file = translations_dir / "large.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        with patch.object(i18n_mod, "_TRANSLATIONS_DIR", translations_dir):
            _load_translations("large")
            assert len(i18n_mod._translations) == 500  # noqa: PLR2004

    def test_nested_json_values(self, tmp_path: Path) -> None:
        """Nested JSON values load (even if tr() may not use them well)."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        translations_dir = tmp_path / "translations"
        translations_dir.mkdir()
        data = {"nested": {"inner": "value"}}
        json_file = translations_dir / "nested.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        with patch.object(i18n_mod, "_TRANSLATIONS_DIR", translations_dir):
            _load_translations("nested")
            assert "nested" in i18n_mod._translations


# ── CallbackSignal additional tests ──────────────────────────


class TestCallbackSignalAdditional:
    """Additional tests for CallbackSignal."""

    def test_emit_with_no_args(self) -> None:
        """emit() with no arguments invokes callbacks with empty args."""
        signal = CallbackSignal()
        received: list[tuple] = []
        signal.connect(lambda *a: received.append(a))
        signal.emit()
        assert received == [()]

    def test_emit_with_kwargs_like_positional(self) -> None:
        """emit() passes positional args only (no kwargs support)."""
        signal = CallbackSignal()
        received: list[tuple] = []
        signal.connect(lambda *a: received.append(a))
        signal.emit("a", "b", "c")
        assert received == [("a", "b", "c")]

    def test_callback_error_does_not_prevent_others(self) -> None:
        """One callback's exception must NOT abort the rest of the chain.

        Critical for language-changed broadcasts: a single buggy
        listener used to escape ``emit`` and silently leave every
        later listener un-fired (the exact symptom of half-translated
        UI on language switch).  ``emit`` now traps each callback
        independently and logs the failure.
        """
        signal = CallbackSignal()
        results: list[str] = []

        def bad_callback(*a: object) -> None:
            raise ValueError("intentional")

        signal.connect(bad_callback)
        signal.connect(lambda *a: results.append("second"))

        # Should NOT raise — first callback's error is swallowed,
        # second callback still runs.
        signal.emit()
        assert results == ["second"]

    def test_disconnect_after_emit(self) -> None:
        """Disconnecting after emit still allows clean disconnect."""
        signal = CallbackSignal()
        results: list[str] = []
        cb = lambda *a: results.append("ok")  # noqa: E731
        signal.connect(cb)
        signal.emit()
        signal.disconnect(cb)
        signal.emit()
        assert results == ["ok"]  # Called only once

    def test_multiple_disconnects_is_silent_noop(self) -> None:
        """Double-disconnect is a silent no-op (race-tolerant design).

        Widget ``destroyed`` lambdas can fire after the conftest
        ``_callbacks.clear()`` has emptied the list — raising
        ValueError on the second disconnect would cascade as
        spurious test failures.  See ``CallbackSignal.disconnect``
        for the full rationale.
        """
        signal = CallbackSignal()
        cb = lambda: None  # noqa: E731
        signal.connect(cb)
        signal.disconnect(cb)
        # Second disconnect on already-removed callback: silent.
        signal.disconnect(cb)
        assert signal._callbacks == []

    def test_connect_different_lambdas(self) -> None:
        """Different lambda objects are registered independently."""
        signal = CallbackSignal()
        results: list[int] = []
        cb1 = lambda *a: results.append(1)  # noqa: E731
        cb2 = lambda *a: results.append(2)  # noqa: E731, PLR2004
        signal.connect(cb1)
        signal.connect(cb2)
        signal.emit()
        assert results == [1, 2]  # noqa: PLR2004


# ── UI_LANGUAGES tests ───────────────────────────────────────


class TestUILanguages:
    """Tests for the UI_LANGUAGES constant."""

    def test_ui_languages_is_list(self) -> None:
        """UI_LANGUAGES is a list."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        assert isinstance(UI_LANGUAGES, list)

    def test_ui_languages_has_at_least_three_entries(self) -> None:
        """UI_LANGUAGES has at least 3 entries."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        assert len(UI_LANGUAGES) >= 3  # noqa: PLR2004

    def test_ui_languages_tuples_have_three_elements(self) -> None:
        """Each UI_LANGUAGES entry is a 3-tuple."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        for entry in UI_LANGUAGES:
            assert len(entry) == 3, f"Entry {entry} doesn't have 3 elements"  # noqa: PLR2004

    def test_ui_languages_codes_are_unique(self) -> None:
        """All language codes in UI_LANGUAGES are unique."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        codes = [c for c, *_ in UI_LANGUAGES]
        assert len(codes) == len(set(codes))

    def test_ui_languages_display_names_are_unique(self) -> None:
        """All display names in UI_LANGUAGES are unique."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        names = [name for _, name, _ in UI_LANGUAGES]
        assert len(names) == len(set(names))

    def test_ui_languages_codes_are_strings(self) -> None:
        """All language codes are non-empty strings."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        for code, *_ in UI_LANGUAGES:
            assert isinstance(code, str)
            assert len(code) > 0

    def test_ui_languages_contains_en_us(self) -> None:
        """UI_LANGUAGES contains en-US."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        codes = {c for c, *_ in UI_LANGUAGES}
        assert "en-US" in codes

    def test_ui_languages_contains_vi(self) -> None:
        """UI_LANGUAGES contains vi."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        codes = {c for c, *_ in UI_LANGUAGES}
        assert "vi" in codes


# ── Translation consistency tests ────────────────────────────


class TestTranslationConsistency:
    """Tests for consistency across translation files."""

    def _load_json(self, locale: str) -> dict:
        json_path = (
            Path(__file__).parent.parent
            / "src"
            / "constants"
            / "translations"
            / f"{locale}.json"
        )
        with json_path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def test_no_empty_values_in_en_uk(self) -> None:
        """en-UK.json has no empty string values."""
        data = self._load_json("en-UK")
        for key, value in data.items():
            assert len(value) > 0, f"en-UK/{key} has empty value"

    def test_no_empty_values_in_vi(self) -> None:
        """vi.json has no empty string values."""
        data = self._load_json("vi")
        for key, value in data.items():
            assert len(value) > 0, f"vi/{key} has empty value"

    def test_all_keys_are_strings(self) -> None:
        """All translation keys are strings."""
        for locale in ("en-US", "en-UK", "vi"):
            data = self._load_json(locale)
            for key in data:
                assert isinstance(key, str), f"{locale}/{key} key is not a string"

    def test_format_placeholders_consistent(self) -> None:
        """Placeholders in en-US also appear in other translations."""
        import re  # noqa: PLC0415

        en_us = self._load_json("en-US")
        for locale in ("en-UK", "vi"):
            other = self._load_json(locale)
            for key in en_us:
                us_placeholders = set(re.findall(r"\{(\w+)\}", en_us[key]))
                if us_placeholders and key in other:
                    other_placeholders = set(re.findall(r"\{(\w+)\}", other[key]))
                    assert us_placeholders == other_placeholders, (
                        f"{locale}/{key}: placeholders differ. "
                        f"US={us_placeholders}, {locale}={other_placeholders}"
                    )

    def test_en_us_keys_are_dotted(self) -> None:
        """Most en-US keys use dotted notation (sanity check)."""
        data = self._load_json("en-US")
        dotted_count = sum(1 for k in data if "." in k)
        # At least half should be dotted
        assert dotted_count > len(data) // 2

    def test_tr_returns_en_us_value_for_known_key(self) -> None:
        """tr() with en-US active returns the value from en-US.json."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = current_language()
        try:
            i18n_mod._current_language = "invalid"  # force
            set_language("en-US")
            en_data = self._load_json("en-US")
            key = "btn.ok"
            assert tr(key) == en_data[key]
        finally:
            if current_language() != original:
                i18n_mod._current_language = "invalid"
                set_language(original)

    def test_tr_returns_vi_value_for_known_key(self) -> None:
        """tr() with vi active returns the value from vi.json."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        original = current_language()
        try:
            set_language("vi")
            vi_data = self._load_json("vi")
            key = "btn.ok"
            assert tr(key) == vi_data[key]
        finally:
            i18n_mod._current_language = "invalid"
            set_language(original if original != "invalid" else "en-US")

    def test_language_changed_signal_is_callback_signal(self) -> None:
        """language_changed is a CallbackSignal instance."""
        assert isinstance(language_changed, CallbackSignal)

    def test_multiple_listeners_on_language_changed(self) -> None:
        """Multiple listeners all receive the language change notification."""
        import src.constants.i18n as i18n_mod  # noqa: PLC0415

        results1: list[str] = []
        results2: list[str] = []
        h1 = lambda c: results1.append(c)  # noqa: E731
        h2 = lambda c: results2.append(c)  # noqa: E731
        language_changed.connect(h1)
        language_changed.connect(h2)
        try:
            set_language("vi")
            assert results1 == ["vi"]
            assert results2 == ["vi"]
        finally:
            language_changed.disconnect(h1)
            language_changed.disconnect(h2)
            i18n_mod._current_language = "en-US"
            _load_translations("en-US")


# ===========================================================================
# EXPANDED: tr() parameter formatting edge cases
# ===========================================================================


def test_tr_with_multiple_kwargs() -> None:
    """tr() substitutes multiple keyword arguments."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original_translations = i18n_mod._translations.copy()
    try:
        i18n_mod._translations["test.multi"] = "Hello {name}, you have {count} items"
        result = tr("test.multi", name="Alice", count=5)
        assert result == "Hello Alice, you have 5 items"
    finally:
        i18n_mod._translations = original_translations


def test_tr_format_missing_kwarg_returns_template() -> None:
    """tr() returns template unchanged when a kwarg is missing."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original_translations = i18n_mod._translations.copy()
    try:
        i18n_mod._translations["test.missing"] = "Hello {name}, {missing_key}"
        result = tr("test.missing", name="Bob")
        assert result == "Hello {name}, {missing_key}"
    finally:
        i18n_mod._translations = original_translations


def test_tr_format_extra_kwargs_ignored() -> None:
    """tr() ignores extra keyword arguments not in the template."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original_translations = i18n_mod._translations.copy()
    try:
        i18n_mod._translations["test.extra"] = "Hello {name}"
        result = tr("test.extra", name="Charlie", extra_arg="ignored")
        assert result == "Hello Charlie"
    finally:
        i18n_mod._translations = original_translations


def test_tr_format_with_integer_arg() -> None:
    """tr() handles integer arguments correctly."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original_translations = i18n_mod._translations.copy()
    try:
        i18n_mod._translations["test.int"] = "Count: {count}"
        assert tr("test.int", count=42) == "Count: 42"
    finally:
        i18n_mod._translations = original_translations


def test_tr_format_with_empty_string_arg() -> None:
    """tr() handles empty string arguments correctly."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original_translations = i18n_mod._translations.copy()
    try:
        i18n_mod._translations["test.empty"] = "Value: [{val}]"
        assert tr("test.empty", val="") == "Value: []"
    finally:
        i18n_mod._translations = original_translations


# ===========================================================================
# EXPANDED: set_language edge cases
# ===========================================================================


def test_set_language_skips_same_language() -> None:
    """set_language() does not emit signal when language is already set."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    emitted: list[str] = []
    handler = lambda c: emitted.append(c)  # noqa: E731
    language_changed.connect(handler)
    try:
        i18n_mod._current_language = "en-US"
        _load_translations("en-US")
        set_language("en-US")
        assert emitted == []
    finally:
        language_changed.disconnect(handler)
        if current_language() != original:
            i18n_mod._current_language = "invalid"
            set_language(original if original != "invalid" else "en-US")


def test_set_language_switches_between_all_valid_languages() -> None:
    """set_language() can switch among all valid UI languages."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    try:
        for code, _, _ in UI_LANGUAGES:
            i18n_mod._current_language = "invalid"
            set_language(code)
            assert current_language() == code
    finally:
        i18n_mod._current_language = "invalid"
        set_language(original if original != "invalid" else "en-US")


def test_set_language_rejects_empty_string() -> None:
    """set_language() ignores empty string."""
    original = current_language()
    set_language("")
    assert current_language() == original


def test_set_language_rejects_none_like() -> None:
    """set_language() ignores a language code not in UI_LANGUAGES."""
    original = current_language()
    set_language("xx-XX")
    assert current_language() == original


def test_set_language_rejects_partial_match() -> None:
    """set_language() does not accept partial locale codes."""
    original = current_language()
    set_language("en")
    assert current_language() == original


# ===========================================================================
# EXPANDED: _set_initial_language edge cases
# ===========================================================================


def test_set_initial_language_does_not_emit_signal() -> None:
    """_set_initial_language() does not emit language_changed."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    emitted: list[str] = []
    handler = lambda c: emitted.append(c)  # noqa: E731
    language_changed.connect(handler)
    try:
        _set_initial_language("vi")
        assert emitted == []
        assert current_language() == "vi"
    finally:
        language_changed.disconnect(handler)
        i18n_mod._current_language = "invalid"
        set_language(original if original != "invalid" else "en-US")


def test_set_initial_language_invalid_keeps_default() -> None:
    """_set_initial_language() with invalid code still loads translations."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    try:
        i18n_mod._current_language = "en-US"
        _set_initial_language("xx-INVALID")
        # Language stays unchanged but translations are loaded
        assert current_language() == "en-US"
    finally:
        if current_language() != original:
            i18n_mod._current_language = "invalid"
            set_language(original if original != "invalid" else "en-US")


def test_set_initial_language_all_valid_codes() -> None:
    """_set_initial_language() accepts all valid UI language codes."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    try:
        for code, _, _ in UI_LANGUAGES:
            _set_initial_language(code)
            assert current_language() == code
    finally:
        i18n_mod._current_language = "invalid"
        set_language(original if original != "invalid" else "en-US")


# ===========================================================================
# EXPANDED: _load_translations edge cases
# ===========================================================================


def test_load_translations_nonexistent_clears_translations() -> None:
    """_load_translations() with nonexistent file clears translations."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    old_translations = i18n_mod._translations.copy()
    try:
        _load_translations("xx-NONEXISTENT")
        assert i18n_mod._translations == {}
    finally:
        i18n_mod._translations = old_translations
        if current_language() != original:
            i18n_mod._current_language = original


def test_load_translations_populates_translations() -> None:
    """_load_translations() with valid file populates _translations."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    old_translations = i18n_mod._translations.copy()
    try:
        _load_translations("en-US")
        assert len(i18n_mod._translations) > 0
        assert isinstance(i18n_mod._translations, dict)
    finally:
        i18n_mod._translations = old_translations
        if current_language() != original:
            i18n_mod._current_language = original


# ===========================================================================
# EXPANDED: current_language edge cases
# ===========================================================================


def test_current_language_returns_string() -> None:
    """current_language() always returns a string."""
    assert isinstance(current_language(), str)


def test_current_language_after_set() -> None:
    """current_language() reflects the last set_language() call."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    try:
        i18n_mod._current_language = "invalid"
        set_language("vi")
        assert current_language() == "vi"
        i18n_mod._current_language = "vi"
        set_language("en-UK")
        assert current_language() == "en-UK"
    finally:
        i18n_mod._current_language = "invalid"
        set_language(original if original != "invalid" else "en-US")


# ===========================================================================
# EXPANDED: tr() with real translation keys
# ===========================================================================


def test_tr_btn_cancel_in_all_languages() -> None:
    """tr('btn.cancel') returns a non-empty string in all languages."""
    import json  # noqa: PLC0415

    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    try:
        for code, _, _ in UI_LANGUAGES:
            json_path = i18n_mod._TRANSLATIONS_DIR / f"{code}.json"
            if json_path.exists():
                with json_path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                if "btn.cancel" in data:
                    i18n_mod._current_language = "invalid"
                    set_language(code)
                    result = tr("btn.cancel")
                    assert result and result != "btn.cancel"
    finally:
        i18n_mod._current_language = "invalid"
        set_language(original if original != "invalid" else "en-US")


def test_tr_returns_key_for_nonexistent_key() -> None:
    """tr() returns the key itself when translation is missing."""
    result = tr("completely.nonexistent.key.12345")
    assert result == "completely.nonexistent.key.12345"


def test_tr_returns_key_with_dots() -> None:
    """tr() correctly returns dotted key when translation is missing."""
    result = tr("a.b.c.d.e")
    assert result == "a.b.c.d.e"


def test_tr_empty_key_returns_empty_or_key() -> None:
    """tr('') returns either an empty string or the empty key."""
    result = tr("")
    assert isinstance(result, str)


# ===========================================================================
# EXPANDED: language_changed signal edge cases
# ===========================================================================


def test_language_changed_disconnect() -> None:
    """Disconnected handler no longer receives signals."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    results: list[str] = []
    handler = lambda c: results.append(c)  # noqa: E731
    language_changed.connect(handler)
    language_changed.disconnect(handler)
    try:
        i18n_mod._current_language = "invalid"
        set_language("vi")
        assert results == []
    finally:
        i18n_mod._current_language = "invalid"
        set_language(original if original != "invalid" else "en-US")


def test_language_changed_emits_new_code() -> None:
    """language_changed emits the new language code, not the old one."""
    import src.constants.i18n as i18n_mod  # noqa: PLC0415

    original = current_language()
    emitted: list[str] = []
    handler = lambda c: emitted.append(c)  # noqa: E731
    language_changed.connect(handler)
    try:
        i18n_mod._current_language = "invalid"
        set_language("en-UK")
        assert emitted == ["en-UK"]
    finally:
        language_changed.disconnect(handler)
        i18n_mod._current_language = "invalid"
        set_language(original if original != "invalid" else "en-US")


# ===========================================================================
# EXPANDED: UI_LANGUAGES validation
# ===========================================================================


def test_ui_languages_all_have_three_elements() -> None:
    """Every entry in UI_LANGUAGES is a 3-tuple."""
    for entry in UI_LANGUAGES:
        assert len(entry) == 3


def test_ui_languages_codes_are_unique() -> None:
    """All locale codes in UI_LANGUAGES are unique."""
    codes = [c for c, _, _ in UI_LANGUAGES]
    assert len(codes) == len(set(codes))


def test_ui_languages_display_names_are_non_empty() -> None:
    """All display names in UI_LANGUAGES are non-empty strings."""
    for _, name, _ in UI_LANGUAGES:
        assert isinstance(name, str) and len(name) > 0


def test_ui_languages_flag_icons_are_non_empty() -> None:
    """All flag icon names in UI_LANGUAGES are non-empty strings."""
    for _, _, flag in UI_LANGUAGES:
        assert isinstance(flag, str) and len(flag) > 0


def test_ui_languages_contains_en_us() -> None:
    """UI_LANGUAGES contains en-US."""
    codes = {c for c, _, _ in UI_LANGUAGES}
    assert "en-US" in codes


def test_ui_languages_contains_vi() -> None:
    """UI_LANGUAGES contains vi."""
    codes = {c for c, _, _ in UI_LANGUAGES}
    assert "vi" in codes


# ── Locale key parity ──────────────────────────────────────────


def test_all_locales_have_identical_key_sets_against_en_us() -> None:
    """Every locale file contains exactly the same keys as en-US.

    Drift here means users on the affected locale see raw keys
    leaking into the UI (``tr()`` falls back to the key string
    when the lookup misses).  The previous failure mode: when a
    feature was added or removed, only some locales were updated,
    and 13 of 15 fell out of sync silently.

    Treats en-US as canonical.  Both directions matter — extras
    in a non-en-US locale mean en-US is missing a key the rest
    have, which leaks the raw key to the largest user base.
    """
    translations_dir = (
        Path(__file__).parent.parent / "src" / "constants" / "translations"
    )
    en_us_path = translations_dir / "en-US.json"
    assert en_us_path.exists(), "en-US.json (canonical locale) must exist"

    canonical = set(json.loads(en_us_path.read_text(encoding="utf-8")).keys())

    drift: dict[str, dict[str, list[str]]] = {}
    for path in sorted(translations_dir.glob("*.json")):
        if path.name == "en-US.json":
            continue
        keys = set(json.loads(path.read_text(encoding="utf-8")).keys())
        missing = sorted(canonical - keys)
        extra = sorted(keys - canonical)
        if missing or extra:
            drift[path.stem] = {"missing": missing, "extra": extra}

    assert not drift, (
        "Locale key drift detected (each locale must match en-US):\n"
        + "\n".join(
            f"  {locale}: -{len(d['missing'])} +{len(d['extra'])}"
            + ("".join(f"\n    MISSING: {k}" for k in d["missing"][:5]))
            + ("".join(f"\n    EXTRA:   {k}" for k in d["extra"][:5]))
            for locale, d in drift.items()
        )
    )


# ── Locale value-quality checks ──────────────────────────────────────


def test_no_locale_uses_raw_key_as_translation_value() -> None:
    """A value that equals its key is an untranslated copy-paste bug.

    Common pattern when a translator forgot to translate: the JSON
    value just echoes the key path (e.g.
    ``"settings.piper_installed_langs": "settings.piper_installed_langs"``).
    Neither parity nor empty-value checks catch this — the value is
    non-empty and the key exists in every locale.
    """
    translations_dir = (
        Path(__file__).parent.parent / "src" / "constants" / "translations"
    )
    offenders: dict[str, list[str]] = {}
    for path in sorted(translations_dir.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        bad = [k for k, v in d.items() if v == k]
        if bad:
            offenders[path.stem] = bad

    assert not offenders, (
        "Locale values must not equal their keys (untranslated copy-paste):\n"
        + "\n".join(
            f"  {locale}: {len(keys)} key(s) — first 3: {keys[:3]}"
            for locale, keys in offenders.items()
        )
    )


def test_no_locale_value_has_trailing_whitespace() -> None:
    """Trailing whitespace leaks into the UI as misaligned labels.

    Trailing whitespace is almost never intentional — a translator
    hitting Enter at the end of a string adds a stray newline that
    survives JSON serialization but renders as visible whitespace.
    Leading whitespace IS sometimes intentional (e.g. inline-suffix
    composition like ``" — run <code>{cmd}</code>"`` appended to a
    sibling label) so we check trailing only.
    """
    translations_dir = (
        Path(__file__).parent.parent / "src" / "constants" / "translations"
    )
    offenders: dict[str, list[str]] = {}
    for path in sorted(translations_dir.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        bad = [k for k, v in d.items() if isinstance(v, str) and v != v.rstrip()]
        if bad:
            offenders[path.stem] = bad

    assert not offenders, (
        "Locale values must not have trailing whitespace:\n"
        + "\n".join(f"  {locale}: {keys[:3]}" for locale, keys in offenders.items())
    )


def test_locale_values_have_balanced_html_tags() -> None:
    """Open/close HTML tag counts must match per value.

    A banner that opens ``<b>`` without ``</b>`` leaks markup into
    surrounding UI elements that share the same QLabel parent.  This
    is a quick balance check — counts of ``<a>`` / ``</a>`` and
    ``<b>`` / ``</b>`` tags must match per value.  Self-closing /
    void tags (``<br>``, ``<hr>``, ``<img>``) are excluded.
    """
    import re  # noqa: PLC0415

    translations_dir = (
        Path(__file__).parent.parent / "src" / "constants" / "translations"
    )
    # Only check tags that have a closing form in this codebase's
    # banners.  Add more here if new tags are introduced.
    paired_tags = ("a", "b", "i", "code", "p")

    offenders: list[str] = []
    for path in sorted(translations_dir.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        for key, value in d.items():
            if not isinstance(value, str):
                continue
            for tag in paired_tags:
                opens = len(
                    re.findall(rf"<{tag}\b[^>]*>", value, flags=re.IGNORECASE),
                )
                closes = len(
                    re.findall(rf"</{tag}>", value, flags=re.IGNORECASE),
                )
                if opens != closes:
                    offenders.append(
                        f"{path.stem}::{key} — <{tag}>={opens} </{tag}>={closes}",
                    )

    assert not offenders, (
        "Unbalanced HTML tags detected (would leak markup into UI):\n  "
        + "\n  ".join(offenders[:10])
        + (f"\n  ... +{len(offenders) - 10} more" if len(offenders) > 10 else "")
    )


def test_format_placeholders_are_consistent_across_locales() -> None:
    """Placeholder sets must match across locales for every key.

    A locale missing ``{count}`` (or adding a stray ``{foo}``) makes
    ``tr(key, count=N)`` raise ``KeyError`` at runtime — silent until
    the localised value is actually rendered.  Compare placeholder
    sets per key across all locales to en-US.
    """
    import re  # noqa: PLC0415

    translations_dir = (
        Path(__file__).parent.parent / "src" / "constants" / "translations"
    )
    en_us = json.loads(
        (translations_dir / "en-US.json").read_text(encoding="utf-8"),
    )
    placeholder_pat = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    def _placeholders(value: str) -> set[str]:
        if not isinstance(value, str):
            return set()
        return set(placeholder_pat.findall(value))

    offenders: list[str] = []
    for path in sorted(translations_dir.glob("*.json")):
        if path.name == "en-US.json":
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        for key, en_value in en_us.items():
            en_holders = _placeholders(en_value)
            other_holders = _placeholders(d.get(key, ""))
            if en_holders != other_holders:
                offenders.append(
                    f"{path.stem}::{key} — en={sorted(en_holders)} "
                    f"loc={sorted(other_holders)}",
                )

    assert not offenders, (
        "Format-placeholder drift (will raise KeyError in tr()):\n  "
        + "\n  ".join(offenders[:10])
        + (f"\n  ... +{len(offenders) - 10} more" if len(offenders) > 10 else "")
    )


class TestVietnameseLanguageSortOrder:
    """Vietnamese (and other accent-heavy) locales sort accents inline.

    Bug surfaced from a Vietnamese user screenshot: the language picker
    placed "Tiếng Đan Mạch" (Danish) AFTER "Tiếng Việt" (Vietnamese)
    because plain ``casefold()`` doesn't break ``Đ`` into base letter
    + combining mark — so it sorted as if it were beyond Z in the
    alphabet.  Fix routes the sort key through ``normalize_for_search``
    which strips combining marks AND maps non-decomposable extended
    Latin (Đ, Ł, Ø, Å, Æ, Œ, Þ, Ð) to base letters.
    """

    def test_vietnamese_locale_places_d_with_d(self) -> None:
        """In vi locale, "Đan Mạch" (Danish) sorts between D and E.

        Pin the linguistic invariant: Danish "Tiếng Đan Mạch" must
        appear after "Tiếng Croatia" (C) and before "Tiếng Estonia" (E)
        — between D-words.  Plain casefold sort would drop it after
        "Tiếng Việt" (V) which is the regression we're guarding.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.languages import (  # noqa: PLC0415
            iter_languages_sorted_for_ui,
        )

        _set_initial_language("vi")
        try:
            order = [eng for _loc, eng, _ic, _nat in iter_languages_sorted_for_ui()]
            danish_idx = order.index("Danish")
            croatian_idx = order.index("Croatian")
            estonian_idx = order.index("Estonian")
            vietnamese_idx = order.index("Vietnamese")
            assert croatian_idx < danish_idx < estonian_idx, (
                f"Vietnamese sort: 'Tiếng Đan Mạch' (Danish) must land "
                f"between Croatian (C) and Estonian (E); got order "
                f"Croatian={croatian_idx}, Danish={danish_idx}, "
                f"Estonian={estonian_idx}"
            )
            assert danish_idx < vietnamese_idx, (
                f"Danish must sort BEFORE Vietnamese in vi locale "
                f"(Danish={danish_idx}, Vietnamese={vietnamese_idx}); "
                f"the bug placed Đan Mạch after Việt because Đ wasn't "
                f"normalised to D"
            )
        finally:
            _set_initial_language("en-US")

    def test_vietnamese_locale_places_arabic_first(self) -> None:
        """In vi locale, "Tiếng Ả Rập" (Arabic) sorts as A — first.

        Ả (a-with-hook-above) decomposes via NFKD to A + combining
        mark, so this case actually works WITHOUT the
        extended-Latin map — but pin it anyway as a smoke test that
        Arabic lands at the alphabet's start and not under Ả-after-Z.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.languages import (  # noqa: PLC0415
            iter_languages_sorted_for_ui,
        )

        _set_initial_language("vi")
        try:
            order = [eng for _loc, eng, _ic, _nat in iter_languages_sorted_for_ui()]
            assert order[0] == "Arabic", (
                f"Vietnamese sort: 'Tiếng Ả Rập' (Arabic) must be the "
                f"first entry (Ả → A in alphabet); got order[0]={order[0]!r}"
            )
        finally:
            _set_initial_language("en-US")
