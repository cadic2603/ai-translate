import os
import resource
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import defusedxml.ElementTree  # noqa: E402, F401
import lxml.etree  # noqa: E402, F401
import openpyxl  # noqa: E402, F401

# Pre-load pymupdf and defusedxml/openpyxl before anything can trigger the
# LibreOffice UNO import hook, which drops venv site-packages from sys.path
# and then corrupts stdlib submodule imports (e.g. xml.etree._elementtree).
# Mirrors the workaround in main.py.
import pymupdf  # noqa: E402, F401
import pytest  # noqa: E402

from src.core import database  # noqa: E402

# ---------------------------------------------------------------------------
# Memory safety: cap the test process's virtual address space so that an
# infinite-loop bug (e.g. unmocked UNO hasMoreElements → always truthy
# MagicMock) raises MemoryError instead of consuming all system RAM and
# forcing a hard reboot.
# ---------------------------------------------------------------------------
_MEMORY_LIMIT_GB = 16  # PyTorch/EasyOCR maps ~8 GB virtual address space alone

if sys.platform != "win32":
    _soft, _hard = resource.getrlimit(resource.RLIMIT_AS)
    _limit_bytes = _MEMORY_LIMIT_GB * 1024**3
    # Only tighten; never raise above the existing hard limit
    _effective = (
        min(_limit_bytes, _hard) if _hard != resource.RLIM_INFINITY else _limit_bytes
    )
    resource.setrlimit(resource.RLIMIT_AS, (_effective, _hard))

# ---------------------------------------------------------------------------
# Redirect JVM crash logs away from the project root.
#
# LibreOffice's Java component writes hs_err_pid*.log and replay_pid*.log
# to the current working directory on JVM crashes.  Route them to a temp
# directory so they don't pollute the repository.
# ---------------------------------------------------------------------------
_JVM_LOG_DIR = tempfile.mkdtemp(prefix="jvm_logs_")
_JVM_OPTS = (
    f"-XX:ErrorFile={_JVM_LOG_DIR}/hs_err_pid%p.log "
    f"-XX:ReplayDataFile={_JVM_LOG_DIR}/replay_pid%p.log"
)
# Append to any existing _JAVA_OPTIONS rather than overwriting
_existing = os.environ.get("_JAVA_OPTIONS", "")
os.environ["_JAVA_OPTIONS"] = f"{_existing} {_JVM_OPTS}".strip()


# ---------------------------------------------------------------------------
# Centralized QApplication fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp_args():
    """Provides QApplication arguments for pytest-qt's built-in qapp fixture."""
    return ["-platform", "offscreen"]


# ---------------------------------------------------------------------------
# Isolated database fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _no_retry_sleep_in_tests():
    """Replace ``time.sleep`` inside the LLM retry decorator with a no-op.

    A leaked worker thread that retries an unmocked API call ends up in
    ``time.sleep(delay)`` (3-12 s) while the originating test has long
    since finished.  When the next test's per-test pytest timeout fires
    SIGALRM, the signal interrupts Python mid-sleep at a bad bytecode
    boundary; pytest-qt's ``_process_events`` then chases dangling
    state on the next iteration → SIGSEGV.

    Skipping the sleep keeps the retry *logic* intact (still loops up
    to ``RETRY_MAX_ATTEMPTS``) but turns each pause into a no-op so a
    leaked thread cannot hold the interpreter in a sleep when SIGALRM
    arrives.  Production code is unaffected — this only patches the
    in-process module reference for the duration of the test session.
    """
    import types  # noqa: PLC0415

    # Replace ``llm_engine.time`` with a stand-in namespace so we
    # ONLY intercept sleep calls made from within ``llm_engine`` (and
    # transitively, the retry wrapper).  The original implementation
    # patched ``llm_engine.time.sleep`` directly; because Python's
    # ``time`` module is a singleton, that mutation leaked to every
    # other module's ``time.sleep`` and broke tests that rely on real
    # delays (e.g. SQLite CURRENT_TIMESTAMP-second resolution).
    fake_time = types.SimpleNamespace(sleep=lambda _s: None)
    patcher = patch("src.core.llm_engine.time", fake_time)
    patcher.start()
    yield
    patcher.stop()


@pytest.fixture(scope="session", autouse=True)
def _isolate_keyring_in_tests():
    """Replace the OS keyring with an in-memory dict for the test session.

    Several code paths (``load_setting`` migration of legacy plaintext
    INI values, ``save_setting`` for ``_SECURE_KEYS``) call ``keyring``
    directly.  Without this fixture:

    * tests pollute the user's real OS keychain (a credential entry
      named ``ai-translate / llm/custom_providers`` gets left behind);
    * tests become order-dependent — ``load_custom_providers`` migrates
      legacy values on first call, after which subsequent tests see the
      migrated value and skip the path; under ``pytest --forked`` each
      test is a fresh process, so every one of them re-runs the
      migration and stumbles when other patches (e.g. a test mocking
      ``Path.open`` to a ``BytesIO``) break the INI fallback.

    The in-memory dict is per-process: each fork gets its own clean
    keychain, exactly matching real-world fresh-app behaviour.
    """
    import keyring  # noqa: PLC0415

    store: dict[tuple[str, str], str] = {}

    def fake_get(service: str, username: str) -> str | None:
        return store.get((service, username))

    def fake_set(service: str, username: str, password: str) -> None:
        # Mirror real keyring behaviour: it would happily accept str.
        # Reject non-str so a bug feeding bytes (we hit one once) still
        # surfaces in tests instead of going unnoticed.
        if not isinstance(password, str):
            msg = f"keyring expects str, got {type(password).__name__}"
            raise TypeError(msg)
        store[(service, username)] = password

    def fake_delete(service: str, username: str) -> None:
        store.pop((service, username), None)

    patches = [
        patch.object(keyring, "get_password", fake_get),
        patch.object(keyring, "set_password", fake_set),
        patch.object(keyring, "delete_password", fake_delete),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


@pytest.fixture(scope="session", autouse=True)
def global_database_redirection():  # noqa: ANN201
    """Redirects the database to a temporary directory."""
    temp_dir = tempfile.TemporaryDirectory(prefix="translator_test_")
    db_path = Path(temp_dir.name) / "test_translator.db"

    # Initialize the schema in the temporary database
    with patch("src.core.database.get_db_path", return_value=str(db_path)):
        database.init_db()

    # Patch for the duration of the session
    patcher = patch("src.core.database.get_db_path", return_value=str(db_path))
    patcher.start()

    yield

    patcher.stop()
    temp_dir.cleanup()


@pytest.fixture(scope="session", autouse=True)
def _redirect_desktop_path():
    """Prevent tests from writing translated output files to ~/Desktop."""
    temp_dir = tempfile.TemporaryDirectory(prefix="translator_test_desktop_")
    patcher = patch(
        "src.utils.path_manager.get_desktop_path",
        return_value=Path(temp_dir.name),
    )
    patcher.start()

    yield

    patcher.stop()
    temp_dir.cleanup()


# ---------------------------------------------------------------------------
# Isolated LLM endpoint cache file
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _redirect_llm_endpoint_cache_path():
    """Keep the persisted LLM endpoint cache out of the user's real cache dir.

    ``llm_engine`` calls ``_persist_caches()`` on every variant /
    api-choice cache write; without this redirect a test that exercises
    ``_translate_custom`` would write to the real
    ``~/.cache/ai-translate/llm_endpoint_cache.json`` and bleed state
    into the user's actual sessions.
    """
    temp_dir = tempfile.TemporaryDirectory(prefix="translator_test_llm_cache_")
    cache_path = Path(temp_dir.name) / "llm_endpoint_cache.json"
    patcher = patch(
        "src.utils.path_manager.get_llm_endpoint_cache_path",
        return_value=cache_path,
    )
    patcher.start()

    yield

    patcher.stop()
    temp_dir.cleanup()


# ---------------------------------------------------------------------------
# Isolated config file
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _redirect_config_path():
    """Redirect the INI config file to a temporary directory."""
    temp_dir = tempfile.TemporaryDirectory(prefix="translator_test_config_")
    config_path = Path(temp_dir.name) / "settings.ini"
    patcher = patch(
        "src.utils.config_manager._get_config_path",
        return_value=config_path,
    )
    patcher.start()

    yield

    patcher.stop()
    temp_dir.cleanup()


# ---------------------------------------------------------------------------
# Module cache and global state cleanup
# ---------------------------------------------------------------------------


def _reset_module_caches() -> None:  # noqa: PLR0912
    """Resets module-level caches and globals that leak between tests.

    Covers dict caches, scalar caches, soffice subprocess state,
    test-file counters, and i18n/theme globals.
    """
    # Dict caches — cleared in-place so aliased references stay valid.
    # ``_CUSTOM_API_CACHE`` is the per-(endpoint, model) chat-vs-responses
    # API choice cache used by ``_translate_custom``; without this clear,
    # a test that primes the cache (e.g. seeds ``"responses"``) would
    # bypass the chat→responses fallback in any later test that exercises
    # the same endpoint+model pair.
    for mod_path, attr_name in [
        ("src.core.ocr_engine", "_easyocr_readers"),
        ("src.core.pdf_processor", "_fontfile_cache"),
        ("src.core.llm_engine", "_CUSTOM_API_CACHE"),
        ("src.core.llm_engine", "_CUSTOM_VARIANT_CACHE"),
    ]:
        mod = sys.modules.get(mod_path)
        if mod:
            cache = getattr(mod, attr_name, None)
            if isinstance(cache, dict):
                cache.clear()

    # Scalar caches — reset via setattr.
    for mod_path, attr_name, reset_val in [
        ("src.core.live_engine", "_cached_model", None),
        ("src.core.live_engine", "_cached_model_size", ""),
        ("src.core.office_processor", "_ODF_TAB_QNAME", None),
        ("src.core.office_processor", "_ODF_LB_QNAME", None),
        ("src.core.office_processor", "_ODF_SPAN_QNAME", None),
        ("src.core.office_processor", "_ODF_A_QNAME", None),
    ]:
        mod = sys.modules.get(mod_path)
        if mod and hasattr(mod, attr_name):
            setattr(mod, attr_name, reset_val)

    # Audio-availability probe caches — module-level sentinel-guarded.
    # Without this reset, a prior test that primed the cache with
    # ``""`` (success) would silently short-circuit a later test
    # expecting ``"live.error_no_mic"``, since the cache check at
    # the top of ``check_audio_available`` runs before the mock'd
    # ``sd.query_devices`` would.  Use the module's own
    # ``invalidate_audio_caches`` helper so the canonical clear
    # logic stays in one place.
    le_mod = sys.modules.get("src.core.live_engine")
    if le_mod and hasattr(le_mod, "invalidate_audio_caches"):
        le_mod.invalidate_audio_caches()

    # Reset hyperlink counter in test helper to prevent ID collisions.
    fmt_mod = sys.modules.get("tests.test_office_formatter")
    if fmt_mod and hasattr(fmt_mod, "_hyperlink_counter"):
        fmt_mod._hyperlink_counter = 0

    # Reset i18n/theme global state.
    i18n_mod = sys.modules.get("src.constants.i18n")
    if i18n_mod and hasattr(i18n_mod, "_current_language"):
        i18n_mod._current_language = "en-US"
    # Clear loaded translations so tr() falls back to raw keys, matching
    # the expectation of tests that look up banners by tr-key substrings.
    if i18n_mod and hasattr(i18n_mod, "_translations"):
        i18n_mod._translations = {}

    theme_mod = sys.modules.get("src.constants.theme")
    if theme_mod and hasattr(theme_mod, "_current_theme"):
        theme_mod._current_theme = "light"

    # Clear CallbackSignal subscriber lists to prevent unbounded growth
    # from leaked create_main_window() closures.  Pages that connect a
    # ``_sync_shortcuts`` handler to ``shortcuts_changed`` (live, screen
    # live, subtitle, voice, dubbing, translate_document, glossary, etc.)
    # must also be cleared — otherwise the next test's
    # ``reset_all_shortcuts`` fixture emits the signal, the stale handler
    # fires against the deleted Qt page, and pytest reports
    # ``RuntimeError: Internal C++ object (PySide6.QtGui.QShortcut)
    # already deleted`` at fixture setup time on every shortcut test.
    if i18n_mod and hasattr(i18n_mod, "language_changed"):
        i18n_mod.language_changed._callbacks.clear()
    if theme_mod and hasattr(theme_mod, "theme_changed"):
        theme_mod.theme_changed._callbacks.clear()
    shortcuts_mod = sys.modules.get("src.constants.shortcuts")
    if shortcuts_mod and hasattr(shortcuts_mod, "shortcuts_changed"):
        shortcuts_mod.shortcuts_changed._callbacks.clear()
    # The overlay-appearance signal is connected by both the Settings
    # → Live tab factory AND each ``_OverlayWindow`` instance.  Left
    # un-cleared, listeners leak between tests: a later test's emit
    # fires against a deleted Qt overlay and raises ``RuntimeError:
    # Internal C++ object … already deleted`` at random.  Same
    # mitigation as the other module-level signals above.
    settings_const_mod = sys.modules.get("src.constants.settings")
    if settings_const_mod and hasattr(
        settings_const_mod, "overlay_appearance_changed",
    ):
        settings_const_mod.overlay_appearance_changed._callbacks.clear()


@pytest.fixture(autouse=True)
def _cleanup_qt_and_worker_state():  # noqa: PLR0912
    """Clean up leaked Qt timers, widgets, and worker flags after every test.

    This prevents cross-test contamination where:
    - A HistoryPage's background QTimer fires during processEvents() in the
      next test's setup/teardown, connecting to the DB and hanging.
    - A worker's _is_any_worker_running flag is left True, blocking subsequent
      tests from starting workers.
    - Leaked top-level widgets from a previous test retain stale signal
      connections that fire during the next test's event processing.
    """
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    app = QApplication.instance()

    # Snapshot top-level widgets that exist *before* the test runs so we can
    # identify newly created (leaked) widgets after the test finishes.
    pre_existing = {id(w) for w in app.topLevelWidgets()} if app else set()

    yield

    # Stop all active QTimers to prevent processEvents() hangs
    from PySide6.QtCore import QTimer  # noqa: PLC0415

    if app:
        for widget in app.topLevelWidgets():
            for timer in widget.findChildren(QTimer):
                timer.stop()

        # Close and schedule deletion of widgets created during this test.
        for widget in app.topLevelWidgets():
            if id(widget) not in pre_existing:
                widget.close()
                widget.deleteLater()

        app.processEvents()

    # Reset worker class flags
    for mod_path, cls_name in [
        ("src.core.translator", "TranslationWorker"),
        ("src.ui.pages.extract_text", "_ExtractionWorker"),
        ("src.ui.pages.subtitle", "_SubtitleWorker"),
        ("src.ui.pages.voice", "_VoiceWorker"),
        ("src.ui.pages.dubbing", "_DubbingWorker"),
    ]:
        mod = sys.modules.get(mod_path)
        if mod:
            cls = getattr(mod, cls_name, None)
            if cls and hasattr(cls, "_is_any_worker_running"):
                cls._is_any_worker_running = False

    _reset_module_caches()
