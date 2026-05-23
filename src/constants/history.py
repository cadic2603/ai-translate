"""Standardized statuses for translation and extraction history."""

STATUS_PENDING = "Pending"
STATUS_TRANSLATING = "Translating"
STATUS_EXTRACTING = "Extracting"
STATUS_GENERATING = "Generating"
STATUS_DONE = "Done"
STATUS_FAILED = "Failed"
STATUS_PAUSED = "Paused"
STATUS_DELETING = "Deleting"


def display_status(status: str) -> str:
    """Returns the localized display text for a status string.

    The DB stores English status values. This translates them for the UI
    via ``tr()``, falling back to the raw string if no key exists.

    Args:
        status: English status string (e.g. "Done", "Failed").

    Returns:
        Translated display string.
    """
    from src.constants.i18n import tr  # noqa: PLC0415

    key = f"status.{status.lower()}"
    translated = tr(key)
    # If tr() returns the key unchanged, the key doesn't exist
    return status if translated == key else translated


# Status groups
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_TRANSLATING)
UNFINISHED_STATUSES = (STATUS_PENDING, STATUS_TRANSLATING, STATUS_PAUSED)
REPROCESSABLE_STATUSES = (STATUS_DONE, STATUS_FAILED, STATUS_PAUSED)

# Progress milestones for translation pipeline stages.
# Image pipeline: OCR is fast, LLM is slow, render is moderate.
# Weights are chosen so each callback fills its range with no gaps.
PROGRESS_INITIAL = 5
PROGRESS_OCR_DONE = 15
PROGRESS_LLM_DONE = 90
PROGRESS_COMPLETE = 100
PROGRESS_IMAGE_LLM_WEIGHT = 0.75  # fills OCR_DONE → LLM_DONE (15→90)
PROGRESS_TEXT_WEIGHT = 0.9  # fills INITIAL → near-complete (5→95)

# ── Dubbing pipeline progress milestones ──────────────────────────────────
# 4-step pipeline: STT (5-25%) → Translate (25-50%) → TTS (50-90%) → Mix (90-100%)
DUBBING_PROGRESS_STT_START = 5
DUBBING_PROGRESS_STT_DONE = 25
DUBBING_PROGRESS_TRANSLATE_DONE = 50
DUBBING_PROGRESS_TTS_START = 50
DUBBING_PROGRESS_TTS_DONE = 90
DUBBING_PROGRESS_MIX_START = 90
