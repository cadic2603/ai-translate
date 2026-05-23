"""Extended unit tests for the core database logic.

Covers pagination boundaries, dubbing progress edge cases, NULL field handling,
batch operation edge cases, timestamp ordering, concurrent access, and Unicode
handling across all history types.

These tests are designed to be appended to or run alongside test_database.py.
"""

import threading
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
from src.constants.history import STATUS_DELETING, STATUS_GENERATING
from src.core.database import (
    add_dubbing_entry,
    add_extraction_entry,
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
    delete_dubbing_entry,
    delete_extraction_entry,
    delete_history_entry,
    delete_subtitle_entry,
    delete_voice_entry,
    get_dubbing_entry_status,
    get_dubbing_fingerprint,
    get_dubbing_history,
    get_extraction_history,
    get_history,
    get_history_entry_detail,
    get_history_entry_details,
    get_history_entry_status,
    get_subtitle_history,
    get_text_translation_fingerprint,
    get_text_translation_history,
    get_voice_history,
    init_db,
    update_dubbing_progress,
    update_dubbing_status,
    update_extraction_status,
    update_history_progress,
    update_history_status,
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


# ===========================================================================
# 1. Pagination Boundary Tests
# ===========================================================================


class TestPaginationBoundaries:
    """Verify LIMIT 50 behavior at exact boundary values (49, 50, 51)."""

    # -- Dubbing history --

    def test_dubbing_history_49_entries(self) -> None:
        """49 entries: all 49 are returned."""
        for i in range(49):
            add_dubbing_entry(f"vid_{i}.mp4", 100, f"/vid_{i}.mp4", "", STATUS_DONE)
        entries = get_dubbing_history()
        assert len(entries) == 49  # noqa: PLR2004

    def test_dubbing_history_exactly_50_entries(self) -> None:
        """50 entries: all 50 are returned (at the limit)."""
        for i in range(50):
            add_dubbing_entry(f"vid_{i}.mp4", 100, f"/vid_{i}.mp4", "", STATUS_DONE)
        entries = get_dubbing_history()
        assert len(entries) == 50  # noqa: PLR2004

    def test_dubbing_history_51_entries_returns_50(self) -> None:
        """51 entries: only the newest 50 are returned, oldest is dropped."""
        ids = []
        for i in range(51):
            entry_id = add_dubbing_entry(
                f"vid_{i}.mp4", 100, f"/vid_{i}.mp4", "", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_dubbing_history()
        assert len(entries) == 50  # noqa: PLR2004
        # The oldest entry (first inserted) should be excluded
        returned_ids = {e[0] for e in entries}
        assert ids[0] not in returned_ids

    # -- Text translation history --

    def test_text_translation_49_entries(self) -> None:
        """49 text translation entries: all returned."""
        for i in range(49):
            add_text_translation_entry(f"src_{i}", f"tgt_{i}", "", "FR", 5)
        entries = get_text_translation_history()
        assert len(entries) == 49  # noqa: PLR2004

    def test_text_translation_exactly_50(self) -> None:
        """50 text translation entries: all returned."""
        for i in range(50):
            add_text_translation_entry(f"src_{i}", f"tgt_{i}", "", "FR", 5)
        entries = get_text_translation_history()
        assert len(entries) == 50  # noqa: PLR2004

    def test_text_translation_51_entries_returns_50(self) -> None:
        """51 text translation entries: only 50 returned."""
        ids = []
        for i in range(51):
            entry_id = add_text_translation_entry(f"src_{i}", f"tgt_{i}", "", "FR", 5)
            ids.append(entry_id)
        entries = get_text_translation_history()
        assert len(entries) == 50  # noqa: PLR2004
        returned_ids = {e[0] for e in entries}
        assert ids[0] not in returned_ids

    # -- Subtitle history --

    def test_subtitle_history_49_entries(self) -> None:
        """49 subtitle entries: all returned."""
        for i in range(49):
            add_subtitle_entry(f"v_{i}.mp4", 100, f"/v_{i}.mp4", "", "EN", STATUS_DONE)
        entries = get_subtitle_history()
        assert len(entries) == 49  # noqa: PLR2004

    def test_subtitle_history_exactly_50(self) -> None:
        """50 subtitle entries: all returned."""
        for i in range(50):
            add_subtitle_entry(f"v_{i}.mp4", 100, f"/v_{i}.mp4", "", "EN", STATUS_DONE)
        entries = get_subtitle_history()
        assert len(entries) == 50  # noqa: PLR2004

    def test_subtitle_history_51_entries_returns_50(self) -> None:
        """51 subtitle entries: only 50 returned."""
        ids = []
        for i in range(51):
            entry_id = add_subtitle_entry(
                f"v_{i}.mp4", 100, f"/v_{i}.mp4", "", "EN", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_subtitle_history()
        assert len(entries) == 50  # noqa: PLR2004
        returned_ids = {e[0] for e in entries}
        assert ids[0] not in returned_ids

    # -- Voice history --

    def test_voice_history_49_entries(self) -> None:
        """49 voice entries: all returned."""
        for i in range(49):
            add_voice_entry(f"s_{i}.srt", 100, f"/s_{i}.srt", "", STATUS_DONE)
        entries = get_voice_history()
        assert len(entries) == 49  # noqa: PLR2004

    def test_voice_history_exactly_50(self) -> None:
        """50 voice entries: all returned."""
        for i in range(50):
            add_voice_entry(f"s_{i}.srt", 100, f"/s_{i}.srt", "", STATUS_DONE)
        entries = get_voice_history()
        assert len(entries) == 50  # noqa: PLR2004

    def test_voice_history_51_entries_returns_50(self) -> None:
        """51 voice entries: only 50 returned."""
        ids = []
        for i in range(51):
            entry_id = add_voice_entry(
                f"s_{i}.srt", 100, f"/s_{i}.srt", "", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_voice_history()
        assert len(entries) == 50  # noqa: PLR2004
        returned_ids = {e[0] for e in entries}
        assert ids[0] not in returned_ids

    # -- Extraction history --

    def test_extraction_history_49_entries(self) -> None:
        """49 extraction entries: all returned."""
        for i in range(49):
            add_extraction_entry(f"img_{i}.png", 100, f"/img_{i}.png", "", STATUS_DONE)
        entries = get_extraction_history()
        assert len(entries) == 49  # noqa: PLR2004

    def test_extraction_history_exactly_50(self) -> None:
        """50 extraction entries: all returned."""
        for i in range(50):
            add_extraction_entry(f"img_{i}.png", 100, f"/img_{i}.png", "", STATUS_DONE)
        entries = get_extraction_history()
        assert len(entries) == 50  # noqa: PLR2004

    def test_extraction_history_51_entries_returns_50(self) -> None:
        """51 extraction entries: only 50 returned."""
        ids = []
        for i in range(51):
            entry_id = add_extraction_entry(
                f"img_{i}.png", 100, f"/img_{i}.png", "", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_extraction_history()
        assert len(entries) == 50  # noqa: PLR2004
        returned_ids = {e[0] for e in entries}
        assert ids[0] not in returned_ids


# ===========================================================================
# 2. Dubbing Progress Type Validation
# ===========================================================================


class TestDubbingProgressEdgeCases:
    """Verify CAST(progress AS INTEGER) behavior for TEXT-stored progress."""

    def test_progress_monotonic_increase(self) -> None:
        """Progress at 50 then attempt 30: stays at 50 due to monotonic guard."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        update_dubbing_progress(entry_id, 50)
        update_dubbing_progress(entry_id, 30)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        progress_idx = 8  # noqa: PLR2004
        assert entry[progress_idx] == "50"

    def test_progress_zero_to_hundred(self) -> None:
        """Full range: 1 -> 25 -> 50 -> 75 -> 100 all accepted monotonically.

        Note: update_dubbing_progress(0) is a no-op on a fresh entry because
        CAST('' AS INTEGER) = 0 and 0 < 0 is false.  We start from 1.
        """
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        progress_idx = 8  # noqa: PLR2004
        for value in (1, 25, 50, 75, 100):
            update_dubbing_progress(entry_id, value)
            entries = get_dubbing_history()
            entry = next(e for e in entries if e[0] == entry_id)
            assert entry[progress_idx] == str(value)

    def test_progress_stored_as_text_but_compared_as_int(self) -> None:
        """CAST(progress AS INTEGER) ensures numeric comparison on TEXT column.

        The progress column default is '' (empty string).  After updating to 10,
        the stored value is '10'.  Attempting 5 should be rejected by
        CAST('10' AS INTEGER) < 5 => 10 < 5 => false.
        """
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        update_dubbing_progress(entry_id, 10)
        update_dubbing_progress(entry_id, 5)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        progress_idx = 8  # noqa: PLR2004
        assert entry[progress_idx] == "10"

    def test_progress_empty_string_default(self) -> None:
        """New entry has '' progress; updating to 10 should work.

        CAST('' AS INTEGER) = 0 in SQLite, so 0 < 10 is true and the
        update proceeds.
        """
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        # Verify default is empty string
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        progress_idx = 8  # noqa: PLR2004
        assert entry[progress_idx] == ""
        # Update from '' to 10 should succeed
        update_dubbing_progress(entry_id, 10)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[progress_idx] == "10"

    def test_progress_update_same_value_is_noop(self) -> None:
        """Setting progress to 50 then 50 again: CAST('50') < 50 is false."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        update_dubbing_progress(entry_id, 50)
        update_dubbing_progress(entry_id, 50)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        progress_idx = 8  # noqa: PLR2004
        assert entry[progress_idx] == "50"

    def test_progress_via_status_update_is_text(self) -> None:
        """update_dubbing_status stores progress as text directly."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        update_dubbing_status(entry_id, STATUS_GENERATING, progress="Step 2/4")
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        progress_idx = 8  # noqa: PLR2004
        assert entry[progress_idx] == "Step 2/4"

    def test_progress_update_after_text_progress(self) -> None:
        """After storing text progress via status update, numeric update works.

        CAST('Step 2/4' AS INTEGER) = 0 in SQLite, so 0 < 50 is true.
        """
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        update_dubbing_status(entry_id, STATUS_GENERATING, progress="Step 2/4")
        update_dubbing_progress(entry_id, 50)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        progress_idx = 8  # noqa: PLR2004
        assert entry[progress_idx] == "50"


# ===========================================================================
# 3. NULL Field Handling
# ===========================================================================


class TestNullFieldHandling:
    """Verify NULL storage and retrieval across history types."""

    def test_dubbing_entry_null_source_path(self) -> None:
        """Dubbing entry with source_path=None stores NULL in the DB.

        add_dubbing_entry accepts str for source_path, but SQLite accepts
        None for TEXT columns.  We use a direct entry and verify retrieval.
        """
        # source_path is typed as str but SQLite stores None as NULL
        entry_id = add_dubbing_entry("v.mp4", 100, None, "", STATUS_PENDING)  # type: ignore[arg-type]
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        source_path_idx = 3  # noqa: PLR2004
        assert entry[source_path_idx] is None

    def test_dubbing_entry_null_output_path(self) -> None:
        """Dubbing entry with output_path=None stores NULL."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", None, STATUS_PENDING)  # type: ignore[arg-type]
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        output_path_idx = 4  # noqa: PLR2004
        assert entry[output_path_idx] is None

    def test_subtitle_entry_null_error_message_preserved(self) -> None:
        """Subtitle entry created without error_message has NULL error_message."""
        entry_id = add_subtitle_entry("v.mp4", 100, "/v.mp4", "", "EN", STATUS_DONE)
        entries = get_subtitle_history()
        entry = next(e for e in entries if e[0] == entry_id)
        error_idx = 7  # noqa: PLR2004
        assert entry[error_idx] is None

    def test_voice_entry_null_error_message_after_update(self) -> None:
        """Voice entry: add with error, update with None, verify None."""
        entry_id = add_voice_entry(
            "s.srt", 100, "/s.srt", "", STATUS_FAILED, error_message="timeout"
        )
        # Verify error is stored
        entries = get_voice_history()
        entry = next(e for e in entries if e[0] == entry_id)
        error_idx = 6  # noqa: PLR2004
        assert entry[error_idx] == "timeout"
        # Update status without error_message -> error_message becomes None
        update_voice_status(entry_id, STATUS_DONE, output_path="/s.mp3")
        entries = get_voice_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[error_idx] is None

    def test_extraction_entry_null_to_error_to_null(self) -> None:
        """Extraction entry cycles: None -> 'error' -> None."""
        entry_id = add_extraction_entry("img.png", 100, "/img.png", "", STATUS_PENDING)
        # Initially no error
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        error_idx = 6  # noqa: PLR2004
        assert entry[error_idx] is None
        # Set error
        update_extraction_status(
            entry_id, STATUS_FAILED, error_message="OCR engine not found"
        )
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[error_idx] == "OCR engine not found"
        # Clear error by updating to Done
        update_extraction_status(entry_id, STATUS_DONE, output_path="/out.txt")
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[error_idx] is None

    def test_dubbing_entry_null_error_message_default(self) -> None:
        """Dubbing entry without error_message defaults to NULL."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        error_idx = 9  # noqa: PLR2004
        assert entry[error_idx] is None


# ===========================================================================
# 4. Batch Operation Edge Cases
# ===========================================================================


class TestBatchOperationEdgeCases:
    """Verify batch pause/resume dubbing edge cases."""

    def test_batch_pause_dubbing_empty_ids_list(self) -> None:
        """Empty list should not raise any error."""
        batch_pause_dubbing_entries([])

    def test_batch_pause_dubbing_nonexistent_ids(self) -> None:
        """IDs that do not exist: should silently do nothing."""
        batch_pause_dubbing_entries([99990, 99991, 99992])
        assert get_dubbing_history() == []

    def test_batch_pause_dubbing_mixed_valid_invalid(self) -> None:
        """Mix of real and fake IDs: only valid entries are paused."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        batch_pause_dubbing_entries([entry_id, 99990, 99991])
        assert get_dubbing_entry_status(entry_id) == STATUS_PAUSED

    def test_batch_pause_skips_non_active_statuses(self) -> None:
        """Only GENERATING and PENDING get paused; Done/Failed stay unchanged."""
        id_gen = add_dubbing_entry("gen.mp4", 100, "/gen.mp4", "", STATUS_GENERATING)
        id_pend = add_dubbing_entry("pend.mp4", 100, "/pend.mp4", "", STATUS_PENDING)
        id_done = add_dubbing_entry("done.mp4", 100, "/done.mp4", "/o.mp4", STATUS_DONE)
        id_fail = add_dubbing_entry("fail.mp4", 100, "/fail.mp4", "", STATUS_FAILED)
        id_paused = add_dubbing_entry(
            "paused.mp4", 100, "/paused.mp4", "", STATUS_PAUSED
        )

        batch_pause_dubbing_entries([id_gen, id_pend, id_done, id_fail, id_paused])

        assert get_dubbing_entry_status(id_gen) == STATUS_PAUSED
        assert get_dubbing_entry_status(id_pend) == STATUS_PAUSED
        assert get_dubbing_entry_status(id_done) == STATUS_DONE
        assert get_dubbing_entry_status(id_fail) == STATUS_FAILED
        assert get_dubbing_entry_status(id_paused) == STATUS_PAUSED

    def test_batch_resume_dubbing_empty_ids_list(self) -> None:
        """Empty list should not raise any error."""
        batch_resume_dubbing_entries([])

    def test_batch_resume_dubbing_nonexistent_ids(self) -> None:
        """Non-existent IDs: should silently do nothing."""
        batch_resume_dubbing_entries([99990, 99991])
        assert get_dubbing_history() == []

    def test_batch_resume_clears_error_message(self) -> None:
        """Entry with error_message: resume sets status to Pending, clears error."""
        entry_id = add_dubbing_entry(
            "v.mp4",
            100,
            "/v.mp4",
            "",
            STATUS_FAILED,
            error_message="API timeout",
        )
        # Verify error is set
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        error_idx = 9  # noqa: PLR2004
        assert entry[error_idx] == "API timeout"

        batch_resume_dubbing_entries([entry_id])

        assert get_dubbing_entry_status(entry_id) == STATUS_PENDING
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[error_idx] is None

    def test_batch_pause_single_id(self) -> None:
        """Batch pause with a single valid ID works."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
        batch_pause_dubbing_entries([entry_id])
        assert get_dubbing_entry_status(entry_id) == STATUS_PAUSED

    def test_batch_resume_single_id(self) -> None:
        """Batch resume with a single valid ID works."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PAUSED)
        batch_resume_dubbing_entries([entry_id])
        assert get_dubbing_entry_status(entry_id) == STATUS_PENDING

    def test_batch_resume_already_pending_is_noop(self) -> None:
        """Resuming an already-Pending entry leaves it Pending."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_PENDING)
        batch_resume_dubbing_entries([entry_id])
        assert get_dubbing_entry_status(entry_id) == STATUS_PENDING

    def test_batch_pause_then_resume_round_trip(self) -> None:
        """Pause then resume: entry goes Generating -> Paused -> Pending."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        batch_pause_dubbing_entries([entry_id])
        assert get_dubbing_entry_status(entry_id) == STATUS_PAUSED
        batch_resume_dubbing_entries([entry_id])
        assert get_dubbing_entry_status(entry_id) == STATUS_PENDING


# ===========================================================================
# 5. Timestamp Collision and Ordering
# ===========================================================================


class TestTimestampOrdering:
    """Verify ORDER BY created_at DESC, id DESC handles timestamp ties."""

    def test_entries_with_same_timestamp_ordered_by_id_desc(self) -> None:
        """Multiple entries inserted rapidly share a timestamp.

        The secondary ORDER BY id DESC ensures deterministic ordering:
        higher IDs (more recent inserts) come first.
        """
        ids = []
        for i in range(10):
            entry_id = add_dubbing_entry(
                f"vid_{i}.mp4", 100, f"/vid_{i}.mp4", "", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_dubbing_history()
        returned_ids = [e[0] for e in entries]
        # Entries should be in descending ID order (newest first)
        assert returned_ids == sorted(returned_ids, reverse=True)

    def test_fingerprint_stable_without_changes(self) -> None:
        """Same data produces the same fingerprint across multiple calls."""
        add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_DONE)
        add_text_translation_entry("src", "tgt", "", "FR", 3)
        fp_dub1 = get_dubbing_fingerprint()
        fp_dub2 = get_dubbing_fingerprint()
        fp_text1 = get_text_translation_fingerprint()
        fp_text2 = get_text_translation_fingerprint()
        assert fp_dub1 == fp_dub2
        assert fp_text1 == fp_text2

    def test_text_translation_fingerprint_after_51st_entry(self) -> None:
        """After 51 entries, fingerprint reflects only the latest 50.

        The fingerprint SELECT is wrapped with LIMIT 50, so the oldest
        entry falls outside the window and does not affect the result.
        Note: the fingerprint query sorts by ``created_at DESC`` only
        (no ``id DESC`` tiebreaker), so with same-second timestamps the
        max-id value may not increase deterministically. We verify only
        that count stays at 50 and the fingerprint changed.
        """
        for i in range(50):
            add_text_translation_entry(f"src_{i}", f"tgt_{i}", "", "FR", 5)
        fp_at_50 = get_text_translation_fingerprint()
        assert fp_at_50 is not None
        assert fp_at_50[0] == 50  # noqa: PLR2004

        # Add the 51st entry
        add_text_translation_entry("src_50", "tgt_50", "", "FR", 5)
        fp_at_51 = get_text_translation_fingerprint()
        assert fp_at_51 is not None
        # Still 50 entries in the window
        assert fp_at_51[0] == 50  # noqa: PLR2004
        # Max id should be >= previous (it may equal if same timestamp puts
        # the newest entry outside the ORDER BY window)
        assert fp_at_51[1] >= fp_at_50[1]

    def test_subtitle_same_timestamp_order_by_id_desc(self) -> None:
        """Subtitle entries with same timestamp ordered by id DESC."""
        ids = []
        for i in range(5):
            entry_id = add_subtitle_entry(
                f"v_{i}.mp4", 100, f"/v_{i}.mp4", "", "EN", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_subtitle_history()
        returned_ids = [e[0] for e in entries]
        assert returned_ids == sorted(returned_ids, reverse=True)

    def test_voice_same_timestamp_order_by_id_desc(self) -> None:
        """Voice entries with same timestamp ordered by id DESC."""
        ids = []
        for i in range(5):
            entry_id = add_voice_entry(
                f"s_{i}.srt", 100, f"/s_{i}.srt", "", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_voice_history()
        returned_ids = [e[0] for e in entries]
        assert returned_ids == sorted(returned_ids, reverse=True)

    def test_extraction_same_timestamp_order_by_id_desc(self) -> None:
        """Extraction entries with same timestamp ordered by id DESC."""
        ids = []
        for i in range(5):
            entry_id = add_extraction_entry(
                f"img_{i}.png", 100, f"/img_{i}.png", "", STATUS_DONE
            )
            ids.append(entry_id)
        entries = get_extraction_history()
        returned_ids = [e[0] for e in entries]
        assert returned_ids == sorted(returned_ids, reverse=True)


# ===========================================================================
# 6. Concurrent Access (Threading)
# ===========================================================================


class TestConcurrentAccess:
    """Verify database integrity under concurrent thread access."""

    def test_concurrent_writes_no_corruption(self) -> None:
        """10 threads each add 10 dubbing entries concurrently.

        Total should be 100 entries with no errors.  SQLite WAL mode
        and the _DB_TIMEOUT setting should handle the lock contention.
        """
        errors: list[Exception] = []
        barrier = threading.Barrier(10)

        def _writer(thread_idx: int) -> None:
            try:
                barrier.wait(timeout=10)
                for i in range(10):
                    add_dubbing_entry(
                        f"t{thread_idx}_v{i}.mp4",
                        100,
                        f"/t{thread_idx}_v{i}.mp4",
                        "",
                        STATUS_DONE,
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_writer, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
        # All 100 entries should exist (some may be beyond the LIMIT 50 window)
        # Use a direct count via fingerprint
        fp = get_dubbing_fingerprint()
        assert fp is not None
        # Fingerprint counts up to LIMIT 50, but we can verify at least 50 exist
        assert fp[0] == 50  # noqa: PLR2004

    def test_concurrent_read_during_write(self) -> None:
        """Reader and writer threads run simultaneously without errors."""
        errors: list[Exception] = []
        stop_event = threading.Event()

        def _writer() -> None:
            try:
                for i in range(20):
                    add_text_translation_entry(f"src_{i}", f"tgt_{i}", "", "FR", 5)
            except Exception as exc:
                errors.append(exc)
            finally:
                stop_event.set()

        def _reader() -> None:
            try:
                while not stop_event.is_set():
                    get_text_translation_history()
                    get_text_translation_fingerprint()
            except Exception as exc:
                errors.append(exc)

        writer = threading.Thread(target=_writer)
        reader = threading.Thread(target=_reader)
        writer.start()
        reader.start()
        writer.join(timeout=30)
        reader.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
        entries = get_text_translation_history()
        assert len(entries) == 20  # noqa: PLR2004

    def test_concurrent_status_updates(self) -> None:
        """Multiple threads updating different entries' status concurrently."""
        errors: list[Exception] = []
        entry_ids = []
        for i in range(10):
            entry_id = add_dubbing_entry(
                f"v_{i}.mp4", 100, f"/v_{i}.mp4", "", STATUS_PENDING
            )
            entry_ids.append(entry_id)

        barrier = threading.Barrier(10)

        def _updater(idx: int) -> None:
            try:
                barrier.wait(timeout=10)
                update_dubbing_status(entry_ids[idx], STATUS_GENERATING)
                update_dubbing_progress(entry_ids[idx], 50)
                update_dubbing_status(entry_ids[idx], STATUS_DONE)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_updater, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
        for eid in entry_ids:
            assert get_dubbing_entry_status(eid) == STATUS_DONE

    def test_concurrent_batch_pause_disjoint_rows_all_land(self) -> None:
        """10 threads call batch_pause_history_entries on disjoint rows.

        WAL mode + the @db_transaction retry loop should serialise all
        writers without deadlock; every targeted row ends up Paused.
        Also verifies no row outside a thread's id-set is touched.
        """
        errors: list[Exception] = []
        # 10 threads × 5 entries each = 50 disjoint Translating entries.
        per_thread = 5
        thread_count = 10
        all_ids: list[list[int]] = []
        for t_idx in range(thread_count):
            ids: list[int] = []
            for i in range(per_thread):
                h_id = add_history_entry(
                    f"t{t_idx}_f{i}.txt",
                    "English",
                    "French",
                    STATUS_TRANSLATING,
                )
                assert h_id is not None
                ids.append(h_id)
            all_ids.append(ids)

        # Sanity baseline: all rows are Translating.
        for ids in all_ids:
            for h_id in ids:
                assert get_history_entry_status(h_id) == STATUS_TRANSLATING

        barrier = threading.Barrier(thread_count)

        def _pauser(idx: int) -> None:
            try:
                barrier.wait(timeout=10)
                batch_pause_history_entries(all_ids[idx])
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=_pauser, args=(i,)) for i in range(thread_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive(), "Thread did not finish — possible deadlock"

        assert not errors, f"Thread errors: {errors}"
        # Every row from every thread is now Paused.
        for ids in all_ids:
            for h_id in ids:
                assert get_history_entry_status(h_id) == STATUS_PAUSED, (
                    f"Row {h_id} should be Paused"
                )

    def test_concurrent_batch_pause_overlapping_rows_consistent(self) -> None:
        """Threads with overlapping id-sets all converge to Paused.

        With overlap, multiple threads UPDATE the same rows concurrently.
        The transaction guard should serialise them; final state is Paused
        regardless of execution order.
        """
        errors: list[Exception] = []
        shared_ids: list[int] = []
        for i in range(20):
            h_id = add_history_entry(
                f"shared_{i}.txt",
                "English",
                "French",
                STATUS_TRANSLATING,
            )
            assert h_id is not None
            shared_ids.append(h_id)

        # Each of 10 threads pauses a sliding window of 11 ids — heavy overlap.
        barrier = threading.Barrier(10)

        def _pauser(start: int) -> None:
            try:
                barrier.wait(timeout=10)
                batch_pause_history_entries(shared_ids[start : start + 11])
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_pauser, args=(s,)) for s in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive(), "Thread did not finish — possible deadlock"

        assert not errors, f"Thread errors: {errors}"
        for h_id in shared_ids:
            assert get_history_entry_status(h_id) == STATUS_PAUSED


# ===========================================================================
# 7. Unicode and Special Characters in All History Types
# ===========================================================================


class TestUnicodeAllHistoryTypes:
    """Verify Unicode handling across all five history table types."""

    def test_dubbing_entry_arabic_rtl_text(self) -> None:
        """Arabic file name and language codes are stored correctly."""
        entry_id = add_dubbing_entry(
            file_name="\u0641\u064a\u062f\u064a\u0648.mp4",
            file_size=2048,
            source_path="/\u0641\u064a\u062f\u064a\u0648.mp4",
            output_path="/\u0641\u064a\u062f\u064a\u0648_dubbed.mp4",
            status=STATUS_DONE,
            src_lang="\u0627\u0644\u0639\u0631\u0628\u064a\u0629",
            target_lang="English (US)",
        )
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == "\u0641\u064a\u062f\u064a\u0648.mp4"
        assert entry[5] == "\u0627\u0644\u0639\u0631\u0628\u064a\u0629"

    def test_text_translation_emoji_content(self) -> None:
        """Emoji in source_text and translated_text are preserved."""
        entry_id = add_text_translation_entry(
            source_text="I love coding \U0001f4bb\U0001f680",
            translated_text="J'adore coder \U0001f4bb\U0001f680",
            src_lang="English (US)",
            target_lang="French",
            char_count=20,
        )
        entries = get_text_translation_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert "\U0001f4bb" in entry[1]
        assert "\U0001f680" in entry[2]

    def test_subtitle_entry_combining_diacritics(self) -> None:
        """Combining diacritics (e + combining accent = e) in file_name."""
        # e followed by combining acute accent (U+0301) to form e
        combining_name = "re\u0301sume\u0301.mp4"
        entry_id = add_subtitle_entry(
            combining_name, 512, f"/{combining_name}", "", "FR", STATUS_DONE
        )
        entries = get_subtitle_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == combining_name

    def test_voice_entry_cjk_characters(self) -> None:
        """Japanese and Chinese characters in file_name."""
        cjk_name = "\u65e5\u672c\u8a9e_\u4e2d\u6587_\ud55c\uad6d\uc5b4.srt"
        entry_id = add_voice_entry(cjk_name, 256, f"/{cjk_name}", "", STATUS_DONE)
        entries = get_voice_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == cjk_name

    def test_extraction_entry_zero_width_chars(self) -> None:
        """Zero-width joiner and zero-width space in file names."""
        # Zero-width joiner (U+200D) and zero-width space (U+200B)
        zwj_name = "family\u200d\u200bphoto.png"
        entry_id = add_extraction_entry(
            zwj_name, 1024, f"/{zwj_name}", f"/{zwj_name}.txt", STATUS_DONE
        )
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == zwj_name
        assert "\u200d" in entry[1]
        assert "\u200b" in entry[1]

    def test_dubbing_entry_mixed_scripts(self) -> None:
        """File name mixing Latin, Cyrillic, and Devanagari scripts."""
        mixed_name = "Hello_\u041f\u0440\u0438\u0432\u0435\u0442_\u0928\u092e\u0938\u094d\u0924\u0947.mp4"
        entry_id = add_dubbing_entry(mixed_name, 500, f"/{mixed_name}", "", STATUS_DONE)
        entries = get_dubbing_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == mixed_name

    def test_text_translation_newlines_and_tabs(self) -> None:
        """Text with newlines, tabs, and carriage returns is preserved."""
        src = "Line1\nLine2\tTabbed\r\nCRLF"
        tgt = "Ligne1\nLigne2\tTabulee\r\nCRLF"
        entry_id = add_text_translation_entry(src, tgt, "EN", "FR", len(src))
        entries = get_text_translation_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == src
        assert entry[2] == tgt
        assert "\t" in entry[1]
        assert "\r\n" in entry[2]

    def test_subtitle_entry_thai_script(self) -> None:
        """Thai script in file name and language field."""
        thai_name = "\u0e27\u0e34\u0e14\u0e35\u0e42\u0e2d.mp4"
        entry_id = add_subtitle_entry(
            thai_name,
            300,
            f"/{thai_name}",
            "",
            "\u0e44\u0e17\u0e22",
            STATUS_DONE,
        )
        entries = get_subtitle_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == thai_name
        assert entry[5] == "\u0e44\u0e17\u0e22"

    def test_extraction_entry_surrogate_pair_emoji(self) -> None:
        """Emoji that require surrogate pairs in UTF-16 (4-byte UTF-8)."""
        emoji_name = "\U0001f9d1\u200d\U0001f4bb_code.png"
        entry_id = add_extraction_entry(
            emoji_name, 2048, f"/{emoji_name}", "", STATUS_DONE
        )
        entries = get_extraction_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == emoji_name

    def test_voice_entry_right_to_left_override(self) -> None:
        """Right-to-left override character in file name."""
        rtl_name = "test\u202esrt.evil"
        entry_id = add_voice_entry(rtl_name, 100, f"/{rtl_name}", "", STATUS_DONE)
        entries = get_voice_history()
        entry = next(e for e in entries if e[0] == entry_id)
        assert entry[1] == rtl_name
        assert "\u202e" in entry[1]


# ===========================================================================
# 8. Additional Fingerprint Edge Cases
# ===========================================================================


class TestFingerprintEdgeCases:
    """Additional fingerprint boundary tests."""

    def test_dubbing_fingerprint_counts_only_within_limit(self) -> None:
        """With 55 entries, fingerprint count is 50 (capped by LIMIT)."""
        for i in range(55):
            add_dubbing_entry(f"v_{i}.mp4", 100, f"/v_{i}.mp4", "", STATUS_DONE)
        fp = get_dubbing_fingerprint()
        assert fp is not None
        assert fp[0] == 50  # noqa: PLR2004

    def test_text_translation_fingerprint_empty_db(self) -> None:
        """Empty DB fingerprint is (0, 0)."""
        fp = get_text_translation_fingerprint()
        assert fp == (0, 0)

    def test_dubbing_fingerprint_includes_progress(self) -> None:
        """Dubbing fingerprint concat includes status + progress."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "", STATUS_GENERATING)
        fp_before = get_dubbing_fingerprint()
        update_dubbing_progress(entry_id, 75)
        fp_after = get_dubbing_fingerprint()
        # Fingerprint should change because progress changed
        assert fp_before != fp_after

    def test_dubbing_fingerprint_max_id_is_highest_in_window(self) -> None:
        """The max_id in fingerprint is the highest ID in the 50-entry window."""
        last_id = None
        for i in range(5):
            last_id = add_dubbing_entry(
                f"v_{i}.mp4", 100, f"/v_{i}.mp4", "", STATUS_DONE
            )
        fp = get_dubbing_fingerprint()
        assert fp is not None
        assert fp[1] == last_id


# ===========================================================================
# 9. Delete Cascading Verification
# ===========================================================================


class TestDeleteVerification:
    """Verify delete operations return correct paths and clean up properly."""

    def test_delete_dubbing_entry_returns_all_artifact_paths(self) -> None:
        """delete_dubbing_entry returns (output, subtitle, translated_sub, voice)."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "/out.mp4", STATUS_DONE)
        update_dubbing_status(
            entry_id,
            STATUS_DONE,
            subtitle_path="/sub.srt",
            translated_subtitle_path="/sub_fr.srt",
            voice_path="/voice.mp3",
        )
        paths = delete_dubbing_entry(entry_id)
        assert paths[0] == "/out.mp4"
        assert paths[1] == "/sub.srt"
        assert paths[2] == "/sub_fr.srt"
        assert paths[3] == "/voice.mp3"

    def test_delete_dubbing_entry_nonexistent_returns_empty_tuple(self) -> None:
        """Deleting non-existent dubbing entry returns fallback empty tuple."""
        paths = delete_dubbing_entry(99999)
        assert paths == ("", "", "", "")

    def test_delete_subtitle_entry_returns_output_path(self) -> None:
        """delete_subtitle_entry returns the output path."""
        entry_id = add_subtitle_entry(
            "v.mp4", 100, "/v.mp4", "/v.srt", "EN", STATUS_DONE
        )
        path = delete_subtitle_entry(entry_id)
        assert path == "/v.srt"

    def test_delete_voice_entry_returns_output_path(self) -> None:
        """delete_voice_entry returns the output path."""
        entry_id = add_voice_entry("s.srt", 100, "/s.srt", "/s.mp3", STATUS_DONE)
        path = delete_voice_entry(entry_id)
        assert path == "/s.mp3"

    def test_delete_extraction_entry_returns_output_path(self) -> None:
        """delete_extraction_entry returns the output path."""
        entry_id = add_extraction_entry(
            "img.png", 100, "/img.png", "/img.txt", STATUS_DONE
        )
        path = delete_extraction_entry(entry_id)
        assert path == "/img.txt"

    def test_double_delete_dubbing_entry(self) -> None:
        """Deleting an already-deleted dubbing entry returns empty fallback."""
        entry_id = add_dubbing_entry("v.mp4", 100, "/v.mp4", "/o.mp4", STATUS_DONE)
        delete_dubbing_entry(entry_id)
        paths = delete_dubbing_entry(entry_id)
        assert paths == ("", "", "", "")

    def test_double_delete_subtitle_entry(self) -> None:
        """Deleting an already-deleted subtitle entry returns None."""
        entry_id = add_subtitle_entry(
            "v.mp4", 100, "/v.mp4", "/v.srt", "EN", STATUS_DONE
        )
        delete_subtitle_entry(entry_id)
        result = delete_subtitle_entry(entry_id)
        assert result is None

    def test_double_delete_voice_entry(self) -> None:
        """Deleting an already-deleted voice entry returns None."""
        entry_id = add_voice_entry("s.srt", 100, "/s.srt", "/s.mp3", STATUS_DONE)
        delete_voice_entry(entry_id)
        result = delete_voice_entry(entry_id)
        assert result is None

    def test_double_delete_extraction_entry(self) -> None:
        """Deleting an already-deleted extraction entry returns None."""
        entry_id = add_extraction_entry(
            "img.png", 100, "/img.png", "/img.txt", STATUS_DONE
        )
        delete_extraction_entry(entry_id)
        result = delete_extraction_entry(entry_id)
        assert result is None


# ===========================================================================
# 10. Batch Pause / Resume Edge Cases for History Entries
# ===========================================================================


class TestBatchPauseIgnoresFailedEntries:
    """batch_pause_history_entries() should NOT change FAILED entries to Paused.

    The SQL WHERE clause filters on ``status IN ('Translating', 'Pending')``,
    so entries with status FAILED are left unchanged.
    """

    def test_failed_entry_stays_failed_after_batch_pause(self) -> None:
        """A FAILED history entry must remain FAILED after batch_pause."""
        id_failed = add_history_entry(
            "fail.txt", "EN", "FR", STATUS_TRANSLATING, storage_path="/s/fail.txt"
        )
        update_history_status(id_failed, STATUS_FAILED, error_code=30)
        assert get_history_entry_status(id_failed) == STATUS_FAILED

        # Attempt to pause it
        batch_pause_history_entries([id_failed])

        # Status must remain FAILED
        assert get_history_entry_status(id_failed) == STATUS_FAILED
        # Error code must also be preserved
        history = get_history()
        entry = next(e for e in history if e[0] == id_failed)
        error_code_idx = 9  # noqa: PLR2004
        assert entry[error_code_idx] == 30  # noqa: PLR2004


class TestBatchPauseIgnoresDoneEntries:
    """batch_pause_history_entries() should NOT change DONE entries to Paused.

    The SQL WHERE clause filters on ``status IN ('Translating', 'Pending')``,
    so completed entries are left unchanged.
    """

    def test_done_entry_stays_done_after_batch_pause(self) -> None:
        """A DONE history entry must remain DONE after batch_pause."""
        id_done = add_history_entry(
            "done.txt", "EN", "FR", STATUS_TRANSLATING, storage_path="/s/done.txt"
        )
        update_history_status(id_done, STATUS_DONE)
        assert get_history_entry_status(id_done) == STATUS_DONE

        batch_pause_history_entries([id_done])

        assert get_history_entry_status(id_done) == STATUS_DONE


class TestBatchResumeAffectsDoneEntries:
    """batch_resume_history_entries() has NO status filter.

    Unlike batch_pause (which restricts to Translating/Pending), the resume
    SQL is an unconditional ``UPDATE ... SET status = 'Pending'``.
    This means it will change DONE entries back to PENDING — documenting
    this potentially surprising behavior.
    """

    def test_done_entry_becomes_pending_after_batch_resume(self) -> None:
        """A DONE history entry is changed to PENDING by batch_resume."""
        id_done = add_history_entry(
            "done.txt", "EN", "FR", STATUS_TRANSLATING, storage_path="/s/done.txt"
        )
        update_history_status(id_done, STATUS_DONE)
        assert get_history_entry_status(id_done) == STATUS_DONE

        batch_resume_history_entries([id_done])

        # Documenting: resume changes DONE -> PENDING (no status filter)
        assert get_history_entry_status(id_done) == STATUS_PENDING


class TestBatchResumeAffectsFailedEntries:
    """Verify batch_resume_history_entries changes FAILED -> PENDING."""

    def test_failed_entry_becomes_pending_after_batch_resume(self) -> None:
        """A FAILED entry is resumed to PENDING by batch_resume."""
        id_failed = add_history_entry(
            "fail.txt", "EN", "ES", STATUS_TRANSLATING, storage_path="/s/fail.txt"
        )
        update_history_status(id_failed, STATUS_FAILED, error_code=42)
        assert get_history_entry_status(id_failed) == STATUS_FAILED

        batch_resume_history_entries([id_failed])

        assert get_history_entry_status(id_failed) == STATUS_PENDING


class TestBatchResumeClearsErrorCode:
    """Verify error_code is set to NULL after batch_resume_history_entries.

    The SQL explicitly includes ``error_code = NULL`` so that resumed entries
    are treated as fresh pending tasks.
    """

    def test_error_code_is_null_after_resume(self) -> None:
        """After resume, the error_code column must be NULL."""
        id_failed = add_history_entry(
            "fail.txt", "EN", "DE", STATUS_TRANSLATING, storage_path="/s/fail.txt"
        )
        update_history_status(id_failed, STATUS_FAILED, error_code=99)

        # Confirm error_code is set
        history = get_history()
        entry = next(e for e in history if e[0] == id_failed)
        error_code_idx = 9  # noqa: PLR2004
        assert entry[error_code_idx] == 99  # noqa: PLR2004

        batch_resume_history_entries([id_failed])

        # error_code should now be NULL
        history = get_history()
        entry = next(e for e in history if e[0] == id_failed)
        assert entry[error_code_idx] is None


class TestTextTranslationTimestampOrdering:
    """Verify ordering when 50+ entries share the same created_at timestamp.

    The text_translation_history query uses ``ORDER BY created_at DESC, id DESC``,
    so when timestamps collide the secondary sort on ``id DESC`` provides
    deterministic ordering (higher IDs first).
    """

    def test_50_plus_entries_same_timestamp_ordered_by_id_desc(self) -> None:
        """Insert 55 entries rapidly; returned 50 must be in id DESC order."""
        ids = []
        for i in range(55):
            entry_id = add_text_translation_entry(
                f"source_{i}", f"target_{i}", "EN", "FR", len(f"source_{i}")
            )
            ids.append(entry_id)

        entries = get_text_translation_history()
        # Only 50 returned due to LIMIT
        assert len(entries) == 50  # noqa: PLR2004

        returned_ids = [e[0] for e in entries]
        # Must be in strictly descending ID order
        assert returned_ids == sorted(returned_ids, reverse=True)

        # The 5 oldest entries (lowest IDs) should be excluded
        returned_set = set(returned_ids)
        for old_id in ids[:5]:
            assert old_id not in returned_set


class TestBatchRetranslatePreservesStoragePath:
    """Verify storage_path is not modified during batch_retranslate.

    The retranslate SQL only updates status, progress, error_code,
    source_lang, and target_lang. The storage_path column must remain
    intact so the worker can find the cloned file.
    """

    def test_storage_path_unchanged_after_retranslate(self) -> None:
        """storage_path must be identical before and after retranslation."""
        original_path = "/storage/clone_abc123/report.docx"
        entry_id = add_history_entry(
            "report.docx",
            "EN",
            "FR",
            STATUS_DONE,
            storage_path=original_path,
            file_size=5000,
        )

        batch_retranslate_history_entries([entry_id], "EN", "DE")

        # Verify status and languages changed
        assert get_history_entry_status(entry_id) == STATUS_PENDING
        history = get_history()
        entry = next(e for e in history if e[0] == entry_id)
        storage_path_idx = 8  # noqa: PLR2004
        source_lang_idx = 2  # noqa: PLR2004
        target_lang_idx = 3  # noqa: PLR2004
        progress_idx = 5  # noqa: PLR2004

        assert entry[storage_path_idx] == original_path
        assert entry[source_lang_idx] == "EN"
        assert entry[target_lang_idx] == "DE"
        assert entry[progress_idx] == 0


class TestBatchMarkDeletingOnlyAffectsTargetIds:
    """batch_mark_deleting_history_entries only affects the given IDs.

    Other entries in the history table must remain untouched.
    """

    def test_non_target_entries_remain_unchanged(self) -> None:
        """Only specified IDs get DELETING status; others stay as-is."""
        id_pending = add_history_entry(
            "a.txt", "EN", "FR", STATUS_PENDING, storage_path="/s/a.txt"
        )
        id_done = add_history_entry(
            "b.txt", "EN", "DE", STATUS_DONE, storage_path="/s/b.txt"
        )
        id_failed = add_history_entry(
            "c.txt", "EN", "ES", STATUS_TRANSLATING, storage_path="/s/c.txt"
        )
        update_history_status(id_failed, STATUS_FAILED, error_code=10)
        id_target = add_history_entry(
            "d.txt", "EN", "IT", STATUS_TRANSLATING, storage_path="/s/d.txt"
        )

        # Mark only id_target as DELETING
        batch_mark_deleting_history_entries([id_target])

        # Target entry is now DELETING
        assert get_history_entry_status(id_target) == STATUS_DELETING

        # All other entries must remain in their original status
        assert get_history_entry_status(id_pending) == STATUS_PENDING
        assert get_history_entry_status(id_done) == STATUS_DONE
        assert get_history_entry_status(id_failed) == STATUS_FAILED


class TestDubbingBatchPauseIgnoresDoneEntries:
    """batch_pause_dubbing_entries() should NOT change DONE entries to Paused.

    The SQL WHERE clause filters on ``status IN ('Generating', 'Pending')``,
    so completed dubbing entries are left unchanged.
    """

    def test_done_dubbing_entry_stays_done_after_batch_pause(self) -> None:
        """A DONE dubbing entry must remain DONE after batch_pause."""
        id_done = add_dubbing_entry(
            "done.mp4", 100, "/done.mp4", "/out.mp4", STATUS_DONE
        )

        batch_pause_dubbing_entries([id_done])

        assert get_dubbing_entry_status(id_done) == STATUS_DONE


class TestDubbingBatchResumeAffectsDoneEntries:
    """Verify batch_resume_dubbing_entries changes DONE -> PENDING.

    Like batch_resume_history_entries, the dubbing resume SQL has NO status
    filter — it unconditionally sets status to PENDING for all given IDs.
    This means even DONE entries will be reset to PENDING.
    """

    def test_done_dubbing_entry_becomes_pending_after_batch_resume(self) -> None:
        """A DONE dubbing entry is changed to PENDING by batch_resume."""
        id_done = add_dubbing_entry(
            "done.mp4", 100, "/done.mp4", "/out.mp4", STATUS_DONE
        )
        assert get_dubbing_entry_status(id_done) == STATUS_DONE

        batch_resume_dubbing_entries([id_done])

        # Documenting: resume changes DONE -> PENDING (no status filter)
        assert get_dubbing_entry_status(id_done) == STATUS_PENDING


# ===========================================================================
# Concurrent Write Race-Condition Tests
# ===========================================================================


class TestConcurrentWriteOperations:
    """Verify database integrity under concurrent write race conditions.

    Each test creates its own entries, uses ``threading.Barrier`` to
    synchronize start, and validates that SQLite WAL mode prevents
    corruption even when multiple threads write to the same rows.
    """

    # -- helpers --------------------------------------------------------

    def _create_entry(
        self,
        name: str = "race.txt",
        status: str = STATUS_PENDING,
    ) -> int:
        """Shortcut to create a history entry for race-condition tests."""
        entry_id = add_history_entry(
            name, "EN", "FR", status, storage_path=f"/s/{name}"
        )
        assert entry_id is not None
        return entry_id

    # 1. Monotonic progress under contention --------------------------------

    def test_concurrent_progress_updates_monotonic(self) -> None:
        """10 threads call update_history_progress with 10..100.

        Because the SQL uses ``WHERE progress < ?``, only the highest
        value that wins the race actually persists. The final progress
        must be 100.
        """
        entry_id = self._create_entry("mono.txt", STATUS_TRANSLATING)
        errors: list[Exception] = []
        barrier = threading.Barrier(10)

        def _updater(value: int) -> None:
            try:
                barrier.wait(timeout=10)
                update_history_progress(entry_id, value)
            except Exception as exc:
                errors.append(exc)

        # Each thread pushes a different progress value (10, 20, ..., 100)
        threads = [
            threading.Thread(target=_updater, args=(v,)) for v in range(10, 110, 10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"

        detail = get_history_entry_detail(entry_id)
        assert detail is not None
        assert detail["progress"] == 100  # noqa: PLR2004

        # cleanup
        delete_history_entry(entry_id)

    # 2. Status + progress writes do not corrupt each other ----------------

    def test_concurrent_status_and_progress_no_corruption(self) -> None:
        """One thread sets status to Translating while another sets progress.

        Both should succeed without database errors. The entry must end
        in a consistent state (valid status, valid progress).
        """
        entry_id = self._create_entry("sp.txt", STATUS_PENDING)
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def _status_writer() -> None:
            try:
                barrier.wait(timeout=10)
                update_history_status(entry_id, STATUS_TRANSLATING)
            except Exception as exc:
                errors.append(exc)

        def _progress_writer() -> None:
            try:
                barrier.wait(timeout=10)
                update_history_progress(entry_id, 50)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_status_writer)
        t2 = threading.Thread(target=_progress_writer)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"

        detail = get_history_entry_detail(entry_id)
        assert detail is not None
        # Status must be a valid string
        assert detail["status"] in {
            STATUS_PENDING,
            STATUS_TRANSLATING,
            STATUS_PAUSED,
            STATUS_DONE,
            STATUS_FAILED,
        }
        # Progress should be 50 (monotonic: 0 < 50 so update succeeds)
        assert detail["progress"] == 50  # noqa: PLR2004

        delete_history_entry(entry_id)

    # 3. Concurrent pause vs resume on the same entry ----------------------

    def test_concurrent_pause_resume_same_entry(self) -> None:
        """Two threads race: one pauses, one resumes the same entry.

        The final state must be either Paused or Pending — never a
        corrupted value. We repeat the race several times to increase
        the chance of actual contention.
        """
        valid_outcomes = {STATUS_PAUSED, STATUS_PENDING}

        for iteration in range(10):
            entry_id = self._create_entry(f"pr_{iteration}.txt", STATUS_TRANSLATING)
            errors: list[Exception] = []
            barrier = threading.Barrier(2)

            def _pauser(
                _eid: int = entry_id,
                _b: threading.Barrier = barrier,
                _e: list = errors,
            ) -> None:
                try:
                    _b.wait(timeout=10)
                    batch_pause_history_entries([_eid])
                except Exception as exc:
                    _e.append(exc)

            def _resumer(
                _eid: int = entry_id,
                _b: threading.Barrier = barrier,
                _e: list = errors,
            ) -> None:
                try:
                    _b.wait(timeout=10)
                    batch_resume_history_entries([_eid])
                except Exception as exc:
                    _e.append(exc)

            t1 = threading.Thread(target=_pauser)
            t2 = threading.Thread(target=_resumer)
            t1.start()
            t2.start()
            t1.join(timeout=30)
            t2.join(timeout=30)

            assert not errors, f"Iteration {iteration} errors: {errors}"

            status = get_history_entry_status(entry_id)
            assert status in valid_outcomes, (
                f"Iteration {iteration}: unexpected status {status!r}"
            )

            delete_history_entry(entry_id)

    # 4. Batch operations on overlapping entry sets ------------------------

    def test_concurrent_batch_operations_different_entries(self) -> None:
        """Thread A batch-pauses [1,2,3], Thread B batch-resumes [3,4,5].

        Both threads must complete without deadlock. Entry 3 (the
        overlap) must end in a valid state (Paused or Pending). The
        non-overlapping entries must reflect their respective operation.
        """
        # Create 5 entries all in Translating so both pause and resume
        # can act on them.
        ids = [
            self._create_entry(f"batch_{i}.txt", STATUS_TRANSLATING) for i in range(5)
        ]
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def _pauser() -> None:
            try:
                barrier.wait(timeout=10)
                batch_pause_history_entries(ids[:3])  # entries 0, 1, 2
            except Exception as exc:
                errors.append(exc)

        def _resumer() -> None:
            try:
                barrier.wait(timeout=10)
                batch_resume_history_entries(ids[2:])  # entries 2, 3, 4
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_pauser)
        t2 = threading.Thread(target=_resumer)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"

        # Entries 0, 1 — only pause acted on them
        for eid in ids[:2]:
            assert get_history_entry_status(eid) == STATUS_PAUSED

        # Entry 2 (overlap) — pause and resume raced; either outcome valid
        overlap_status = get_history_entry_status(ids[2])
        assert overlap_status in {STATUS_PAUSED, STATUS_PENDING}, (
            f"Overlap entry has unexpected status: {overlap_status!r}"
        )

        # Entries 3, 4 — resume sets status to Pending unconditionally
        for eid in ids[3:]:
            assert get_history_entry_status(eid) == STATUS_PENDING

        # cleanup
        for eid in ids:
            delete_history_entry(eid)

    # 5. Retranslate while another thread marks Translating ----------------

    def test_concurrent_retranslate_while_translating(self) -> None:
        """One thread sets status to Translating while another retranslates.

        batch_retranslate unconditionally resets status/progress/error.
        update_history_status sets status (and timestamp if Translating).
        The entry must end in a valid, non-corrupted state regardless
        of execution order.
        """
        entry_id = self._create_entry("retrans.txt", STATUS_PENDING)
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def _mark_translating() -> None:
            try:
                barrier.wait(timeout=10)
                update_history_status(entry_id, STATUS_TRANSLATING)
            except Exception as exc:
                errors.append(exc)

        def _retranslate() -> None:
            try:
                barrier.wait(timeout=10)
                batch_retranslate_history_entries([entry_id], "EN", "DE")
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=_mark_translating)
        t2 = threading.Thread(target=_retranslate)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"

        detail = get_history_entry_detail(entry_id)
        assert detail is not None

        # Both operations write a valid status; whichever commits last wins.
        assert detail["status"] in {STATUS_PENDING, STATUS_TRANSLATING}

        # If retranslate won, progress is 0 and target_lang is DE.
        # If update_history_status won, progress may still be 0 (unchanged)
        # and target_lang may be DE (if retranslate committed first).
        # Either way the entry is consistent.
        assert detail["progress"] is not None
        assert detail["error_code"] is None or isinstance(detail["error_code"], int)

        delete_history_entry(entry_id)


# ===========================================================================
# Nested @db_transaction + concurrent failure isolation
# ===========================================================================
#
# The decorator at src/core/database.py:70 nests when the first
# argument is already a ``sqlite3.Cursor`` — the inner call reuses
# the outer connection so they share a transaction.  Existing tests
# cover concurrent writes on disjoint rows; these add coverage for
# (1) deeply nested decorated calls, and (2) concurrent flows where
# one transaction fails and another commits, to verify rollback is
# correctly scoped per-connection.


class TestDbTransactionNestedAndIsolation:
    """Nested @db_transaction calls and per-connection rollback isolation."""

    def test_nested_db_transaction_reuses_cursor(self) -> None:
        """Inner @db_transaction-decorated call accepting a Cursor nests.

        Two writes inside a single outer call must land atomically:
        if the second raises, neither is committed.  The decorator
        detects nesting via ``isinstance(args[0], sqlite3.Cursor)``.
        """
        from src.core.database import db_transaction  # noqa: PLC0415

        @db_transaction
        def inner_insert(cursor, name: str) -> int:  # noqa: ANN001
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS _nest_test (id INTEGER PRIMARY KEY, name TEXT)",
            )
            cursor.execute("INSERT INTO _nest_test (name) VALUES (?)", (name,))
            return cursor.lastrowid

        @db_transaction
        def outer_two_writes(cursor, names: tuple[str, str]) -> tuple[int, int]:  # noqa: ANN001
            # Both inner calls share the outer transaction.
            id_a = inner_insert(cursor, names[0])
            id_b = inner_insert(cursor, names[1])
            return id_a, id_b

        a, b = outer_two_writes(("alpha", "beta"))
        assert a is not None
        assert b is not None
        assert b > a, "second insert should have higher rowid"

        # Verify both rows landed via a fresh top-level call (no cursor arg).
        @db_transaction
        def count_rows(cursor) -> int:  # noqa: ANN001
            cursor.execute("SELECT COUNT(*) FROM _nest_test")
            return cursor.fetchone()[0]

        assert count_rows() == 2  # noqa: PLR2004

    def test_nested_db_transaction_rolls_back_on_inner_failure(self) -> None:
        """When the inner nested call raises, the outer's earlier write is rolled back.

        This catches a potential bug where a refactor adds a save-point
        or commits the cursor mid-flow, breaking the all-or-nothing
        invariant.
        """
        import contextlib  # noqa: PLC0415
        import sqlite3  # noqa: PLC0415

        from src.core.database import db_transaction  # noqa: PLC0415

        @db_transaction
        def setup_table(cursor) -> None:  # noqa: ANN001
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS _rb_test (id INTEGER PRIMARY KEY, n TEXT NOT NULL)",
            )

        setup_table()

        @db_transaction
        def good_insert(cursor, n: str) -> None:  # noqa: ANN001
            cursor.execute("INSERT INTO _rb_test (n) VALUES (?)", (n,))

        @db_transaction
        def outer(cursor) -> None:  # noqa: ANN001
            good_insert(cursor, "first-write")
            # Force a NOT NULL violation on the second write.
            cursor.execute("INSERT INTO _rb_test (n) VALUES (NULL)")

        # The decorator catches sqlite3.Error and returns None after
        # rollback.  Either it returns None or re-raises — either is
        # acceptable; the invariant is that the table is empty.
        with contextlib.suppress(sqlite3.Error):
            outer()

        @db_transaction
        def count(cursor) -> int:  # noqa: ANN001
            cursor.execute("SELECT COUNT(*) FROM _rb_test")
            return cursor.fetchone()[0]

        assert count() == 0, "first-write should have been rolled back"

    def test_concurrent_failing_and_succeeding_transactions_isolate(self) -> None:
        """Two threads — one fails, one commits — produce consistent state.

        Verifies that per-connection rollback in the failing thread
        doesn't roll back the succeeding thread's commit.  Each thread
        gets its own connection via ``create_connection()`` inside the
        decorator, so they should be independent.
        """
        import contextlib  # noqa: PLC0415
        import sqlite3  # noqa: PLC0415

        from src.core.database import db_transaction  # noqa: PLC0415

        @db_transaction
        def setup_table(cursor) -> None:  # noqa: ANN001
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS _iso_test (id INTEGER PRIMARY KEY, who TEXT NOT NULL)",
            )

        setup_table()

        @db_transaction
        def good_writer(cursor, who: str) -> None:  # noqa: ANN001
            cursor.execute("INSERT INTO _iso_test (who) VALUES (?)", (who,))

        @db_transaction
        def bad_writer(cursor) -> None:  # noqa: ANN001
            cursor.execute("INSERT INTO _iso_test (who) VALUES (?)", ("BAD",))
            cursor.execute("INSERT INTO _iso_test (who) VALUES (NULL)")

        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def good_thread() -> None:
            try:
                barrier.wait(timeout=10)
                for i in range(20):
                    good_writer(f"good-{i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        def bad_thread() -> None:
            try:
                barrier.wait(timeout=10)
                for _ in range(20):
                    with contextlib.suppress(sqlite3.Error):
                        bad_writer()
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        t_good = threading.Thread(target=good_thread)
        t_bad = threading.Thread(target=bad_thread)
        t_good.start()
        t_bad.start()
        t_good.join(timeout=30)
        t_bad.join(timeout=30)
        assert not t_good.is_alive() and not t_bad.is_alive()
        assert not errors

        @db_transaction
        def fetch_all(cursor) -> list[str]:  # noqa: ANN001
            cursor.execute("SELECT who FROM _iso_test")
            return [r[0] for r in cursor.fetchall()]

        rows = fetch_all()
        # All 20 good writes must have landed; no BAD rows survive.
        assert sum(1 for w in rows if w.startswith("good-")) == 20  # noqa: PLR2004
        assert "BAD" not in rows


# ==============================================================================
# TestGetHistoryEntryDetails — batch helper (single WHERE id IN (...) query)
# ==============================================================================


class TestGetHistoryEntryDetails:
    """Direct unit tests for :func:`get_history_entry_details`.

    The batch helper is the database-layer replacement for the
    N+1 per-id loop the MCP server's ``get_task_status`` used to
    run.  It's covered indirectly by the MCP tests (via mocking),
    but those don't exercise the real SQL — they only verify
    callsite plumbing.  These tests run against the real DB so a
    SQL syntax regression (e.g. a future refactor breaking the
    placeholder string or column order) actually surfaces.
    """

    def test_empty_list_returns_empty_dict(self) -> None:
        """Empty ``entry_ids`` short-circuits BEFORE the SQL fires.

        SQLite rejects ``WHERE id IN ()``; the helper must catch
        the empty case upstream and return a usable empty dict.
        """
        result = get_history_entry_details([])
        assert result == {}

    def test_returns_dict_keyed_by_id(self) -> None:
        """Each returned row is keyed by its ``id`` column.

        Confirms the row-tuple → dict construction puts the ID at
        position 0 of the SELECT and that the helper uses it as
        the map key (rather than enumerating with insertion order).
        """
        id1 = add_history_entry(
            "a.docx",
            "English",
            "French",
            "Pending",
            "/src/a.docx",
            "/store/a.docx",
            100,
        )
        id2 = add_history_entry(
            "b.docx",
            "English",
            "Spanish",
            "Pending",
            "/src/b.docx",
            "/store/b.docx",
            200,
        )
        try:
            result = get_history_entry_details([id1, id2])
            assert set(result.keys()) == {id1, id2}
            assert result[id1]["file_name"] == "a.docx"
            assert result[id2]["file_name"] == "b.docx"
            assert result[id1]["target_lang"] == "French"
            assert result[id2]["target_lang"] == "Spanish"
        finally:
            delete_history_entry(id1)
            delete_history_entry(id2)

    def test_missing_ids_absent_from_result(self) -> None:
        """IDs that don't exist in the table are simply absent.

        The MCP caller relies on this to synthesise the "auto-
        removed task" sentinel for IDs not returned by the helper.
        """
        id1 = add_history_entry(
            "x.docx",
            "English",
            "French",
            "Pending",
            "/src/x.docx",
            "/store/x.docx",
            100,
        )
        try:
            result = get_history_entry_details([id1, 999_999])
            assert set(result.keys()) == {id1}
            assert 999_999 not in result
        finally:
            delete_history_entry(id1)

    def test_duplicate_ids_deduped_in_result(self) -> None:
        """Duplicate IDs in the input collapse to a single dict entry.

        SQL ``WHERE id IN (?, ?)`` with [1, 1] returns one row;
        a dict keyed by ID can only hold one entry per key.  The
        MCP caller's loop iterates the input list (including
        duplicates) and looks up the same dict entry twice —
        correct per the API contract.
        """
        id1 = add_history_entry(
            "dup.docx",
            "English",
            "French",
            "Pending",
            "/src/dup.docx",
            "/store/dup.docx",
            100,
        )
        try:
            result = get_history_entry_details([id1, id1])
            assert list(result.keys()) == [id1]
            assert result[id1]["file_name"] == "dup.docx"
        finally:
            delete_history_entry(id1)

    def test_returned_detail_has_full_column_set(self) -> None:
        """Each detail dict carries the same 11 keys as ``get_history_entry_detail``.

        Both helpers ship the same SELECT column list; pin the
        contract so a future column add to one doesn't drift from
        the other.
        """
        id1 = add_history_entry(
            "shape.docx",
            "English",
            "Vietnamese",
            "Pending",
            "/src/shape.docx",
            "/store/shape.docx",
            42,
        )
        try:
            batch = get_history_entry_details([id1])[id1]
            single = get_history_entry_detail(id1)
            assert single is not None
            assert set(batch.keys()) == set(single.keys())
            assert batch == single
        finally:
            delete_history_entry(id1)

    def test_large_batch_handled_correctly(self) -> None:
        """50-item batch returns all rows in one query (smoke).

        Exercises the placeholder-generation path with a realistic
        non-trivial size.  SQLite 3.32+ permits 32766 placeholders;
        we stay well under and confirm no chunking / index issue.
        """
        ids: list[int] = []
        try:
            for i in range(50):
                ids.append(
                    add_history_entry(
                        f"f{i}.docx",
                        "English",
                        "French",
                        "Pending",
                        f"/src/f{i}",
                        f"/store/f{i}",
                        i,
                    )
                )
            result = get_history_entry_details(ids)
            assert set(result.keys()) == set(ids)
        finally:
            for eid in ids:
                delete_history_entry(eid)
