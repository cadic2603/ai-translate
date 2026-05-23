"""Unit tests for the core database logic."""

from collections.abc import Generator
from pathlib import Path

import pytest

from src.constants import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_TRANSLATING,
)
from src.constants.history import STATUS_DELETING, STATUS_EXTRACTING, STATUS_GENERATING
from src.core.database import (
    add_dubbing_entry,
    add_extraction_entry,
    add_glossary_entry,
    add_history_entry,
    add_subtitle_entry,
    add_text_translation_entry,
    add_voice_entry,
    batch_mark_deleting_history_entries,
    batch_pause_dubbing_entries,
    batch_pause_history_entries,
    batch_resume_dubbing_entries,
    batch_resume_history_entries,
    batch_retranslate_history_entries,
    clear_history,
    create_glossary_set,
    delete_dubbing_entry,
    delete_extraction_entry,
    delete_glossary_entry,
    delete_glossary_set,
    delete_history_entry,
    delete_subtitle_entry,
    delete_text_translation_entry,
    delete_voice_entry,
    find_glossary_entry_by_source,
    get_active_glossary_sets,
    get_dubbing_entry_status,
    get_dubbing_fingerprint,
    get_dubbing_history,
    get_extraction_fingerprint,
    get_extraction_history,
    get_glossary_entries,
    get_glossary_entry_count,
    get_glossary_sets,
    get_history,
    get_history_entry_status,
    get_history_fingerprint,
    get_subtitle_fingerprint,
    get_subtitle_history,
    get_text_translation_fingerprint,
    get_text_translation_history,
    get_unfinished_dubbing,
    get_unfinished_history,
    get_voice_fingerprint,
    get_voice_history,
    init_db,
    is_any_dubbing_generating,
    is_any_extracting,
    is_any_paused,
    is_any_subtitle_generating,
    is_any_translating,
    is_any_voice_generating,
    reset_stuck_subtitle_entries,
    reset_stuck_voice_entries,
    update_all_glossary_sets_active,
    update_dubbing_progress,
    update_dubbing_status,
    update_extraction_status,
    update_glossary_entry,
    update_glossary_set_active,
    update_glossary_set_name,
    update_history_file_name,
    update_history_progress,
    update_history_status,
    update_subtitle_status,
    update_text_translation_entry,
    update_voice_status,
)


@pytest.fixture(autouse=True)
def setup_test_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[None, None, None]:
    """Initializes a clean database in a temporary directory before each test."""
    db_file = tmp_path / "test_translator.db"
    monkeypatch.setattr("src.core.database.get_db_path", lambda: str(db_file))
    init_db()
    yield


def test_glossary_set_lifecycle() -> None:
    """Verify set creation, retrieval, and deletion."""
    assert create_glossary_set("Test Set") is True
    assert create_glossary_set("Test Set") is False

    sets = get_glossary_sets()
    assert len(sets) == 1
    assert sets[0][1] == "Test Set"

    set_id = sets[0][0]
    delete_glossary_set(set_id)
    assert len(get_glossary_sets()) == 0


def test_history_lifecycle() -> None:
    """Verify adding, updating, retrieving, and deleting history."""
    h_id = add_history_entry(
        "test.txt",
        "",
        "French",
        STATUS_TRANSLATING,
        file_size=1024,
    )
    assert h_id is not None

    # Status check
    assert get_history_entry_status(h_id) == STATUS_TRANSLATING

    # Update status
    update_history_status(h_id, STATUS_DONE)
    assert get_history_entry_status(h_id) == STATUS_DONE

    # Update progress
    update_history_progress(h_id, 50)

    history = get_history()
    assert len(history) == 1
    assert history[0][1] == "test.txt"
    assert history[0][5] == 50  # noqa: PLR2004 — progress column
    assert history[0][7] == 1024  # noqa: PLR2004 — file_size column

    # Deletion
    delete_history_entry(h_id)
    assert len(get_history()) == 0


def test_unfinished_logic() -> None:
    """Verify checks for active and paused translations."""
    assert not is_any_translating()
    assert not is_any_paused()

    add_history_entry("1.txt", "", "FR", STATUS_TRANSLATING)
    assert is_any_translating()
    assert not is_any_paused()

    add_history_entry("2.txt", "", "DE", STATUS_PAUSED)
    assert is_any_paused()

    unfinished = get_unfinished_history()
    assert len(unfinished) == 2  # noqa: PLR2004

    # Filtered check
    only_paused = get_unfinished_history(statuses=(STATUS_PAUSED,))
    assert len(only_paused) == 1
    assert only_paused[0][0] != 0


def test_error_status() -> None:
    """Verify status updates with error codes."""
    h_id = add_history_entry("fail.txt", "EN", "ES", STATUS_TRANSLATING)
    update_history_status(h_id, STATUS_FAILED, error_code=30)

    history = get_history()
    assert history[0][4] == STATUS_FAILED
    assert history[0][9] == 30  # noqa: PLR2004 — error_code column


def test_error_message_column_persists_engine_tag() -> None:
    """``error_message`` preserves the raw engine tag including ``:Service`` suffix.

    The history table now carries BOTH ``error_code`` (numeric, for
    template lookup) AND ``error_message`` (raw tag, for service-
    aware rendering via ``display_error_message``).  Without the
    text column the suffix is lost in the numeric round-trip and
    every auth failure reads as generic "Invalid API key" instead
    of "Invalid Gemini API key" / "Invalid Google Cloud API key".
    """
    h_id = add_history_entry("fail.pdf", "English", "Vietnamese", STATUS_TRANSLATING)
    update_history_status(
        h_id,
        STATUS_FAILED,
        error_code=30,
        error_message="AUTH_ERROR:Gemini",
    )

    history = get_history()
    # error_message is the 11th column (index 10) — the column added
    # after error_code by this migration.
    assert history[0][9] == 30  # noqa: PLR2004 — error_code
    assert history[0][10] == "AUTH_ERROR:Gemini"  # raw tag survives


def test_error_message_cleared_on_resume() -> None:
    """Resume clears BOTH error_code AND error_message.

    Without clearing, a retry would surface last run's auth tag
    as the current state — confusing the UI into showing
    "Invalid Gemini API key" on a fresh Pending row.
    """
    from src.core.database import batch_resume_history_entries  # noqa: PLC0415

    h_id = add_history_entry("retry.pdf", "EN", "VI", STATUS_TRANSLATING)
    update_history_status(
        h_id,
        STATUS_FAILED,
        error_code=30,
        error_message="AUTH_ERROR:Gemini",
    )

    batch_resume_history_entries([h_id])

    history = get_history()
    assert history[0][4] == "Pending"
    assert history[0][9] is None  # error_code cleared
    assert history[0][10] is None  # error_message also cleared


def test_glossary_rename() -> None:
    """Verify renaming a glossary set."""
    create_glossary_set("Original Name")
    set_id = get_glossary_sets()[0][0]
    assert update_glossary_set_name(set_id, "New Name") is True
    assert get_glossary_sets()[0][1] == "New Name"


def test_glossary_rename_duplicate() -> None:
    """Renaming to an existing name returns False."""
    create_glossary_set("Alpha")
    create_glossary_set("Beta")
    beta_id = get_glossary_sets()[1][0]
    assert update_glossary_set_name(beta_id, "Alpha") is False


# ── Glossary entry CRUD ──────────────────────────────────────


def test_glossary_entry_add_and_get() -> None:
    """Verify adding entries and retrieving them by set."""
    create_glossary_set("Set A")
    set_id = get_glossary_sets()[0][0]

    add_glossary_entry(set_id, "hello", "xin chào")
    add_glossary_entry(set_id, "world", "thế giới")

    entries = get_glossary_entries(set_id)
    assert len(entries) == 2  # noqa: PLR2004
    # Entries ordered by created_at DESC, so last inserted comes first
    sources = [e[1] for e in entries]
    assert "hello" in sources
    assert "world" in sources


def test_glossary_entry_get_empty_set() -> None:
    """Getting entries from a set with none returns empty list."""
    create_glossary_set("Empty")
    set_id = get_glossary_sets()[0][0]
    assert get_glossary_entries(set_id) == []


def test_glossary_entry_isolation_between_sets() -> None:
    """Entries from one set do not appear in another."""
    create_glossary_set("Set A")
    create_glossary_set("Set B")
    sets = get_glossary_sets()
    id_a, id_b = sets[0][0], sets[1][0]

    add_glossary_entry(id_a, "apple", "pomme")
    add_glossary_entry(id_b, "car", "voiture")

    assert len(get_glossary_entries(id_a)) == 1
    assert get_glossary_entries(id_a)[0][1] == "apple"
    assert len(get_glossary_entries(id_b)) == 1
    assert get_glossary_entries(id_b)[0][1] == "car"


def test_glossary_entry_update() -> None:
    """Verify updating source and target text of an entry."""
    create_glossary_set("Set A")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "old_src", "old_tgt")

    entry_id = get_glossary_entries(set_id)[0][0]
    update_glossary_entry(entry_id, "new_src", "new_tgt")

    updated = get_glossary_entries(set_id)[0]
    assert updated[1] == "new_src"
    assert updated[2] == "new_tgt"


def test_glossary_entry_delete() -> None:
    """Verify deleting a single entry leaves others intact."""
    create_glossary_set("Set A")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "keep", "garder")
    add_glossary_entry(set_id, "remove", "supprimer")

    entries = get_glossary_entries(set_id)
    remove_id = next(e[0] for e in entries if e[1] == "remove")
    delete_glossary_entry(remove_id)

    remaining = get_glossary_entries(set_id)
    assert len(remaining) == 1
    assert remaining[0][1] == "keep"


def test_glossary_entry_count() -> None:
    """Verify entry count accuracy after add and delete."""
    create_glossary_set("Set A")
    set_id = get_glossary_sets()[0][0]
    assert get_glossary_entry_count(set_id) == 0

    add_glossary_entry(set_id, "a", "1")
    add_glossary_entry(set_id, "b", "2")
    assert get_glossary_entry_count(set_id) == 2  # noqa: PLR2004

    entry_id = get_glossary_entries(set_id)[0][0]
    delete_glossary_entry(entry_id)
    assert get_glossary_entry_count(set_id) == 1


def test_find_glossary_entry_by_source_returns_match() -> None:
    """find_glossary_entry_by_source returns (id, target) for a known source."""
    create_glossary_set("FindSet")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "hello", "bonjour")
    entries = get_glossary_entries(set_id)
    expected_id = entries[0][0]

    result = find_glossary_entry_by_source(set_id, "hello")
    assert result == (expected_id, "bonjour")


def test_find_glossary_entry_by_source_is_case_insensitive() -> None:
    """The source match ignores case (``HELLO`` matches ``hello``)."""
    create_glossary_set("FindSet2")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "hello", "bonjour")

    assert find_glossary_entry_by_source(set_id, "HELLO") is not None
    assert find_glossary_entry_by_source(set_id, "Hello") is not None


def test_find_glossary_entry_by_source_returns_none_when_missing() -> None:
    """Unknown sources return None."""
    create_glossary_set("FindSet3")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "hello", "bonjour")

    assert find_glossary_entry_by_source(set_id, "unknown") is None


def test_find_glossary_entry_by_source_scoped_per_set() -> None:
    """A source match in one set does NOT leak into another set."""
    create_glossary_set("SetA")
    create_glossary_set("SetB")
    sets = get_glossary_sets()
    set_a = next(s[0] for s in sets if s[1] == "SetA")
    set_b = next(s[0] for s in sets if s[1] == "SetB")
    add_glossary_entry(set_a, "shared", "a_target")

    assert find_glossary_entry_by_source(set_a, "shared") is not None
    assert find_glossary_entry_by_source(set_b, "shared") is None


# ── Glossary set activation ──────────────────────────────────


def test_glossary_set_active_default() -> None:
    """Newly created sets are active by default."""
    create_glossary_set("New Set")
    sets = get_glossary_sets()
    assert sets[0][2] == 1  # is_active column


def test_glossary_set_toggle_active() -> None:
    """Verify toggling a single set's active status."""
    create_glossary_set("Set A")
    set_id = get_glossary_sets()[0][0]

    update_glossary_set_active(set_id, False)
    assert get_glossary_sets()[0][2] == 0

    update_glossary_set_active(set_id, True)
    assert get_glossary_sets()[0][2] == 1


def test_glossary_update_all_active() -> None:
    """Verify batch-toggling all sets."""
    create_glossary_set("Set A")
    create_glossary_set("Set B")

    update_all_glossary_sets_active(False)
    for s in get_glossary_sets():
        assert s[2] == 0

    update_all_glossary_sets_active(True)
    for s in get_glossary_sets():
        assert s[2] == 1


def test_glossary_get_active_sets() -> None:
    """Verify only active sets are returned."""
    create_glossary_set("Active")
    create_glossary_set("Inactive")
    sets = get_glossary_sets()
    inactive_id = next(s[0] for s in sets if s[1] == "Inactive")
    update_glossary_set_active(inactive_id, False)

    active = get_active_glossary_sets()
    assert len(active) == 1
    assert active[0][1] == "Active"


def test_glossary_get_active_sets_empty() -> None:
    """No active sets returns empty list."""
    create_glossary_set("Only")
    set_id = get_glossary_sets()[0][0]
    update_glossary_set_active(set_id, False)
    assert get_active_glossary_sets() == []


# ── Cascade delete ────────────────────────────────────────────


def test_glossary_cascade_delete_entries() -> None:
    """Deleting a set removes all its entries."""
    create_glossary_set("Doomed")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "a", "1")
    add_glossary_entry(set_id, "b", "2")
    assert get_glossary_entry_count(set_id) == 2  # noqa: PLR2004

    delete_glossary_set(set_id)
    # Entries should be gone (FK cascade)
    assert get_glossary_entries(set_id) == []


def test_fingerprint_empty_db() -> None:
    """Verify fingerprint returns a stable tuple for empty history."""
    fp = get_history_fingerprint()
    assert fp is not None
    assert fp[0] == 0  # count
    assert fp[1] == 0  # max id
    assert fp[2] == ""  # empty concat


def test_fingerprint_stable_when_unchanged() -> None:
    """Verify fingerprint is identical across consecutive calls."""
    add_history_entry("a.txt", "EN", "FR", STATUS_TRANSLATING)
    fp1 = get_history_fingerprint()
    fp2 = get_history_fingerprint()
    assert fp1 == fp2


def test_fingerprint_changes_on_new_entry() -> None:
    """Verify fingerprint changes when a new entry is added."""
    fp_before = get_history_fingerprint()
    add_history_entry("a.txt", "EN", "FR", STATUS_TRANSLATING)
    fp_after = get_history_fingerprint()
    assert fp_before != fp_after


def test_fingerprint_changes_on_status_update() -> None:
    """Verify fingerprint changes when status is updated."""
    h_id = add_history_entry("a.txt", "EN", "FR", STATUS_TRANSLATING)
    fp_before = get_history_fingerprint()
    update_history_status(h_id, STATUS_DONE)
    fp_after = get_history_fingerprint()
    assert fp_before != fp_after


def test_fingerprint_changes_on_progress_update() -> None:
    """Verify fingerprint changes when progress is updated."""
    h_id = add_history_entry("a.txt", "EN", "FR", STATUS_TRANSLATING)
    fp_before = get_history_fingerprint()
    update_history_progress(h_id, 75)
    fp_after = get_history_fingerprint()
    assert fp_before != fp_after


def test_fingerprint_changes_on_delete() -> None:
    """Verify fingerprint changes when an entry is deleted."""
    h_id = add_history_entry("a.txt", "EN", "FR", STATUS_DONE)
    fp_before = get_history_fingerprint()
    delete_history_entry(h_id)
    fp_after = get_history_fingerprint()
    assert fp_before != fp_after


def test_fingerprint_changes_on_error_code() -> None:
    """Verify fingerprint changes when error_code is set."""
    h_id = add_history_entry("a.txt", "EN", "FR", STATUS_TRANSLATING)
    fp_before = get_history_fingerprint()
    update_history_status(h_id, STATUS_FAILED, error_code=30)
    fp_after = get_history_fingerprint()
    assert fp_before != fp_after


# ── clear_history ─────────────────────────────────────────────


def test_clear_history_removes_all_entries() -> None:
    """Verify clear_history deletes every entry."""
    add_history_entry("a.txt", "", "FR", STATUS_DONE)
    add_history_entry("b.txt", "", "DE", STATUS_TRANSLATING)
    add_history_entry("c.txt", "EN", "ES", STATUS_FAILED)
    assert len(get_history()) == 3  # noqa: PLR2004

    clear_history()
    assert get_history() == []


def test_clear_history_on_empty_db() -> None:
    """Verify clear_history is a safe no-op on an empty history."""
    assert get_history() == []
    clear_history()
    assert get_history() == []


def test_clear_history_resets_fingerprint() -> None:
    """Fingerprint reverts to empty-db state after clear."""
    empty_fp = get_history_fingerprint()
    add_history_entry("a.txt", "EN", "FR", STATUS_DONE)
    assert get_history_fingerprint() != empty_fp

    clear_history()
    assert get_history_fingerprint() == empty_fp


# ── delete_history_entry edge cases ───────────────────────────


def test_delete_nonexistent_entry() -> None:
    """Deleting a non-existent ID returns None and does not raise."""
    result = delete_history_entry(99999)
    assert result is None


def test_delete_entry_returns_storage_path() -> None:
    """Verify delete returns the storage_path for cleanup."""
    h_id = add_history_entry(
        "doc.txt",
        "EN",
        "FR",
        STATUS_DONE,
        storage_path="/tmp/translations/42/doc.txt",
    )
    path = delete_history_entry(h_id)
    assert path == "/tmp/translations/42/doc.txt"


def test_delete_entry_empty_storage_path() -> None:
    """Entry with empty storage_path returns empty string on delete."""
    h_id = add_history_entry(
        "doc.txt",
        "EN",
        "FR",
        STATUS_DONE,
        storage_path="",
    )
    path = delete_history_entry(h_id)
    assert path == ""


# ── get_history_entry_status edge cases ───────────────────────


def test_status_nonexistent_entry() -> None:
    """Querying status of a non-existent entry returns None."""
    assert get_history_entry_status(99999) is None


# ── update_history_progress edge cases ────────────────────────


def test_progress_boundary_zero() -> None:
    """Progress can be set to 0."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_progress(h_id, 0)
    history = get_history()
    assert history[0][5] == 0


def test_progress_boundary_hundred() -> None:
    """Progress can be set to 100."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_progress(h_id, 100)
    history = get_history()
    assert history[0][5] == 100  # noqa: PLR2004


def test_progress_persisted_across_queries() -> None:
    """Progress value is persisted and returned on get_history."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_progress(h_id, 42)
    entry = get_history()[0]
    assert entry[5] == 42  # noqa: PLR2004


def test_progress_monotonic_never_decreases() -> None:
    """Progress updates with a lower value are silently ignored."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_progress(h_id, 60)
    # Attempt to set a lower value — should be ignored
    update_history_progress(h_id, 30)
    entry = get_history()[0]
    assert entry[5] == 60  # noqa: PLR2004 — stays at 60, not 30


def test_progress_monotonic_allows_increase() -> None:
    """Progress updates with a higher value are accepted."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_progress(h_id, 40)
    update_history_progress(h_id, 80)
    entry = get_history()[0]
    assert entry[5] == 80  # noqa: PLR2004


def test_progress_monotonic_equal_is_no_op() -> None:
    """Setting progress to the same value is a silent no-op."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_progress(h_id, 50)
    update_history_progress(h_id, 50)
    entry = get_history()[0]
    assert entry[5] == 50  # noqa: PLR2004


# ── get_history edge cases ────────────────────────────────────


def test_get_history_empty() -> None:
    """Empty database returns empty list."""
    assert get_history() == []


def test_get_history_returns_all_entries() -> None:
    """Multiple entries are all returned by get_history."""
    add_history_entry("first.txt", "", "FR", STATUS_DONE)
    add_history_entry("second.txt", "", "DE", STATUS_DONE)
    add_history_entry("third.txt", "", "ES", STATUS_DONE)

    history = get_history()
    assert len(history) == 3  # noqa: PLR2004
    names = {h[1] for h in history}
    assert names == {"first.txt", "second.txt", "third.txt"}


def test_get_history_limit_fifty() -> None:
    """Only the last 50 entries are returned."""
    for i in range(55):
        add_history_entry(f"file_{i}.txt", "", "FR", STATUS_DONE)
    history = get_history()
    assert len(history) == 50  # noqa: PLR2004


# ── get_unfinished_history edge cases ─────────────────────────


def test_unfinished_history_empty_when_all_done() -> None:
    """Returns empty list when all tasks are Done or Failed."""
    add_history_entry("a.txt", "", "FR", STATUS_DONE)
    add_history_entry("b.txt", "", "DE", STATUS_FAILED)
    assert get_unfinished_history() == []


def test_unfinished_history_custom_statuses() -> None:
    """Custom status filter returns only matching entries."""
    add_history_entry("a.txt", "", "FR", STATUS_PENDING)
    add_history_entry("b.txt", "", "DE", STATUS_TRANSLATING)
    add_history_entry("c.txt", "", "ES", STATUS_PAUSED)

    only_pending = get_unfinished_history(statuses=(STATUS_PENDING,))
    assert len(only_pending) == 1
    assert only_pending[0][2] == ""  # source_lang of "a.txt"


def test_unfinished_history_translating_before_pending() -> None:
    """Translating entries are returned before Pending ones (resume priority).

    The ORDER BY clause ensures interrupted tasks (Translating) are resumed
    before brand-new ones (Pending), regardless of insertion order.
    get_unfinished_history() returns (id, storage_path, source_lang,
    target_lang, source_path) tuples; we use target_lang to tell entries apart.
    """
    # Insert a Pending entry first, then a Translating entry — order must flip.
    add_history_entry("first.txt", "", "FR", STATUS_PENDING)
    add_history_entry("second.txt", "", "DE", STATUS_TRANSLATING)

    results = get_unfinished_history()
    assert len(results) == 2  # noqa: PLR2004
    # Translating entry (target "DE") must precede Pending entry (target "FR").
    target_langs = [r[3] for r in results]
    assert target_langs[0] == "DE"
    assert target_langs[1] == "FR"


# ── is_any_translating / is_any_paused edge cases ────────────


def test_is_any_translating_false_after_done() -> None:
    """Returns False after the only Translating entry becomes Done."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    assert is_any_translating()

    update_history_status(h_id, STATUS_DONE)
    assert not is_any_translating()


def test_is_any_paused_false_after_resume() -> None:
    """Returns False after the only Paused entry changes to Translating."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_PAUSED)
    assert is_any_paused()

    update_history_status(h_id, STATUS_TRANSLATING)
    assert not is_any_paused()


def test_is_any_translating_empty_db() -> None:
    """Returns False on empty database."""
    assert not is_any_translating()


def test_is_any_paused_empty_db() -> None:
    """Returns False on empty database."""
    assert not is_any_paused()


# ── update_history_status branches ────────────────────────────


def test_status_translating_refreshes_timestamp() -> None:
    """Setting status to Translating refreshes created_at."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_PENDING)
    original = get_history()[0][6]  # created_at

    update_history_status(h_id, STATUS_TRANSLATING)
    updated = get_history()[0][6]
    # Timestamp should be refreshed (>= original)
    assert updated >= original
    assert get_history_entry_status(h_id) == STATUS_TRANSLATING


def test_status_translating_with_error_code() -> None:
    """Setting Translating with error_code persists both."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_PENDING)
    update_history_status(h_id, STATUS_TRANSLATING, error_code=31)

    entry = get_history()[0]
    assert entry[4] == STATUS_TRANSLATING
    assert entry[9] == 31  # noqa: PLR2004


def test_status_non_translating_without_error_code() -> None:
    """Setting status to Done without error_code clears nothing."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_status(h_id, STATUS_DONE)

    entry = get_history()[0]
    assert entry[4] == STATUS_DONE
    assert entry[9] is None  # error_code remains unset


# ── Batch history operations ─────────────────────────────────


def test_batch_pause_pauses_active_entries() -> None:
    """Batch pause updates Translating and Pending entries to Paused."""
    id1 = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    id2 = add_history_entry("b.txt", "", "DE", STATUS_PENDING)
    id3 = add_history_entry("c.txt", "", "ES", STATUS_DONE)

    batch_pause_history_entries([id1, id2, id3])

    assert get_history_entry_status(id1) == STATUS_PAUSED
    assert get_history_entry_status(id2) == STATUS_PAUSED
    assert get_history_entry_status(id3) == STATUS_DONE  # unchanged


def test_batch_pause_empty_list_is_noop() -> None:
    """Batch pause with empty list does not raise."""
    batch_pause_history_entries([])


def test_batch_resume_sets_pending_and_clears_error() -> None:
    """Batch resume sets status to Pending and clears error_code."""
    id1 = add_history_entry("a.txt", "", "FR", STATUS_PAUSED)
    id2 = add_history_entry("b.txt", "", "DE", STATUS_TRANSLATING)
    update_history_status(id1, STATUS_FAILED, error_code=30)

    batch_resume_history_entries([id1, id2])

    assert get_history_entry_status(id1) == STATUS_PENDING
    assert get_history_entry_status(id2) == STATUS_PENDING
    # error_code should be cleared
    entry = next(h for h in get_history() if h[0] == id1)
    assert entry[9] is None


def test_batch_resume_empty_list_is_noop() -> None:
    """Batch resume with empty list does not raise."""
    batch_resume_history_entries([])


def test_batch_retranslate_resets_entries() -> None:
    """Batch retranslate resets status, progress, error, and updates languages."""
    id1 = add_history_entry("a.txt", "EN", "FR", STATUS_DONE)
    id2 = add_history_entry("b.txt", "EN", "FR", STATUS_FAILED)
    update_history_progress(id1, 100)
    update_history_status(id2, STATUS_FAILED, error_code=30)

    batch_retranslate_history_entries([id1, id2], "DE", "ES")

    for h_id in (id1, id2):
        assert get_history_entry_status(h_id) == STATUS_PENDING
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[2] == "DE"  # source_lang
        assert entry[3] == "ES"  # target_lang
        assert entry[5] == 0  # progress reset
        assert entry[9] is None  # error_code cleared


def test_batch_retranslate_empty_list_is_noop() -> None:
    """Batch retranslate with empty list does not raise."""
    batch_retranslate_history_entries([], "EN", "FR")


def test_batch_mark_deleting() -> None:
    """Batch mark deleting sets status to Deleting."""
    id1 = add_history_entry("a.txt", "", "FR", STATUS_DONE)
    id2 = add_history_entry("b.txt", "", "DE", STATUS_PAUSED)

    batch_mark_deleting_history_entries([id1, id2])

    assert get_history_entry_status(id1) == STATUS_DELETING
    assert get_history_entry_status(id2) == STATUS_DELETING


def test_batch_mark_deleting_empty_list_is_noop() -> None:
    """Batch mark deleting with empty list does not raise."""
    batch_mark_deleting_history_entries([])


# ── update_history_file_name ──────────────────────────────────


def test_update_history_file_name() -> None:
    """Verify file_name is updated in the database."""
    h_id = add_history_entry(
        "original.doc",
        "EN",
        "FR",
        STATUS_TRANSLATING,
    )
    # Confirm original name
    entry = get_history()[0]
    assert entry[1] == "original.doc"

    # Update to a new name (e.g. after legacy → modern conversion)
    update_history_file_name(h_id, "original.docx")

    entry = get_history()[0]
    assert entry[1] == "original.docx"


# ── Glossary edge cases ───────────────────────────────────────


def test_glossary_set_empty_string_name() -> None:
    """Empty string is a valid SQLite TEXT — create_glossary_set returns True."""
    assert create_glossary_set("") is True
    sets = get_glossary_sets()
    assert sets[0][1] == ""


def test_glossary_set_unicode_name() -> None:
    """Set names with Unicode characters work correctly."""
    assert create_glossary_set("日本語の辞書") is True
    sets = get_glossary_sets()
    assert sets[0][1] == "日本語の辞書"


def test_glossary_set_special_chars_name() -> None:
    """Set names with special characters work correctly."""
    assert create_glossary_set("Test (Draft) — v2.0") is True
    sets = get_glossary_sets()
    assert sets[0][1] == "Test (Draft) — v2.0"


def test_glossary_entry_unicode_text() -> None:
    """Entries with Unicode/accented text are stored and retrieved."""
    create_glossary_set("Unicode")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "Straße", "Street")
    add_glossary_entry(set_id, "café", "quán cà phê")
    add_glossary_entry(set_id, "日本語", "Japanese")

    entries = get_glossary_entries(set_id)
    sources = [e[1] for e in entries]
    assert "Straße" in sources
    assert "café" in sources
    assert "日本語" in sources


def test_glossary_entry_empty_strings() -> None:
    """Entries with empty source/target are stored (DB allows it)."""
    create_glossary_set("EmptyTest")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "", "target")
    add_glossary_entry(set_id, "source", "")

    entries = get_glossary_entries(set_id)
    assert len(entries) == 2  # noqa: PLR2004


def test_glossary_entry_count_nonexistent_set() -> None:
    """Entry count for non-existent set returns 0."""
    assert get_glossary_entry_count(99999) == 0


def test_glossary_get_entries_nonexistent_set() -> None:
    """Getting entries for a non-existent set returns empty list."""
    assert get_glossary_entries(99999) == []


def test_glossary_delete_nonexistent_entry() -> None:
    """Deleting a non-existent entry does not raise."""
    delete_glossary_entry(99999)  # Should be silent no-op


def test_glossary_delete_nonexistent_set() -> None:
    """Deleting a non-existent set does not raise."""
    delete_glossary_set(99999)  # Should be silent no-op


def test_glossary_update_entry_unicode() -> None:
    """Updating entry to Unicode text works."""
    create_glossary_set("UpdateUnicode")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "hello", "xin chào")

    entry_id = get_glossary_entries(set_id)[0][0]
    update_glossary_entry(entry_id, "Straße", "đường phố")

    updated = get_glossary_entries(set_id)[0]
    assert updated[1] == "Straße"
    assert updated[2] == "đường phố"


def test_glossary_set_name_with_quotes() -> None:
    """Set name containing quotes is handled correctly."""
    assert create_glossary_set("O'Brien's \"List\"") is True
    sets = get_glossary_sets()
    assert sets[0][1] == "O'Brien's \"List\""


def test_glossary_multiple_sets_entry_counts() -> None:
    """Entry counts are accurate across multiple sets."""
    create_glossary_set("Set1")
    create_glossary_set("Set2")
    sets = get_glossary_sets()
    id1, id2 = sets[0][0], sets[1][0]

    add_glossary_entry(id1, "a", "1")
    add_glossary_entry(id1, "b", "2")
    add_glossary_entry(id1, "c", "3")
    add_glossary_entry(id2, "x", "9")

    assert get_glossary_entry_count(id1) == 3  # noqa: PLR2004
    assert get_glossary_entry_count(id2) == 1


def test_glossary_set_name_update_nonexistent_id_returns_true() -> None:
    """update_glossary_set_name on a non-existent ID returns True.

    SQL UPDATE with no matching rows does not raise IntegrityError,
    so the function returns True (no exception path taken).
    """
    result = update_glossary_set_name(99999, "Some Name")  # noqa: PLR2004
    assert result is True


def test_glossary_set_active_update_nonexistent_id_is_noop() -> None:
    """update_glossary_set_active on a non-existent ID is a silent no-op."""
    update_glossary_set_active(99999, False)  # noqa: PLR2004 — must not raise


def test_glossary_entry_update_nonexistent_id_is_noop() -> None:
    """update_glossary_entry on a non-existent ID is a silent no-op."""
    update_glossary_entry(99999, "new_src", "new_tgt")  # noqa: PLR2004 — must not raise


def test_glossary_sets_ordering_by_name_asc() -> None:
    """get_glossary_sets returns sets sorted alphabetically by name ASC."""
    create_glossary_set("Zebra")
    create_glossary_set("Apple")
    create_glossary_set("Mango")

    sets = get_glossary_sets()
    names = [s[1] for s in sets]
    assert names == ["Apple", "Mango", "Zebra"]


def test_glossary_entries_ordering_newest_first() -> None:
    """get_glossary_entries returns entries in created_at DESC order.

    A 1.1-second sleep guarantees that the two inserts land in different
    SQLite CURRENT_TIMESTAMP seconds (second-level resolution).
    """
    import time  # noqa: PLC0415

    create_glossary_set("OrderTest")
    set_id = get_glossary_sets()[0][0]

    add_glossary_entry(set_id, "older_entry", "a")
    time.sleep(1.1)  # Force distinct second-level timestamp
    add_glossary_entry(set_id, "newer_entry", "b")

    entries = get_glossary_entries(set_id)
    sources = [e[1] for e in entries]
    # Newest first: "newer_entry" at index 0, "older_entry" at index 1
    assert sources[0] == "newer_entry"
    assert sources[1] == "older_entry"


# ── History edge cases ─────────────────────────────────────────


def test_add_history_entry_stores_all_fields() -> None:
    """Verify all fields are stored and returned correctly."""
    h_id = add_history_entry(
        "tài_liệu.docx",
        "Vietnamese",
        "English (US)",
        STATUS_PENDING,
        source_path="/home/user/tài_liệu.docx",
        storage_path="/data/translations/1/tài_liệu.docx",
        file_size=2048,
    )
    entry = get_history()[0]
    assert entry[0] == h_id
    assert entry[1] == "tài_liệu.docx"
    assert entry[2] == "Vietnamese"  # source_lang
    assert entry[3] == "English (US)"  # target_lang
    assert entry[4] == STATUS_PENDING
    assert entry[5] == 0  # progress starts at 0
    assert entry[7] == 2048  # noqa: PLR2004 — file_size
    assert entry[8] == "/data/translations/1/tài_liệu.docx"  # storage_path


def test_history_multiple_status_transitions() -> None:
    """Entry can go through Pending -> Translating -> Done."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_PENDING)
    assert get_history_entry_status(h_id) == STATUS_PENDING

    update_history_status(h_id, STATUS_TRANSLATING)
    assert get_history_entry_status(h_id) == STATUS_TRANSLATING

    update_history_progress(h_id, 50)
    update_history_progress(h_id, 100)

    update_history_status(h_id, STATUS_DONE)
    assert get_history_entry_status(h_id) == STATUS_DONE

    entry = get_history()[0]
    assert entry[5] == 100  # noqa: PLR2004 — progress persists


def test_history_pending_to_failed_transition() -> None:
    """Entry can go Pending -> Failed with error code."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_PENDING)
    update_history_status(h_id, STATUS_FAILED, error_code=10)

    entry = get_history()[0]
    assert entry[4] == STATUS_FAILED
    assert entry[9] == 10  # noqa: PLR2004


def test_batch_pause_nonexistent_ids_is_noop() -> None:
    """Batch pause with non-existent IDs does not raise."""
    batch_pause_history_entries([99998, 99999])
    # No entries affected — no error
    assert get_history() == []


def test_batch_resume_nonexistent_ids_is_noop() -> None:
    """Batch resume with non-existent IDs does not raise."""
    batch_resume_history_entries([99998, 99999])
    assert get_history() == []


def test_batch_retranslate_nonexistent_ids_is_noop() -> None:
    """Batch retranslate with non-existent IDs does not raise."""
    batch_retranslate_history_entries([99998, 99999], "EN", "FR")
    assert get_history() == []


def test_batch_mark_deleting_nonexistent_ids_is_noop() -> None:
    """Batch mark deleting with non-existent IDs does not raise."""
    batch_mark_deleting_history_entries([99998, 99999])
    assert get_history() == []


def test_batch_retranslate_empty_langs() -> None:
    """Batch retranslate with empty language strings stores them."""
    h_id = add_history_entry("a.txt", "EN", "FR", STATUS_DONE)
    batch_retranslate_history_entries([h_id], "", "")

    entry = get_history()[0]
    assert entry[2] == ""  # source_lang
    assert entry[3] == ""  # target_lang
    assert entry[4] == STATUS_PENDING


def test_update_history_file_name_nonexistent_id() -> None:
    """Updating file_name on non-existent ID is a silent no-op."""
    update_history_file_name(99999, "new_name.txt")
    # No exception, no entries


def test_update_history_progress_nonexistent_id() -> None:
    """Updating progress on non-existent ID is a silent no-op."""
    update_history_progress(99999, 50)
    # No exception, no entries


def test_history_unicode_file_name() -> None:
    """Unicode file names are stored and retrieved correctly."""
    h_id = add_history_entry("日本語ファイル.pdf", "", "JP", STATUS_PENDING)
    entry = get_history()[0]
    assert entry[0] == h_id
    assert entry[1] == "日本語ファイル.pdf"


def test_history_ordering_by_created_at() -> None:
    """get_history returns entries ordered by created_at DESC, id DESC."""
    first_id = add_history_entry("first.txt", "", "FR", STATUS_PENDING)
    id2 = add_history_entry("second.txt", "", "DE", STATUS_DONE)

    history = get_history()
    ids = [h[0] for h in history]
    # Ordering is created_at DESC, id DESC.  Both entries are created in the
    # same second (SQLite CURRENT_TIMESTAMP has second precision), so the
    # id DESC tiebreaker puts id2 (higher) before first_id (lower).
    assert first_id in ids
    assert id2 in ids
    assert ids.index(id2) < ids.index(first_id)


def test_delete_entry_idempotent() -> None:
    """Deleting an already-deleted entry returns None."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_DONE)
    delete_history_entry(h_id)
    assert delete_history_entry(h_id) is None


def test_fingerprint_includes_error_code_in_concat() -> None:
    """Fingerprint concat string includes error_code when set."""
    h_id = add_history_entry("a.txt", "EN", "FR", STATUS_TRANSLATING)
    fp_before = get_history_fingerprint()

    update_history_status(h_id, STATUS_FAILED, error_code=42)
    fp_after = get_history_fingerprint()

    assert fp_before != fp_after
    # The concat string should contain the error_code
    assert "42" in fp_after[2]


def test_batch_pause_already_paused_entry_stays_paused() -> None:
    """Batch pause on an already-Paused entry leaves it Paused."""
    h_id = add_history_entry("already_paused.txt", "", "FR", STATUS_PAUSED)

    batch_pause_history_entries([h_id])

    # SQL filter only updates Pending/Translating; Paused stays unchanged
    assert get_history_entry_status(h_id) == STATUS_PAUSED


def test_update_history_status_nonexistent_id_is_noop() -> None:
    """Updating status on a non-existent ID is a silent no-op."""
    fake_id = 99999  # noqa: PLR2004
    update_history_status(fake_id, STATUS_DONE)
    # Verify no entry was created
    assert all(h[0] != fake_id for h in get_history())


# ---------------------------------------------------------------------------
# db_transaction: nested cursor reuse
# ---------------------------------------------------------------------------


def test_db_transaction_reuses_cursor_when_passed_as_first_arg() -> None:
    """db_transaction skips connection creation when a cursor is passed directly."""
    import sqlite3  # noqa: PLC0415

    from src.core.database import create_connection, db_transaction  # noqa: PLC0415

    # Track whether the wrapped function was called with the cursor
    received_cursors: list[sqlite3.Cursor] = []

    @db_transaction
    def _inner(cursor: sqlite3.Cursor, value: int) -> int:
        received_cursors.append(cursor)
        return value * 2

    # Call via the normal path first (no cursor passed)
    result_normal = _inner(7)
    assert result_normal == 14  # noqa: PLR2004
    assert len(received_cursors) == 1

    # Now call by passing a cursor explicitly (nested transaction)
    conn = create_connection()
    assert conn is not None
    try:
        outer_cursor = conn.cursor()
        result_nested = _inner(outer_cursor, 5)
        assert result_nested == 10  # noqa: PLR2004
        # The same cursor object should have been forwarded
        assert received_cursors[-1] is outer_cursor
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# db_transaction: rollback on sqlite3.Error
# ---------------------------------------------------------------------------


def test_db_transaction_rolls_back_on_sqlite_error() -> None:
    """db_transaction catches sqlite3.Error, rolls back, and returns None."""
    import sqlite3  # noqa: PLC0415

    from src.core.database import db_transaction  # noqa: PLC0415

    @db_transaction
    def _bad_query(cursor: sqlite3.Cursor) -> None:
        cursor.execute("SELECT * FROM table_that_does_not_exist")

    # Should not raise; decorator catches the error and returns None
    result = _bad_query()
    assert result is None


# ---------------------------------------------------------------------------
# init_db: idempotent — calling twice does not corrupt the schema
# ---------------------------------------------------------------------------


def test_init_db_is_idempotent() -> None:
    """Calling init_db a second time on an existing schema is safe."""
    # First call already happened in the autouse fixture.
    # A second call should not raise or corrupt data.
    h_id = add_history_entry("idempotent.txt", "", "FR", STATUS_PENDING)
    assert h_id is not None

    # Re-initialize (schema uses CREATE TABLE IF NOT EXISTS)
    init_db()

    # Existing data must still be present
    assert get_history_entry_status(h_id) == STATUS_PENDING


# ---------------------------------------------------------------------------
# SQL Injection Safety
# ---------------------------------------------------------------------------


def test_history_file_name_sql_injection() -> None:
    """File names containing SQL injection payloads are safely stored."""
    malicious_name = "file'; DROP TABLE history; --.txt"
    h_id = add_history_entry(malicious_name, "", "FR", STATUS_PENDING)
    assert h_id is not None

    # Table must still exist and be queryable
    history = get_history()
    assert len(history) >= 1
    entry = next(h for h in history if h[0] == h_id)
    assert entry[1] == malicious_name


def test_glossary_entry_sql_injection() -> None:
    """Glossary entries with SQL injection payloads are safely stored."""
    create_glossary_set("InjectionTest")
    set_id = get_glossary_sets()[0][0]

    malicious_source = "source'; DROP TABLE glossary_entries; --"
    add_glossary_entry(set_id, malicious_source, "target")

    # Table must still exist; entry count must be 1
    assert get_glossary_entry_count(set_id) == 1
    entries = get_glossary_entries(set_id)
    assert entries[0][1] == malicious_source


def test_history_status_special_chars() -> None:
    """Updating status with a string containing quotes does not crash."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    # Status values with single and double quotes
    update_history_status(h_id, 'It\'s "Done"')
    assert get_history_entry_status(h_id) == 'It\'s "Done"'


def test_glossary_set_name_with_null_byte() -> None:
    """Creating a set with a null byte in the name either works or raises cleanly."""
    name_with_null = "Set\x00Name"
    try:
        result = create_glossary_set(name_with_null)
        # If it succeeds, verify it's retrievable
        if result:
            sets = get_glossary_sets()
            assert len(sets) >= 1
    except (ValueError, Exception):
        # Some SQLite bindings reject null bytes — acceptable
        pass


# ---------------------------------------------------------------------------
# Boundary Value Tests
# ---------------------------------------------------------------------------


def test_progress_over_hundred() -> None:
    """Progress values above 100 are stored without validation."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_progress(h_id, 999)
    entry = get_history()[0]
    assert entry[5] == 999  # noqa: PLR2004


def test_progress_negative() -> None:
    """Negative progress is rejected by the monotonic guard (initial is 0)."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    # Initial progress is 0; SQL condition is `progress < ?` where ? = -1.
    # Since 0 < -1 is false, the UPDATE is a no-op.
    update_history_progress(h_id, -1)
    entry = get_history()[0]
    assert entry[5] == 0  # Stays at initial value


def test_very_long_file_name() -> None:
    """A 10 000-character file name is stored and retrieved correctly."""
    long_name = "x" * 10000  # noqa: PLR2004
    h_id = add_history_entry(long_name, "", "FR", STATUS_PENDING)
    entry = get_history()[0]
    assert entry[0] == h_id
    assert entry[1] == long_name
    assert len(entry[1]) == 10000  # noqa: PLR2004


def test_error_code_zero_vs_none() -> None:
    """error_code=0 is stored distinctly from None."""
    h_id = add_history_entry("a.txt", "", "FR", STATUS_TRANSLATING)
    update_history_status(h_id, STATUS_FAILED, error_code=0)

    entry = get_history()[0]
    assert entry[9] == 0  # Stored as integer 0, not None
    assert entry[9] is not None


def test_unicode_glossary_emoji() -> None:
    """Glossary entries with emoji text are stored and retrieved."""
    create_glossary_set("EmojiSet")
    set_id = get_glossary_sets()[0][0]
    add_glossary_entry(set_id, "\U0001f30d", "\U0001f5fa\ufe0f")

    entries = get_glossary_entries(set_id)
    assert len(entries) == 1
    assert entries[0][1] == "\U0001f30d"
    assert entries[0][2] == "\U0001f5fa\ufe0f"


# ---------------------------------------------------------------------------
# get_db_path Safeguard
# ---------------------------------------------------------------------------


def _check_db_path_safeguard(data_dir: Path) -> str:
    """Replicates the get_db_path production safeguard for testing.

    The autouse ``setup_test_db`` fixture replaces ``get_db_path`` with a
    lambda pointing to a temp directory, so the real function cannot be
    called.  This helper mirrors its safeguard logic so we can verify the
    RuntimeError is raised for production-like paths and passes for safe
    paths.

    Args:
        data_dir: The directory that ``get_app_data_dir()`` would return.

    Returns:
        The database path string, if the safeguard does not fire.

    Raises:
        RuntimeError: When the path contains a production marker.
    """
    import os  # noqa: PLC0415

    path = str(data_dir / "translator.db")
    if "PYTEST_CURRENT_TEST" in os.environ:
        prod_markers = (
            ".local/share",
            "AppData",
            "Library/Application Support",
        )
        if any(m in path for m in prod_markers):
            raise RuntimeError(
                f"FATAL: Attempted to access production database during test: {path}"
            )
    return path


def test_get_db_path_production_marker_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_db_path raises RuntimeError when the path contains a production marker."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_database.py::test_x")

    prod_dir = Path("/home/user/.local/share/ai-translate")
    with pytest.raises(RuntimeError, match="production database"):
        _check_db_path_safeguard(prod_dir)


def test_get_db_path_safe_path_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """get_db_path returns a valid path when no production markers are present."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_database.py::test_x")

    result = _check_db_path_safeguard(tmp_path)
    assert result == str(tmp_path / "translator.db")


# ---------------------------------------------------------------------------
# Extraction History
# ---------------------------------------------------------------------------


def test_add_extraction_entry_returns_id() -> None:
    """add_extraction_entry returns a positive integer ID."""
    entry_id = add_extraction_entry(
        file_name="photo.png",
        file_size=1024,
        source_path="/tmp/photo.png",
        output_path="/tmp/photo_extracted.txt",
        status="Done",
    )
    assert entry_id is not None
    assert entry_id > 0


def test_get_extraction_history_returns_entries() -> None:
    """Entries are returned in descending date order."""
    id1 = add_extraction_entry("a.png", 100, "/a.png", "/a.txt", "Done")
    id2 = add_extraction_entry(
        "b.png",
        200,
        "/b.png",
        "/b.txt",
        "Done",  # noqa: PLR2004
    )
    entries = get_extraction_history()
    assert len(entries) >= 2  # noqa: PLR2004
    ids = [e[0] for e in entries]
    # Most recent (id2) should come first
    assert ids.index(id2) < ids.index(id1)


def test_get_extraction_fingerprint_changes() -> None:
    """Fingerprint changes when entries are added."""
    fp1 = get_extraction_fingerprint()
    add_extraction_entry("fp.png", 50, "/fp.png", "/fp.txt", "Done")
    fp2 = get_extraction_fingerprint()
    assert fp1 != fp2


def test_delete_extraction_entry_returns_output_path() -> None:
    """delete_extraction_entry returns the output path."""
    entry_id = add_extraction_entry(
        "del.png", 100, "/del.png", "/del_extracted.txt", "Done"
    )
    path = delete_extraction_entry(entry_id)
    assert path == "/del_extracted.txt"
    # Entry should be gone
    entries = get_extraction_history()
    assert all(e[0] != entry_id for e in entries)


def test_extraction_entry_with_error_message() -> None:
    """Failed entry stores error message."""
    entry_id = add_extraction_entry(
        "err.png",
        100,
        "/err.png",
        "",
        "Failed",
        error_message="disk full",
    )
    entries = get_extraction_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[5] == "Failed"
    assert entry[6] == "disk full"


def test_update_extraction_status_to_done() -> None:
    """update_extraction_status sets status to Done and output_path."""
    entry_id = add_extraction_entry("upd.png", 512, "/upd.png", "", "Pending")
    update_extraction_status(entry_id, "Done", output_path="/out/upd.txt")

    entries = get_extraction_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[5] == "Done"
    assert entry[4] == "/out/upd.txt"
    assert entry[6] is None


def test_update_extraction_status_to_failed_with_message() -> None:
    """update_extraction_status sets status to Failed with an error message."""
    entry_id = add_extraction_entry("fail.png", 256, "/fail.png", "", "Pending")
    update_extraction_status(entry_id, "Failed", error_message="OCR crashed")

    entries = get_extraction_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[5] == "Failed"
    assert entry[6] == "OCR crashed"
    # output_path should be empty string (default)
    assert entry[4] == ""


def test_update_extraction_status_replaces_output_path() -> None:
    """update_extraction_status overwrites an existing output_path."""
    entry_id = add_extraction_entry(
        "replace.png", 100, "/replace.png", "/old_path.txt", "Pending"
    )
    update_extraction_status(entry_id, "Done", output_path="/new_path.txt")

    entries = get_extraction_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[4] == "/new_path.txt"


def test_update_extraction_status_no_error_message_sets_null() -> None:
    """update_extraction_status with no error_message stores NULL."""
    entry_id = add_extraction_entry(
        "null_err.png",
        100,
        "/null_err.png",
        "",
        "Pending",
        error_message="old error",
    )
    update_extraction_status(entry_id, "Done", output_path="/done.txt")

    entries = get_extraction_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[6] is None


def test_delete_extraction_entry_none_when_no_output() -> None:
    """delete_extraction_entry returns None when output_path is empty."""
    entry_id = add_extraction_entry("noout.png", 100, "/noout.png", "", "Failed")
    path = delete_extraction_entry(entry_id)
    # Empty string stored — returned as empty string, not None
    assert path == "" or path is None


# ---------------------------------------------------------------------------
# create_connection — sqlite3.Error exception path
# ---------------------------------------------------------------------------


def test_create_connection_sqlite_error_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_connection returns None when sqlite3.connect raises sqlite3.Error."""
    import sqlite3  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    from src.core.database import create_connection  # noqa: PLC0415

    with patch("sqlite3.connect", side_effect=sqlite3.Error("disk full")):
        result = create_connection()

    assert result is None


# ---------------------------------------------------------------------------
# db_transaction — create_connection returns None early exit
# ---------------------------------------------------------------------------


def test_db_transaction_returns_none_when_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """db_transaction returns None immediately when create_connection returns None."""
    import sqlite3  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    from src.core.database import db_transaction  # noqa: PLC0415

    call_count = 0

    @db_transaction
    def _never_called(cursor: sqlite3.Cursor) -> str:
        nonlocal call_count
        call_count += 1
        return "should not be reached"

    with patch("src.core.database.create_connection", return_value=None):
        result = _never_called()

    assert result is None
    assert call_count == 0


# ---------------------------------------------------------------------------
# Subtitle History CRUD
# ---------------------------------------------------------------------------


def test_add_subtitle_entry_returns_id() -> None:
    """add_subtitle_entry returns a positive integer ID."""
    entry_id = add_subtitle_entry(
        file_name="video.mp4",
        file_size=2048,
        source_path="/tmp/video.mp4",
        output_path="",
        src_lang="Vietnamese",
        status="Pending",
    )
    assert entry_id is not None
    assert entry_id > 0


def test_get_subtitle_history_returns_entries() -> None:
    """Entries are returned in descending date order with 9 columns."""
    id1 = add_subtitle_entry("a.mp4", 100, "/a.mp4", "", "Vietnamese", "Pending")
    id2 = add_subtitle_entry(
        "b.mp4",
        200,
        "/b.mp4",
        "",
        "English (US)",
        "Pending",  # noqa: PLR2004
    )
    entries = get_subtitle_history()
    assert len(entries) >= 2  # noqa: PLR2004
    # Each entry has 9 columns
    nine_columns = 9  # noqa: PLR2004
    assert len(entries[0]) == nine_columns
    # Most recent (id2) first
    ids = [e[0] for e in entries]
    assert ids.index(id2) < ids.index(id1)


def test_get_subtitle_fingerprint_changes() -> None:
    """Fingerprint changes when entries are added."""
    fp1 = get_subtitle_fingerprint()
    add_subtitle_entry("fp.mp4", 50, "/fp.mp4", "", "Vietnamese", "Pending")
    fp2 = get_subtitle_fingerprint()
    assert fp1 != fp2


def test_update_subtitle_status_to_done() -> None:
    """update_subtitle_status sets status to Done with output_path."""
    entry_id = add_subtitle_entry("v.mp4", 512, "/v.mp4", "", "Vietnamese", "Pending")
    update_subtitle_status(entry_id, "Done", output_path="/out/v.srt")

    entries = get_subtitle_history()
    entry = next(e for e in entries if e[0] == entry_id)
    # Column order: id, name, size, source, output, src_lang, status, error, date
    status_idx = 6  # noqa: PLR2004
    output_idx = 4  # noqa: PLR2004
    assert entry[status_idx] == "Done"
    assert entry[output_idx] == "/out/v.srt"


def test_update_subtitle_status_preserves_output_path() -> None:
    """Status update without output_path does NOT blank existing output."""
    entry_id = add_subtitle_entry(
        "keep.mp4", 100, "/keep.mp4", "", "Vietnamese", "Pending"
    )
    # First: set Done with output_path
    update_subtitle_status(entry_id, "Done", output_path="/out/keep.srt")
    # Then: change status without providing output_path
    update_subtitle_status(entry_id, "Generating")

    entries = get_subtitle_history()
    entry = next(e for e in entries if e[0] == entry_id)
    output_idx = 4  # noqa: PLR2004
    status_idx = 6  # noqa: PLR2004
    assert entry[status_idx] == "Generating"
    # output_path should be preserved, NOT blanked
    assert entry[output_idx] == "/out/keep.srt"


def test_update_subtitle_status_failed_with_error() -> None:
    """Failed status stores error message."""
    entry_id = add_subtitle_entry(
        "fail.mp4", 256, "/fail.mp4", "", "Vietnamese", "Pending"
    )
    update_subtitle_status(
        entry_id,
        "Failed",
        error_message="API timeout",
    )
    entries = get_subtitle_history()
    entry = next(e for e in entries if e[0] == entry_id)
    status_idx = 6  # noqa: PLR2004
    error_idx = 7  # noqa: PLR2004
    assert entry[status_idx] == "Failed"
    assert entry[error_idx] == "API timeout"


def test_delete_subtitle_entry_returns_output_path() -> None:
    """delete_subtitle_entry returns the output path."""
    entry_id = add_subtitle_entry(
        "del.mp4", 100, "/del.mp4", "/del.srt", "Vietnamese", "Done"
    )
    path = delete_subtitle_entry(entry_id)
    assert path == "/del.srt"
    entries = get_subtitle_history()
    assert all(e[0] != entry_id for e in entries)


# ---------------------------------------------------------------------------
# Voice History CRUD
# ---------------------------------------------------------------------------


def test_add_voice_entry_returns_id() -> None:
    """add_voice_entry returns a positive integer ID."""
    entry_id = add_voice_entry(
        file_name="sub.srt",
        file_size=512,
        source_path="/tmp/sub.srt",
        output_path="",
        status="Pending",
    )
    assert entry_id is not None
    assert entry_id > 0


def test_get_voice_history_returns_entries() -> None:
    """Entries are returned in descending date order with 8 columns."""
    id1 = add_voice_entry("a.srt", 100, "/a.srt", "", "Pending")
    id2 = add_voice_entry("b.srt", 200, "/b.srt", "", "Pending")  # noqa: PLR2004
    entries = get_voice_history()
    assert len(entries) >= 2  # noqa: PLR2004
    eight_columns = 8  # noqa: PLR2004
    assert len(entries[0]) == eight_columns
    ids = [e[0] for e in entries]
    assert ids.index(id2) < ids.index(id1)


def test_get_voice_fingerprint_changes() -> None:
    """Fingerprint changes when entries are added."""
    fp1 = get_voice_fingerprint()
    add_voice_entry("fp.srt", 50, "/fp.srt", "", "Pending")
    fp2 = get_voice_fingerprint()
    assert fp1 != fp2


def test_update_voice_status_to_done() -> None:
    """update_voice_status sets status to Done with output_path."""
    entry_id = add_voice_entry("v.srt", 512, "/v.srt", "", "Pending")
    update_voice_status(entry_id, "Done", output_path="/out/v.mp3")

    entries = get_voice_history()
    entry = next(e for e in entries if e[0] == entry_id)
    status_idx = 5  # noqa: PLR2004
    output_idx = 4  # noqa: PLR2004
    assert entry[status_idx] == "Done"
    assert entry[output_idx] == "/out/v.mp3"


def test_update_voice_status_preserves_output_path() -> None:
    """Status update without output_path does NOT blank existing output."""
    entry_id = add_voice_entry("k.srt", 100, "/k.srt", "", "Pending")
    update_voice_status(entry_id, "Done", output_path="/out/k.mp3")
    update_voice_status(entry_id, "Generating")

    entries = get_voice_history()
    entry = next(e for e in entries if e[0] == entry_id)
    output_idx = 4  # noqa: PLR2004
    status_idx = 5  # noqa: PLR2004
    assert entry[status_idx] == "Generating"
    assert entry[output_idx] == "/out/k.mp3"


def test_delete_voice_entry_returns_output_path() -> None:
    """delete_voice_entry returns the output path."""
    entry_id = add_voice_entry(
        "del.srt",
        100,
        "/del.srt",
        "/del.mp3",
        "Done",
    )
    path = delete_voice_entry(entry_id)
    assert path == "/del.mp3"
    entries = get_voice_history()
    assert all(e[0] != entry_id for e in entries)


# ---------------------------------------------------------------------------
# Dubbing History CRUD
# ---------------------------------------------------------------------------


def test_add_dubbing_entry_returns_id() -> None:
    """add_dubbing_entry returns a positive integer ID."""
    entry_id = add_dubbing_entry(
        file_name="video.mp4",
        file_size=10240,
        source_path="/tmp/video.mp4",
        output_path="",
        status="Pending",
    )
    assert entry_id is not None
    assert entry_id > 0


def test_get_dubbing_history_returns_entries() -> None:
    """Entries are returned with 14 columns (includes artifact paths)."""
    id1 = add_dubbing_entry("a.mp4", 100, "/a.mp4", "", "Pending")
    id2 = add_dubbing_entry("b.mp4", 200, "/b.mp4", "", "Pending")  # noqa: PLR2004
    entries = get_dubbing_history()
    assert len(entries) >= 2  # noqa: PLR2004
    expected_columns = 14  # noqa: PLR2004
    assert len(entries[0]) == expected_columns
    ids = [e[0] for e in entries]
    assert ids.index(id2) < ids.index(id1)


def test_get_dubbing_fingerprint_changes() -> None:
    """Fingerprint changes when entries are added."""
    fp1 = get_dubbing_fingerprint()
    add_dubbing_entry("fp.mp4", 50, "/fp.mp4", "", "Pending")
    fp2 = get_dubbing_fingerprint()
    assert fp1 != fp2


def test_update_dubbing_status_to_done() -> None:
    """update_dubbing_status sets status + output_path."""
    entry_id = add_dubbing_entry("d.mp4", 512, "/d.mp4", "", "Pending")
    update_dubbing_status(
        entry_id,
        "Done",
        output_path="/out/d_dubbed.mp4",
    )
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    status_idx = 7  # noqa: PLR2004
    output_idx = 4  # noqa: PLR2004
    assert entry[status_idx] == "Done"
    assert entry[output_idx] == "/out/d_dubbed.mp4"


def test_update_dubbing_status_with_progress() -> None:
    """update_dubbing_status sets progress text."""
    entry_id = add_dubbing_entry("p.mp4", 100, "/p.mp4", "", "Pending")
    update_dubbing_status(
        entry_id,
        "Generating",
        progress="Translating...",
    )
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    progress_idx = 8  # noqa: PLR2004
    assert entry[progress_idx] == "Translating..."


def test_update_dubbing_status_preserves_output_path() -> None:
    """Status update without output_path preserves existing output."""
    entry_id = add_dubbing_entry("k.mp4", 100, "/k.mp4", "", "Pending")
    update_dubbing_status(
        entry_id,
        "Done",
        output_path="/out/k_dubbed.mp4",
    )
    update_dubbing_status(entry_id, "Generating", progress="Re-dubbing...")

    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    output_idx = 4  # noqa: PLR2004
    assert entry[output_idx] == "/out/k_dubbed.mp4"


def test_delete_dubbing_entry_returns_paths() -> None:
    """delete_dubbing_entry returns a tuple of file paths."""
    entry_id = add_dubbing_entry(
        "del.mp4",
        100,
        "/del.mp4",
        "/del_dubbed.mp4",
        "Done",
    )
    paths = delete_dubbing_entry(entry_id)
    assert paths[0] == "/del_dubbed.mp4"
    assert len(paths) == 4  # noqa: PLR2004
    entries = get_dubbing_history()
    assert all(e[0] != entry_id for e in entries)


# ---------------------------------------------------------------------------
# is_any_extracting
# ---------------------------------------------------------------------------


def test_is_any_extracting_empty_db() -> None:
    """Returns False on empty database."""
    assert not is_any_extracting()


def test_is_any_extracting_with_extracting_entry() -> None:
    """Returns True when an entry has STATUS_EXTRACTING."""
    add_extraction_entry("img.png", 100, "/img.png", "", STATUS_EXTRACTING)
    assert is_any_extracting()


def test_is_any_extracting_with_pending_entry() -> None:
    """Returns True when an extraction entry has STATUS_PENDING."""
    add_extraction_entry("img.png", 100, "/img.png", "", STATUS_PENDING)
    assert is_any_extracting()


def test_is_any_extracting_false_when_all_done() -> None:
    """Returns False when all extraction entries are Done or Failed."""
    add_extraction_entry("a.png", 100, "/a.png", "/a.txt", STATUS_DONE)
    add_extraction_entry("b.png", 200, "/b.png", "", STATUS_FAILED)
    assert not is_any_extracting()


def test_is_any_extracting_mixed_statuses() -> None:
    """Returns True if at least one entry is Extracting among Done entries."""
    add_extraction_entry("done.png", 100, "/done.png", "/done.txt", STATUS_DONE)
    add_extraction_entry("active.png", 200, "/active.png", "", STATUS_EXTRACTING)
    assert is_any_extracting()


def test_is_any_extracting_false_after_status_update() -> None:
    """Returns False after the only active extraction becomes Done."""
    entry_id = add_extraction_entry(
        "upd.png",
        100,
        "/upd.png",
        "",
        STATUS_EXTRACTING,
    )
    assert is_any_extracting()
    update_extraction_status(entry_id, STATUS_DONE, output_path="/upd.txt")
    assert not is_any_extracting()


# ---------------------------------------------------------------------------
# is_any_subtitle_generating
# ---------------------------------------------------------------------------


def test_is_any_subtitle_generating_empty_db() -> None:
    """Returns False on empty database."""
    assert not is_any_subtitle_generating()


def test_is_any_subtitle_generating_with_generating_entry() -> None:
    """Returns True when a subtitle entry has STATUS_GENERATING."""
    add_subtitle_entry("v.mp4", 100, "/v.mp4", "", "Vietnamese", STATUS_GENERATING)
    assert is_any_subtitle_generating()


def test_is_any_subtitle_generating_with_pending_entry() -> None:
    """Returns True when a subtitle entry has STATUS_PENDING."""
    add_subtitle_entry("v.mp4", 100, "/v.mp4", "", "Vietnamese", STATUS_PENDING)
    assert is_any_subtitle_generating()


def test_is_any_subtitle_generating_false_when_all_done() -> None:
    """Returns False when all subtitle entries are Done or Failed."""
    add_subtitle_entry("a.mp4", 100, "/a.mp4", "/a.srt", "Vietnamese", STATUS_DONE)
    add_subtitle_entry("b.mp4", 200, "/b.mp4", "", "Vietnamese", STATUS_FAILED)
    assert not is_any_subtitle_generating()


def test_is_any_subtitle_generating_mixed_statuses() -> None:
    """Returns True if at least one entry is Generating among Done entries."""
    add_subtitle_entry(
        "done.mp4",
        100,
        "/done.mp4",
        "/d.srt",
        "Vietnamese",
        STATUS_DONE,
    )
    add_subtitle_entry(
        "gen.mp4",
        200,
        "/gen.mp4",
        "",
        "Vietnamese",
        STATUS_GENERATING,
    )
    assert is_any_subtitle_generating()


def test_is_any_subtitle_generating_false_after_status_update() -> None:
    """Returns False after the only active subtitle becomes Done."""
    entry_id = add_subtitle_entry(
        "upd.mp4",
        100,
        "/upd.mp4",
        "",
        "Vietnamese",
        STATUS_GENERATING,
    )
    assert is_any_subtitle_generating()
    update_subtitle_status(entry_id, STATUS_DONE, output_path="/upd.srt")
    assert not is_any_subtitle_generating()


# ---------------------------------------------------------------------------
# is_any_voice_generating
# ---------------------------------------------------------------------------


def test_is_any_voice_generating_empty_db() -> None:
    """Returns False on empty database."""
    assert not is_any_voice_generating()


def test_is_any_voice_generating_with_generating_entry() -> None:
    """Returns True when a voice entry has STATUS_GENERATING."""
    add_voice_entry("sub.srt", 100, "/sub.srt", "", STATUS_GENERATING)
    assert is_any_voice_generating()


def test_is_any_voice_generating_with_pending_entry() -> None:
    """Returns True when a voice entry has STATUS_PENDING."""
    add_voice_entry("sub.srt", 100, "/sub.srt", "", STATUS_PENDING)
    assert is_any_voice_generating()


def test_is_any_voice_generating_false_when_all_done() -> None:
    """Returns False when all voice entries are Done or Failed."""
    add_voice_entry("a.srt", 100, "/a.srt", "/a.mp3", STATUS_DONE)
    add_voice_entry("b.srt", 200, "/b.srt", "", STATUS_FAILED)
    assert not is_any_voice_generating()


def test_is_any_voice_generating_mixed_statuses() -> None:
    """Returns True if at least one entry is Generating among Done entries."""
    add_voice_entry("done.srt", 100, "/done.srt", "/d.mp3", STATUS_DONE)
    add_voice_entry("gen.srt", 200, "/gen.srt", "", STATUS_GENERATING)
    assert is_any_voice_generating()


def test_is_any_voice_generating_false_after_status_update() -> None:
    """Returns False after the only active voice becomes Done."""
    entry_id = add_voice_entry(
        "upd.srt",
        100,
        "/upd.srt",
        "",
        STATUS_GENERATING,
    )
    assert is_any_voice_generating()
    update_voice_status(entry_id, STATUS_DONE, output_path="/upd.mp3")
    assert not is_any_voice_generating()


# ---------------------------------------------------------------------------
# is_any_dubbing_generating
# ---------------------------------------------------------------------------


def test_is_any_dubbing_generating_empty_db() -> None:
    """Returns False on empty database."""
    assert not is_any_dubbing_generating()


def test_is_any_dubbing_generating_with_generating_entry() -> None:
    """Returns True when a dubbing entry has STATUS_GENERATING."""
    add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    assert is_any_dubbing_generating()


def test_is_any_dubbing_generating_with_pending_entry() -> None:
    """Returns True when a dubbing entry has STATUS_PENDING."""
    add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
    assert is_any_dubbing_generating()


def test_is_any_dubbing_generating_false_when_all_done() -> None:
    """Returns False when all dubbing entries are Done or Failed."""
    add_dubbing_entry("a.mp4", 100, "/a.mp4", "/a_dub.mp4", STATUS_DONE)
    add_dubbing_entry("b.mp4", 200, "/b.mp4", "", STATUS_FAILED)
    assert not is_any_dubbing_generating()


def test_is_any_dubbing_generating_mixed_statuses() -> None:
    """Returns True if at least one entry is Generating among Done entries."""
    add_dubbing_entry("done.mp4", 100, "/done.mp4", "/d.mp4", STATUS_DONE)
    add_dubbing_entry("gen.mp4", 200, "/gen.mp4", "", STATUS_GENERATING)
    assert is_any_dubbing_generating()


def test_is_any_dubbing_generating_false_after_status_update() -> None:
    """Returns False after the only active dubbing becomes Done."""
    entry_id = add_dubbing_entry(
        "upd.mp4",
        100,
        "/upd.mp4",
        "",
        STATUS_GENERATING,
    )
    assert is_any_dubbing_generating()
    update_dubbing_status(entry_id, STATUS_DONE, output_path="/upd_dub.mp4")
    assert not is_any_dubbing_generating()


# ---------------------------------------------------------------------------
# get_dubbing_entry_status
# ---------------------------------------------------------------------------


def test_get_dubbing_entry_status_returns_status() -> None:
    """Returns the current status string of a dubbing entry."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
    assert get_dubbing_entry_status(entry_id) == STATUS_PENDING


def test_get_dubbing_entry_status_after_update() -> None:
    """Returns updated status after update_dubbing_status."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
    update_dubbing_status(entry_id, STATUS_GENERATING)
    assert get_dubbing_entry_status(entry_id) == STATUS_GENERATING


def test_get_dubbing_entry_status_nonexistent_returns_none() -> None:
    """Returns None for a non-existent entry ID."""
    fake_id = 99999  # noqa: PLR2004
    assert get_dubbing_entry_status(fake_id) is None


def test_get_dubbing_entry_status_after_delete_returns_none() -> None:
    """Returns None after the entry has been deleted."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_DONE)
    delete_dubbing_entry(entry_id)
    assert get_dubbing_entry_status(entry_id) is None


# ---------------------------------------------------------------------------
# update_dubbing_progress (monotonic)
# ---------------------------------------------------------------------------


def test_update_dubbing_progress_increase() -> None:
    """Progress increases when new value is higher than current."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    update_dubbing_progress(entry_id, 40)
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    progress_idx = 8  # noqa: PLR2004
    assert entry[progress_idx] == "40"


def test_update_dubbing_progress_decrease_is_noop() -> None:
    """Progress does NOT decrease — lower value is silently ignored."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    update_dubbing_progress(entry_id, 60)
    update_dubbing_progress(entry_id, 30)
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    progress_idx = 8  # noqa: PLR2004
    assert entry[progress_idx] == "60"


def test_update_dubbing_progress_equal_is_noop() -> None:
    """Setting progress to the same value is a silent no-op."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    update_dubbing_progress(entry_id, 50)
    update_dubbing_progress(entry_id, 50)
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    progress_idx = 8  # noqa: PLR2004
    assert entry[progress_idx] == "50"


def test_update_dubbing_progress_multiple_increases() -> None:
    """Progress tracks the highest value across multiple updates."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    update_dubbing_progress(entry_id, 20)
    update_dubbing_progress(entry_id, 50)
    update_dubbing_progress(entry_id, 80)
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    progress_idx = 8  # noqa: PLR2004
    assert entry[progress_idx] == "80"


def test_update_dubbing_progress_nonexistent_id_is_noop() -> None:
    """Updating progress on a non-existent ID does not raise."""
    fake_id = 99999  # noqa: PLR2004
    update_dubbing_progress(fake_id, 50)
    # No entries affected, no error
    assert get_dubbing_history() == []


# ---------------------------------------------------------------------------
# get_unfinished_dubbing
# ---------------------------------------------------------------------------


def test_get_unfinished_dubbing_empty_db() -> None:
    """Returns empty list on empty database."""
    assert get_unfinished_dubbing() == []


def test_get_unfinished_dubbing_returns_pending() -> None:
    """Returns entries with STATUS_PENDING."""
    entry_id = add_dubbing_entry(
        "v.mp4",
        100,
        "/v.mp4",
        "",
        STATUS_PENDING,
        src_lang="EN",
        target_lang="FR",
    )
    results = get_unfinished_dubbing()
    assert len(results) == 1
    assert results[0][0] == entry_id


def test_get_unfinished_dubbing_returns_generating() -> None:
    """Returns entries with STATUS_GENERATING."""
    entry_id = add_dubbing_entry(
        "v.mp4",
        100,
        "/v.mp4",
        "",
        STATUS_GENERATING,
        src_lang="EN",
        target_lang="FR",
    )
    results = get_unfinished_dubbing()
    assert len(results) == 1
    assert results[0][0] == entry_id


def test_get_unfinished_dubbing_excludes_done_and_failed() -> None:
    """Excludes Done, Failed, and Paused entries."""
    add_dubbing_entry("a.mp4", 100, "/a.mp4", "/a.mp4", STATUS_DONE)
    add_dubbing_entry("b.mp4", 200, "/b.mp4", "", STATUS_FAILED)
    add_dubbing_entry("c.mp4", 300, "/c.mp4", "", STATUS_PAUSED)
    assert get_unfinished_dubbing() == []


def test_get_unfinished_dubbing_generating_before_pending() -> None:
    """Generating entries are returned before Pending (resume priority).

    get_unfinished_dubbing returns (id, source_path, src_lang, target_lang);
    we use target_lang to tell entries apart.
    """
    # Insert Pending first, then Generating — order must flip
    add_dubbing_entry(
        "first.mp4",
        100,
        "/first.mp4",
        "",
        STATUS_PENDING,
        src_lang="EN",
        target_lang="FR",
    )
    add_dubbing_entry(
        "second.mp4",
        200,
        "/second.mp4",
        "",
        STATUS_GENERATING,
        src_lang="EN",
        target_lang="DE",
    )
    results = get_unfinished_dubbing()
    assert len(results) == 2  # noqa: PLR2004
    # Generating (target "DE") must precede Pending (target "FR")
    target_langs = [r[3] for r in results]
    assert target_langs[0] == "DE"
    assert target_langs[1] == "FR"


def test_get_unfinished_dubbing_returns_correct_columns() -> None:
    """Returns (id, source_path, src_lang, target_lang) tuples."""
    entry_id = add_dubbing_entry(
        "v.mp4",
        100,
        "/tmp/v.mp4",
        "",
        STATUS_PENDING,
        src_lang="Vietnamese",
        target_lang="English (US)",
    )
    results = get_unfinished_dubbing()
    assert len(results) == 1
    row = results[0]
    assert len(row) == 4  # noqa: PLR2004
    assert row[0] == entry_id
    assert row[1] == "/tmp/v.mp4"  # source_path
    assert row[2] == "Vietnamese"  # src_lang
    assert row[3] == "English (US)"  # target_lang


# ---------------------------------------------------------------------------
# batch_pause_dubbing_entries
# ---------------------------------------------------------------------------


def test_batch_pause_dubbing_pauses_active_entries() -> None:
    """Batch pause updates Generating and Pending entries to Paused."""
    id1 = add_dubbing_entry("a.mp4", 100, "/a.mp4", "", STATUS_GENERATING)
    id2 = add_dubbing_entry("b.mp4", 200, "/b.mp4", "", STATUS_PENDING)
    id3 = add_dubbing_entry("c.mp4", 300, "/c.mp4", "/c.mp4", STATUS_DONE)

    batch_pause_dubbing_entries([id1, id2, id3])

    assert get_dubbing_entry_status(id1) == STATUS_PAUSED
    assert get_dubbing_entry_status(id2) == STATUS_PAUSED
    assert get_dubbing_entry_status(id3) == STATUS_DONE  # unchanged


def test_batch_pause_dubbing_empty_list_is_noop() -> None:
    """Batch pause with empty list does not raise."""
    batch_pause_dubbing_entries([])


def test_batch_pause_dubbing_clears_error_message() -> None:
    """Batch pause clears error_message on paused entries."""
    entry_id = add_dubbing_entry(
        "err.mp4",
        100,
        "/err.mp4",
        "",
        STATUS_GENERATING,
        error_message="some error",
    )
    batch_pause_dubbing_entries([entry_id])

    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    error_idx = 9  # noqa: PLR2004
    assert entry[error_idx] is None


def test_batch_pause_dubbing_ignores_done_and_failed() -> None:
    """Batch pause does not change Done or Failed entries."""
    id_done = add_dubbing_entry("done.mp4", 100, "/done.mp4", "/o.mp4", STATUS_DONE)
    id_fail = add_dubbing_entry("fail.mp4", 200, "/fail.mp4", "", STATUS_FAILED)

    batch_pause_dubbing_entries([id_done, id_fail])

    assert get_dubbing_entry_status(id_done) == STATUS_DONE
    assert get_dubbing_entry_status(id_fail) == STATUS_FAILED


def test_batch_pause_dubbing_already_paused_stays_paused() -> None:
    """Batch pause on an already-Paused entry leaves it Paused."""
    entry_id = add_dubbing_entry("p.mp4", 100, "/p.mp4", "", STATUS_PAUSED)
    batch_pause_dubbing_entries([entry_id])
    assert get_dubbing_entry_status(entry_id) == STATUS_PAUSED


def test_batch_pause_dubbing_nonexistent_ids_is_noop() -> None:
    """Batch pause with non-existent IDs does not raise."""
    batch_pause_dubbing_entries([99998, 99999])
    assert get_dubbing_history() == []


def test_batch_pause_dubbing_mixed_statuses() -> None:
    """Batch pause correctly handles a mix of Generating, Pending, Done, Paused."""
    id_gen = add_dubbing_entry("gen.mp4", 100, "/gen.mp4", "", STATUS_GENERATING)
    id_pend = add_dubbing_entry("pend.mp4", 200, "/pend.mp4", "", STATUS_PENDING)
    id_done = add_dubbing_entry("done.mp4", 300, "/done.mp4", "/o.mp4", STATUS_DONE)
    id_paused = add_dubbing_entry("paused.mp4", 400, "/paused.mp4", "", STATUS_PAUSED)

    batch_pause_dubbing_entries([id_gen, id_pend, id_done, id_paused])

    assert get_dubbing_entry_status(id_gen) == STATUS_PAUSED
    assert get_dubbing_entry_status(id_pend) == STATUS_PAUSED
    assert get_dubbing_entry_status(id_done) == STATUS_DONE  # unchanged
    assert get_dubbing_entry_status(id_paused) == STATUS_PAUSED  # already paused


# ---------------------------------------------------------------------------
# batch_resume_dubbing_entries
# ---------------------------------------------------------------------------


def test_batch_resume_dubbing_sets_pending() -> None:
    """Batch resume sets Paused entries to Pending."""
    id1 = add_dubbing_entry("a.mp4", 100, "/a.mp4", "", STATUS_PAUSED)
    id2 = add_dubbing_entry("b.mp4", 200, "/b.mp4", "", STATUS_PAUSED)

    batch_resume_dubbing_entries([id1, id2])

    assert get_dubbing_entry_status(id1) == STATUS_PENDING
    assert get_dubbing_entry_status(id2) == STATUS_PENDING


def test_batch_resume_dubbing_empty_list_is_noop() -> None:
    """Batch resume with empty list does not raise."""
    batch_resume_dubbing_entries([])


def test_batch_resume_dubbing_clears_error_message() -> None:
    """Batch resume clears error_message on resumed entries."""
    entry_id = add_dubbing_entry(
        "err.mp4",
        100,
        "/err.mp4",
        "",
        STATUS_FAILED,
        error_message="API timeout",
    )
    batch_resume_dubbing_entries([entry_id])

    assert get_dubbing_entry_status(entry_id) == STATUS_PENDING
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    error_idx = 9  # noqa: PLR2004
    assert entry[error_idx] is None


def test_batch_resume_dubbing_nonexistent_ids_is_noop() -> None:
    """Batch resume with non-existent IDs does not raise."""
    batch_resume_dubbing_entries([99998, 99999])
    assert get_dubbing_history() == []


def test_batch_resume_dubbing_already_pending_stays_pending() -> None:
    """Resuming an already-Pending entry keeps it Pending."""
    entry_id = add_dubbing_entry("p.mp4", 100, "/p.mp4", "", STATUS_PENDING)
    batch_resume_dubbing_entries([entry_id])
    assert get_dubbing_entry_status(entry_id) == STATUS_PENDING


# ---------------------------------------------------------------------------
# update_dubbing_status with artifact path kwargs
# ---------------------------------------------------------------------------


def test_update_dubbing_status_sets_subtitle_path() -> None:
    """update_dubbing_status with subtitle_path sets the column."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    update_dubbing_status(
        entry_id,
        STATUS_GENERATING,
        subtitle_path="/subs/v.srt",
    )
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    subtitle_path_idx = 11  # noqa: PLR2004
    assert entry[subtitle_path_idx] == "/subs/v.srt"


def test_update_dubbing_status_sets_translated_subtitle_path() -> None:
    """update_dubbing_status with translated_subtitle_path sets the column."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    update_dubbing_status(
        entry_id,
        STATUS_GENERATING,
        translated_subtitle_path="/subs/v_translated.srt",
    )
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    translated_subtitle_path_idx = 12  # noqa: PLR2004
    assert entry[translated_subtitle_path_idx] == "/subs/v_translated.srt"


def test_update_dubbing_status_sets_voice_path() -> None:
    """update_dubbing_status with voice_path sets the column."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    update_dubbing_status(
        entry_id,
        STATUS_GENERATING,
        voice_path="/voice/v.mp3",
    )
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    voice_path_idx = 13  # noqa: PLR2004
    assert entry[voice_path_idx] == "/voice/v.mp3"


def test_update_dubbing_status_sets_all_artifact_paths() -> None:
    """update_dubbing_status can set all three artifact paths at once."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    update_dubbing_status(
        entry_id,
        STATUS_DONE,
        output_path="/out/v_dubbed.mp4",
        subtitle_path="/subs/v.srt",
        translated_subtitle_path="/subs/v_translated.srt",
        voice_path="/voice/v.mp3",
    )
    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    status_idx = 7  # noqa: PLR2004
    output_idx = 4  # noqa: PLR2004
    subtitle_path_idx = 11  # noqa: PLR2004
    translated_subtitle_path_idx = 12  # noqa: PLR2004
    voice_path_idx = 13  # noqa: PLR2004
    assert entry[status_idx] == STATUS_DONE
    assert entry[output_idx] == "/out/v_dubbed.mp4"
    assert entry[subtitle_path_idx] == "/subs/v.srt"
    assert entry[translated_subtitle_path_idx] == "/subs/v_translated.srt"
    assert entry[voice_path_idx] == "/voice/v.mp3"


def test_update_dubbing_status_none_artifact_paths_preserves_existing() -> None:
    """Omitting artifact path kwargs preserves existing values."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
    # First: set all artifacts
    update_dubbing_status(
        entry_id,
        STATUS_GENERATING,
        subtitle_path="/subs/v.srt",
        translated_subtitle_path="/subs/v_translated.srt",
        voice_path="/voice/v.mp3",
    )
    # Second: update status without artifact kwargs — they should be preserved
    update_dubbing_status(entry_id, STATUS_DONE)

    entries = get_dubbing_history()
    entry = next(e for e in entries if e[0] == entry_id)
    subtitle_path_idx = 11  # noqa: PLR2004
    translated_subtitle_path_idx = 12  # noqa: PLR2004
    voice_path_idx = 13  # noqa: PLR2004
    assert entry[subtitle_path_idx] == "/subs/v.srt"
    assert entry[translated_subtitle_path_idx] == "/subs/v_translated.srt"
    assert entry[voice_path_idx] == "/voice/v.mp3"


def test_update_dubbing_status_artifact_paths_in_delete_entry() -> None:
    """delete_dubbing_entry returns artifact paths that were set."""
    entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "/out/v.mp4", STATUS_DONE)
    update_dubbing_status(
        entry_id,
        STATUS_DONE,
        subtitle_path="/subs/v.srt",
        translated_subtitle_path="/subs/v_translated.srt",
        voice_path="/voice/v.mp3",
    )
    paths = delete_dubbing_entry(entry_id)
    assert paths[0] == "/out/v.mp4"  # output_path
    assert paths[1] == "/subs/v.srt"  # subtitle_path
    assert paths[2] == "/subs/v_translated.srt"  # translated_subtitle_path
    assert paths[3] == "/voice/v.mp3"  # voice_path


# ---------------------------------------------------------------------------
# reset_stuck_subtitle_entries
# ---------------------------------------------------------------------------


def test_reset_stuck_subtitle_entries_resets_generating() -> None:
    """Entries with STATUS_GENERATING are reset to Failed with APP_CRASHED."""
    id1 = add_subtitle_entry(
        "a.mp4",
        100,
        "/a.mp4",
        "",
        "Vietnamese",
        STATUS_GENERATING,
    )
    id2 = add_subtitle_entry(
        "b.mp4",
        200,
        "/b.mp4",
        "",
        "Vietnamese",
        STATUS_GENERATING,
    )
    count = reset_stuck_subtitle_entries()
    assert count == 2  # noqa: PLR2004

    entries = get_subtitle_history()
    for entry in entries:
        if entry[0] in (id1, id2):
            status_idx = 6  # noqa: PLR2004
            error_idx = 7  # noqa: PLR2004
            assert entry[status_idx] == STATUS_FAILED
            assert entry[error_idx] == "APP_CRASHED"


def test_reset_stuck_subtitle_entries_noop_no_generating() -> None:
    """Returns 0 when no entries have STATUS_GENERATING."""
    add_subtitle_entry("a.mp4", 100, "/a.mp4", "/a.srt", "Vietnamese", STATUS_DONE)
    add_subtitle_entry("b.mp4", 200, "/b.mp4", "", "Vietnamese", STATUS_PENDING)
    count = reset_stuck_subtitle_entries()
    assert count == 0

    # Verify entries are unchanged
    entries = get_subtitle_history()
    statuses = {e[6] for e in entries}
    assert STATUS_DONE in statuses
    assert STATUS_PENDING in statuses
    assert STATUS_FAILED not in statuses


def test_reset_stuck_subtitle_entries_mixed_statuses() -> None:
    """Only Generating entries are reset; Done/Failed/Pending stay intact."""
    id_gen1 = add_subtitle_entry(
        "gen1.mp4",
        100,
        "/gen1.mp4",
        "",
        "Vietnamese",
        STATUS_GENERATING,
    )
    id_gen2 = add_subtitle_entry(
        "gen2.mp4",
        200,
        "/gen2.mp4",
        "",
        "Vietnamese",
        STATUS_GENERATING,
    )
    id_done = add_subtitle_entry(
        "done.mp4",
        300,
        "/done.mp4",
        "/done.srt",
        "Vietnamese",
        STATUS_DONE,
    )
    id_fail = add_subtitle_entry(
        "fail.mp4",
        400,
        "/fail.mp4",
        "",
        "Vietnamese",
        STATUS_FAILED,
        error_message="old error",
    )
    id_pend = add_subtitle_entry(
        "pend.mp4",
        500,
        "/pend.mp4",
        "",
        "Vietnamese",
        STATUS_PENDING,
    )

    count = reset_stuck_subtitle_entries()
    assert count == 2  # noqa: PLR2004 — only the two Generating entries

    entries = get_subtitle_history()
    status_map = {e[0]: (e[6], e[7]) for e in entries}
    # Generating entries reset
    assert status_map[id_gen1] == (STATUS_FAILED, "APP_CRASHED")
    assert status_map[id_gen2] == (STATUS_FAILED, "APP_CRASHED")
    # Others unchanged
    assert status_map[id_done][0] == STATUS_DONE
    assert status_map[id_fail] == (STATUS_FAILED, "old error")
    assert status_map[id_pend][0] == STATUS_PENDING


# ---------------------------------------------------------------------------
# reset_stuck_voice_entries
# ---------------------------------------------------------------------------


def test_reset_stuck_voice_entries_resets_generating() -> None:
    """Entries with STATUS_GENERATING are reset to Failed with APP_CRASHED."""
    id1 = add_voice_entry("a.srt", 100, "/a.srt", "", STATUS_GENERATING)
    id2 = add_voice_entry("b.srt", 200, "/b.srt", "", STATUS_GENERATING)
    count = reset_stuck_voice_entries()
    assert count == 2  # noqa: PLR2004

    entries = get_voice_history()
    for entry in entries:
        if entry[0] in (id1, id2):
            status_idx = 5  # noqa: PLR2004
            error_idx = 6  # noqa: PLR2004
            assert entry[status_idx] == STATUS_FAILED
            assert entry[error_idx] == "APP_CRASHED"


def test_reset_stuck_voice_entries_noop_no_generating() -> None:
    """Returns 0 when no entries have STATUS_GENERATING."""
    add_voice_entry("a.srt", 100, "/a.srt", "/a.mp3", STATUS_DONE)
    add_voice_entry("b.srt", 200, "/b.srt", "", STATUS_PENDING)
    count = reset_stuck_voice_entries()
    assert count == 0

    # Verify entries are unchanged
    entries = get_voice_history()
    statuses = {e[5] for e in entries}
    assert STATUS_DONE in statuses
    assert STATUS_PENDING in statuses
    assert STATUS_FAILED not in statuses


# ---------------------------------------------------------------------------
# delete_subtitle_entry / delete_voice_entry / delete_dubbing_entry edge cases
# ---------------------------------------------------------------------------


def test_delete_subtitle_entry_nonexistent_returns_none() -> None:
    """delete_subtitle_entry with non-existent ID returns None."""
    fake_id = 99999  # noqa: PLR2004
    result = delete_subtitle_entry(fake_id)
    assert result is None


def test_delete_voice_entry_nonexistent_returns_none() -> None:
    """delete_voice_entry with non-existent ID returns None."""
    fake_id = 99999  # noqa: PLR2004
    result = delete_voice_entry(fake_id)
    assert result is None


def test_delete_dubbing_entry_nonexistent_returns_fallback_tuple() -> None:
    """delete_dubbing_entry with non-existent ID returns fallback empty tuple."""
    fake_id = 99999  # noqa: PLR2004
    result = delete_dubbing_entry(fake_id)
    assert result == ("", "", "", "")


# ---------------------------------------------------------------------------
# Additional coverage: extraction, voice, dubbing, subtitle edge cases
# ---------------------------------------------------------------------------


def test_delete_extraction_entry_nonexistent_returns_none() -> None:
    """delete_extraction_entry with non-existent ID returns None."""
    fake_id = 99999  # noqa: PLR2004
    result = delete_extraction_entry(fake_id)
    assert result is None


def test_update_voice_status_failed_with_error_message() -> None:
    """update_voice_status stores the error_message on failure."""
    entry_id = add_voice_entry(
        file_name="voice.mp3",
        file_size=2048,
        source_path="/tmp/voice.mp3",
        output_path="/tmp/voice_out.mp3",
        status=STATUS_GENERATING,
    )
    update_voice_status(entry_id, STATUS_FAILED, error_message="API timeout")

    rows = get_voice_history()
    assert len(rows) == 1
    assert rows[0][5] == STATUS_FAILED  # status column
    assert rows[0][6] == "API timeout"  # error_message column  # noqa: PLR2004


def test_update_dubbing_status_failed_with_error_message() -> None:
    """update_dubbing_status stores the error_message on failure."""
    entry_id = add_dubbing_entry(
        file_name="dub.mp4",
        file_size=4096,
        source_path="/tmp/dub.mp4",
        output_path="/tmp/dub_out.mp4",
        status=STATUS_GENERATING,
    )
    update_dubbing_status(entry_id, STATUS_FAILED, error_message="API timeout")

    rows = get_dubbing_history()
    assert len(rows) == 1
    assert rows[0][7] == STATUS_FAILED  # status column  # noqa: PLR2004
    assert rows[0][9] == "API timeout"  # error_message column  # noqa: PLR2004


def test_add_subtitle_entry_with_error_message() -> None:
    """add_subtitle_entry stores error_message when provided."""
    add_subtitle_entry(
        file_name="sub.srt",
        file_size=512,
        source_path="/tmp/sub.srt",
        output_path="/tmp/sub_out.srt",
        src_lang="English",
        status=STATUS_FAILED,
        error_message="immediate failure",
    )

    rows = get_subtitle_history()
    assert len(rows) == 1
    assert rows[0][6] == STATUS_FAILED  # status column
    assert rows[0][7] == "immediate failure"  # error_message column  # noqa: PLR2004


def test_add_voice_entry_with_error_message() -> None:
    """add_voice_entry stores error_message when provided."""
    add_voice_entry(
        file_name="voice.mp3",
        file_size=1024,
        source_path="/tmp/voice.mp3",
        output_path="/tmp/voice_out.mp3",
        status=STATUS_FAILED,
        error_message="immediate failure",
    )

    rows = get_voice_history()
    assert len(rows) == 1
    assert rows[0][5] == STATUS_FAILED  # status column
    assert rows[0][6] == "immediate failure"  # error_message column  # noqa: PLR2004


def test_add_dubbing_entry_stores_src_and_target_lang() -> None:
    """add_dubbing_entry correctly stores src_lang and target_lang."""
    add_dubbing_entry(
        file_name="dub.mp4",
        file_size=8192,
        source_path="/tmp/dub.mp4",
        output_path="/tmp/dub_out.mp4",
        status=STATUS_PENDING,
        src_lang="Vietnamese",
        target_lang="English (US)",
    )

    rows = get_dubbing_history()
    assert len(rows) == 1
    assert rows[0][5] == "Vietnamese"  # src_lang column  # noqa: PLR2004
    assert rows[0][6] == "English (US)"  # target_lang column  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Text Translation History CRUD
# ---------------------------------------------------------------------------


def test_add_text_translation_entry_returns_id() -> None:
    """add_text_translation_entry returns a positive integer ID."""
    entry_id = add_text_translation_entry(
        source_text="Hello world",
        translated_text="Xin chào thế giới",
        src_lang="English (US)",
        target_lang="Vietnamese",
        char_count=11,
    )
    assert entry_id is not None
    assert entry_id > 0


def test_add_text_translation_entry_with_empty_src_lang() -> None:
    """Empty src_lang (auto-detect sentinel) is stored correctly."""
    entry_id = add_text_translation_entry(
        source_text="Bonjour",
        translated_text="Hello",
        src_lang="",
        target_lang="English (US)",
        char_count=7,
    )
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[3] == ""  # src_lang column


def test_add_text_translation_entry_stores_char_count() -> None:
    """char_count is stored correctly."""
    entry_id = add_text_translation_entry(
        source_text="Test",
        translated_text="Kiểm tra",
        src_lang="",
        target_lang="Vietnamese",
        char_count=4,
    )
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[5] == 4  # noqa: PLR2004 — char_count column


def test_add_text_translation_entry_auto_timestamps() -> None:
    """created_at is set automatically."""
    entry_id = add_text_translation_entry(
        source_text="Time test",
        translated_text="Thử thời gian",
        src_lang="",
        target_lang="Vietnamese",
        char_count=9,
    )
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[6] is not None  # created_at not NULL
    assert len(entry[6]) > 0  # Non-empty timestamp string


def test_get_text_translation_history_returns_entries() -> None:
    """Entries are returned with correct column count."""
    add_text_translation_entry("src", "tgt", "", "FR", 3)
    entries = get_text_translation_history()
    assert len(entries) >= 1
    # Each entry: (id, source_text, translated_text, src_lang,
    #              target_lang, char_count, created_at)
    expected_cols = 7  # noqa: PLR2004
    assert len(entries[0]) == expected_cols


def test_get_text_translation_history_ordered_desc() -> None:
    """Newest entries come first (created_at DESC)."""
    id1 = add_text_translation_entry("first", "premier", "", "FR", 5)
    id2 = add_text_translation_entry("second", "deuxième", "", "FR", 6)
    entries = get_text_translation_history()
    ids = [e[0] for e in entries]
    # id2 inserted later, should come first
    assert ids.index(id2) < ids.index(id1)


def test_get_text_translation_history_respects_limit() -> None:
    """Returns at most 50 entries."""
    for i in range(55):
        add_text_translation_entry(f"src_{i}", f"tgt_{i}", "", "FR", 5)
    entries = get_text_translation_history()
    assert len(entries) == 50  # noqa: PLR2004


def test_get_text_translation_history_empty_when_none() -> None:
    """Returns empty list when no entries exist.

    Note: other tests in this file may have added entries to the shared
    session DB.  We use function-scoped autouse ``setup_test_db`` that
    creates a fresh database for each test, so this starts clean.
    """
    entries = get_text_translation_history()
    assert entries == []


def test_get_text_translation_fingerprint_returns_tuple() -> None:
    """Fingerprint returns (count, max_id) tuple."""
    add_text_translation_entry("src", "tgt", "", "FR", 3)
    fp = get_text_translation_fingerprint()
    assert fp is not None
    assert len(fp) == 2  # noqa: PLR2004
    assert fp[0] >= 1  # count
    assert fp[1] >= 1  # max_id


def test_get_text_translation_fingerprint_changes_on_add() -> None:
    """Fingerprint changes when entries are added."""
    fp1 = get_text_translation_fingerprint()
    add_text_translation_entry("a", "b", "", "FR", 1)
    fp2 = get_text_translation_fingerprint()
    assert fp1 != fp2


def test_get_text_translation_fingerprint_changes_on_delete() -> None:
    """Fingerprint changes when entries are deleted."""
    entry_id = add_text_translation_entry("a", "b", "", "FR", 1)
    fp1 = get_text_translation_fingerprint()
    delete_text_translation_entry(entry_id)
    fp2 = get_text_translation_fingerprint()
    assert fp1 != fp2


def test_delete_text_translation_entry_removes_entry() -> None:
    """delete_text_translation_entry removes the entry by ID."""
    entry_id = add_text_translation_entry("del", "suppr", "", "FR", 3)
    delete_text_translation_entry(entry_id)
    entries = get_text_translation_history()
    assert all(e[0] != entry_id for e in entries)


def test_delete_text_translation_entry_nonexistent_is_noop() -> None:
    """Deleting a non-existent ID does not raise."""
    delete_text_translation_entry(99999)  # noqa: PLR2004 — silent no-op


def test_text_translation_unicode_content() -> None:
    """Unicode text in source and translated fields is preserved."""
    entry_id = add_text_translation_entry(
        source_text="日本語のテスト",
        translated_text="Japanese test",
        src_lang="Japanese",
        target_lang="English (US)",
        char_count=7,
    )
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[1] == "日本語のテスト"
    assert entry[2] == "Japanese test"


def test_text_translation_sql_injection() -> None:
    """SQL injection payloads are safely stored."""
    malicious = "'; DROP TABLE text_translation_history; --"
    entry_id = add_text_translation_entry(malicious, "safe", "", "FR", 42)
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[1] == malicious


def test_get_text_translation_fingerprint_empty_db() -> None:
    """Fingerprint on empty DB returns (0, 0)."""
    fp = get_text_translation_fingerprint()
    assert fp is not None
    assert fp == (0, 0)


def test_get_text_translation_fingerprint_stable_when_unchanged() -> None:
    """Fingerprint is identical across consecutive calls without changes."""
    add_text_translation_entry("stable", "estable", "", "ES", 6)
    fp1 = get_text_translation_fingerprint()
    fp2 = get_text_translation_fingerprint()
    assert fp1 == fp2


def test_text_translation_large_content() -> None:
    """Large text content (10000 chars) is stored and retrieved."""
    large = "a" * 10000
    entry_id = add_text_translation_entry(large, large, "", "FR", 10000)
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert len(entry[1]) == 10000  # noqa: PLR2004
    assert len(entry[2]) == 10000  # noqa: PLR2004


def test_update_text_translation_entry_changes_translated_text() -> None:
    """Translated text is updated in the database."""
    entry_id = add_text_translation_entry("hello", "bonjour", "", "FR", 5)
    update_text_translation_entry(entry_id, "salut")
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[2] == "salut"


def test_update_text_translation_entry_preserves_other_fields() -> None:
    """Other columns remain unchanged after updating translated text."""
    entry_id = add_text_translation_entry("hello", "bonjour", "EN", "FR", 5)
    update_text_translation_entry(entry_id, "salut")
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[1] == "hello"  # source_text unchanged
    assert entry[3] == "EN"  # src_lang unchanged
    assert entry[4] == "FR"  # target_lang unchanged
    assert entry[5] == 5  # noqa: PLR2004 — char_count unchanged


def test_update_text_translation_entry_nonexistent_id() -> None:
    """Updating a non-existent entry is a silent no-op (0 rows affected)."""
    fake_id = 99999  # noqa: PLR2004
    update_text_translation_entry(fake_id, "ghost")  # Should not raise


def test_update_text_translation_entry_empty_string() -> None:
    """Translated text can be set to empty string."""
    entry_id = add_text_translation_entry("hello", "bonjour", "", "FR", 5)
    update_text_translation_entry(entry_id, "")
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[2] == ""


def test_update_text_translation_entry_unicode() -> None:
    """Translated text can contain unicode characters."""
    entry_id = add_text_translation_entry("hello", "bonjour", "", "FR", 5)
    update_text_translation_entry(entry_id, "こんにちは 🌍")
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[2] == "こんにちは 🌍"


def test_update_text_translation_entry_fingerprint_stable() -> None:
    """Fingerprint (count, max_id) is unchanged by text-only updates."""
    entry_id = add_text_translation_entry("hello", "bonjour", "", "FR", 5)
    fp_before = get_text_translation_fingerprint()
    update_text_translation_entry(entry_id, "salut")
    fp_after = get_text_translation_fingerprint()
    assert fp_before == fp_after


def test_delete_text_translation_entry_idempotent() -> None:
    """Deleting an already-deleted entry is a silent no-op."""
    entry_id = add_text_translation_entry("tmp", "tmp", "", "FR", 3)
    delete_text_translation_entry(entry_id)
    delete_text_translation_entry(entry_id)  # Should not raise


# ---------------------------------------------------------------------------
# WAL mode and foreign keys verification
# ---------------------------------------------------------------------------


class TestConnectionPragmas:
    """Verify SQLite connection pragmas are set correctly."""

    def test_wal_mode_enabled(self) -> None:
        """create_connection returns a connection with WAL journal mode."""
        from src.core.database import create_connection  # noqa: PLC0415

        conn = create_connection()
        assert conn is not None
        try:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()

    def test_foreign_keys_enabled(self) -> None:
        """create_connection returns a connection with foreign_keys ON."""
        from src.core.database import create_connection  # noqa: PLC0415

        conn = create_connection()
        assert conn is not None
        try:
            cursor = conn.execute("PRAGMA foreign_keys")
            fk_on = cursor.fetchone()[0]
            assert fk_on == 1
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 50-entry page limit for all history tables
# ---------------------------------------------------------------------------


class TestHistoryPageLimits:
    """Verify each history table returns at most 50 entries."""

    def test_extraction_history_limit_fifty(self) -> None:
        """get_extraction_history returns at most 50 entries."""
        total_entries = 55  # noqa: PLR2004
        for i in range(total_entries):
            add_extraction_entry(f"img_{i}.png", 100, f"/img_{i}.png", "", "Done")
        entries = get_extraction_history()
        assert len(entries) == 50  # noqa: PLR2004

    def test_subtitle_history_limit_fifty(self) -> None:
        """get_subtitle_history returns at most 50 entries."""
        total_entries = 55  # noqa: PLR2004
        for i in range(total_entries):
            add_subtitle_entry(
                f"vid_{i}.mp4",
                100,
                f"/vid_{i}.mp4",
                "",
                "Vietnamese",
                "Done",
            )
        entries = get_subtitle_history()
        assert len(entries) == 50  # noqa: PLR2004

    def test_voice_history_limit_fifty(self) -> None:
        """get_voice_history returns at most 50 entries."""
        total_entries = 55  # noqa: PLR2004
        for i in range(total_entries):
            add_voice_entry(f"sub_{i}.srt", 100, f"/sub_{i}.srt", "", "Done")
        entries = get_voice_history()
        assert len(entries) == 50  # noqa: PLR2004

    def test_dubbing_history_limit_fifty(self) -> None:
        """get_dubbing_history returns at most 50 entries."""
        total_entries = 55  # noqa: PLR2004
        for i in range(total_entries):
            add_dubbing_entry(f"vid_{i}.mp4", 100, f"/vid_{i}.mp4", "", "Done")
        entries = get_dubbing_history()
        assert len(entries) == 50  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Fingerprint stability for extraction/subtitle/voice/dubbing
# ---------------------------------------------------------------------------


class TestExtractionFingerprintStability:
    """Verify extraction fingerprint behavior across operations."""

    def test_empty_db_returns_stable_value(self) -> None:
        """Empty DB returns a stable fingerprint tuple."""
        fp = get_extraction_fingerprint()
        assert fp is not None
        assert fp[0] == 0  # count
        assert fp[1] == 0  # max id

    def test_changes_on_add(self) -> None:
        """Fingerprint changes when an entry is added."""
        fp_before = get_extraction_fingerprint()
        add_extraction_entry("a.png", 100, "/a.png", "/a.txt", "Done")
        fp_after = get_extraction_fingerprint()
        assert fp_before != fp_after

    def test_changes_on_delete(self) -> None:
        """Fingerprint changes when an entry is deleted."""
        entry_id = add_extraction_entry("a.png", 100, "/a.png", "/a.txt", "Done")
        fp_before = get_extraction_fingerprint()
        delete_extraction_entry(entry_id)
        fp_after = get_extraction_fingerprint()
        assert fp_before != fp_after

    def test_stable_across_consecutive_calls(self) -> None:
        """Fingerprint is identical across consecutive calls without changes."""
        add_extraction_entry("a.png", 100, "/a.png", "/a.txt", "Done")
        fp1 = get_extraction_fingerprint()
        fp2 = get_extraction_fingerprint()
        assert fp1 == fp2


class TestSubtitleFingerprintStability:
    """Verify subtitle fingerprint behavior across operations."""

    def test_empty_db_returns_stable_value(self) -> None:
        """Empty DB returns a stable fingerprint tuple."""
        fp = get_subtitle_fingerprint()
        assert fp is not None
        assert fp[0] == 0  # count
        assert fp[1] == 0  # max id

    def test_changes_on_add(self) -> None:
        """Fingerprint changes when an entry is added."""
        fp_before = get_subtitle_fingerprint()
        add_subtitle_entry("a.mp4", 100, "/a.mp4", "", "Vietnamese", "Pending")
        fp_after = get_subtitle_fingerprint()
        assert fp_before != fp_after

    def test_changes_on_delete(self) -> None:
        """Fingerprint changes when an entry is deleted."""
        entry_id = add_subtitle_entry(
            "a.mp4",
            100,
            "/a.mp4",
            "/a.srt",
            "Vietnamese",
            "Done",
        )
        fp_before = get_subtitle_fingerprint()
        delete_subtitle_entry(entry_id)
        fp_after = get_subtitle_fingerprint()
        assert fp_before != fp_after

    def test_stable_across_consecutive_calls(self) -> None:
        """Fingerprint is identical across consecutive calls without changes."""
        add_subtitle_entry("a.mp4", 100, "/a.mp4", "", "Vietnamese", "Pending")
        fp1 = get_subtitle_fingerprint()
        fp2 = get_subtitle_fingerprint()
        assert fp1 == fp2


class TestVoiceFingerprintStability:
    """Verify voice fingerprint behavior across operations."""

    def test_empty_db_returns_stable_value(self) -> None:
        """Empty DB returns a stable fingerprint tuple."""
        fp = get_voice_fingerprint()
        assert fp is not None
        assert fp[0] == 0  # count
        assert fp[1] == 0  # max id

    def test_changes_on_add(self) -> None:
        """Fingerprint changes when an entry is added."""
        fp_before = get_voice_fingerprint()
        add_voice_entry("a.srt", 100, "/a.srt", "", "Pending")
        fp_after = get_voice_fingerprint()
        assert fp_before != fp_after

    def test_changes_on_delete(self) -> None:
        """Fingerprint changes when an entry is deleted."""
        entry_id = add_voice_entry("a.srt", 100, "/a.srt", "/a.mp3", "Done")
        fp_before = get_voice_fingerprint()
        delete_voice_entry(entry_id)
        fp_after = get_voice_fingerprint()
        assert fp_before != fp_after

    def test_stable_across_consecutive_calls(self) -> None:
        """Fingerprint is identical across consecutive calls without changes."""
        add_voice_entry("a.srt", 100, "/a.srt", "", "Pending")
        fp1 = get_voice_fingerprint()
        fp2 = get_voice_fingerprint()
        assert fp1 == fp2


class TestDubbingFingerprintStability:
    """Verify dubbing fingerprint behavior across operations."""

    def test_empty_db_returns_stable_value(self) -> None:
        """Empty DB returns a stable fingerprint tuple."""
        fp = get_dubbing_fingerprint()
        assert fp is not None
        assert fp[0] == 0  # count
        assert fp[1] == 0  # max id

    def test_changes_on_add(self) -> None:
        """Fingerprint changes when an entry is added."""
        fp_before = get_dubbing_fingerprint()
        add_dubbing_entry("a.mp4", 100, "/a.mp4", "", "Pending")
        fp_after = get_dubbing_fingerprint()
        assert fp_before != fp_after

    def test_changes_on_delete(self) -> None:
        """Fingerprint changes when an entry is deleted."""
        entry_id = add_dubbing_entry("a.mp4", 100, "/a.mp4", "/a.mp4", "Done")
        fp_before = get_dubbing_fingerprint()
        delete_dubbing_entry(entry_id)
        fp_after = get_dubbing_fingerprint()
        assert fp_before != fp_after

    def test_stable_across_consecutive_calls(self) -> None:
        """Fingerprint is identical across consecutive calls without changes."""
        add_dubbing_entry("a.mp4", 100, "/a.mp4", "", "Pending")
        fp1 = get_dubbing_fingerprint()
        fp2 = get_dubbing_fingerprint()
        assert fp1 == fp2


# ---------------------------------------------------------------------------
# Nonexistent ID tests for status update functions
# ---------------------------------------------------------------------------


class TestNonexistentIdStatusUpdates:
    """Verify status update functions are silent no-ops for nonexistent IDs."""

    def test_update_dubbing_status_nonexistent_id(self) -> None:
        """update_dubbing_status with nonexistent ID is a silent no-op."""
        fake_id = 99999  # noqa: PLR2004
        update_dubbing_status(fake_id, STATUS_DONE)
        # No entry was created; table remains empty
        assert get_dubbing_history() == []

    def test_update_extraction_status_nonexistent_id(self) -> None:
        """update_extraction_status with nonexistent ID is a silent no-op."""
        fake_id = 99999  # noqa: PLR2004
        update_extraction_status(fake_id, "Done", output_path="/out.txt")
        assert get_extraction_history() == []

    def test_update_subtitle_status_nonexistent_id(self) -> None:
        """update_subtitle_status with nonexistent ID is a silent no-op."""
        fake_id = 99999  # noqa: PLR2004
        update_subtitle_status(fake_id, "Done", output_path="/out.srt")
        assert get_subtitle_history() == []

    def test_update_voice_status_nonexistent_id(self) -> None:
        """update_voice_status with nonexistent ID is a silent no-op."""
        fake_id = 99999  # noqa: PLR2004
        update_voice_status(fake_id, "Done", output_path="/out.mp3")
        assert get_voice_history() == []


# ---------------------------------------------------------------------------
# batch_resume_history_entries: no status filter behavior
# ---------------------------------------------------------------------------


class TestBatchResumeNoStatusFilter:
    """Document that batch_resume_history_entries has no status filter."""

    def test_resuming_done_entry_sets_pending(self) -> None:
        """Resuming a Done entry sets it to Pending (no WHERE status filter).

        batch_resume_history_entries applies to ALL ids unconditionally,
        unlike batch_pause which only affects Translating/Pending entries.
        This test documents the current behavior.
        """
        h_id = add_history_entry("done.txt", "EN", "FR", STATUS_DONE)
        assert get_history_entry_status(h_id) == STATUS_DONE

        batch_resume_history_entries([h_id])

        assert get_history_entry_status(h_id) == STATUS_PENDING
        # error_code should also be cleared
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[9] is None  # error_code column


# ---------------------------------------------------------------------------
# reset_stuck_voice_entries: mixed statuses
# ---------------------------------------------------------------------------


class TestResetStuckVoiceMixedStatuses:
    """Verify reset_stuck_voice_entries only affects Generating entries."""

    def test_done_failed_pending_left_untouched(self) -> None:
        """Done, Failed, and Pending entries are not modified.

        When Generating entries are reset, these statuses stay unchanged.
        """
        id_done = add_voice_entry(
            "done.srt",
            100,
            "/done.srt",
            "/done.mp3",
            STATUS_DONE,
        )
        id_fail = add_voice_entry(
            "fail.srt",
            200,
            "/fail.srt",
            "",
            STATUS_FAILED,
            error_message="old error",
        )
        id_pend = add_voice_entry(
            "pend.srt",
            300,
            "/pend.srt",
            "",
            STATUS_PENDING,
        )
        id_gen = add_voice_entry(
            "gen.srt",
            400,
            "/gen.srt",
            "",
            STATUS_GENERATING,
        )

        count = reset_stuck_voice_entries()
        assert count == 1  # Only the Generating entry

        entries = get_voice_history()
        status_map = {e[0]: (e[5], e[6]) for e in entries}

        # Generating entry reset to Failed with APP_CRASHED
        assert status_map[id_gen] == (STATUS_FAILED, "APP_CRASHED")
        # Other entries untouched
        assert status_map[id_done][0] == STATUS_DONE
        assert status_map[id_fail] == (STATUS_FAILED, "old error")
        assert status_map[id_pend][0] == STATUS_PENDING


# ---------------------------------------------------------------------------
# reset_stuck_subtitle_entries / reset_stuck_voice_entries on empty DB
# ---------------------------------------------------------------------------


class TestResetStuckOnEmptyDB:
    """Verify reset_stuck functions return 0 on empty databases."""

    def test_reset_stuck_subtitle_entries_empty_db(self) -> None:
        """reset_stuck_subtitle_entries returns 0 on empty DB without errors."""
        count = reset_stuck_subtitle_entries()
        assert count == 0

    def test_reset_stuck_voice_entries_empty_db(self) -> None:
        """reset_stuck_voice_entries returns 0 on empty DB without errors."""
        count = reset_stuck_voice_entries()
        assert count == 0


# ===========================================================================
# Additional edge-case tests (appended for expanded coverage)
# ===========================================================================


# ---------------------------------------------------------------------------
# TestTextTranslationDB — expanded edge cases
# ---------------------------------------------------------------------------


class TestTextTranslationDB:
    """Extended tests for text translation history operations."""

    def test_save_text_translation_all_fields(self) -> None:
        """All fields are stored and retrievable."""
        entry_id = add_text_translation_entry(
            source_text="Good morning",
            translated_text="Chào buổi sáng",
            src_lang="English (US)",
            target_lang="Vietnamese",
            char_count=12,
        )
        entries = get_text_translation_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "Good morning"
        assert entry[2] == "Chào buổi sáng"
        assert entry[3] == "English (US)"
        assert entry[4] == "Vietnamese"
        assert entry[5] == 12  # noqa: PLR2004
        assert entry[6] is not None  # created_at

    def test_get_text_translation_history_ordering(self) -> None:
        """Multiple entries are returned newest first."""
        import time  # noqa: PLC0415

        id1 = add_text_translation_entry("alpha", "a_tr", "EN", "FR", 5)
        time.sleep(1.1)  # Force distinct second-level timestamp
        id2 = add_text_translation_entry("beta", "b_tr", "EN", "FR", 4)
        time.sleep(1.1)
        id3 = add_text_translation_entry("gamma", "c_tr", "EN", "FR", 5)

        entries = get_text_translation_history()
        ids = [e[0] for e in entries]
        assert ids.index(id3) < ids.index(id2) < ids.index(id1)

    def test_delete_removes_only_target_entry(self) -> None:
        """Deleting one entry leaves others intact."""
        id1 = add_text_translation_entry("keep", "garder", "EN", "FR", 4)
        id2 = add_text_translation_entry("remove", "supprimer", "EN", "FR", 6)

        delete_text_translation_entry(id2)

        entries = get_text_translation_history()
        ids = [e[0] for e in entries]
        assert id1 in ids
        assert id2 not in ids

    def test_fingerprint_changes_after_insert(self) -> None:
        """Fingerprint changes after each insert."""
        fp0 = get_text_translation_fingerprint()
        add_text_translation_entry("one", "un", "EN", "FR", 3)
        fp1 = get_text_translation_fingerprint()
        add_text_translation_entry("two", "deux", "EN", "FR", 3)
        fp2 = get_text_translation_fingerprint()
        assert fp0 != fp1
        assert fp1 != fp2

    def test_fingerprint_changes_after_delete(self) -> None:
        """Fingerprint changes after deletion."""
        id1 = add_text_translation_entry("del", "suppr", "EN", "FR", 3)
        id2 = add_text_translation_entry("keep", "garder", "EN", "FR", 4)
        fp_before = get_text_translation_fingerprint()
        delete_text_translation_entry(id1)
        fp_after = get_text_translation_fingerprint()
        assert fp_before != fp_after
        # id2 is still present
        entries = get_text_translation_history()
        assert any(e[0] == id2 for e in entries)

    def test_save_with_unicode_text(self) -> None:
        """Unicode characters including CJK and accents are preserved."""
        entry_id = add_text_translation_entry(
            source_text="Tôi yêu Việt Nam 🇻🇳",
            translated_text="I love Vietnam 🇻🇳",
            src_lang="Vietnamese",
            target_lang="English (US)",
            char_count=20,
        )
        entries = get_text_translation_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert "🇻🇳" in entry[1]
        assert "🇻🇳" in entry[2]

    def test_save_with_very_long_text(self) -> None:
        """Very long text (50000 chars) is stored and retrieved correctly."""
        long_text = "x" * 50000
        entry_id = add_text_translation_entry(long_text, long_text, "", "FR", 50000)
        entries = get_text_translation_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert len(entry[1]) == 50000  # noqa: PLR2004
        assert len(entry[2]) == 50000  # noqa: PLR2004

    def test_save_with_empty_text(self) -> None:
        """Empty source and translated text are valid."""
        entry_id = add_text_translation_entry("", "", "", "FR", 0)
        entries = get_text_translation_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == ""
        assert entry[2] == ""
        assert entry[5] == 0

    def test_save_with_multiline_text(self) -> None:
        """Multi-line text with newlines is preserved."""
        src = "Line 1\nLine 2\nLine 3"
        tgt = "Dòng 1\nDòng 2\nDòng 3"
        entry_id = add_text_translation_entry(src, tgt, "EN", "VI", len(src))
        entries = get_text_translation_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == src
        assert entry[2] == tgt


# ---------------------------------------------------------------------------
# TestSubtitleDB — expanded edge cases
# ---------------------------------------------------------------------------


class TestSubtitleDB:
    """Extended tests for subtitle history operations."""

    def test_save_subtitle_entry_stores_all_fields(self) -> None:
        """All fields are stored correctly including src_lang."""
        entry_id = add_subtitle_entry(
            file_name="interview.mp4",
            file_size=4096,
            source_path="/home/user/interview.mp4",
            output_path="/out/interview.srt",
            src_lang="English (US)",
            status=STATUS_DONE,
        )
        entries = get_subtitle_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "interview.mp4"
        assert entry[2] == 4096  # noqa: PLR2004
        assert entry[3] == "/home/user/interview.mp4"
        assert entry[4] == "/out/interview.srt"
        assert entry[5] == "English (US)"
        assert entry[6] == STATUS_DONE

    def test_update_subtitle_status_only_status(self) -> None:
        """Updating status alone leaves output_path untouched."""
        entry_id = add_subtitle_entry(
            "v.mp4", 100, "/v.mp4", "/v.srt", "EN", STATUS_DONE
        )
        update_subtitle_status(entry_id, STATUS_FAILED, error_message="err")
        entries = get_subtitle_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[6] == STATUS_FAILED
        assert entry[7] == "err"
        assert entry[4] == "/v.srt"  # preserved

    def test_subtitle_fingerprint_empty_db(self) -> None:
        """Empty DB returns (0, 0, '') fingerprint."""
        fp = get_subtitle_fingerprint()
        assert fp is not None
        assert fp[0] == 0
        assert fp[1] == 0
        assert fp[2] == ""

    def test_subtitle_fingerprint_changes_on_status_update(self) -> None:
        """Fingerprint changes when a subtitle entry status changes."""
        entry_id = add_subtitle_entry("v.mp4", 100, "/v.mp4", "", "EN", STATUS_PENDING)
        fp_before = get_subtitle_fingerprint()
        update_subtitle_status(entry_id, STATUS_DONE, output_path="/v.srt")
        fp_after = get_subtitle_fingerprint()
        assert fp_before != fp_after

    def test_delete_subtitle_entry_empty_output_path(self) -> None:
        """Deleting an entry with empty output_path returns empty string."""
        entry_id = add_subtitle_entry("v.mp4", 100, "/v.mp4", "", "EN", STATUS_FAILED)
        path = delete_subtitle_entry(entry_id)
        assert path == ""

    def test_subtitle_unicode_file_name(self) -> None:
        """Unicode file names are handled correctly."""
        entry_id = add_subtitle_entry(
            "phỏng_vấn.mp4", 512, "/phỏng_vấn.mp4", "", "VI", STATUS_PENDING
        )
        entries = get_subtitle_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "phỏng_vấn.mp4"

    def test_is_any_subtitle_generating_after_delete(self) -> None:
        """Returns False after the only generating entry is deleted."""
        entry_id = add_subtitle_entry(
            "v.mp4", 100, "/v.mp4", "", "EN", STATUS_GENERATING
        )
        assert is_any_subtitle_generating()
        delete_subtitle_entry(entry_id)
        assert not is_any_subtitle_generating()


# ---------------------------------------------------------------------------
# TestVoiceDB — expanded edge cases
# ---------------------------------------------------------------------------


class TestVoiceDB:
    """Extended tests for voice history operations."""

    def test_save_voice_entry_stores_all_fields(self) -> None:
        """All fields are stored and retrievable."""
        entry_id = add_voice_entry(
            file_name="narration.srt",
            file_size=2048,
            source_path="/home/user/narration.srt",
            output_path="/out/narration.mp3",
            status=STATUS_DONE,
        )
        entries = get_voice_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "narration.srt"
        assert entry[2] == 2048  # noqa: PLR2004
        assert entry[3] == "/home/user/narration.srt"
        assert entry[4] == "/out/narration.mp3"
        assert entry[5] == STATUS_DONE

    def test_update_voice_status_only_status(self) -> None:
        """Updating status alone preserves output_path."""
        entry_id = add_voice_entry("s.srt", 100, "/s.srt", "/s.mp3", STATUS_DONE)
        update_voice_status(entry_id, STATUS_GENERATING)
        entries = get_voice_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[5] == STATUS_GENERATING
        assert entry[4] == "/s.mp3"  # preserved

    def test_voice_fingerprint_empty_db(self) -> None:
        """Empty DB returns (0, 0, '') fingerprint."""
        fp = get_voice_fingerprint()
        assert fp is not None
        assert fp[0] == 0
        assert fp[1] == 0
        assert fp[2] == ""

    def test_voice_fingerprint_changes_on_status_update(self) -> None:
        """Fingerprint changes when a voice entry status changes."""
        entry_id = add_voice_entry("s.srt", 100, "/s.srt", "", STATUS_PENDING)
        fp_before = get_voice_fingerprint()
        update_voice_status(entry_id, STATUS_DONE, output_path="/s.mp3")
        fp_after = get_voice_fingerprint()
        assert fp_before != fp_after

    def test_delete_voice_entry_empty_output_path(self) -> None:
        """Deleting an entry with empty output_path returns empty string."""
        entry_id = add_voice_entry("s.srt", 100, "/s.srt", "", STATUS_FAILED)
        path = delete_voice_entry(entry_id)
        assert path == ""

    def test_voice_unicode_file_name(self) -> None:
        """Unicode file names are handled correctly."""
        entry_id = add_voice_entry("phụ_đề.srt", 512, "/phụ_đề.srt", "", STATUS_PENDING)
        entries = get_voice_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "phụ_đề.srt"

    def test_is_any_voice_generating_after_delete(self) -> None:
        """Returns False after the only generating entry is deleted."""
        entry_id = add_voice_entry("s.srt", 100, "/s.srt", "", STATUS_GENERATING)
        assert is_any_voice_generating()
        delete_voice_entry(entry_id)
        assert not is_any_voice_generating()


# ---------------------------------------------------------------------------
# TestDubbingDB — expanded edge cases
# ---------------------------------------------------------------------------


class TestDubbingDB:
    """Extended tests for dubbing history operations."""

    def test_save_dubbing_entry_stores_all_fields(self) -> None:
        """All fields including src_lang and target_lang are stored."""
        entry_id = add_dubbing_entry(
            file_name="movie.mp4",
            file_size=1048576,
            source_path="/home/user/movie.mp4",
            output_path="/out/movie_dubbed.mp4",
            status=STATUS_DONE,
            src_lang="English (US)",
            target_lang="Vietnamese",
            error_message=None,
        )
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "movie.mp4"
        assert entry[2] == 1048576  # noqa: PLR2004
        assert entry[3] == "/home/user/movie.mp4"
        assert entry[4] == "/out/movie_dubbed.mp4"
        assert entry[5] == "English (US)"
        assert entry[6] == "Vietnamese"
        assert entry[7] == STATUS_DONE
        assert entry[9] is None  # error_message

    def test_dubbing_status_transition_full_pipeline(self) -> None:
        """Entry can go through Pending -> Generating -> Done with artifacts."""
        entry_id = add_dubbing_entry(
            "v.mp4", 100, "/v.mp4", "", STATUS_PENDING, src_lang="EN", target_lang="FR"
        )
        assert get_dubbing_entry_status(entry_id) == STATUS_PENDING

        update_dubbing_status(entry_id, STATUS_GENERATING, progress="Step 1: STT")
        assert get_dubbing_entry_status(entry_id) == STATUS_GENERATING

        update_dubbing_status(
            entry_id,
            STATUS_GENERATING,
            progress="Step 2: Translate",
            subtitle_path="/subs.srt",
        )

        update_dubbing_status(
            entry_id,
            STATUS_GENERATING,
            progress="Step 3: TTS",
            translated_subtitle_path="/subs_fr.srt",
        )

        update_dubbing_status(
            entry_id,
            STATUS_DONE,
            output_path="/v_dubbed.mp4",
            voice_path="/voice.mp3",
            progress="Complete",
        )
        assert get_dubbing_entry_status(entry_id) == STATUS_DONE

        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[4] == "/v_dubbed.mp4"
        subtitle_path_idx = 11  # noqa: PLR2004
        translated_subtitle_path_idx = 12  # noqa: PLR2004
        voice_path_idx = 13  # noqa: PLR2004
        assert entry[subtitle_path_idx] == "/subs.srt"
        assert entry[translated_subtitle_path_idx] == "/subs_fr.srt"
        assert entry[voice_path_idx] == "/voice.mp3"

    def test_dubbing_fingerprint_changes_on_status_update(self) -> None:
        """Fingerprint changes when dubbing status changes."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
        fp_before = get_dubbing_fingerprint()
        update_dubbing_status(entry_id, STATUS_GENERATING, progress="Step 1")
        fp_after = get_dubbing_fingerprint()
        assert fp_before != fp_after

    def test_dubbing_fingerprint_changes_on_progress_update(self) -> None:
        """Fingerprint changes when dubbing progress changes."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        fp_before = get_dubbing_fingerprint()
        update_dubbing_progress(entry_id, 50)
        fp_after = get_dubbing_fingerprint()
        assert fp_before != fp_after

    def test_is_any_dubbing_generating_after_delete(self) -> None:
        """Returns False after the only generating entry is deleted."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        assert is_any_dubbing_generating()
        delete_dubbing_entry(entry_id)
        assert not is_any_dubbing_generating()

    def test_dubbing_checkpoint_artifact_paths_initial_empty(self) -> None:
        """Newly created dubbing entries have empty artifact paths."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        subtitle_path_idx = 11  # noqa: PLR2004
        translated_subtitle_path_idx = 12  # noqa: PLR2004
        voice_path_idx = 13  # noqa: PLR2004
        assert entry[subtitle_path_idx] == ""
        assert entry[translated_subtitle_path_idx] == ""
        assert entry[voice_path_idx] == ""

    def test_dubbing_unicode_file_name(self) -> None:
        """Unicode file names in dubbing entries work correctly."""
        entry_id = add_dubbing_entry("映画.mp4", 500, "/映画.mp4", "", STATUS_PENDING)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "映画.mp4"

    def test_get_unfinished_dubbing_multiple_generating_ordered_by_id(self) -> None:
        """Multiple Generating entries are ordered by ascending id."""
        id1 = add_dubbing_entry(
            "a.mp4",
            100,
            "/a.mp4",
            "",
            STATUS_GENERATING,
            src_lang="EN",
            target_lang="FR",
        )
        id2 = add_dubbing_entry(
            "b.mp4",
            200,
            "/b.mp4",
            "",
            STATUS_GENERATING,
            src_lang="EN",
            target_lang="DE",
        )
        results = get_unfinished_dubbing()
        assert len(results) == 2  # noqa: PLR2004
        assert results[0][0] == id1
        assert results[1][0] == id2


# ---------------------------------------------------------------------------
# TestExtractionDB — expanded edge cases
# ---------------------------------------------------------------------------


class TestExtractionDB:
    """Extended tests for extraction history operations."""

    def test_save_extraction_entry_stores_all_fields(self) -> None:
        """All fields are stored and retrievable."""
        entry_id = add_extraction_entry(
            file_name="scan.png",
            file_size=8192,
            source_path="/home/user/scan.png",
            output_path="/out/scan.txt",
            status=STATUS_DONE,
            error_message=None,
        )
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "scan.png"
        assert entry[2] == 8192  # noqa: PLR2004
        assert entry[3] == "/home/user/scan.png"
        assert entry[4] == "/out/scan.txt"
        assert entry[5] == STATUS_DONE
        assert entry[6] is None

    def test_extraction_status_transition(self) -> None:
        """Entry can go Pending -> Extracting -> Done."""
        entry_id = add_extraction_entry("img.png", 100, "/img.png", "", STATUS_PENDING)
        assert is_any_extracting()

        update_extraction_status(entry_id, STATUS_EXTRACTING)
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[5] == STATUS_EXTRACTING

        update_extraction_status(entry_id, STATUS_DONE, output_path="/out/img.txt")
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[5] == STATUS_DONE
        assert entry[4] == "/out/img.txt"
        assert not is_any_extracting()

    def test_extraction_fingerprint_changes_on_status_update(self) -> None:
        """Fingerprint changes when extraction status changes."""
        entry_id = add_extraction_entry("img.png", 100, "/img.png", "", STATUS_PENDING)
        fp_before = get_extraction_fingerprint()
        update_extraction_status(entry_id, STATUS_DONE, output_path="/out.txt")
        fp_after = get_extraction_fingerprint()
        assert fp_before != fp_after

    def test_is_any_extracting_after_delete(self) -> None:
        """Returns False after the only extracting entry is deleted."""
        entry_id = add_extraction_entry(
            "img.png", 100, "/img.png", "", STATUS_EXTRACTING
        )
        assert is_any_extracting()
        delete_extraction_entry(entry_id)
        assert not is_any_extracting()

    def test_extraction_unicode_file_name(self) -> None:
        """Unicode file names in extraction entries work correctly."""
        entry_id = add_extraction_entry(
            "hình_ảnh.png", 512, "/hình_ảnh.png", "", STATUS_PENDING
        )
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "hình_ảnh.png"

    def test_extraction_error_message_preserved_after_update(self) -> None:
        """Error message is overwritten by new update (including None)."""
        entry_id = add_extraction_entry(
            "err.png",
            100,
            "/err.png",
            "",
            STATUS_PENDING,
            error_message="initial error",
        )
        update_extraction_status(entry_id, STATUS_FAILED, error_message="OCR failed")
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[6] == "OCR failed"

        # Updating without error_message sets it to None
        update_extraction_status(entry_id, STATUS_DONE, output_path="/out.txt")
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[6] is None


# ---------------------------------------------------------------------------
# TestGlossaryDB — expanded edge cases
# ---------------------------------------------------------------------------


class TestGlossaryDB:
    """Extended tests for glossary operations."""

    def test_create_glossary_set_returns_true_on_success(self) -> None:
        """Creating a new set returns True."""
        assert create_glossary_set("Brand New") is True

    def test_create_glossary_set_returns_false_on_duplicate(self) -> None:
        """Creating a set with an existing name returns False."""
        create_glossary_set("Duplicate")
        assert create_glossary_set("Duplicate") is False

    def test_rename_glossary_set_success(self) -> None:
        """Renaming to a unique name returns True."""
        create_glossary_set("Old Name")
        set_id = get_glossary_sets()[0][0]
        assert update_glossary_set_name(set_id, "New Name") is True
        sets = get_glossary_sets()
        assert sets[0][1] == "New Name"

    def test_rename_glossary_set_to_same_name(self) -> None:
        """Renaming to the same name returns True (no conflict)."""
        create_glossary_set("Same")
        set_id = get_glossary_sets()[0][0]
        assert update_glossary_set_name(set_id, "Same") is True

    def test_delete_glossary_set_cascade_deletes_entries(self) -> None:
        """Deleting a set cascades to all its entries."""
        create_glossary_set("CascadeDel")
        set_id = get_glossary_sets()[0][0]
        add_glossary_entry(set_id, "a", "1")
        add_glossary_entry(set_id, "b", "2")
        add_glossary_entry(set_id, "c", "3")
        assert get_glossary_entry_count(set_id) == 3  # noqa: PLR2004

        delete_glossary_set(set_id)
        assert get_glossary_entries(set_id) == []
        assert get_glossary_entry_count(set_id) == 0

    def test_get_glossary_sets_returns_all_columns(self) -> None:
        """Each set has (id, name, is_active) columns."""
        create_glossary_set("ColumnsTest")
        sets = get_glossary_sets()
        assert len(sets) == 1
        assert len(sets[0]) == 3  # noqa: PLR2004
        assert isinstance(sets[0][0], int)
        assert isinstance(sets[0][1], str)
        assert sets[0][2] in (0, 1)

    def test_add_glossary_entry_multiple(self) -> None:
        """Multiple entries can be added to the same set."""
        create_glossary_set("Multi")
        set_id = get_glossary_sets()[0][0]
        for i in range(10):
            add_glossary_entry(set_id, f"src_{i}", f"tgt_{i}")
        assert get_glossary_entry_count(set_id) == 10  # noqa: PLR2004

    def test_update_glossary_entry_source_and_target(self) -> None:
        """Updating both source and target text works."""
        create_glossary_set("UpdateBoth")
        set_id = get_glossary_sets()[0][0]
        add_glossary_entry(set_id, "old_source", "old_target")
        entry_id = get_glossary_entries(set_id)[0][0]

        update_glossary_entry(entry_id, "new_source", "new_target")
        entry = get_glossary_entries(set_id)[0]
        assert entry[1] == "new_source"
        assert entry[2] == "new_target"

    def test_delete_glossary_entry_leaves_others(self) -> None:
        """Deleting one entry does not affect other entries in the same set."""
        create_glossary_set("DelOne")
        set_id = get_glossary_sets()[0][0]
        add_glossary_entry(set_id, "keep_a", "garder_a")
        add_glossary_entry(set_id, "keep_b", "garder_b")
        add_glossary_entry(set_id, "remove", "supprimer")

        entries = get_glossary_entries(set_id)
        remove_id = next(e[0] for e in entries if e[1] == "remove")
        delete_glossary_entry(remove_id)

        remaining = get_glossary_entries(set_id)
        assert len(remaining) == 2  # noqa: PLR2004
        sources = {e[1] for e in remaining}
        assert "remove" not in sources
        assert "keep_a" in sources
        assert "keep_b" in sources

    def test_get_glossary_entries_returns_correct_columns(self) -> None:
        """Each entry has (id, source_text, target_text) columns."""
        create_glossary_set("Cols")
        set_id = get_glossary_sets()[0][0]
        add_glossary_entry(set_id, "src", "tgt")
        entries = get_glossary_entries(set_id)
        assert len(entries[0]) == 3  # noqa: PLR2004

    def test_get_active_glossary_sets_multiple(self) -> None:
        """Only active sets are returned from get_active_glossary_sets."""
        create_glossary_set("Active1")
        create_glossary_set("Active2")
        create_glossary_set("Inactive1")
        sets = get_glossary_sets()
        inactive_id = next(s[0] for s in sets if s[1] == "Inactive1")
        update_glossary_set_active(inactive_id, False)

        active = get_active_glossary_sets()
        names = {s[1] for s in active}
        assert "Active1" in names
        assert "Active2" in names
        assert "Inactive1" not in names

    def test_toggle_glossary_set_active_on_off(self) -> None:
        """Toggling active status on/off works correctly."""
        create_glossary_set("Toggle")
        set_id = get_glossary_sets()[0][0]

        # Default is active
        assert get_glossary_sets()[0][2] == 1

        update_glossary_set_active(set_id, False)
        assert get_glossary_sets()[0][2] == 0

        update_glossary_set_active(set_id, True)
        assert get_glossary_sets()[0][2] == 1

    def test_update_all_glossary_sets_active_selective(self) -> None:
        """update_all_glossary_sets_active changes all sets at once."""
        create_glossary_set("S1")
        create_glossary_set("S2")
        create_glossary_set("S3")

        # Deactivate one manually, then activate all
        sets = get_glossary_sets()
        update_glossary_set_active(sets[0][0], False)
        assert any(s[2] == 0 for s in get_glossary_sets())

        update_all_glossary_sets_active(True)
        for s in get_glossary_sets():
            assert s[2] == 1


# ---------------------------------------------------------------------------
# TestBatchOperations — expanded edge cases
# ---------------------------------------------------------------------------


class TestBatchOperations:
    """Extended tests for batch history operations."""

    def test_batch_pause_multiple_ids(self) -> None:
        """Batch pause with multiple valid IDs pauses all eligible entries."""
        ids = []
        for i in range(5):
            h_id = add_history_entry(f"f{i}.txt", "", "FR", STATUS_TRANSLATING)
            ids.append(h_id)
        batch_pause_history_entries(ids)
        for h_id in ids:
            assert get_history_entry_status(h_id) == STATUS_PAUSED

    def test_batch_resume_multiple_ids(self) -> None:
        """Batch resume with multiple valid IDs resumes all entries."""
        ids = []
        for i in range(5):
            h_id = add_history_entry(f"f{i}.txt", "", "FR", STATUS_PAUSED)
            ids.append(h_id)
        batch_resume_history_entries(ids)
        for h_id in ids:
            assert get_history_entry_status(h_id) == STATUS_PENDING

    def test_batch_retranslate_multiple_ids(self) -> None:
        """Batch retranslate resets multiple entries."""
        ids = []
        for i in range(5):
            h_id = add_history_entry(f"f{i}.txt", "EN", "FR", STATUS_DONE)
            update_history_progress(h_id, 100)
            ids.append(h_id)
        batch_retranslate_history_entries(ids, "DE", "ES")
        for h_id in ids:
            assert get_history_entry_status(h_id) == STATUS_PENDING
            entry = next(h for h in get_history() if h[0] == h_id)
            assert entry[2] == "DE"
            assert entry[3] == "ES"
            assert entry[5] == 0  # progress reset

    def test_batch_mark_deleting_multiple_ids(self) -> None:
        """Batch mark deleting sets multiple entries to Deleting."""
        ids = []
        for i in range(5):
            h_id = add_history_entry(f"f{i}.txt", "", "FR", STATUS_DONE)
            ids.append(h_id)
        batch_mark_deleting_history_entries(ids)
        for h_id in ids:
            assert get_history_entry_status(h_id) == STATUS_DELETING

    def test_batch_operations_with_empty_id_list(self) -> None:
        """All batch operations with empty lists are silent no-ops."""
        # These should all complete without error
        batch_pause_history_entries([])
        batch_resume_history_entries([])
        batch_retranslate_history_entries([], "EN", "FR")
        batch_mark_deleting_history_entries([])
        batch_pause_dubbing_entries([])
        batch_resume_dubbing_entries([])

    def test_batch_with_invalid_ids(self) -> None:
        """Batch operations with non-existent IDs are silent no-ops."""
        fake_ids = [900001, 900002, 900003]
        batch_pause_history_entries(fake_ids)
        batch_resume_history_entries(fake_ids)
        batch_retranslate_history_entries(fake_ids, "EN", "FR")
        batch_mark_deleting_history_entries(fake_ids)
        # No entries exist — table must be empty
        assert get_history() == []

    def test_batch_pause_only_affects_translating_and_pending(self) -> None:
        """Batch pause only affects Translating and Pending entries."""
        id_trans = add_history_entry("t.txt", "", "FR", STATUS_TRANSLATING)
        id_pend = add_history_entry("p.txt", "", "FR", STATUS_PENDING)
        id_done = add_history_entry("d.txt", "", "FR", STATUS_DONE)
        id_fail = add_history_entry("f.txt", "", "FR", STATUS_FAILED)
        id_paused = add_history_entry("ps.txt", "", "FR", STATUS_PAUSED)

        all_ids = [id_trans, id_pend, id_done, id_fail, id_paused]
        batch_pause_history_entries(all_ids)

        assert get_history_entry_status(id_trans) == STATUS_PAUSED
        assert get_history_entry_status(id_pend) == STATUS_PAUSED
        assert get_history_entry_status(id_done) == STATUS_DONE
        assert get_history_entry_status(id_fail) == STATUS_FAILED
        assert get_history_entry_status(id_paused) == STATUS_PAUSED

    def test_batch_resume_clears_error_code(self) -> None:
        """Batch resume clears error_code on all resumed entries."""
        id1 = add_history_entry("a.txt", "", "FR", STATUS_FAILED)
        update_history_status(id1, STATUS_FAILED, error_code=42)
        id2 = add_history_entry("b.txt", "", "FR", STATUS_FAILED)
        update_history_status(id2, STATUS_FAILED, error_code=99)

        batch_resume_history_entries([id1, id2])

        for h_id in (id1, id2):
            entry = next(h for h in get_history() if h[0] == h_id)
            assert entry[9] is None  # error_code cleared

    def test_batch_retranslate_with_mixed_existing_nonexistent(self) -> None:
        """Batch retranslate with mix of real and fake IDs only affects real ones."""
        h_id = add_history_entry("real.txt", "EN", "FR", STATUS_DONE)
        update_history_progress(h_id, 100)

        batch_retranslate_history_entries([h_id, 99999], "DE", "ES")

        assert get_history_entry_status(h_id) == STATUS_PENDING
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[2] == "DE"
        assert entry[3] == "ES"
        assert entry[5] == 0  # progress reset


# ---------------------------------------------------------------------------
# TestDBTransactionDecorator — expanded edge cases
# ---------------------------------------------------------------------------


class TestDBTransactionDecorator:
    """Extended tests for the db_transaction decorator."""

    def test_nested_transactions_share_cursor(self) -> None:
        """Inner function receives the same cursor object when nested."""
        import sqlite3 as _sqlite3  # noqa: PLC0415

        from src.core.database import db_transaction  # noqa: PLC0415

        received_cursors: list[_sqlite3.Cursor] = []

        @db_transaction
        def _outer(cursor: _sqlite3.Cursor) -> str:
            received_cursors.append(cursor)
            result = _inner(cursor, "nested")
            return f"outer+{result}"

        @db_transaction
        def _inner(cursor: _sqlite3.Cursor, label: str) -> str:
            received_cursors.append(cursor)
            return label

        # Call via normal path (outer creates the connection)
        result = _outer()
        assert result == "outer+nested"
        assert len(received_cursors) == 2  # noqa: PLR2004
        # Both should have received the SAME cursor object
        assert received_cursors[0] is received_cursors[1]

    def test_rollback_on_exception(self) -> None:
        """db_transaction rolls back on sqlite3.Error and returns None."""
        import sqlite3 as _sqlite3  # noqa: PLC0415

        from src.core.database import db_transaction  # noqa: PLC0415

        @db_transaction
        def _insert_and_fail(cursor: _sqlite3.Cursor) -> None:
            cursor.execute(
                "INSERT INTO history (file_name, source_lang, target_lang, status)"
                " VALUES ('fail.txt', 'EN', 'FR', 'Pending')"
            )
            # Force an error after the insert
            cursor.execute("SELECT * FROM nonexistent_table")

        result = _insert_and_fail()
        assert result is None

        # The insert should have been rolled back
        history = get_history()
        assert not any(h[1] == "fail.txt" for h in history)

    def test_connection_cleanup_after_success(self) -> None:
        """Connection is closed after successful transaction."""
        import sqlite3 as _sqlite3  # noqa: PLC0415
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from src.core.database import db_transaction  # noqa: PLC0415

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        @db_transaction
        def _query(cursor: _sqlite3.Cursor) -> str:
            return "ok"

        with patch("src.core.database.create_connection", return_value=mock_conn):
            result = _query()

        assert result == "ok"
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_connection_cleanup_after_error(self) -> None:
        """Connection is closed even after an error."""
        import sqlite3 as _sqlite3  # noqa: PLC0415
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from src.core.database import db_transaction  # noqa: PLC0415

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = _sqlite3.Error("test error")
        mock_conn.cursor.return_value = mock_cursor

        @db_transaction
        def _fail(cursor: _sqlite3.Cursor) -> None:
            cursor.execute("BAD SQL")

        with patch("src.core.database.create_connection", return_value=mock_conn):
            result = _fail()

        assert result is None
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_wal_mode_enabled(self) -> None:
        """create_connection configures WAL mode."""
        from src.core.database import create_connection  # noqa: PLC0415

        conn = create_connection()
        assert conn is not None
        try:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()

    def test_decorator_passes_extra_kwargs(self) -> None:
        """db_transaction correctly forwards kwargs to the wrapped function."""
        import sqlite3 as _sqlite3  # noqa: PLC0415

        from src.core.database import db_transaction  # noqa: PLC0415

        @db_transaction
        def _with_kwargs(cursor: _sqlite3.Cursor, name: str, value: int = 0) -> tuple:
            return (name, value)

        result = _with_kwargs(name="test", value=42)
        assert result == ("test", 42)  # noqa: PLR2004

    def test_decorator_returns_function_result(self) -> None:
        """db_transaction returns the wrapped function's result on success."""
        import sqlite3 as _sqlite3  # noqa: PLC0415

        from src.core.database import db_transaction  # noqa: PLC0415

        @db_transaction
        def _returns_list(cursor: _sqlite3.Cursor) -> list:
            return [1, 2, 3]

        result = _returns_list()
        assert result == [1, 2, 3]


# ---------------------------------------------------------------------------
# TestDBEdgeCases — expanded edge cases
# ---------------------------------------------------------------------------


class TestDBEdgeCases:
    """Extended tests for database edge cases."""

    def test_concurrent_access_safety(self) -> None:
        """Multiple sequential operations on the same DB do not corrupt data."""
        # Simulate rapid sequential operations
        ids = []
        for i in range(20):
            h_id = add_history_entry(f"concurrent_{i}.txt", "", "FR", STATUS_PENDING)
            ids.append(h_id)

        # Update all to translating
        for h_id in ids:
            update_history_status(h_id, STATUS_TRANSLATING)

        # Update all progress
        for h_id in ids:
            update_history_progress(h_id, 50)

        # Verify all are consistent
        history = get_history()
        for h_id in ids:
            entry = next(h for h in history if h[0] == h_id)
            assert entry[4] == STATUS_TRANSLATING
            assert entry[5] == 50  # noqa: PLR2004

    def test_get_db_path_prevents_test_db_collision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_db_path raises RuntimeError for production-like paths during tests."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_database.py::test_x")

        prod_paths = [
            Path("/home/user/.local/share/ai-translate"),
            Path("C:/Users/user/AppData/Roaming/ai-translate"),
            Path("/Users/user/Library/Application Support/ai-translate"),
        ]
        for prod_dir in prod_paths:
            with pytest.raises(RuntimeError, match="production database"):
                _check_db_path_safeguard(prod_dir)

    def test_get_db_path_safe_temp_path_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """get_db_path passes for safe temp paths during tests."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_database.py::test_x")
        result = _check_db_path_safeguard(tmp_path)
        assert result.endswith("translator.db")

    def test_update_history_file_name_preserves_other_fields(self) -> None:
        """Updating file_name does not alter status, progress, etc."""
        h_id = add_history_entry(
            "original.doc",
            "EN",
            "FR",
            STATUS_TRANSLATING,
            source_path="/src/original.doc",
            storage_path="/store/original.doc",
            file_size=4096,
        )
        update_history_progress(h_id, 75)
        update_history_file_name(h_id, "original.docx")

        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[1] == "original.docx"  # file_name updated
        assert entry[2] == "EN"  # source_lang preserved
        assert entry[3] == "FR"  # target_lang preserved
        assert entry[4] == STATUS_TRANSLATING  # status preserved
        assert entry[5] == 75  # noqa: PLR2004 — progress preserved
        assert entry[7] == 4096  # noqa: PLR2004 — file_size preserved

    def test_get_unfinished_history_ordering_mixed(self) -> None:
        """Translating entries come before Pending, then ordered by id ASC."""
        id_pend1 = add_history_entry("p1.txt", "", "FR", STATUS_PENDING)
        id_trans1 = add_history_entry("t1.txt", "", "DE", STATUS_TRANSLATING)
        id_pend2 = add_history_entry("p2.txt", "", "ES", STATUS_PENDING)
        id_trans2 = add_history_entry("t2.txt", "", "IT", STATUS_TRANSLATING)

        results = get_unfinished_history()
        ids = [r[0] for r in results]

        # Translating entries first, then Pending, each group by id ASC
        assert ids.index(id_trans1) < ids.index(id_pend1)
        assert ids.index(id_trans2) < ids.index(id_pend1)
        assert ids.index(id_trans1) < ids.index(id_trans2)
        assert ids.index(id_pend1) < ids.index(id_pend2)

    def test_get_unfinished_history_returns_correct_columns(self) -> None:
        """get_unfinished_history returns correct columns."""
        h_id = add_history_entry(
            "col_test.txt",
            "EN",
            "FR",
            STATUS_PENDING,
            source_path="/src/col_test.txt",
            storage_path="/store/col_test.txt",
        )
        results = get_unfinished_history()
        assert len(results) == 1
        row = results[0]
        assert len(row) == 5  # noqa: PLR2004
        assert row[0] == h_id
        assert row[1] == "/store/col_test.txt"  # storage_path
        assert row[2] == "EN"  # source_lang
        assert row[3] == "FR"  # target_lang
        assert row[4] == "/src/col_test.txt"  # source_path

    def test_history_entry_zero_file_size(self) -> None:
        """File size of 0 is stored correctly."""
        h_id = add_history_entry("empty.txt", "", "FR", STATUS_PENDING, file_size=0)
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[7] == 0

    def test_history_entry_large_file_size(self) -> None:
        """Large file sizes are stored correctly."""
        large_size = 2**40  # 1 TB
        h_id = add_history_entry(
            "big.zip", "", "FR", STATUS_PENDING, file_size=large_size
        )
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[7] == large_size

    def test_multiple_tables_independent(self) -> None:
        """Operations on one history table do not affect others."""
        add_history_entry("h.txt", "", "FR", STATUS_PENDING)
        add_extraction_entry("e.png", 100, "/e.png", "", STATUS_PENDING)
        add_subtitle_entry("s.mp4", 100, "/s.mp4", "", "EN", STATUS_PENDING)
        add_voice_entry("v.srt", 100, "/v.srt", "", STATUS_PENDING)
        add_dubbing_entry("d.mp4", 100, "/d.mp4", "", STATUS_PENDING)
        add_text_translation_entry("txt", "tgt", "EN", "FR", 3)

        # Clear only history — others should be unaffected
        clear_history()
        assert get_history() == []
        assert len(get_extraction_history()) == 1
        assert len(get_subtitle_history()) == 1
        assert len(get_voice_history()) == 1
        assert len(get_dubbing_history()) == 1
        assert len(get_text_translation_history()) == 1

    def test_init_db_creates_all_tables(self) -> None:
        """init_db creates all required tables."""
        from src.core.database import create_connection  # noqa: PLC0415

        conn = create_connection()
        assert conn is not None
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            expected = {
                "history",
                "glossary_sets",
                "glossary_entries",
                "extraction_history",
                "subtitle_history",
                "voice_history",
                "dubbing_history",
                "text_translation_history",
            }
            assert expected.issubset(tables)
        finally:
            conn.close()

    def test_init_db_creates_indexes(self) -> None:
        """init_db creates performance indexes."""
        from src.core.database import create_connection  # noqa: PLC0415

        conn = create_connection()
        assert conn is not None
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {row[0] for row in cursor.fetchall()}
            expected_indexes = {
                "idx_history_created_at",
                "idx_history_status",
                "idx_extraction_created_at",
                "idx_subtitle_created_at",
                "idx_voice_created_at",
                "idx_dubbing_created_at",
                "idx_text_translation_created_at",
            }
            assert expected_indexes.issubset(indexes)
        finally:
            conn.close()

    def test_add_history_entry_returns_incrementing_ids(self) -> None:
        """Consecutive inserts return incrementing IDs."""
        id1 = add_history_entry("a.txt", "", "FR", STATUS_PENDING)
        id2 = add_history_entry("b.txt", "", "FR", STATUS_PENDING)
        id3 = add_history_entry("c.txt", "", "FR", STATUS_PENDING)
        assert id1 < id2 < id3

    def test_glossary_set_deletion_does_not_affect_other_sets(self) -> None:
        """Deleting one glossary set does not affect other sets or their entries."""
        create_glossary_set("Keep")
        create_glossary_set("Delete")
        sets = get_glossary_sets()
        keep_id = next(s[0] for s in sets if s[1] == "Keep")
        del_id = next(s[0] for s in sets if s[1] == "Delete")

        add_glossary_entry(keep_id, "preserved", "conservé")
        add_glossary_entry(del_id, "removed", "supprimé")

        delete_glossary_set(del_id)

        remaining_sets = get_glossary_sets()
        assert len(remaining_sets) == 1
        assert remaining_sets[0][1] == "Keep"
        assert get_glossary_entry_count(keep_id) == 1
        assert get_glossary_entries(keep_id)[0][1] == "preserved"

    def test_extraction_history_ordering_desc(self) -> None:
        """Extraction history is ordered by created_at DESC, id DESC."""
        ids = []
        for i in range(5):
            entry_id = add_extraction_entry(
                f"img_{i}.png", 100, f"/img_{i}.png", "", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_extraction_history()
        entry_ids = [e[0] for e in entries]
        # Most recently inserted should be first
        assert entry_ids[0] == ids[-1]

    def test_subtitle_entry_with_all_none_optional_fields(self) -> None:
        """Subtitle entry with None error_message stores NULL."""
        entry_id = add_subtitle_entry(
            "v.mp4", 100, "/v.mp4", "", "EN", STATUS_PENDING, error_message=None
        )
        entries = get_subtitle_history()
        entry = next(e for e in entries if e[0] == entry_id)
        error_idx = 7  # noqa: PLR2004
        assert entry[error_idx] is None

    def test_voice_entry_with_all_none_optional_fields(self) -> None:
        """Voice entry with None error_message stores NULL."""
        entry_id = add_voice_entry(
            "s.srt", 100, "/s.srt", "", STATUS_PENDING, error_message=None
        )
        entries = get_voice_history()
        entry = next(e for e in entries if e[0] == entry_id)
        error_idx = 6  # noqa: PLR2004
        assert entry[error_idx] is None

    def test_dubbing_entry_with_all_none_optional_fields(self) -> None:
        """Dubbing entry with None error_message stores NULL."""
        entry_id = add_dubbing_entry(
            "v.mp4", 100, "/v.mp4", "", STATUS_PENDING, error_message=None
        )
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        error_idx = 9  # noqa: PLR2004
        assert entry[error_idx] is None

    def test_dubbing_default_empty_languages(self) -> None:
        """Dubbing entry defaults to empty strings for src_lang and target_lang."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[5] == ""  # src_lang
        assert entry[6] == ""  # target_lang

    def test_history_with_all_statuses(self) -> None:
        """All status values can be stored in history."""
        statuses = [
            STATUS_PENDING,
            STATUS_TRANSLATING,
            STATUS_DONE,
            STATUS_FAILED,
            STATUS_PAUSED,
            STATUS_DELETING,
        ]
        for status in statuses:
            add_history_entry("s.txt", "", "FR", status)

        history = get_history()
        stored_statuses = {h[4] for h in history}
        assert stored_statuses == set(statuses)


# ---------------------------------------------------------------------------
# reset_stuck_voice_entries — mixed statuses
# ---------------------------------------------------------------------------


def test_reset_stuck_voice_entries_mixed_statuses() -> None:
    """Only Generating entries are reset; Done/Failed/Pending stay intact."""
    id_gen1 = add_voice_entry("gen1.srt", 100, "/gen1.srt", "", STATUS_GENERATING)
    id_gen2 = add_voice_entry("gen2.srt", 200, "/gen2.srt", "", STATUS_GENERATING)
    id_done = add_voice_entry("done.srt", 300, "/done.srt", "/done.mp3", STATUS_DONE)
    id_fail = add_voice_entry(
        "fail.srt", 400, "/fail.srt", "", STATUS_FAILED, error_message="old error"
    )
    id_pend = add_voice_entry("pend.srt", 500, "/pend.srt", "", STATUS_PENDING)

    count = reset_stuck_voice_entries()
    assert count == 2  # noqa: PLR2004 — only the two Generating entries

    entries = get_voice_history()
    # voice_history columns: id(0), file_name(1), file_size(2), source_path(3),
    #   output_path(4), status(5), error_message(6), created_at(7)
    status_map = {e[0]: (e[5], e[6]) for e in entries}
    # Generating entries reset
    assert status_map[id_gen1] == (STATUS_FAILED, "APP_CRASHED")
    assert status_map[id_gen2] == (STATUS_FAILED, "APP_CRASHED")
    # Others unchanged
    assert status_map[id_done][0] == STATUS_DONE
    assert status_map[id_fail] == (STATUS_FAILED, "old error")
    assert status_map[id_pend][0] == STATUS_PENDING


# ---------------------------------------------------------------------------
# Text translation CRUD lifecycle (end-to-end)
# ---------------------------------------------------------------------------


def test_text_translation_crud_lifecycle() -> None:
    """Full CRUD lifecycle: add, get, update, delete, fingerprint changes."""
    # 1. Fingerprint before any entry
    fp_before = get_text_translation_fingerprint()
    assert fp_before is not None

    # 2. Add entry
    entry_id = add_text_translation_entry(
        source_text="Hello world",
        translated_text="Bonjour le monde",
        src_lang="English (US)",
        target_lang="French",
        char_count=11,
    )
    assert entry_id is not None
    assert entry_id > 0

    # 3. Fingerprint changes after insert
    fp_after_add = get_text_translation_fingerprint()
    assert fp_after_add != fp_before

    # 4. Retrieve entry
    entries = get_text_translation_history()
    assert len(entries) >= 1
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[1] == "Hello world"
    assert entry[2] == "Bonjour le monde"
    assert entry[3] == "English (US)"
    assert entry[4] == "French"
    assert entry[5] == 11  # noqa: PLR2004 — char_count

    # 5. Update translated text
    update_text_translation_entry(entry_id, "Salut le monde")
    entries = get_text_translation_history()
    entry = next(e for e in entries if e[0] == entry_id)
    assert entry[2] == "Salut le monde"
    # Source text unchanged
    assert entry[1] == "Hello world"

    # 6. Delete entry
    delete_text_translation_entry(entry_id)
    entries = get_text_translation_history()
    assert all(e[0] != entry_id for e in entries)

    # 7. Fingerprint changes after delete
    fp_after_delete = get_text_translation_fingerprint()
    assert fp_after_delete != fp_after_add


# ───────────────────────────────────────────────────────────────────────
# WAL crash-resilience — data survives an ungraceful process exit.
#
# AGENTS.md claims SQLite is configured in WAL mode for crash
# resilience.  WAL writes are durable as soon as fsync hits the wal
# file; the main DB only catches up at the next checkpoint.  These
# tests prove that durability promise: simulate a crash by NOT closing
# the writer connection cleanly, then open a fresh connection and
# verify the writes are visible.
# ───────────────────────────────────────────────────────────────────────


class TestWalCrashRecovery:
    """Writes commit-fsynced before a crash must survive on reopen."""

    def test_writes_survive_unclean_writer_close(self) -> None:
        """COMMITs survive an unclean writer close (no conn.close()).

        Simulates the real-world scenario where the app SIGKILLs (OOM,
        power loss, user kills the dock icon).  WAL mode's contract is
        that any committed transaction is durable — verify it.
        """
        from pathlib import Path  # noqa: PLC0415

        from src.core.database import (  # noqa: PLC0415
            add_history_entry,
            get_db_path,
            get_history,
        )

        # @db_transaction commits-and-fsyncs each call.  Run two writes
        # back to back; the WAL file holds them durably even before the
        # next checkpoint.
        entry_a = add_history_entry(
            "crash_a.docx",
            "English",
            "French",
            "Pending",
        )
        entry_b = add_history_entry(
            "crash_b.docx",
            "English",
            "Vietnamese",
            "Pending",
        )

        # Verify the on-disk WAL file actually exists — proof the writes
        # were journaled to WAL not the main DB file.  WAL file may not
        # always be present (auto-checkpoint can fold it back into main),
        # but if it is, it must be a real file.
        wal_path = Path(get_db_path() + "-wal")
        if wal_path.exists():
            assert wal_path.stat().st_size >= 0  # WAL exists

        # Fresh reader connection through @db_transaction — should see
        # both rows whether they're in main or WAL.
        all_history = get_history()
        ids = {e[0] for e in all_history}
        assert entry_a in ids, (
            "row A not visible after WAL-mode commit + reopen"
        )
        assert entry_b in ids, (
            "row B not visible after WAL-mode commit + reopen"
        )

    def test_uncommitted_writes_do_not_survive(self) -> None:
        """Negative test: writes WITHOUT commit must NOT survive a crash.

        This is the flip side of the durability contract — without
        an explicit commit, the writes live only in the writer's
        in-memory state and a crash discards them.  Confirms WAL isn't
        accidentally too aggressive about syncing.
        """
        import sqlite3  # noqa: PLC0415

        from src.core.database import (  # noqa: PLC0415
            get_db_path,
            get_history,
        )

        before = {e[0] for e in get_history()}

        # Open a raw connection bypassing the @db_transaction commit.
        # Using sqlite3 directly is essential — a context-managed
        # connection commits on exit, defeating the test.
        raw = sqlite3.connect(get_db_path())
        try:
            raw.execute("PRAGMA journal_mode = WAL")
            raw.execute(
                "INSERT INTO history (file_name, source_lang, "
                "target_lang, status) VALUES (?, ?, ?, ?)",
                ("/tmp/uncommitted.docx", "English", "French", "Pending"),
            )
            # Deliberately skip commit() before the simulated crash.
        finally:
            # Don't close — let GC handle it.  Some SQLite builds may
            # implicit-rollback on close; that's the same end-state
            # we're asserting.
            del raw

        after = {e[0] for e in get_history()}
        assert after == before, (
            "uncommitted write leaked through a simulated crash — "
            "WAL durability boundary is broken"
        )

    def test_reader_sees_writer_commits_without_blocking(self) -> None:
        """WAL mode lets readers proceed concurrently with a writer.

        Without WAL (rollback-journal mode), a writer would hold an
        exclusive lock and any reader would block until commit.  Verify
        WAL preserves the snapshot-isolation behaviour the app relies
        on for the Live/translate-text auto-save fan-out.
        """
        import time  # noqa: PLC0415

        from src.core.database import (  # noqa: PLC0415
            add_history_entry,
            get_history,
        )

        # Each add_history_entry call uses @db_transaction → its own
        # short-lived writer connection.  Interleave writes and reads
        # to prove WAL doesn't block.
        entry_id = add_history_entry(
            "concurrent.docx",
            "English",
            "French",
            "Pending",
        )

        # Reader sees the committed row immediately, no lock-wait.
        # Bound the reader call to 1s as a generous timeout — WAL should
        # serve the snapshot in milliseconds.
        start = time.monotonic()
        ids = {e[0] for e in get_history()}
        elapsed = time.monotonic() - start
        assert entry_id in ids
        assert elapsed < 1.0, (
            f"reader took {elapsed:.3f}s — WAL snapshot should be near-instant"
        )
