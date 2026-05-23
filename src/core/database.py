"""Core database functionality for the AI Translate application."""

import contextlib
import logging
import os
import sqlite3
from collections.abc import Callable
from typing import Any

from src.constants import (
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_TRANSLATING,
    UNFINISHED_STATUSES,
)
from src.constants.history import (
    STATUS_DELETING,
    STATUS_EXTRACTING,
    STATUS_FAILED,
    STATUS_GENERATING,
)
from src.utils import path_manager as _path_manager

logger = logging.getLogger("database")

# SQLite connection timeout (seconds) to handle concurrent access / WAL locks
_DB_TIMEOUT = 15

# Maximum number of history rows returned per query
_DB_HISTORY_PAGE_SIZE = 50


def get_db_path() -> str:
    """Returns the full path to the SQLite database file.

    Returns:
        str: Path to the database file.
    """
    # Safeguard: Prevent tests from touching production data
    if "PYTEST_CURRENT_TEST" in os.environ:
        path = str(_path_manager.get_app_data_dir() / "translator.db")
        # Check if the path resolves to a user data directory
        prod_markers = (".local/share", "AppData", "Library/Application Support")
        if any(m in path for m in prod_markers):
            raise RuntimeError(
                f"FATAL: Attempted to access production database during test: {path}"
            )

    return str(_path_manager.get_app_data_dir() / "translator.db")


def create_connection() -> sqlite3.Connection | None:
    """Creates a database connection to the SQLite database.

    Returns:
        Optional[sqlite3.Connection]: Connection object or None.
    """
    try:
        # Increase timeout to handle potential locks during crashes or concurrent access
        conn = sqlite3.connect(get_db_path(), timeout=_DB_TIMEOUT)
        conn.execute("PRAGMA foreign_keys = ON")  # Enable FK support
        # Enable WAL mode for better crash resilience and concurrent performance
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    except sqlite3.Error as e:
        logger.error("Error connecting to database: %s", e)
    return None


def db_transaction(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to handle database connections and transactions.

    If the first argument is already a sqlite3.Cursor, it uses it without
    creating a new connection, allowing for nested calls or shared transactions.

    Args:
        func: The database operation function to wrap.

    Returns:
        Callable: The wrapped function.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Execute *func* inside a database transaction."""
        # Check if we are already in a transaction (cursor passed as first arg)
        if args and isinstance(args[0], sqlite3.Cursor):
            return func(*args, **kwargs)

        conn = create_connection()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            result = func(cursor, *args, **kwargs)
            conn.commit()
            return result
        except sqlite3.Error as e:
            logger.error("Database error in %s: %s", func.__name__, e)
            conn.rollback()
            return None
        finally:
            conn.close()

    return wrapper


@db_transaction
def init_db(cursor: sqlite3.Cursor) -> None:
    """Initializes the database tables if they do not exist."""
    # Using executescript for atomic schema initialization
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            source_path TEXT,
            storage_path TEXT,
            source_lang TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            error_code INTEGER,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS glossary_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS glossary_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER NOT NULL,
            source_text TEXT NOT NULL,
            target_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (set_id) REFERENCES glossary_sets(id) ON DELETE CASCADE
        );
    """)
    # Migration: add is_active if it doesn't exist (e.g. for existing databases)
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute(
            "ALTER TABLE glossary_sets ADD COLUMN is_active INTEGER DEFAULT 0"
        )
    # Migration: add progress if it doesn't exist
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute("ALTER TABLE history ADD COLUMN progress INTEGER DEFAULT 0")
    # Migration: add source_path if it doesn't exist
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute("ALTER TABLE history ADD COLUMN source_path TEXT")
    # Migration: add storage_path if it doesn't exist
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute("ALTER TABLE history ADD COLUMN storage_path TEXT")
    # Migration: add file_size if it doesn't exist
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute("ALTER TABLE history ADD COLUMN file_size INTEGER DEFAULT 0")
    # Migration: add source_lang if it doesn't exist
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute("ALTER TABLE history ADD COLUMN source_lang TEXT DEFAULT ''")
    # Migration: add error_code if it doesn't exist
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute("ALTER TABLE history ADD COLUMN error_code INTEGER")
    # Migration: add error_message if it doesn't exist.  Preserves
    # the raw error tag string (including ``AUTH_ERROR:Service``
    # suffix) so the UI can render service-specific copy
    # ("Invalid Google Cloud API key") instead of the generic
    # message derived from the numeric error_code alone.  Other
    # history tables (extraction/subtitle/voice/dubbing) already
    # have this column — this brings the Translate Document
    # ``history`` table into parity.
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute("ALTER TABLE history ADD COLUMN error_message TEXT")

    # Performance indexes
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at DESC)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON history(status)")

    # Extraction history (OCR text extraction results)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extraction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            source_path TEXT,
            output_path TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_extraction_created_at"
        " ON extraction_history(created_at DESC)"
    )

    # Subtitle history (speech-to-text subtitle generation)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subtitle_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            source_path TEXT,
            output_path TEXT,
            src_lang TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_subtitle_created_at"
        " ON subtitle_history(created_at DESC)"
    )

    # Voice history (text-to-speech voice generation)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            source_path TEXT,
            output_path TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_created_at"
        " ON voice_history(created_at DESC)"
    )

    # Dubbing history (full pipeline: STT → translate → TTS → mix)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dubbing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            source_path TEXT,
            output_path TEXT,
            src_lang TEXT DEFAULT '',
            target_lang TEXT DEFAULT '',
            status TEXT NOT NULL,
            progress TEXT DEFAULT '',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_dubbing_created_at"
        " ON dubbing_history(created_at DESC)"
    )
    # Migration: add src_lang / target_lang to dubbing_history
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute(
            "ALTER TABLE dubbing_history ADD COLUMN src_lang TEXT DEFAULT ''"
        )
    with contextlib.suppress(sqlite3.OperationalError):
        cursor.execute(
            "ALTER TABLE dubbing_history ADD COLUMN target_lang TEXT DEFAULT ''"
        )
    # Migration: add artifact path columns to dubbing_history
    for col in ("subtitle_path", "translated_subtitle_path", "voice_path"):
        with contextlib.suppress(sqlite3.OperationalError):
            cursor.execute(
                f"ALTER TABLE dubbing_history ADD COLUMN {col} TEXT DEFAULT ''"
            )

    # Text translation history (instant text-to-text translations)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS text_translation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_text TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            src_lang TEXT DEFAULT '',
            target_lang TEXT NOT NULL,
            char_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_text_translation_created_at"
        " ON text_translation_history(created_at DESC)"
    )


# ── Translation History ──────────────────────────────────────────────────


@db_transaction
def add_history_entry(  # noqa: PLR0913
    cursor: sqlite3.Cursor,
    file_name: str,
    src: str,
    target: str,
    status: str,
    source_path: str = "",
    storage_path: str = "",
    file_size: int = 0,
) -> int:
    """Adds a new entry to the translation history and returns its ID.

    Args:
        cursor: Database cursor (injected by decorator).
        file_name: Original file name.
        src: Source language label.
        target: Target language label.
        status: Initial status string (e.g. STATUS_PENDING).
        source_path: Absolute path to the original file.
        storage_path: Path to the cloned file in app storage.
        file_size: Size of the original file in bytes.
    """
    cursor.execute(
        "INSERT INTO history"
        " (file_name, source_lang, target_lang,"
        " status, progress, source_path,"
        " storage_path, file_size)"
        " VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
        (file_name, src, target, status, source_path, storage_path, file_size),
    )
    return cursor.lastrowid


@db_transaction
def update_history_status(
    cursor: sqlite3.Cursor,
    history_id: int,
    status: str,
    error_code: int | None = None,
    error_message: str | None = None,
) -> None:
    """Updates the status of a history entry and refreshes timestamp if starting.

    ``error_message`` is the raw error tag string (e.g.
    ``"AUTH_ERROR:Gemini"``) — preserved so the UI can render
    service-specific copy via :func:`display_error_message`.  Passed
    independently from ``error_code`` (the numeric code) so the
    persisted columns stay in sync: code drives the localised
    template, message drives the ``{service}`` substitution.
    """
    if status == STATUS_TRANSLATING:
        if error_code is not None:
            cursor.execute(
                "UPDATE history SET status = ?, error_code = ?,"
                " error_message = ?, created_at = CURRENT_TIMESTAMP"
                " WHERE id = ?",
                (status, error_code, error_message, history_id),
            )
        else:
            cursor.execute(
                "UPDATE history SET status = ?,"
                " created_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, history_id),
            )
    elif error_code is not None:
        cursor.execute(
            "UPDATE history SET status = ?, error_code = ?,"
            " error_message = ? WHERE id = ?",
            (status, error_code, error_message, history_id),
        )
    else:
        cursor.execute(
            "UPDATE history SET status = ? WHERE id = ?",
            (status, history_id),
        )


@db_transaction
def update_history_progress(
    cursor: sqlite3.Cursor, history_id: int, progress: int
) -> None:
    """Updates the progress of a history entry (monotonic — never decreases)."""
    cursor.execute(
        "UPDATE history SET progress = ? WHERE id = ? AND progress < ?",
        (progress, history_id, progress),
    )


@db_transaction
def update_history_file_name(
    cursor: sqlite3.Cursor, history_id: int, file_name: str
) -> None:
    """Updates the original file_name of a history entry."""
    cursor.execute(
        "UPDATE history SET file_name = ? WHERE id = ?",
        (file_name, history_id),
    )


@db_transaction
def batch_pause_history_entries(cursor: sqlite3.Cursor, ids: list[int]) -> None:
    """Pauses multiple history entries in a single transaction."""
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    # Only entries currently Translating or Pending can be paused;
    # already-completed or failed entries are left unchanged.
    query = (
        f"UPDATE history SET status = ? WHERE id IN ({placeholders}) "
        "AND status IN (?, ?)"
    )
    cursor.execute(query, (STATUS_PAUSED, *ids, STATUS_TRANSLATING, STATUS_PENDING))


@db_transaction
def batch_resume_history_entries(cursor: sqlite3.Cursor, ids: list[int]) -> None:
    """Resumes multiple paused or failed history entries."""
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    # error_code + error_message are cleared so the entry is treated
    # as a fresh pending task — otherwise the stale error tag (with
    # ``:Service`` suffix) would survive into the next attempt and
    # the UI would show last run's failure as the current state.
    query = (
        f"UPDATE history SET status = ?, error_code = NULL,"
        f" error_message = NULL WHERE id IN ({placeholders})"
    )
    cursor.execute(query, (STATUS_PENDING, *ids))


@db_transaction
def batch_retranslate_history_entries(
    cursor: sqlite3.Cursor, ids: list[int], source_lang: str, target_lang: str
) -> None:
    """Prepares multiple history entries for retranslation."""
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    query = (
        "UPDATE history SET status = ?, progress = 0,"
        " error_code = NULL, error_message = NULL, source_lang = ?,"
        f" target_lang = ? WHERE id IN ({placeholders})"
    )
    cursor.execute(query, (STATUS_PENDING, source_lang, target_lang, *ids))


@db_transaction
def batch_mark_deleting_history_entries(
    cursor: sqlite3.Cursor,
    ids: list[int],
) -> None:
    """Marks multiple history entries as 'Deleting'."""
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    query = f"UPDATE history SET status = ? WHERE id IN ({placeholders})"
    cursor.execute(query, (STATUS_DELETING, *ids))


@db_transaction
def get_history(cursor: sqlite3.Cursor) -> list[tuple]:
    """Returns the most recent translation history.

    Tuple shape: ``(id, file_name, source_lang, target_lang, status,
    progress, created_at, file_size, storage_path, error_code,
    error_message)``.  ``error_message`` is the raw error tag string
    (may include ``:Service`` suffix) — UI passes it through
    :func:`display_error_message` for service-specific copy.
    """
    cursor.execute(
        "SELECT id, file_name, source_lang, target_lang,"
        " status, progress, created_at, file_size,"
        " storage_path, error_code, error_message"
        f" FROM history ORDER BY created_at DESC, id DESC LIMIT {_DB_HISTORY_PAGE_SIZE}"
    )
    return cursor.fetchall()


@db_transaction
def get_history_fingerprint(cursor: sqlite3.Cursor) -> tuple[int, int, str] | None:
    """Returns a lightweight fingerprint of current history state.

    Used by the UI to skip full table rebuilds when nothing has changed.
    """
    cursor.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), "
        "COALESCE(GROUP_CONCAT(status || progress || COALESCE(error_code, '')), '') "
        "FROM (SELECT id, status, progress, error_code FROM history "
        f"ORDER BY created_at DESC LIMIT {_DB_HISTORY_PAGE_SIZE})"
    )
    return cursor.fetchone()


@db_transaction
def get_history_entry_status(cursor: sqlite3.Cursor, entry_id: int) -> str | None:
    """Returns the current status of a history entry."""
    cursor.execute("SELECT status FROM history WHERE id = ?", (entry_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return None


@db_transaction
def get_history_entry_detail(
    cursor: sqlite3.Cursor, entry_id: int
) -> dict[str, Any] | None:
    """Returns a full detail dict for a history entry, or None if not found.

    Args:
        cursor: Database cursor (injected by ``@db_transaction``).
        entry_id: The history entry ID to look up.

    Returns:
        A dict with keys ``id``, ``file_name``, ``file_size``,
        ``source_path``, ``storage_path``, ``source_lang``,
        ``target_lang``, ``status``, ``progress``, ``error_code``,
        ``created_at``, or ``None`` if the entry does not exist.
    """
    cursor.execute(
        "SELECT id, file_name, file_size, source_path, storage_path,"
        " source_lang, target_lang, status, progress, error_code,"
        " error_message, created_at FROM history WHERE id = ?",
        (entry_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "file_name": row[1],
        "file_size": row[2],
        "source_path": row[3],
        "storage_path": row[4],
        "source_lang": row[5],
        "target_lang": row[6],
        "status": row[7],
        "progress": row[8],
        "error_code": row[9],
        "error_message": row[10],
        "created_at": row[11],
    }


@db_transaction
def get_history_entry_details(
    cursor: sqlite3.Cursor,
    entry_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Returns a ``{id: detail}`` map for multiple history entries.

    Batch variant of :func:`get_history_entry_detail` — a single
    ``WHERE id IN (?, ?, …)`` query replaces the per-id loop +
    round-trip pattern callers used to write.  Missing IDs are
    simply absent from the result dict; the caller decides how to
    surface "task auto-removed" status.

    Driver: the MCP server's ``get_task_status`` polls in batches
    of arbitrary size (clients can ask for every queued task at
    once), where the prior 1-query-per-id pattern was a textbook
    N+1.  Internal callers that already work with a single id
    should keep using :func:`get_history_entry_detail`.

    Returns an empty dict when *entry_ids* is empty (avoids
    generating ``WHERE id IN ()``, which SQLite rejects).
    """
    if not entry_ids:
        return {}
    placeholders = ",".join("?" * len(entry_ids))
    cursor.execute(
        f"SELECT id, file_name, file_size, source_path, storage_path,"  # noqa: S608 — placeholders are not from user input
        f" source_lang, target_lang, status, progress, error_code,"
        f" error_message, created_at FROM history WHERE id IN ({placeholders})",
        list(entry_ids),
    )
    out: dict[int, dict[str, Any]] = {}
    for row in cursor.fetchall():
        out[row[0]] = {
            "id": row[0],
            "file_name": row[1],
            "file_size": row[2],
            "source_path": row[3],
            "storage_path": row[4],
            "source_lang": row[5],
            "target_lang": row[6],
            "status": row[7],
            "progress": row[8],
            "error_code": row[9],
            "error_message": row[10],
            "created_at": row[11],
        }
    return out


@db_transaction
def delete_history_entry(cursor: sqlite3.Cursor, entry_id: int) -> str | None:
    """Deletes a history entry and returns its storage path."""
    cursor.execute("SELECT storage_path FROM history WHERE id = ?", (entry_id,))
    row = cursor.fetchone()
    path = row[0] if row else None
    cursor.execute("DELETE FROM history WHERE id = ?", (entry_id,))
    return path


@db_transaction
def is_any_translating(cursor: sqlite3.Cursor) -> bool:
    """Checks if there are any files currently in 'Translating' status."""
    cursor.execute(
        "SELECT 1 FROM history WHERE status = ? LIMIT 1", (STATUS_TRANSLATING,)
    )
    return cursor.fetchone() is not None


@db_transaction
def is_any_paused(cursor: sqlite3.Cursor) -> bool:
    """Checks if there are any files currently in 'Paused' status."""
    cursor.execute("SELECT 1 FROM history WHERE status = ? LIMIT 1", (STATUS_PAUSED,))
    return cursor.fetchone() is not None


@db_transaction
def is_any_extracting(cursor: sqlite3.Cursor) -> bool:
    """Checks if any extraction entries are currently active."""
    cursor.execute(
        "SELECT 1 FROM extraction_history WHERE status IN (?, ?) LIMIT 1",
        (STATUS_EXTRACTING, STATUS_PENDING),
    )
    return cursor.fetchone() is not None


@db_transaction
def is_any_subtitle_generating(cursor: sqlite3.Cursor) -> bool:
    """Checks if any subtitle entries are currently active."""
    cursor.execute(
        "SELECT 1 FROM subtitle_history WHERE status IN (?, ?) LIMIT 1",
        (STATUS_GENERATING, STATUS_PENDING),
    )
    return cursor.fetchone() is not None


@db_transaction
def is_any_voice_generating(cursor: sqlite3.Cursor) -> bool:
    """Checks if any voice entries are currently active."""
    cursor.execute(
        "SELECT 1 FROM voice_history WHERE status IN (?, ?) LIMIT 1",
        (STATUS_GENERATING, STATUS_PENDING),
    )
    return cursor.fetchone() is not None


@db_transaction
def is_any_dubbing_generating(cursor: sqlite3.Cursor) -> bool:
    """Checks if any dubbing entries are currently active."""
    cursor.execute(
        "SELECT 1 FROM dubbing_history WHERE status IN (?, ?) LIMIT 1",
        (STATUS_GENERATING, STATUS_PENDING),
    )
    return cursor.fetchone() is not None


@db_transaction
def get_unfinished_history(
    cursor: sqlite3.Cursor,
    statuses: tuple[str, ...] = UNFINISHED_STATUSES,
    task_ids: tuple[int, ...] | list[int] | None = None,
) -> list[tuple]:
    """Returns unfinished translation tasks filtered by status.

    Results are ordered so that 'Translating' entries come first
    (interrupted tasks should be resumed before starting new ones),
    then by ascending id for deterministic processing order.
    """
    placeholders = ", ".join("?" for _ in statuses)
    params: list[str | int] = list(statuses)
    query = (
        "SELECT id, storage_path, source_lang, target_lang, source_path"
        f" FROM history WHERE status IN ({placeholders})"
    )
    if task_ids is not None:
        if not task_ids:
            return []
        id_placeholders = ", ".join("?" for _ in task_ids)
        query += f" AND id IN ({id_placeholders})"
        params.extend(task_ids)
    query += " ORDER BY CASE status WHEN 'Translating' THEN 0 ELSE 1 END, id ASC"
    cursor.execute(query, params)
    return cursor.fetchall()


@db_transaction
def clear_history(cursor: sqlite3.Cursor) -> None:
    """Clears all translation history entries."""
    cursor.execute("DELETE FROM history")


# ── Glossary ─────────────────────────────────────────────────────────────


@db_transaction
def create_glossary_set(cursor: sqlite3.Cursor, name: str) -> bool:
    """Creates a new glossary set."""
    try:
        cursor.execute(
            "INSERT INTO glossary_sets (name, is_active) VALUES (?, 1)", (name,)
        )
        return True
    except sqlite3.IntegrityError:
        return False


@db_transaction
def get_glossary_sets(cursor: sqlite3.Cursor) -> list[tuple]:
    """Returns all glossary sets."""
    cursor.execute("SELECT id, name, is_active FROM glossary_sets ORDER BY name ASC")
    return cursor.fetchall()


@db_transaction
def update_all_glossary_sets_active(cursor: sqlite3.Cursor, is_active: bool) -> None:
    """Updates the active status of all glossary sets at once."""
    cursor.execute("UPDATE glossary_sets SET is_active = ?", (1 if is_active else 0,))


@db_transaction
def update_glossary_set_active(
    cursor: sqlite3.Cursor, set_id: int, is_active: bool
) -> None:
    """Updates the active status of a glossary set."""
    cursor.execute(
        "UPDATE glossary_sets SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, set_id),
    )


@db_transaction
def get_active_glossary_sets(cursor: sqlite3.Cursor) -> list[tuple]:
    """Returns all active glossary sets."""
    cursor.execute("SELECT id, name FROM glossary_sets WHERE is_active = 1")
    return cursor.fetchall()


@db_transaction
def update_glossary_set_name(cursor: sqlite3.Cursor, set_id: int, name: str) -> bool:
    """Updates the name of a glossary set."""
    try:
        cursor.execute(
            "UPDATE glossary_sets SET name = ? WHERE id = ?",
            (name, set_id),
        )
        return True
    except sqlite3.IntegrityError:
        return False


@db_transaction
def delete_glossary_set(cursor: sqlite3.Cursor, set_id: int) -> None:
    """Deletes a glossary set and its entries."""
    cursor.execute("DELETE FROM glossary_sets WHERE id = ?", (set_id,))


@db_transaction
def add_glossary_entry(
    cursor: sqlite3.Cursor, set_id: int, source: str, target: str
) -> None:
    """Adds a translation entry to a set."""
    cursor.execute(
        "INSERT INTO glossary_entries (set_id, source_text, target_text) "
        "VALUES (?, ?, ?)",
        (set_id, source, target),
    )


@db_transaction
def get_glossary_entries(cursor: sqlite3.Cursor, set_id: int) -> list[tuple]:
    """Returns all entries for a given set."""
    cursor.execute(
        "SELECT id, source_text, target_text FROM glossary_entries "
        "WHERE set_id = ? ORDER BY created_at DESC",
        (set_id,),
    )
    return cursor.fetchall()


@db_transaction
def get_glossary_entry_count(cursor: sqlite3.Cursor, set_id: int) -> int:
    """Returns the number of entries in a glossary set."""
    cursor.execute("SELECT COUNT(*) FROM glossary_entries WHERE set_id = ?", (set_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return 0


@db_transaction
def find_glossary_entry_by_source(
    cursor: sqlite3.Cursor,
    set_id: int,
    source: str,
) -> tuple[int, str] | None:
    """Returns ``(entry_id, target_text)`` for a case-insensitive match on source.

    Used to detect duplicates before adding a new entry. Returns ``None`` when
    no matching row exists.
    """
    cursor.execute(
        "SELECT id, target_text FROM glossary_entries "
        "WHERE set_id = ? AND LOWER(source_text) = LOWER(?) LIMIT 1",
        (set_id, source),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return (row[0], row[1])


@db_transaction
def delete_glossary_entry(cursor: sqlite3.Cursor, entry_id: int) -> None:
    """Deletes a single glossary entry."""
    cursor.execute("DELETE FROM glossary_entries WHERE id = ?", (entry_id,))


@db_transaction
def update_glossary_entry(
    cursor: sqlite3.Cursor, entry_id: int, source: str, target: str
) -> None:
    """Updates an existing glossary entry."""
    cursor.execute(
        "UPDATE glossary_entries SET source_text = ?, target_text = ? WHERE id = ?",
        (source, target, entry_id),
    )


# ── Extraction History ────────────────────────────────────────────────────


@db_transaction
def add_extraction_entry(  # noqa: PLR0913
    cursor: sqlite3.Cursor,
    file_name: str,
    file_size: int,
    source_path: str,
    output_path: str,
    status: str,
    error_message: str | None = None,
) -> int:
    """Adds a new extraction history entry and returns its ID.

    Args:
        cursor: Database cursor (injected by decorator).
        file_name: Original file name.
        file_size: Size of the file in bytes.
        source_path: Absolute path to the source image.
        output_path: Path where extracted text will be written.
        status: Initial status string.
        error_message: Optional error description if the entry starts failed.
    """
    cursor.execute(
        "INSERT INTO extraction_history"
        " (file_name, file_size, source_path, output_path, status, error_message)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (file_name, file_size, source_path, output_path, status, error_message),
    )
    return cursor.lastrowid


@db_transaction
def get_extraction_history(cursor: sqlite3.Cursor) -> list[tuple]:
    """Returns the most recent extraction history entries."""
    cursor.execute(
        "SELECT id, file_name, file_size, source_path, output_path,"
        " status, error_message, created_at"
        " FROM extraction_history ORDER BY created_at DESC, id DESC"
        f" LIMIT {_DB_HISTORY_PAGE_SIZE}"
    )
    return cursor.fetchall()


@db_transaction
def get_extraction_fingerprint(cursor: sqlite3.Cursor) -> tuple[int, int, str] | None:
    """Returns a lightweight fingerprint of extraction history state."""
    cursor.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), "
        "COALESCE(GROUP_CONCAT(status), '') "
        "FROM (SELECT id, status FROM extraction_history "
        f"ORDER BY created_at DESC LIMIT {_DB_HISTORY_PAGE_SIZE})"
    )
    return cursor.fetchone()


@db_transaction
def update_extraction_status(
    cursor: sqlite3.Cursor,
    entry_id: int,
    status: str,
    output_path: str = "",
    error_message: str | None = None,
) -> None:
    """Updates the status and output of an extraction history entry."""
    cursor.execute(
        "UPDATE extraction_history"
        " SET status = ?, output_path = ?, error_message = ?"
        " WHERE id = ?",
        (status, output_path, error_message, entry_id),
    )


@db_transaction
def delete_extraction_entry(cursor: sqlite3.Cursor, entry_id: int) -> str | None:
    """Deletes an extraction history entry and returns its output path."""
    cursor.execute(
        "SELECT output_path FROM extraction_history WHERE id = ?", (entry_id,)
    )
    row = cursor.fetchone()
    path = row[0] if row else None
    cursor.execute("DELETE FROM extraction_history WHERE id = ?", (entry_id,))
    return path


# ── Subtitle History ──────────────────────────────────────────────────────


@db_transaction
def add_subtitle_entry(  # noqa: PLR0913
    cursor: sqlite3.Cursor,
    file_name: str,
    file_size: int,
    source_path: str,
    output_path: str,
    src_lang: str,
    status: str,
    error_message: str | None = None,
) -> int:
    """Adds a new subtitle history entry and returns its ID.

    Args:
        cursor: Database cursor (injected by decorator).
        file_name: Original media file name.
        file_size: Size of the media file in bytes.
        source_path: Absolute path to the source media file.
        output_path: Path where the generated subtitle will be written.
        src_lang: Source language label for STT.
        status: Initial status string.
        error_message: Optional error description if the entry starts failed.
    """
    cursor.execute(
        "INSERT INTO subtitle_history"
        " (file_name, file_size, source_path, output_path,"
        " src_lang, status, error_message)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            file_name,
            file_size,
            source_path,
            output_path,
            src_lang,
            status,
            error_message,
        ),
    )
    return cursor.lastrowid


@db_transaction
def get_subtitle_history(cursor: sqlite3.Cursor) -> list[tuple]:
    """Returns the most recent subtitle history entries."""
    cursor.execute(
        "SELECT id, file_name, file_size, source_path, output_path,"
        " src_lang, status, error_message, created_at"
        " FROM subtitle_history ORDER BY created_at DESC, id DESC"
        f" LIMIT {_DB_HISTORY_PAGE_SIZE}"
    )
    return cursor.fetchall()


@db_transaction
def get_subtitle_fingerprint(cursor: sqlite3.Cursor) -> tuple[int, int, str] | None:
    """Returns a lightweight fingerprint of subtitle history state."""
    cursor.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), "
        "COALESCE(GROUP_CONCAT(status), '') "
        "FROM (SELECT id, status FROM subtitle_history "
        f"ORDER BY created_at DESC LIMIT {_DB_HISTORY_PAGE_SIZE})"
    )
    return cursor.fetchone()


@db_transaction
def update_subtitle_status(
    cursor: sqlite3.Cursor,
    entry_id: int,
    status: str,
    output_path: str | None = None,
    error_message: str | None = None,
) -> None:
    """Updates the status of a subtitle history entry.

    Args:
        cursor: Database cursor (injected by decorator).
        entry_id: Entry ID to update.
        status: New status string.
        output_path: If not None, also update output_path.
        error_message: If not None, also update error_message.
    """
    if output_path is not None:
        cursor.execute(
            "UPDATE subtitle_history"
            " SET status = ?, output_path = ?, error_message = ?"
            " WHERE id = ?",
            (status, output_path, error_message, entry_id),
        )
    else:
        cursor.execute(
            "UPDATE subtitle_history SET status = ?, error_message = ? WHERE id = ?",
            (status, error_message, entry_id),
        )


@db_transaction
def delete_subtitle_entry(cursor: sqlite3.Cursor, entry_id: int) -> str | None:
    """Deletes a subtitle history entry and returns its output path."""
    cursor.execute("SELECT output_path FROM subtitle_history WHERE id = ?", (entry_id,))
    row = cursor.fetchone()
    path = row[0] if row else None
    cursor.execute("DELETE FROM subtitle_history WHERE id = ?", (entry_id,))
    return path


# ── Voice History ─────────────────────────────────────────────────────────


@db_transaction
def add_voice_entry(  # noqa: PLR0913
    cursor: sqlite3.Cursor,
    file_name: str,
    file_size: int,
    source_path: str,
    output_path: str,
    status: str,
    error_message: str | None = None,
) -> int:
    """Adds a new voice history entry and returns its ID.

    Args:
        cursor: Database cursor (injected by decorator).
        file_name: Original subtitle file name.
        file_size: Size of the subtitle file in bytes.
        source_path: Absolute path to the source subtitle file.
        output_path: Path where the generated audio will be written.
        status: Initial status string.
        error_message: Optional error description if the entry starts failed.
    """
    cursor.execute(
        "INSERT INTO voice_history"
        " (file_name, file_size, source_path, output_path,"
        " status, error_message)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (file_name, file_size, source_path, output_path, status, error_message),
    )
    return cursor.lastrowid


@db_transaction
def get_voice_history(cursor: sqlite3.Cursor) -> list[tuple]:
    """Returns the most recent voice history entries."""
    cursor.execute(
        "SELECT id, file_name, file_size, source_path, output_path,"
        " status, error_message, created_at"
        " FROM voice_history ORDER BY created_at DESC, id DESC"
        f" LIMIT {_DB_HISTORY_PAGE_SIZE}"
    )
    return cursor.fetchall()


@db_transaction
def get_voice_fingerprint(cursor: sqlite3.Cursor) -> tuple[int, int, str] | None:
    """Returns a lightweight fingerprint of voice history state."""
    cursor.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), "
        "COALESCE(GROUP_CONCAT(status), '') "
        "FROM (SELECT id, status FROM voice_history "
        f"ORDER BY created_at DESC LIMIT {_DB_HISTORY_PAGE_SIZE})"
    )
    return cursor.fetchone()


@db_transaction
def update_voice_status(
    cursor: sqlite3.Cursor,
    entry_id: int,
    status: str,
    output_path: str | None = None,
    error_message: str | None = None,
) -> None:
    """Updates the status of a voice history entry."""
    if output_path is not None:
        cursor.execute(
            "UPDATE voice_history"
            " SET status = ?, output_path = ?, error_message = ?"
            " WHERE id = ?",
            (status, output_path, error_message, entry_id),
        )
    else:
        cursor.execute(
            "UPDATE voice_history SET status = ?, error_message = ? WHERE id = ?",
            (status, error_message, entry_id),
        )


@db_transaction
def delete_voice_entry(cursor: sqlite3.Cursor, entry_id: int) -> str | None:
    """Deletes a voice history entry and returns its output path."""
    cursor.execute("SELECT output_path FROM voice_history WHERE id = ?", (entry_id,))
    row = cursor.fetchone()
    path = row[0] if row else None
    cursor.execute("DELETE FROM voice_history WHERE id = ?", (entry_id,))
    return path


@db_transaction
def reset_stuck_subtitle_entries(cursor: sqlite3.Cursor) -> int:
    """Resets any subtitle entries stuck in 'Generating' to 'Failed'.

    Called at app startup to clean up interrupted entries from a previous
    crash.  Returns the number of rows updated.
    """
    cursor.execute(
        "UPDATE subtitle_history SET status = ?, error_message = ? WHERE status = ?",
        (STATUS_FAILED, "APP_CRASHED", STATUS_GENERATING),
    )
    return cursor.rowcount


@db_transaction
def reset_stuck_voice_entries(cursor: sqlite3.Cursor) -> int:
    """Resets any voice entries stuck in 'Generating' to 'Failed'.

    Called at app startup to clean up interrupted entries from a previous
    crash.  Returns the number of rows updated.
    """
    cursor.execute(
        "UPDATE voice_history SET status = ?, error_message = ? WHERE status = ?",
        (STATUS_FAILED, "APP_CRASHED", STATUS_GENERATING),
    )
    return cursor.rowcount


# ── Dubbing History ───────────────────────────────────────────────────────


@db_transaction
def add_dubbing_entry(  # noqa: PLR0913
    cursor: sqlite3.Cursor,
    file_name: str,
    file_size: int,
    source_path: str,
    output_path: str,
    status: str,
    src_lang: str = "",
    target_lang: str = "",
    error_message: str | None = None,
) -> int:
    """Adds a new dubbing history entry and returns its ID.

    Args:
        cursor: Database cursor (injected by decorator).
        file_name: Original video file name.
        file_size: Size of the video file in bytes.
        source_path: Absolute path to the source video file.
        output_path: Path where the dubbed video will be written.
        status: Initial status string.
        src_lang: Source language label (empty string if unknown).
        target_lang: Target language label (empty string if unknown).
        error_message: Optional error description if the entry starts failed.
    """
    cursor.execute(
        "INSERT INTO dubbing_history"
        " (file_name, file_size, source_path, output_path,"
        " src_lang, target_lang, status, error_message)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            file_name,
            file_size,
            source_path,
            output_path,
            src_lang,
            target_lang,
            status,
            error_message,
        ),
    )
    return cursor.lastrowid


@db_transaction
def get_dubbing_history(cursor: sqlite3.Cursor) -> list[tuple]:
    """Returns the most recent dubbing history entries."""
    cursor.execute(
        "SELECT id, file_name, file_size, source_path, output_path,"
        " src_lang, target_lang,"
        " status, progress, error_message, created_at,"
        " subtitle_path, translated_subtitle_path, voice_path"
        " FROM dubbing_history ORDER BY created_at DESC, id DESC"
        f" LIMIT {_DB_HISTORY_PAGE_SIZE}"
    )
    return cursor.fetchall()


@db_transaction
def get_dubbing_fingerprint(cursor: sqlite3.Cursor) -> tuple[int, int, str] | None:
    """Returns a lightweight fingerprint of dubbing history state."""
    cursor.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), "
        "COALESCE(GROUP_CONCAT(status || progress), '') "
        "FROM (SELECT id, status, progress FROM dubbing_history "
        f"ORDER BY created_at DESC LIMIT {_DB_HISTORY_PAGE_SIZE})"
    )
    return cursor.fetchone()


@db_transaction
def update_dubbing_status(  # noqa: PLR0913
    cursor: sqlite3.Cursor,
    entry_id: int,
    status: str,
    output_path: str | None = None,
    progress: str | None = None,
    error_message: str | None = None,
    subtitle_path: str | None = None,
    translated_subtitle_path: str | None = None,
    voice_path: str | None = None,
) -> None:
    """Updates the status of a dubbing history entry.

    Args:
        cursor: Database cursor (injected by decorator).
        entry_id: Entry ID to update.
        status: New status string.
        output_path: If not None, also update the output file path.
        progress: If not None, also update the dubbing step progress.
        error_message: If not None, also update the error description.
        subtitle_path: If not None, also update the generated subtitle path.
        translated_subtitle_path: If not None, also update the translated subtitle path.
        voice_path: If not None, also update the synthesized voice path.
    """
    parts = ["status = ?", "error_message = ?"]
    params: list = [status, error_message]
    if output_path is not None:
        parts.append("output_path = ?")
        params.append(output_path)
    if progress is not None:
        parts.append("progress = ?")
        params.append(progress)
    if subtitle_path is not None:
        parts.append("subtitle_path = ?")
        params.append(subtitle_path)
    if translated_subtitle_path is not None:
        parts.append("translated_subtitle_path = ?")
        params.append(translated_subtitle_path)
    if voice_path is not None:
        parts.append("voice_path = ?")
        params.append(voice_path)
    params.append(entry_id)
    cursor.execute(
        f"UPDATE dubbing_history SET {', '.join(parts)} WHERE id = ?",
        params,
    )


@db_transaction
def get_dubbing_entry_status(
    cursor: sqlite3.Cursor,
    entry_id: int,
) -> str | None:
    """Returns the current status of a dubbing history entry."""
    cursor.execute(
        "SELECT status FROM dubbing_history WHERE id = ?",
        (entry_id,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


@db_transaction
def update_dubbing_progress(
    cursor: sqlite3.Cursor,
    entry_id: int,
    progress: int,
) -> None:
    """Updates the progress percentage of a dubbing entry (monotonic)."""
    cursor.execute(
        "UPDATE dubbing_history SET progress = ?"
        " WHERE id = ? AND CAST(progress AS INTEGER) < ?",
        (str(progress), entry_id, progress),
    )


@db_transaction
def get_unfinished_dubbing(
    cursor: sqlite3.Cursor,
) -> list[tuple]:
    """Returns unfinished dubbing tasks (Pending or Generating).

    Results are ordered so that 'Generating' entries come first
    (interrupted tasks resume before new ones), then by ascending id.

    Returns:
        List of (id, source_path, src_lang, target_lang) tuples.
    """
    cursor.execute(
        "SELECT id, source_path, src_lang, target_lang"
        " FROM dubbing_history WHERE status IN (?, ?)"
        " ORDER BY CASE status WHEN ? THEN 0 ELSE 1 END, id ASC",
        (STATUS_GENERATING, STATUS_PENDING, STATUS_GENERATING),
    )
    return cursor.fetchall()


@db_transaction
def batch_pause_dubbing_entries(
    cursor: sqlite3.Cursor,
    ids: list[int],
) -> None:
    """Pauses multiple dubbing entries in a single transaction."""
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    query = (
        f"UPDATE dubbing_history SET status = ?, error_message = NULL"
        f" WHERE id IN ({placeholders}) AND status IN (?, ?)"
    )
    cursor.execute(
        query,
        (STATUS_PAUSED, *ids, STATUS_GENERATING, STATUS_PENDING),
    )


@db_transaction
def batch_resume_dubbing_entries(
    cursor: sqlite3.Cursor,
    ids: list[int],
) -> None:
    """Resumes multiple paused or failed dubbing entries."""
    if not ids:
        return
    placeholders = ", ".join("?" for _ in ids)
    query = (
        f"UPDATE dubbing_history SET status = ?, error_message = NULL"
        f" WHERE id IN ({placeholders})"
    )
    cursor.execute(query, (STATUS_PENDING, *ids))


@db_transaction
def delete_dubbing_entry(
    cursor: sqlite3.Cursor,
    entry_id: int,
) -> tuple[str, ...]:
    """Deletes a dubbing history entry and returns its file paths.

    Returns:
        Tuple of (output_path, subtitle_path, translated_subtitle_path,
        voice_path). Missing values are empty strings.
    """
    cursor.execute(
        "SELECT output_path, subtitle_path,"
        " translated_subtitle_path, voice_path"
        " FROM dubbing_history WHERE id = ?",
        (entry_id,),
    )
    row = cursor.fetchone()
    paths = row if row else ("", "", "", "")
    cursor.execute("DELETE FROM dubbing_history WHERE id = ?", (entry_id,))
    return paths


# ── Text Translation History ──────────────────────────────────────────────


@db_transaction
def add_text_translation_entry(  # noqa: PLR0913
    cursor: sqlite3.Cursor,
    source_text: str,
    translated_text: str,
    src_lang: str,
    target_lang: str,
    char_count: int,
) -> int:
    """Adds a new text translation history entry and returns its ID.

    Args:
        cursor: Database cursor (injected by decorator).
        source_text: Original text before translation.
        translated_text: Translated text from the LLM.
        src_lang: Source language label.
        target_lang: Target language label.
        char_count: Character count of the source text.
    """
    cursor.execute(
        "INSERT INTO text_translation_history"
        " (source_text, translated_text, src_lang, target_lang, char_count)"
        " VALUES (?, ?, ?, ?, ?)",
        (source_text, translated_text, src_lang, target_lang, char_count),
    )
    return cursor.lastrowid


@db_transaction
def get_text_translation_history(cursor: sqlite3.Cursor) -> list[tuple]:
    """Returns the most recent text translation history entries."""
    cursor.execute(
        "SELECT id, source_text, translated_text, src_lang, target_lang,"
        " char_count, created_at"
        " FROM text_translation_history ORDER BY created_at DESC, id DESC"
        f" LIMIT {_DB_HISTORY_PAGE_SIZE}"
    )
    return cursor.fetchall()


@db_transaction
def get_text_translation_fingerprint(
    cursor: sqlite3.Cursor,
) -> tuple[int, int] | None:
    """Returns a lightweight fingerprint of text translation history state."""
    cursor.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0)"
        " FROM (SELECT id FROM text_translation_history"
        f" ORDER BY created_at DESC LIMIT {_DB_HISTORY_PAGE_SIZE})"
    )
    return cursor.fetchone()


@db_transaction
def update_text_translation_entry(
    cursor: sqlite3.Cursor,
    entry_id: int,
    translated_text: str,
) -> None:
    """Updates the translated text of a text translation history entry."""
    cursor.execute(
        "UPDATE text_translation_history SET translated_text = ? WHERE id = ?",
        (translated_text, entry_id),
    )


@db_transaction
def delete_text_translation_entry(
    cursor: sqlite3.Cursor,
    entry_id: int,
) -> None:
    """Deletes a text translation history entry."""
    cursor.execute(
        "DELETE FROM text_translation_history WHERE id = ?",
        (entry_id,),
    )
