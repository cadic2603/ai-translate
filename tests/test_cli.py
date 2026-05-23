"""Unit tests for the CLI entry point (src/cli.py).

Covers argument parsing, language validation, file validation, config
construction, the main() bootstrap flow, and exit code behavior.
"""

import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from src.cli import (
    EXIT_ALL_FAILED,
    EXIT_ARGS_ERROR,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_PARTIAL_FAILURE,
    EXIT_SETUP_ERROR,
    _build_parser,
    _resolve_language,
    _validate_files,
)

# Lazy imports inside main() are patched at their SOURCE modules.
_PATH_MGR = "src.utils.path_manager"
_DB = "src.core.database"
_CFG_MGR = "src.utils.config_manager"
_TRANSLATOR = "src.core.translator"


# ===================================================================
# _resolve_language()
# ===================================================================


class TestResolveLanguage:
    """Tests for the _resolve_language helper."""

    def test_exact_match(self) -> None:
        """Exact canonical label is returned unchanged."""
        assert _resolve_language("French") == "French"

    def test_case_insensitive(self) -> None:
        """Case-insensitive matching returns the canonical label."""
        assert _resolve_language("french") == "French"
        assert _resolve_language("VIETNAMESE") == "Vietnamese"

    def test_language_with_parentheses(self) -> None:
        """Languages with parenthetical qualifiers are matched."""
        assert _resolve_language("chinese (simplified)") == "Chinese (Simplified)"
        assert _resolve_language("English (US)") == "English (US)"

    def test_empty_string_returns_empty(self) -> None:
        """Empty string returns empty (auto-detect)."""
        assert _resolve_language("") == ""

    def test_unknown_returns_none(self) -> None:
        """Unknown language returns None."""
        assert _resolve_language("Klingon") is None
        assert _resolve_language("xyz") is None

    def test_whitespace_only_treated_as_auto_detect(self) -> None:
        """Regression: ``--source " "`` resolves to auto-detect.

        A shell-quoted whitespace value (often coming from CI scripts
        or accidentally-typed ``--source ''``) is shorthand for
        "let the engine decide" — without the strip, the lookup
        treats it as an unknown language and the CLI errors out.
        """
        for whitespace in (" ", "  ", "\t", "\n", "  \t  "):
            assert _resolve_language(whitespace) == "", (
                f"whitespace {whitespace!r} should auto-detect"
            )

    def test_leading_trailing_whitespace_stripped(self) -> None:
        """Padding whitespace around a real language is forgiven."""
        assert _resolve_language("  French  ") == "French"
        assert _resolve_language("\tVietnamese\n") == "Vietnamese"


class TestSuggestLanguageMatches:
    """Tests for the _suggest_language_matches helper."""

    def test_substring_match_returns_variants(self) -> None:
        """Ambiguous prefix returns every matching canonical language."""
        from src.cli import _suggest_language_matches  # noqa: PLC0415

        matches = _suggest_language_matches("chinese")
        assert "Chinese (Simplified)" in matches
        assert "Chinese (Traditional)" in matches

    def test_whitespace_only_returns_empty(self) -> None:
        """Regression: a whitespace-only label returns no suggestions.

        Without the strip, ``"".lower()`` (= ``""``) is a substring of
        every language label — the user would see a "Did you mean:"
        hint listing every supported language, drowning the message.
        """
        from src.cli import _suggest_language_matches  # noqa: PLC0415

        assert _suggest_language_matches(" ") == []
        assert _suggest_language_matches("") == []
        assert _suggest_language_matches("\t\n") == []


class TestResolveOcrMethod:
    """Tests for the _resolve_ocr_method helper."""

    def test_exact_canonical_match(self) -> None:
        """Exact canonical identifier is returned unchanged."""
        from src.cli import _resolve_ocr_method  # noqa: PLC0415

        assert _resolve_ocr_method("TesseractOCR") == "TesseractOCR"
        assert _resolve_ocr_method("EasyOCR") == "EasyOCR"
        assert _resolve_ocr_method("Google Cloud OCR") == "Google Cloud OCR"

    def test_friendly_spellings_match(self) -> None:
        """Case- and punctuation-insensitive spellings resolve to canonical."""
        from src.cli import _resolve_ocr_method  # noqa: PLC0415

        assert _resolve_ocr_method("tesseract") == "TesseractOCR"
        assert _resolve_ocr_method("easyocr") == "EasyOCR"
        assert _resolve_ocr_method("googlecloud") == "Google Cloud OCR"

    def test_unknown_returns_none(self) -> None:
        """Unknown OCR method returns None."""
        from src.cli import _resolve_ocr_method  # noqa: PLC0415

        assert _resolve_ocr_method("Bogus") is None
        assert _resolve_ocr_method("") is None


# ===================================================================
# _validate_files()
# ===================================================================


class TestValidateFiles:
    """Tests for the _validate_files helper."""

    def test_existing_supported_file(self, tmp_path: Path) -> None:
        """A valid supported file is included in the output."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = _validate_files([f])
        assert len(result) == 1
        assert result[0] == f.resolve()

    def test_nonexistent_file_skipped(self, tmp_path: Path) -> None:
        """A file that doesn't exist is skipped."""
        f = tmp_path / "missing.docx"
        result = _validate_files([f])
        assert result == []

    def test_unsupported_extension_skipped(self, tmp_path: Path) -> None:
        """A file with an unsupported extension is skipped."""
        f = tmp_path / "data.xyz"
        f.write_text("data")
        result = _validate_files([f])
        assert result == []

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        """Only valid files are returned from a mixed set."""
        good = tmp_path / "report.docx"
        good.write_text("content")
        bad = tmp_path / "photo.xyz"
        bad.write_text("data")
        missing = tmp_path / "gone.pdf"
        result = _validate_files([good, bad, missing])
        assert len(result) == 1
        assert result[0] == good.resolve()

    def test_multiple_valid_files(self, tmp_path: Path) -> None:
        """Multiple valid files are all returned."""
        files = []
        for name in ["a.txt", "b.md", "c.html"]:
            f = tmp_path / name
            f.write_text("x")
            files.append(f)
        result = _validate_files(files)
        assert len(result) == 3


# ===================================================================
# _build_parser()
# ===================================================================


class TestBuildParser:
    """Tests for the argument parser."""

    def test_target_defaults_to_none(self) -> None:
        """--target defaults to None when omitted (validated later in main)."""
        parser = _build_parser()
        args = parser.parse_args(["file.txt"])
        assert args.target is None

    def test_minimal_args(self) -> None:
        """Minimal valid args: file + --target."""
        parser = _build_parser()
        args = parser.parse_args(["file.txt", "--target", "French"])
        assert args.target == "French"
        assert args.files == [Path("file.txt")]
        assert args.source == ""
        assert args.output is None
        assert args.quiet is False
        assert args.verbose is False

    def test_short_flags(self) -> None:
        """-t, -s, -o, -q short flags work."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "f.docx",
                "-t",
                "German",
                "-s",
                "English (US)",
                "-o",
                "/tmp/out",
                "-q",
            ]
        )
        assert args.target == "German"
        assert args.source == "English (US)"
        assert args.output == Path("/tmp/out")
        assert args.quiet is True

    def test_boolean_flags_default_false(self) -> None:
        """Translation boolean flags default to False."""
        parser = _build_parser()
        args = parser.parse_args(["f.txt", "-t", "French"])
        assert args.translate_images is False
        assert args.translate_comments is False
        assert args.translate_shapes is False
        assert args.translate_notes is False
        assert args.translate_sheet_names is False
        assert args.convert_legacy is False
        assert args.convert_odf is False
        assert args.keep_history is False

    def test_boolean_flags_enabled(self) -> None:
        """Boolean flags can be explicitly enabled."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "f.xlsx",
                "-t",
                "French",
                "--translate-images",
                "--translate-comments",
                "--translate-shapes",
                "--translate-notes",
                "--translate-sheet-names",
                "--convert-legacy",
                "--convert-odf",
                "--keep-history",
            ]
        )
        assert args.translate_images is True
        assert args.translate_comments is True
        assert args.translate_shapes is True
        assert args.translate_notes is True
        assert args.translate_sheet_names is True
        assert args.convert_legacy is True
        assert args.convert_odf is True
        assert args.keep_history is True

    def test_no_boolean_flags(self) -> None:
        """--no-translate-images etc. explicitly disable flags."""
        parser = _build_parser()
        args = parser.parse_args(
            [
                "f.txt",
                "-t",
                "French",
                "--no-translate-images",
                "--no-translate-comments",
            ]
        )
        assert args.translate_images is False
        assert args.translate_comments is False

    def test_list_languages_flag(self) -> None:
        """--list-languages flag is recognized."""
        parser = _build_parser()
        args = parser.parse_args(["f.txt", "-t", "French", "--list-languages"])
        assert args.list_languages is True

    def test_multiple_files(self) -> None:
        """Multiple positional file arguments are accepted."""
        parser = _build_parser()
        args = parser.parse_args(["a.txt", "b.pdf", "c.docx", "-t", "French"])
        assert len(args.files) == 3

    def test_ocr_method(self) -> None:
        """--ocr-method accepts a value."""
        parser = _build_parser()
        args = parser.parse_args(["f.png", "-t", "French", "--ocr-method", "EasyOCR"])
        assert args.ocr_method == "EasyOCR"


# ===================================================================
# main() — list languages
# ===================================================================


class TestMainListLanguages:
    """Tests for --list-languages early exit."""

    def test_prints_languages_and_exits(self, capsys: pytest.CaptureFixture) -> None:
        """--list-languages prints all languages and exits with 0."""
        with (
            patch("sys.argv", ["cli", "--list-languages"]),
            pytest.raises(SystemExit, match=str(EXIT_OK)),
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        captured = capsys.readouterr()
        assert "French" in captured.out
        assert "Vietnamese" in captured.out
        assert "Japanese" in captured.out


# ===================================================================
# main() — argument validation errors
# ===================================================================


class TestMainArgValidation:
    """Tests for argument validation in main()."""

    def _run_main(self, argv: list[str]) -> None:
        """Runs main() with the given argv, patching bootstrap deps."""
        with (
            patch("sys.argv", ["cli", *argv]),
            patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            patch(f"{_PATH_MGR}.configure_logging"),
            patch(f"{_DB}.init_db"),
        ):
            from src.cli import main  # noqa: PLC0415

            main()

    def test_unknown_target_language(self) -> None:
        """Unknown target language exits with EXIT_ARGS_ERROR."""
        with pytest.raises(SystemExit) as exc_info:
            self._run_main(["f.txt", "-t", "Klingon"])
        assert exc_info.value.code == EXIT_ARGS_ERROR

    def test_unknown_source_language(self, tmp_path: Path) -> None:
        """Unknown source language exits with EXIT_ARGS_ERROR."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with pytest.raises(SystemExit) as exc_info:
            self._run_main([str(f), "-t", "French", "-s", "Elvish"])
        assert exc_info.value.code == EXIT_ARGS_ERROR

    def test_no_valid_files(self) -> None:
        """No valid input files exits with EXIT_ARGS_ERROR."""
        with pytest.raises(SystemExit) as exc_info:
            self._run_main(["/nonexistent/file.txt", "-t", "French"])
        assert exc_info.value.code == EXIT_ARGS_ERROR

    def test_missing_target_exits(self) -> None:
        """Omitting --target exits with argparse error code 2."""
        with pytest.raises(SystemExit) as exc_info:
            self._run_main(["file.txt"])
        assert exc_info.value.code == EXIT_ARGS_ERROR

    def test_missing_files_exits(self) -> None:
        """Omitting positional files exits with argparse error code 2."""
        with pytest.raises(SystemExit) as exc_info:
            self._run_main(["-t", "French"])
        assert exc_info.value.code == EXIT_ARGS_ERROR


# ===================================================================
# main() — LLM setup validation
# ===================================================================


class TestMainLLMSetup:
    """Tests for LLM setup validation in main()."""

    def test_llm_not_configured(self, tmp_path: Path) -> None:
        """Missing LLM config exits with EXIT_SETUP_ERROR."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with (
            patch("sys.argv", ["cli", str(f), "-t", "French"]),
            patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            patch(f"{_PATH_MGR}.configure_logging"),
            patch(f"{_DB}.init_db"),
            patch(f"{_CFG_MGR}.check_llm_setup", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_SETUP_ERROR


# ===================================================================
# main() — full pipeline
# ===================================================================


class TestMainPipeline:
    """Tests for the main translation pipeline flow."""

    @pytest.fixture()
    def _setup(self, tmp_path: Path) -> dict:
        """Creates a temp file and patches all external deps."""
        f = tmp_path / "report.txt"
        f.write_text("Hello world")

        patches = {
            "argv": patch(
                "sys.argv",
                [
                    "cli",
                    str(f),
                    "-t",
                    "French",
                    "-q",
                ],
            ),
            "ensure_dirs": patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            "configure_logging": patch(f"{_PATH_MGR}.configure_logging"),
            "init_db": patch(f"{_DB}.init_db"),
            "check_llm": patch(f"{_CFG_MGR}.check_llm_setup", return_value=True),
            "check_ocr": patch(f"{_CFG_MGR}.check_ocr_setup", return_value=False),
            "setup_tasks": patch(
                f"{_TRANSLATOR}.setup_translation_tasks",
                return_value=[(1, str(f), "", "French")],
            ),
            "run_pipeline": patch(f"{_TRANSLATOR}.run_translation_pipeline"),
            "get_status": patch(
                f"{_DB}.get_history_entry_status",
                return_value="Done",
            ),
        }

        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()

        mocks["_file"] = f
        yield mocks

        for p in patches.values():
            p.stop()

    def test_successful_translation(self, _setup: dict) -> None:
        """Successful pipeline exits with EXIT_OK."""
        with pytest.raises(SystemExit) as exc_info:
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_OK
        _setup["run_pipeline"].assert_called_once()

    def test_all_failed(self, _setup: dict) -> None:
        """All tasks failing exits with EXIT_ALL_FAILED."""
        _setup["get_status"].return_value = "Failed"
        with pytest.raises(SystemExit) as exc_info:
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_ALL_FAILED

    def test_partial_failure(self, _setup: dict, tmp_path: Path) -> None:
        """Some tasks failing exits with EXIT_PARTIAL_FAILURE."""
        f2 = tmp_path / "other.txt"
        f2.write_text("content")
        _setup["setup_tasks"].return_value = [
            (1, str(_setup["_file"]), "", "French"),
            (2, str(f2), "", "French"),
        ]
        # First task done, second failed
        _setup["get_status"].side_effect = ["Done", "Failed"]

        with pytest.raises(SystemExit) as exc_info:
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_PARTIAL_FAILURE

    def test_auto_remove_history_none_status(self, _setup: dict) -> None:
        """None status (entry auto-removed) is treated as success."""
        _setup["get_status"].return_value = None
        with pytest.raises(SystemExit) as exc_info:
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_OK

    def test_setup_tasks_empty(self, _setup: dict) -> None:
        """Empty task list exits with EXIT_ALL_FAILED."""
        _setup["setup_tasks"].return_value = []
        with pytest.raises(SystemExit) as exc_info:
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_ALL_FAILED

    def test_keyboard_interrupt(self, _setup: dict) -> None:
        """KeyboardInterrupt exits with EXIT_INTERRUPTED."""
        _setup["run_pipeline"].side_effect = KeyboardInterrupt
        with pytest.raises(SystemExit) as exc_info:
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_INTERRUPTED

    def test_incomplete_status_counts_as_partial_failure(
        self,
        _setup: dict,
    ) -> None:
        """Pending/Translating left over after pipeline → EXIT_PARTIAL_FAILURE.

        Regression guard: the pre-fix CLI bucketed anything non-Failed as Done,
        so an interrupted-but-not-raised pipeline would misreport success.
        """
        _setup["get_status"].return_value = "Pending"
        with pytest.raises(SystemExit) as exc_info:
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_PARTIAL_FAILURE

    def test_invalid_ocr_method_exits_with_args_error(
        self,
        _setup: dict,
        tmp_path: Path,
    ) -> None:
        """Unknown --ocr-method value exits with EXIT_ARGS_ERROR."""
        f = tmp_path / "img.png"
        f.write_text("fake")
        with (
            patch(
                "sys.argv",
                [
                    "cli",
                    str(f),
                    "-t",
                    "French",
                    "-q",
                    "--ocr-method",
                    "NoSuchEngine",
                ],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_ARGS_ERROR

    def test_config_flags_forwarded(self, _setup: dict, tmp_path: Path) -> None:
        """CLI flags are correctly forwarded to TranslationConfig."""
        f = tmp_path / "doc.xlsx"
        f.write_text("data")
        out = tmp_path / "out"

        # Override the fixture's argv with a richer set of flags.
        with (
            patch(
                "sys.argv",
                [
                    "cli",
                    str(f),
                    "-t",
                    "French",
                    "-q",
                    "--output",
                    str(out),
                    "--translate-comments",
                    "--translate-shapes",
                    "--translate-notes",
                    "--translate-sheet-names",
                    "--convert-legacy",
                    "--keep-history",
                ],
            ),
            pytest.raises(SystemExit),
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        call_kwargs = _setup["run_pipeline"].call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.translate_doc_comments is True
        assert config.translate_doc_shapes is True
        assert config.translate_doc_notes is True
        assert config.translate_sheet_names is True
        assert config.auto_convert_legacy is True
        assert config.auto_remove_history is False  # --keep-history
        assert config.storage_path == str(out.resolve())


# ===================================================================
# _progress_reporter()
# ===================================================================


class TestProgressReporter:
    """Tests for the _progress_reporter daemon-thread helper."""

    _STATUS_PATCH = "src.core.database.get_history_entry_status"

    def test_done_task_prints_ok(self, capsys: pytest.CaptureFixture) -> None:
        """A single task returning STATUS_DONE prints '[OK]' and exits."""
        from src.cli import _progress_reporter  # noqa: PLC0415

        stop = threading.Event()
        with patch(self._STATUS_PATCH, return_value="Done"):
            _progress_reporter([42], stop)

        out = capsys.readouterr().out
        assert "[OK]" in out
        assert "Task 42" in out

    def test_failed_task_prints_fail(self, capsys: pytest.CaptureFixture) -> None:
        """A single task returning STATUS_FAILED prints '[FAIL]' and exits."""
        from src.cli import _progress_reporter  # noqa: PLC0415

        stop = threading.Event()
        with patch(self._STATUS_PATCH, return_value="Failed"):
            _progress_reporter([7], stop)

        out = capsys.readouterr().out
        assert "[FAIL]" in out
        assert "Task 7" in out

    def test_auto_removed_task_exits_silently(
        self,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Status returning None produces no print output but still exits."""
        from src.cli import _progress_reporter  # noqa: PLC0415

        stop = threading.Event()
        with patch(self._STATUS_PATCH, return_value=None):
            _progress_reporter([99], stop)

        out = capsys.readouterr().out
        assert out == ""

    def test_multiple_tasks_mixed_statuses(
        self,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Three tasks (done, failed, none) print for done/failed only."""
        from src.cli import _progress_reporter  # noqa: PLC0415

        stop = threading.Event()
        # side_effect returns one value per call: task 1 → Done,
        # task 2 → Failed, task 3 → None.
        with patch(
            self._STATUS_PATCH,
            side_effect=["Done", "Failed", None],
        ):
            _progress_reporter([1, 2, 3], stop)

        out = capsys.readouterr().out
        assert "[OK]" in out
        assert "Task 1" in out
        assert "[FAIL]" in out
        assert "Task 2" in out
        # Task 3 should NOT appear in the output (None → silent exit)
        assert "Task 3" not in out

    def test_stop_event_causes_exit(self) -> None:
        """Setting stop_event immediately causes the function to return."""
        from src.cli import _progress_reporter  # noqa: PLC0415

        stop = threading.Event()
        stop.set()  # pre-set before calling

        # With the stop_event already set, the while-loop condition is
        # False on the first check so the function returns immediately,
        # regardless of task status.
        with patch(self._STATUS_PATCH, return_value="Translating"):
            _progress_reporter([10, 20], stop)

        # If we reach here the function returned — test passes.

    def test_waits_for_status_change(self, capsys: pytest.CaptureFixture) -> None:
        """First poll returns 'Translating'; second returns 'Done'."""
        from src.cli import _progress_reporter  # noqa: PLC0415

        stop = threading.Event()

        # First call: still translating (no print).
        # The loop then calls stop_event.wait(timeout=1.0); we need it
        # to not actually sleep, so we set the stop_event after the
        # second call returns "Done".  side_effect gives one value per
        # get_history_entry_status call.
        call_count = 0

        def _fake_status(h_id: int) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Translating"
            return "Done"

        with patch(self._STATUS_PATCH, side_effect=_fake_status):
            _progress_reporter([5], stop)

        out = capsys.readouterr().out
        # Should print exactly once for the "Done" status.
        assert out.count("[OK]") == 1
        assert "Task 5" in out

    def test_skips_already_completed_tasks(
        self,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Once a task is in ``completed``, subsequent polls for it are skipped.

        Exercises the ``continue`` branch where ``h_id`` is already in the
        completed set — that branch is only hit on the SECOND poll iteration.
        """
        from src.cli import _progress_reporter  # noqa: PLC0415

        stop = threading.Event()
        call_log: list[int] = []

        def _fake_status(h_id: int) -> str:
            call_log.append(h_id)
            # First poll: task 1 completes, task 2 still translating.
            # After task 1 is added to completed, a second loop iteration
            # runs — at which point it should skip task 1 (the continue
            # branch) and only poll task 2 (which we then mark Done).
            if h_id == 1:
                return "Done"
            # task 2: first poll Translating, second poll Done
            return "Translating" if call_log.count(2) == 1 else "Done"

        with (
            patch(self._STATUS_PATCH, side_effect=_fake_status),
            patch("threading.Event.wait", return_value=False),
        ):
            _progress_reporter([1, 2], stop)

        # Task 1 should be polled only once (then skipped via continue).
        assert call_log.count(1) == 1
        # Task 2 was polled until it returned Done.
        assert call_log.count(2) >= 2  # noqa: PLR2004


# ===================================================================
# main() — non-quiet output and verbose flag
# ===================================================================


class TestMainNonQuietOutput:
    """Tests for the human-readable output paths in main()."""

    @pytest.fixture()
    def _setup_nonquiet(self, tmp_path: Path) -> dict:
        """Same as _setup but WITHOUT the -q flag, so prints are executed."""
        f = tmp_path / "doc.txt"
        f.write_text("content")

        patches = {
            "argv": patch("sys.argv", ["cli", str(f), "-t", "French"]),
            "ensure_dirs": patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            "configure_logging": patch(f"{_PATH_MGR}.configure_logging"),
            "init_db": patch(f"{_DB}.init_db"),
            "check_llm": patch(f"{_CFG_MGR}.check_llm_setup", return_value=True),
            "check_ocr": patch(f"{_CFG_MGR}.check_ocr_setup", return_value=False),
            "setup_tasks": patch(
                f"{_TRANSLATOR}.setup_translation_tasks",
                return_value=[(1, str(f), "", "French")],
            ),
            "run_pipeline": patch(f"{_TRANSLATOR}.run_translation_pipeline"),
            "get_status": patch(
                f"{_DB}.get_history_entry_status",
                return_value="Done",
            ),
        }
        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()
        mocks["_file"] = f
        yield mocks
        for p in patches.values():
            p.stop()

    def test_non_quiet_prints_summary_and_done_count(
        self,
        _setup_nonquiet: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Non-quiet mode prints source/target/files and Done tally."""
        with pytest.raises(SystemExit) as exc_info:
            from src.cli import main  # noqa: PLC0415

            main()

        out = capsys.readouterr().out
        assert exc_info.value.code == EXIT_OK
        assert "Source:" in out
        assert "Target:" in out
        assert "French" in out
        assert "Done:" in out

    def test_non_quiet_prints_output_dir_when_set(
        self,
        _setup_nonquiet: dict,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Output directory line prints when --output is provided."""
        out_dir = tmp_path / "out"
        with (
            patch(
                "sys.argv",
                [
                    "cli",
                    str(_setup_nonquiet["_file"]),
                    "-t",
                    "French",
                    "--output",
                    str(out_dir),
                ],
            ),
            pytest.raises(SystemExit),
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        assert "Output:" in capsys.readouterr().out

    def test_non_quiet_with_failures_prints_failed_line(
        self,
        _setup_nonquiet: dict,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ) -> None:
        """Summary includes ``Failed:`` line when any task failed."""
        f2 = tmp_path / "b.txt"
        f2.write_text("x")
        _setup_nonquiet["setup_tasks"].return_value = [
            (1, str(_setup_nonquiet["_file"]), "", "French"),
            (2, str(f2), "", "French"),
        ]

        # The progress-reporter thread AND the final summary both poll
        # get_history_entry_status; return a deterministic mapping per ID
        # so both consumers see the same result.
        def _status_by_id(h_id: int) -> str:
            return "Done" if h_id == 1 else "Failed"

        _setup_nonquiet["get_status"].side_effect = _status_by_id

        with pytest.raises(SystemExit):
            from src.cli import main  # noqa: PLC0415

            main()

        out = capsys.readouterr().out
        assert "Failed:" in out


class TestMainVerbose:
    """Tests for the --verbose flag."""

    def test_verbose_sets_debug_level(self, tmp_path: Path) -> None:
        """Passing -v sets root logger level to DEBUG."""
        import logging  # noqa: PLC0415

        f = tmp_path / "x.txt"
        f.write_text("hi")

        # Capture original level so we can assert and restore.
        original = logging.getLogger().level
        try:
            with (
                patch(
                    "sys.argv",
                    [
                        "cli",
                        str(f),
                        "-t",
                        "French",
                        "-v",
                        "-q",
                    ],
                ),
                patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
                patch(f"{_PATH_MGR}.configure_logging"),
                patch(f"{_DB}.init_db"),
                patch(f"{_CFG_MGR}.check_llm_setup", return_value=False),
                pytest.raises(SystemExit),
            ):
                from src.cli import main  # noqa: PLC0415

                main()
            assert logging.getLogger().level == logging.DEBUG
        finally:
            logging.getLogger().setLevel(original)


class TestMainModelValidation:
    """Tests for the --model CLI flag validation."""

    def test_unknown_model_exits_with_setup_error(self, tmp_path: Path) -> None:
        """Passing an unknown ``--model`` id exits with EXIT_SETUP_ERROR."""
        f = tmp_path / "x.txt"
        f.write_text("hi")

        with (
            patch(
                "sys.argv",
                [
                    "cli",
                    str(f),
                    "-t",
                    "French",
                    "-q",
                    "--model",
                    "Bogus:nonexistent-model",
                ],
            ),
            patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            patch(f"{_PATH_MGR}.configure_logging"),
            patch(f"{_DB}.init_db"),
            patch(f"{_CFG_MGR}.check_llm_setup", return_value=True),
            patch(
                f"{_CFG_MGR}.get_available_models",
                return_value=[("Gemini", "gemini-3-flash-preview")],
            ),
            patch(
                f"{_CFG_MGR}.parse_model_id",
                return_value=("Bogus", "nonexistent-model"),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_SETUP_ERROR

    def test_valid_model_is_forwarded_to_config(self, tmp_path: Path) -> None:
        """A valid ``--model`` is stored on TranslationConfig.llm_provider/model."""
        f = tmp_path / "x.txt"
        f.write_text("hi")

        with (
            patch(
                "sys.argv",
                [
                    "cli",
                    str(f),
                    "-t",
                    "French",
                    "-q",
                    "--model",
                    "Gemini:gemini-3-flash-preview",
                ],
            ),
            patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            patch(f"{_PATH_MGR}.configure_logging"),
            patch(f"{_DB}.init_db"),
            patch(f"{_CFG_MGR}.check_llm_setup", return_value=True),
            patch(f"{_CFG_MGR}.check_ocr_setup", return_value=False),
            patch(
                f"{_CFG_MGR}.get_available_models",
                return_value=[("Gemini", "gemini-3-flash-preview")],
            ),
            patch(
                f"{_CFG_MGR}.parse_model_id",
                return_value=("Gemini", "gemini-3-flash-preview"),
            ),
            patch(
                f"{_TRANSLATOR}.setup_translation_tasks",
                return_value=[(1, str(f), "", "French")],
            ),
            patch(
                f"{_DB}.get_history_entry_status",
                return_value="Done",
            ),
            patch(f"{_TRANSLATOR}.run_translation_pipeline") as run_pipeline,
            pytest.raises(SystemExit),
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        config = run_pipeline.call_args.kwargs["config"]
        assert config.llm_provider == "Gemini"
        assert config.llm_model == "gemini-3-flash-preview"


# ===================================================================
# Backfill — --keep-history persistence, ambiguous-language behaviour,
# unsupported file extension exit code.
# ===================================================================


class TestKeepHistoryFlag:
    """Tests for the --keep-history flag's effect on auto_remove_history."""

    def test_keep_history_disables_auto_remove(self, tmp_path: Path) -> None:
        """--keep-history sets ``auto_remove_history=False`` on TranslationConfig."""
        f = tmp_path / "doc.txt"
        f.write_text("data")

        with (
            patch(
                "sys.argv",
                ["cli", str(f), "-t", "French", "-q", "--keep-history"],
            ),
            patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            patch(f"{_PATH_MGR}.configure_logging"),
            patch(f"{_DB}.init_db"),
            patch(f"{_CFG_MGR}.check_llm_setup", return_value=True),
            patch(f"{_CFG_MGR}.check_ocr_setup", return_value=False),
            patch(
                f"{_TRANSLATOR}.setup_translation_tasks",
                return_value=[(1, str(f), "", "French")],
            ),
            patch(
                f"{_DB}.get_history_entry_status",
                return_value="Done",
            ),
            patch(f"{_TRANSLATOR}.run_translation_pipeline") as run_pipeline,
            pytest.raises(SystemExit),
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        config = run_pipeline.call_args.kwargs["config"]
        assert config.auto_remove_history is False

    def test_no_keep_history_enables_auto_remove(self, tmp_path: Path) -> None:
        """Without --keep-history, ``auto_remove_history`` defaults to True."""
        f = tmp_path / "doc.txt"
        f.write_text("data")

        with (
            patch("sys.argv", ["cli", str(f), "-t", "French", "-q"]),
            patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            patch(f"{_PATH_MGR}.configure_logging"),
            patch(f"{_DB}.init_db"),
            patch(f"{_CFG_MGR}.check_llm_setup", return_value=True),
            patch(f"{_CFG_MGR}.check_ocr_setup", return_value=False),
            patch(
                f"{_TRANSLATOR}.setup_translation_tasks",
                return_value=[(1, str(f), "", "French")],
            ),
            patch(
                f"{_DB}.get_history_entry_status",
                return_value="Done",
            ),
            patch(f"{_TRANSLATOR}.run_translation_pipeline") as run_pipeline,
            pytest.raises(SystemExit),
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        config = run_pipeline.call_args.kwargs["config"]
        assert config.auto_remove_history is True


class TestAmbiguousLanguage:
    """Tests for ambiguous-language input (e.g. bare 'Chinese')."""

    def test_chinese_without_qualifier_returns_none(self) -> None:
        """Bare 'Chinese' is unknown — caller must qualify with Simplified/Traditional."""
        assert _resolve_language("Chinese") is None
        assert _resolve_language("chinese") is None

    def test_chinese_substring_suggests_qualified_variants(self) -> None:
        """``_suggest_language_matches`` returns the qualified variants."""
        from src.cli import _suggest_language_matches  # noqa: PLC0415

        suggestions = _suggest_language_matches("Chinese")
        assert "Chinese (Simplified)" in suggestions
        assert "Chinese (Traditional)" in suggestions

    def test_suggestions_case_insensitive(self) -> None:
        """Lowercase input still finds matches."""
        from src.cli import _suggest_language_matches  # noqa: PLC0415

        suggestions = _suggest_language_matches("viet")
        assert any("Vietnamese" in s for s in suggestions)

    def test_no_substring_match_returns_empty_list(self) -> None:
        """A nonsense query returns an empty list (no matches)."""
        from src.cli import _suggest_language_matches  # noqa: PLC0415

        assert _suggest_language_matches("zzznotalanguage") == []

    def test_empty_query_returns_no_suggestions(self) -> None:
        """An empty / whitespace-only query returns an empty suggestion list.

        Earlier behaviour returned every language (since ``""`` is a
        substring of every label), which produced a useless "Did you
        mean: <every language>" hint.  The current contract: empty
        input → empty list, because the caller never reaches this
        helper with empty input (``_resolve_language`` short-circuits
        empty to "auto-detect"); even if a future call site does pass
        empty input, an empty list is more honest than dumping the
        full catalogue.
        """
        from src.cli import _suggest_language_matches  # noqa: PLC0415

        assert _suggest_language_matches("") == []

    def test_chinese_simplified_resolves(self) -> None:
        """Qualified 'Chinese (Simplified)' resolves correctly."""
        assert _resolve_language("Chinese (Simplified)") == "Chinese (Simplified)"
        assert _resolve_language("chinese (traditional)") == "Chinese (Traditional)"

    def test_main_chinese_target_exits_args_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """End-to-end: ``--target Chinese`` exits with EXIT_ARGS_ERROR.

        Currently the error message just says \"unknown target language\"
        without suggesting the qualified options.
        """
        f = tmp_path / "test.txt"
        f.write_text("hi")

        with (
            patch("sys.argv", ["cli", str(f), "-t", "Chinese", "-q"]),
            patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            patch(f"{_PATH_MGR}.configure_logging"),
            patch(f"{_DB}.init_db"),
            pytest.raises(SystemExit) as exc_info,
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_ARGS_ERROR
        err = capsys.readouterr().err
        assert "unknown target language" in err.lower()
        assert "Did you mean" in err
        assert "Chinese (Simplified)" in err
        assert "Chinese (Traditional)" in err


class TestUnsupportedExtensionEndToEnd:
    """End-to-end test for unsupported file extension → exit code 2."""

    def test_unsupported_extension_only_input_exits_args_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """When all input files are unsupported, main() exits EXIT_ARGS_ERROR.

        ``_validate_files`` filters out the .xyz file as unsupported,
        leaving an empty list, which triggers the ``no valid input files``
        branch.
        """
        bad = tmp_path / "data.xyz"
        bad.write_text("blob")

        with (
            patch("sys.argv", ["cli", str(bad), "-t", "French", "-q"]),
            patch(f"{_PATH_MGR}.ensure_app_dirs_exist"),
            patch(f"{_PATH_MGR}.configure_logging"),
            patch(f"{_DB}.init_db"),
            pytest.raises(SystemExit) as exc_info,
        ):
            from src.cli import main  # noqa: PLC0415

            main()

        assert exc_info.value.code == EXIT_ARGS_ERROR
        err = capsys.readouterr().err
        assert "unsupported type" in err.lower() or "no valid input" in err.lower()
