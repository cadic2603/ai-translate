"""Live Translation page UI for the AI Translate application.

Captures microphone audio, transcribes in real-time with Whisper,
translates via LLM, displays text, optionally speaks translations,
and supports a floating overlay window for subtitle display.
"""

import contextlib
import logging
import tempfile
import time
from collections import deque
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QStackedWidget,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    BANNER_LINE_SPACING,
    FLAG_ICON_HEIGHT,
    FLAG_ICON_WIDTH,
    FLAGS_DIR,
    HEIGHT_CONTROL,
    RADIUS_BUTTON,
    SPACING_SUBSECTION,
    color,
    style_delete_button,
    style_primary_button,
    style_secondary_button,
    style_setting_combo,
    tr,
)
from src.constants.settings import (
    AUDIO_SOURCE_BOTH,
    AUDIO_SOURCE_MICROPHONE,
    AUDIO_SOURCE_SYSTEM,
    LIVE_DISPLAY_BOTH,
    LIVE_DISPLAY_BOTH_DUAL,
    LIVE_DISPLAY_TRANSLATION,
    LIVE_LAYOUT_DUAL,
    LIVE_LAYOUT_SINGLE,
    LIVE_STT_SONIOX,
    LIVE_STT_WHISPER,
    SETTING_LIVE_AUDIO_SOURCE,
    SETTING_LIVE_SHOW_ORIGINAL,
    SETTING_LIVE_SHOW_TIMESTAMP,
    SETTING_LIVE_SOURCE_LANG,
    SETTING_LIVE_STT_METHOD,
    SETTING_LIVE_TARGET_LANG,
    SETTING_LIVE_TRANSCRIPT_DISPLAY,
    SETTING_LIVE_TRANSCRIPT_LAYOUT,
    SETTING_LIVE_WHISPER_MODEL,
    SETTING_SONIOX_API_KEY,
    SETTING_VOICE_TTS_METHOD,
    VOICE_TTS_ELEVENLABS,
    VOICE_TTS_GOOGLE,
)
from src.ui.components import create_banner, create_page_container
from src.ui.dialogs import BaseDialog
from src.utils.config_manager import load_setting, save_setting

logger = logging.getLogger("live")

# Maximum entries shown in the transcript log
_MAX_LOG_ENTRIES = 100
# Maximum pending TTS items — keeps the audio in sync with the visible text
# when TTS is slower than recognition. Older items are dropped so the user
# hears the most-recent sentences instead of falling further behind.
_MAX_TTS_QUEUE = 3

# Number of prior source sentences sent to the LLM as reference-only
# context for each new translation request.  Three sentences gives the
# LLM enough runway for pronoun resolution + topic / tone continuity
# while keeping the extra ~150 tokens per call cheap and the latency
# hit sub-perceptual.  Source text only — feeding back the LLM's own
# prior translations would amplify any mistakes it made.
_LIVE_CONTEXT_SENTENCES = 3

# Prefix for temp-WAV files written when audio is recorded without an
# Auto save = Audio opt-in (i.e. the user wants the *option* to manually
# save audio without committing it to their output folder by default).
# Shared between the per-session reservation in ``_resolve_save_paths``
# and the orphan-sweep in ``_cleanup_orphan_temp_audio`` so a crashed
# prior run can't leave its WAV in /tmp forever.
_TEMP_AUDIO_PREFIX = "ai_translate_live_audio_"


def _cleanup_orphan_temp_audio() -> None:
    """Sweeps any leftover ``_TEMP_AUDIO_PREFIX*.wav`` from the OS tempdir.

    Picks up files orphaned by a crashed prior run (the in-process
    cleanup in :meth:`LivePage._cleanup_temp_audio` only handles the
    current session's file).  Best-effort: errors are logged and
    ignored so a permission glitch on one file doesn't abort the
    whole sweep.  Cheap — the prefix is specific enough that we
    don't iterate the entire tempdir, just the matching glob.
    """
    import tempfile  # noqa: PLC0415

    tmp = Path(tempfile.gettempdir())
    for path in tmp.glob(f"{_TEMP_AUDIO_PREFIX}*.wav"):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("orphan temp audio cleanup failed for %s: %s", path, exc)

# Per-sentence retry policy for the streaming LLM call.  Live mode has
# a tight latency budget (~3-5 s between sentences), so we use a far
# tighter retry policy than the file/batch ``@retry_api_call`` (3
# retries × 3 s base = up to 12 s).  One retry with a 0.5 s backoff
# adds at most ~500 ms to a transient failure while keeping persistent
# failures fast to surface.  Transient-only — auth / quota / invalid-
# request errors won't fix themselves so we skip retry on those.
_LIVE_RETRY_MAX_ATTEMPTS = 2  # 1 initial + 1 retry
_LIVE_RETRY_BACKOFF_SEC = 0.5
_LIVE_RETRY_TRANSIENT_TAGS = (
    "TIMEOUT_ERROR",
    "CONNECTION_ERROR",
    "SERVICE_UNAVAILABLE_ERROR",
)

# Placeholder shown in a dual-view pair's right card while the LLM is still
# producing the translation.  Swapped in place for the real text by
# ``_add_translated`` once the worker fires its ``translated`` signal.
_TRANSLATION_PLACEHOLDER = "…"

# How long (ms) the status bar shows a translation-failure toast
# before resetting to "Ready".  Long enough to read; short enough
# that a stale error doesn't linger after a successful next sentence.
_TRANSLATION_ERROR_STATUS_MS = 5000

# Tolerance for "is the scrollbar at the bottom?" check — Qt reports
# off-by-one values during layout, so a strict ``value == maximum``
# comparison misses the "already at bottom" case right after a resize.
_AUTOSCROLL_BOTTOM_TOLERANCE = 4


def _lang_to_code(lang_label: str) -> str:
    """Converts a language label (e.g. 'Vietnamese') to a 2-letter code."""
    if not lang_label:
        return ""
    from src.constants.languages import get_locale_code  # noqa: PLC0415

    code = get_locale_code(lang_label) or ""
    # get_locale_code returns BCP-47 (e.g. "vi", "zh-CN"); Soniox wants 2-letter
    return code.split("-")[0] if code else ""


def _bind_last_word(text: str) -> str:
    """Replaces the final space with a non-breaking space.

    Prevents the typographic "widow" problem where word-wrap leaves
    the last word alone on its own line.  The non-breaking space
    forces the last two words to stay together: if the wrap engine
    can't fit them on the current line, it pushes both to the next
    line, producing a more balanced break.

    Locale-agnostic: works for any language whose word separator is
    a regular space, which covers all 20 locales we ship.  No-op for
    text without a space (single-word strings, CJK-only strings) so
    Japanese / Chinese hints pass through unchanged.
    """
    if " " not in text:
        return text
    last_space = text.rfind(" ")
    return text[:last_space] + " " + text[last_space + 1 :]


def _format_speaker(speaker: str) -> str:
    """Formats a raw speaker ID (e.g. 'speaker_0') into a display label."""
    if not speaker:
        return ""
    # Extract number from "speaker_0", "speaker_1" etc.
    parts = speaker.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():  # noqa: PLR2004
        return f"Speaker {int(parts[1]) + 1}"
    return speaker


def _format_timestamp(start_sec: float, end_sec: float) -> str:
    """Formats start/end seconds into an ``HH:MM:SS`` timeline string."""

    def _fmt(s: float) -> str:
        """Format seconds as HH:MM:SS."""
        m, sec = divmod(int(s), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{sec:02d}"

    return f"{_fmt(start_sec)} → {_fmt(end_sec)}"


def _style_transcript_card() -> str:
    """QSS for a transcript entry.

    Flat rows inside the single outer page card — no full per-row
    borders / surfaces (the earlier "stack of competing little cards"
    design).  A faint 1 px bottom border alone delineates each entry
    so the user's eye still flows down the content but each
    sentence reads as discrete; a subtle hover background hints at
    interactivity even though the row isn't clickable today.
    """
    return (
        "_TranscriptCard {"
        " background: transparent;"
        f" border: none;"
        f" border-bottom: 1px solid {color('border_light')};"
        " border-radius: 0;"
        " }"
        " _TranscriptCard:hover {"
        f" background-color: {color('disabled_bg')};"
        " }"
    )


def _style_transcript_card_in_pair() -> str:
    """QSS for a transcript card embedded in a side-by-side pair row.

    Drops the per-card ``border-bottom`` AND per-card hover background
    — both move up to the pair wrapper so the divider runs unbroken
    across the inter-column gap and hovering either column highlights
    the whole logical row (source + translation are one unit to read).
    """
    return (
        "_TranscriptCard {"
        " background: transparent;"
        " border: none;"
        " border-radius: 0;"
        " }"
    )


def _style_dual_pair_row() -> str:
    """QSS for the wrapper widget that bundles a left+right card pair.

    Carries the single continuous bottom divider AND the row-level
    hover background so the dual-column row reads as one unit: divider
    spans the gap, and hovering anywhere over either column lights up
    both halves together.
    """
    # Selector uses the class name directly (not ``QWidget#...``)
    # because Qt's QSS class selector matches by *exact* class name —
    # ``QWidget`` matches only bare-QWidget instances, not subclasses.
    # When the pair-row was a plain ``QWidget()`` this worked; making
    # it a real subclass meant the rule silently stopped applying and
    # hover broke.  ``_DualPairRow`` matches the subclass directly.
    return (
        "_DualPairRow {"
        f" border-bottom: 1px solid {color('border_light')};"
        " }"
        " _DualPairRow:hover {"
        f" background-color: {color('disabled_bg')};"
        " }"
    )


def _style_page_card() -> str:
    """QSS for the single outer card that wraps controls + transcript.

    One card, two visually-joined sections (controller on top, then a
    divider, then the transcript list).  Drops the prior
    card-in-a-card pattern where the controller *and* every
    transcript entry had their own border — busy and repetitive on a
    populated page.  Selector scoped via ``QFrame#LivePageCard`` so
    descendant widgets don't inherit the surface styling.
    """
    return (
        "QFrame#LivePageCard {"
        f" background-color: {color('component_bg')};"
        f" border: 1px solid {color('border_light')};"
        f" border-radius: {RADIUS_BUTTON}px;"
        " }"
    )


class _PillLabel(QLabel):
    """QLabel subclass that paints a rounded coloured background.

    Qt's stylesheet engine renders ``border-radius`` reliably on
    QFrame / QPushButton / QToolButton but not on plain QLabel — the
    style code paths take the palette-based fill route which doesn't
    honour the radius, leaving the background rectangular even when
    ``WA_StyledBackground`` is enabled.

    This subclass bypasses the stylesheet path entirely for the
    background: ``paintEvent`` draws a rounded rect with QPainter,
    then defers to ``QLabel.paintEvent`` for the text.  The text
    colour + font still flow through the stylesheet, so callers
    can theme the text just like a normal QLabel.
    """

    def __init__(  # noqa: PLR0913
        self,
        text: str,
        bg_hex: str,
        *,
        radius: int = 5,
        h_padding: int = 10,
        v_padding: int = 3,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._bg = QColor(bg_hex)
        self._radius = radius
        # Asymmetric top vs bottom padding to compensate for QLabel's
        # font-metrics centring: Qt centres text against the full
        # line box (ascent + descent), but pill text usually has no
        # descenders (e.g. "Speaker 1"), so symmetric padding makes
        # the glyphs sit visibly higher than centre.  Shaving 1 px
        # off the top + adding 1 px to the bottom shifts the visible
        # glyphs toward the optical centre of the pill.
        self.setContentsMargins(
            h_padding,
            max(0, v_padding - 1),
            h_padding,
            v_padding + 1,
        )

    def set_bg(self, bg: str | QColor) -> None:
        """Updates the pill background colour and repaints.

        Used by status / chip widgets that need to swap colours at
        runtime — e.g. flipping the Live status pill to a danger tint
        when a translation error toast comes through.  Accepts either
        a hex / CSS string or a pre-built ``QColor`` so callers can
        precompute an rgba tint without re-parsing every call.
        """
        self._bg = QColor(bg) if isinstance(bg, str) else bg
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        """Paints the rounded background first, then defers to QLabel."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            self.rect().adjusted(0, 0, -1, -1),
            self._radius,
            self._radius,
        )
        painter.fillPath(path, self._bg)
        painter.end()
        super().paintEvent(event)


class _RenamableSpeakerChip(_PillLabel):
    """Speaker pill chip that becomes a QLineEdit on double-click.

    Wraps the read-only :class:`_PillLabel` with an inline-edit
    affordance so the user can replace "Speaker 1" with a real
    name ("Alice", "Boss", ...) by double-clicking the chip.

    Edit-mode UX:
      - **Enter / focus-out** → commit the new name.
      - **Esc** → cancel, restoring the previous text.
      - **Empty** committed text drops the alias so the chip
        reverts to its formatted default ("Speaker N") — see
        :meth:`LivePage._on_speaker_renamed`.

    The chip stores the *raw* speaker ID (e.g. ``"speaker_0"``) so
    the page-level rename slot can find every sibling chip across
    cards, dual-pair gutters, and overlay entries that belong to
    the same speaker.

    Read-only chips (overlay entries) keep using ``_PillLabel``
    directly; the overlay deliberately doesn't expose rename
    interactions because its host window has ``WA_Transparent
    ForMouseEvents`` set on the entry container for drag-to-move
    pass-through.
    """

    renamed = Signal(str, str)

    def __init__(  # noqa: PLR0913
        self,
        speaker_id: str,
        text: str,
        bg_hex: str,
        *,
        radius: int = 5,
        h_padding: int = 10,
        v_padding: int = 3,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            text,
            bg_hex,
            radius=radius,
            h_padding=h_padding,
            v_padding=v_padding,
            parent=parent,
        )
        self._speaker_id = speaker_id
        self._editor: QLineEdit | None = None
        self.setCursor(Qt.CursorShape.IBeamCursor)
        # Keep the chip text selectable when the user single-clicks
        # to drag-select.  Double-click triggers rename via the
        # event override below.
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Left-double-click → enter edit mode; other buttons pass through."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _begin_edit(self) -> None:
        """Reveals an inline QLineEdit positioned over this chip.

        The chip itself is hidden for the duration of the edit and
        re-shown when the editor commits or cancels.  Using a
        sibling QLineEdit (rather than swapping the chip in-place)
        keeps the chip's parent layout undisturbed — the chip slot
        retains its size and adjacent chips don't jump as the
        editor opens.
        """
        if self._editor is not None:
            return  # already editing
        editor = QLineEdit(self.text(), self.parentWidget())
        editor.setGeometry(self.geometry())
        editor.setFixedHeight(self.height())
        editor.selectAll()
        editor.installEventFilter(self)
        # ``editingFinished`` fires on Enter *and* focus-out, which
        # together cover both commit paths in one slot.
        editor.editingFinished.connect(self._commit_edit)
        self._editor = editor
        self.setVisible(False)
        editor.show()
        editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def _commit_edit(self) -> None:
        """Hides the editor and emits the rename signal."""
        editor = self._editor
        if editor is None:
            return
        new_text = editor.text().strip()
        self._editor = None
        # Disconnect before deleteLater so ``editingFinished`` from
        # the about-to-die widget can't re-enter this slot during
        # the focus-loss that ``setFocus`` on the chip will trigger.
        with contextlib.suppress(RuntimeError, TypeError):
            editor.editingFinished.disconnect(self._commit_edit)
        editor.removeEventFilter(self)
        editor.deleteLater()
        self.setVisible(True)
        self.renamed.emit(self._speaker_id, new_text)

    def _cancel_edit(self) -> None:
        """Hides the editor without emitting any rename."""
        editor = self._editor
        if editor is None:
            return
        self._editor = None
        with contextlib.suppress(RuntimeError, TypeError):
            editor.editingFinished.disconnect(self._commit_edit)
        editor.removeEventFilter(self)
        editor.deleteLater()
        self.setVisible(True)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Catches Esc inside the editor so the user can cancel the rename.

        Without this filter Esc would propagate to the parent and
        likely close the overlay / dismiss the focused chip without
        cleaning up the editor widget.
        """
        if (
            obj is self._editor
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape  # type: ignore[attr-defined]
        ):
            self._cancel_edit()
            return True
        return super().eventFilter(obj, event)


def _style_transcript_timestamp_chip() -> str:
    """QSS for the timestamp pill text (background is painted by _PillLabel)."""
    return (
        f" color: {color('text_secondary')};"
        " font-family: monospace;"
        " font-size: 11px;"
        " font-weight: 600;"
        " letter-spacing: 0.4px;"
        " background: transparent;"
        " border: none;"
    )


# Per-speaker pill colour palette.  Chosen so distinct speakers in a
# multi-party conversation each get a visually-distinguishable chip
# even at a glance, without straying outside the app's dark-theme-
# friendly hue range.  ``_speaker_chip_color`` cycles through this
# list keyed off the speaker's index, so Speaker 1 → palette[0],
# Speaker 2 → palette[1], etc.  Wraps modulo length for 7+ speakers.
_SPEAKER_CHIP_COLORS = (
    "#3e79f7",  # blue (matches brand primary)
    "#22c55e",  # green
    "#a855f7",  # purple
    "#f59e0b",  # amber
    "#ec4899",  # pink
    "#14b8a6",  # teal
)


def _speaker_chip_color(speaker: str) -> str:
    """Returns a stable hex colour for *speaker*.

    Speakers formatted as ``"Speaker N"`` (the output of
    :func:`_format_speaker`) hash deterministically to the same hue
    across the session by the trailing integer — Speaker 1 always
    blue, Speaker 2 always green, etc.  Falls back to a string-hash
    cycle for any other label shape (custom speaker names, etc.).
    """
    if not speaker:
        return _SPEAKER_CHIP_COLORS[0]
    parts = speaker.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():  # noqa: PLR2004
        idx = max(0, int(parts[1]) - 1)
    else:
        idx = abs(hash(speaker))
    return _SPEAKER_CHIP_COLORS[idx % len(_SPEAKER_CHIP_COLORS)]


def _style_transcript_speaker_chip() -> str:
    """QSS for the speaker pill text (background is painted by _PillLabel)."""
    return (
        " color: #ffffff;"
        " font-size: 11px;"
        " font-weight: 600;"
        " letter-spacing: 0.4px;"
        " background: transparent;"
        " border: none;"
    )


def _style_transcript_original() -> str:
    """QSS for original (source) text labels inside a card."""
    return (
        f"color: {color('text_secondary')};"
        " font-size: 14px;"
        " background: transparent;"
        " border: none;"
    )


def _style_transcript_translated() -> str:
    """QSS for translated text labels inside a card."""
    return (
        f"color: {color('text_primary')};"
        " font-size: 14px;"
        " font-weight: 600;"
        " background: transparent;"
        " border: none;"
    )


def _style_transcript_error() -> str:
    """QSS for the inline error indicator when LLM translation fails.

    Uses the theme's ``error`` colour so it reads as a warning at a
    glance.  Same font size as the translation slot it replaces so
    row heights in the dual view stay aligned.
    """
    return (
        f"color: {color('error')};"
        " font-size: 14px;"
        " font-weight: 500;"
        " background: transparent;"
        " border: none;"
    )


def _style_transcript_empty_hint() -> str:
    """QSS for the placeholder shown when the transcript is empty."""
    return (
        f"color: {color('text_secondary')};"
        " font-size: 13px;"
        " background: transparent;"
        " padding: 24px;"
    )


def _style_overlay_slider() -> str:
    """QSS for the compact opacity slider embedded in the overlay chrome."""
    return """
        QSlider::groove:horizontal {
            height: 2px;
            background: rgba(255, 255, 255, 70);
            border-radius: 1px;
        }
        QSlider::handle:horizontal {
            width: 12px; height: 12px;
            margin: -5px 0;
            background: white;
            border-radius: 6px;
            border: none;
        }
        QSlider::handle:horizontal:hover {
            background: rgba(255, 255, 255, 230);
        }
        QSlider::sub-page:horizontal {
            background: rgba(255, 255, 255, 180);
            border-radius: 1px;
        }
    """


def _style_status() -> str:
    """QSS for the status indicator pill on the toolbar text.

    The pill background is painted by :class:`_PillLabel`; this
    stylesheet only carries text styling so the same QSS-on-QLabel
    rounding bug that breaks the transcript chips doesn't bite here.
    """
    return (
        f"color: {color('text_secondary')};"
        " font-size: 12px;"
        " font-weight: 600;"
        " letter-spacing: 0.4px;"
        " background: transparent;"
        " border: none;"
    )


def _style_status_error() -> str:
    """QSS for the status pill text when surfacing a failure toast.

    Red-on-tinted-red: keeps the alert quiet (no harsh white-on-
    saturated-red contrast) while still differentiating from the
    neutral "Ready" pill.  Paired with a translucent
    ``error``-coloured pill background painted by :class:`_PillLabel`
    via ``status_label.set_bg``.
    """
    return (
        f" color: {color('error')};"
        " font-size: 12px;"
        " font-weight: 600;"
        " letter-spacing: 0.4px;"
        " background: transparent;"
        " border: none;"
    )


# ── Transcript entry card ─────────────────────────────────────────────────


class _TranscriptCard(QFrame):
    """One transcript entry rendered as a card.

    A card bundles a timestamp / speaker chip, the original (source)
    line, and an optional translation into a single rounded surface so
    the transcript reads as a list of grouped sentences instead of a
    flat wall of alternating-style labels.  ``set_translated`` appends
    (or replaces) the translation after the card is created — matches
    the two-step lifecycle in ``_on_sentence`` where whisper emits the
    original first and the LLM translation arrives later.
    """

    def __init__(  # noqa: PLR0913
        self,
        timestamp_text: str,
        speaker_text: str,
        body_text: str,
        *,
        speaker_id: str = "",
        body_is_translated: bool = False,
        pending_translation: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Initialises a card.

        Args:
            timestamp_text: ``HH:MM:SS → HH:MM:SS`` time range shown
                as a muted monospaced pill.  Empty string hides the
                time chip entirely.
            speaker_text: ``Speaker N`` (or empty) shown as a
                coloured pill next to the timestamp, with a stable
                per-speaker colour from ``_speaker_chip_color``.
            body_text: Text for the card's first line.
            speaker_id: Raw speaker ID (e.g. ``"speaker_0"``) used
                to bind the chip to the page-level alias map for
                rename refreshes.  Empty when speakers are
                unavailable (Whisper) — in that case the chip is
                non-renameable.
            body_is_translated: When True, style *body_text* as
                translation (primary colour / bold).  Used by the
                dual-view right column where the first line IS the
                translation.
            pending_translation: When True, eagerly add a
                ``_TRANSLATION_PLACEHOLDER`` translation slot under
                the body line so the card reads as "translation
                pending" while the LLM worker is in flight.  The
                placeholder is swapped for real text by
                :meth:`set_translated` (or styled as error by
                :meth:`set_error`) when the worker fires.  Only
                meaningful for the stacked single-view card where
                the body is the source; the dual-view RIGHT card
                already uses the placeholder as its body text via
                ``body_is_translated=True``.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(_style_transcript_card())
        self._speaker_id = speaker_id

        # Outer row: chip cluster on the left (time + speaker), then
        # the stacked body + translation column on the right.  Two
        # separate chips instead of one concatenated "00:00:00 →
        # 00:00:02 — Speaker 1" pill so the eye can scan each piece
        # independently and the speaker can carry per-speaker colour.
        # Symmetric top + bottom padding so each divider has equal
        # breathing room on both sides — the inter-row gap above and
        # below a divider should read as the same visual gutter.
        # Padding lives inside the card so the hover background still
        # fills the full row (no layout-spacing dead zone outside any
        # widget).  ``_build_transcript_column`` pairs this with
        # ``setSpacing(0)`` to make the geometry add up cleanly.
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 14, 10, 14)
        outer.setSpacing(10)

        self._chip_container: QWidget | None = None
        self._timestamp_chip: QLabel | None = None
        self._speaker_chip: QLabel | None = None
        if timestamp_text or speaker_text:
            chip_container = QWidget()
            # Deliberately no ``setStyleSheet`` here.  An explicit
            # ``background: transparent`` on the container cascades
            # into the chip QLabels and clobbers their pill-coloured
            # ``background-color``, leaving them rectangular.  Empty
            # stylesheet → no cascade; the QLabels keep their fills.
            chip_row = QHBoxLayout(chip_container)
            chip_row.setContentsMargins(0, 0, 0, 0)
            chip_row.setSpacing(6)
            if timestamp_text:
                # _PillLabel paints its own rounded background — QSS
                # for QLabel won't clip to ``border-radius`` reliably
                # on plain QLabel backgrounds (Qt routes the fill
                # through the palette path that ignores the radius).
                ts_chip = _PillLabel(
                    timestamp_text,
                    color("disabled_bg"),
                )
                ts_chip.setStyleSheet(_style_transcript_timestamp_chip())
                ts_chip.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse,
                )
                chip_row.addWidget(ts_chip)
                self._timestamp_chip = ts_chip
            if speaker_text:
                # Pick the renamable chip subclass whenever we have a
                # speaker_id to bind to.  Without an ID (Whisper or
                # legacy callers), fall back to a read-only pill so
                # double-click silently no-ops instead of dispatching
                # to a nonsense alias map entry.
                if speaker_id:
                    sp_chip: _PillLabel = _RenamableSpeakerChip(
                        speaker_id,
                        speaker_text,
                        _speaker_chip_color(speaker_text),
                    )
                else:
                    sp_chip = _PillLabel(
                        speaker_text,
                        _speaker_chip_color(speaker_text),
                    )
                    sp_chip.setTextInteractionFlags(
                        Qt.TextInteractionFlag.TextSelectableByMouse,
                    )
                sp_chip.setStyleSheet(_style_transcript_speaker_chip())
                chip_row.addWidget(sp_chip)
                self._speaker_chip = sp_chip
            # Pin the chip cluster to the top so it stays aligned with
            # the FIRST line of the body when the body wraps — without
            # this the chip cluster centre-aligns against a tall multi-
            # line column and floats away from "its" line.
            outer.addWidget(chip_container, 0, Qt.AlignmentFlag.AlignTop)
            self._chip_container = chip_container

        # Inner column holds the body line and (later) the translated
        # line, so a translation appended via ``set_translated`` sits
        # under the body — aligned with it under the chip-width gutter
        # — rather than starting back at the card's left edge.
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(6)

        body = QLabel(body_text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        body.setStyleSheet(
            _style_transcript_translated()
            if body_is_translated
            else _style_transcript_original(),
        )
        content.addWidget(body)
        outer.addLayout(content, 1)

        self._content_layout = content
        self._body = body
        self._body_is_translated = body_is_translated

        self._translated: QLabel | None = None
        # Pre-create the translation slot with the placeholder so the
        # card reads as "translation in flight" instead of as a bare
        # source line until the worker fires.  Only for source-body
        # cards — when ``body_is_translated`` is True the body slot
        # ITSELF is the translation, so a second placeholder would be
        # redundant (and visually wrong — two "…" rows stacked).
        if pending_translation and not body_is_translated:
            self.set_translated(_TRANSLATION_PLACEHOLDER)

    def set_chip_visible(self, visible: bool) -> None:
        """Shows or hides the timestamp chip on this card.

        Called when the user toggles the Live-page Timestamps button.
        The speaker chip is controlled separately via
        :meth:`set_speaker_chip_visible`.
        """
        self._timestamp_visible = visible
        if self._timestamp_chip is not None:
            self._timestamp_chip.setVisible(visible)
        self._refresh_chip_container_visibility()

    def set_speaker_chip_visible(self, visible: bool) -> None:
        """Shows or hides the speaker chip on this card.

        Called when the user toggles the Live-page Speakers button.
        The timestamp chip is controlled separately via
        :meth:`set_chip_visible`.
        """
        self._speaker_visible = visible
        if self._speaker_chip is not None:
            self._speaker_chip.setVisible(visible)
        self._refresh_chip_container_visibility()

    def set_speaker_text(self, text: str) -> None:
        """Updates the speaker chip's visible text without rebuilding.

        Called from :meth:`LivePage._refresh_speaker_chips` after a
        rename so every card that shares the speaker's ID picks up
        the new display name without having to be reconstructed.
        """
        if self._speaker_chip is not None:
            self._speaker_chip.setText(text)

    def _refresh_chip_container_visibility(self) -> None:
        """Hides the chip cluster when both chips end up invisible.

        Tracks requested visibility via explicit ``_*_visible`` flags
        rather than querying ``QWidget.isVisible()`` — the latter
        returns False for any widget whose ancestors aren't visible
        yet (e.g. a card just created but not added to a shown
        layout), which would hide chips before they ever get rendered.
        """
        if self._chip_container is None:
            return
        ts_show = (
            self._timestamp_chip is not None
            and getattr(self, "_timestamp_visible", True)
        )
        sp_show = (
            self._speaker_chip is not None
            and getattr(self, "_speaker_visible", True)
        )
        self._chip_container.setVisible(ts_show or sp_show)

    def set_mode_visibility(self, show_src: bool, show_tgt: bool) -> None:
        """Shows / hides source and translation content per display mode.

        Cards always carry both pieces in memory (added as they arrive)
        so a mode flip mid-session retroactively surfaces the piece the
        user just chose to see.  The ``_body`` QLabel might be either
        source or translation depending on how the card was built
        (dual-right cards are created with ``body_is_translated=True``
        where ``_body`` holds the translation).
        """
        body_show = show_tgt if self._body_is_translated else show_src
        self._body.setVisible(body_show)
        if self._translated is not None:
            self._translated.setVisible(show_tgt)
        # When both source and translation are hidden there's nothing
        # left to read on this card; hide the whole frame so empty
        # rows don't leave ghost white space in the transcript.
        self.setVisible(body_show or (self._translated is not None and show_tgt))

    def clear_pending_placeholder(self) -> None:
        """Removes the "…" placeholder if no real translation ever arrived.

        Called from ``_reset_ui_to_ready`` after Stop so cards whose
        LLM worker was abandoned mid-flight (worker still running but
        result silently dropped by ``_on_translated``'s
        ``self._transcriber is None`` guard) don't show a stale "…"
        in the transcript view or in any exported transcript.  No-op
        when the slot already holds real text or an error message.

        The dual-view right card carries the placeholder as its
        ``_body`` (built with ``body_is_translated=True``), so we
        sweep both slots — but only when the on-screen text is
        exactly ``_TRANSLATION_PLACEHOLDER``, never when the user
        already saw real content.
        """
        if (
            self._translated is not None
            and self._translated.text() == _TRANSLATION_PLACEHOLDER
        ):
            self._translated.setVisible(False)
            self._translated.setText("")
        if (
            self._body_is_translated
            and self._body.text() == _TRANSLATION_PLACEHOLDER
        ):
            self._body.setVisible(False)
            self._body.setText("")

    def set_translated(self, text: str) -> None:
        """Appends (or replaces) the translated line inside the card."""
        if self._translated is None:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
            )
            lbl.setStyleSheet(_style_transcript_translated())
            self._content_layout.addWidget(lbl)
            self._translated = lbl
        else:
            self._translated.setText(text)

    def set_body(self, text: str) -> None:
        """Replaces the body label's text in place.

        Used by the dual-view pair-row to swap a placeholder ("…") for
        the real translation when it arrives, without re-creating the
        card.  Keeps row height stable as the card grows.
        """
        self._body.setText(text)

    def set_error(self, text: str) -> None:
        """Marks the translation slot as failed with the given message.

        Reuses the same physical label that ``set_translated`` /
        ``set_body`` use for the translation — just swaps the styling
        to the ``error`` colour — so a user looking at a card can
        tell the LLM tried and failed (vs. is still working, which
        shows the placeholder ``…``).  When the dual-view right card
        was created with ``body_is_translated=True`` (its ``_body``
        is the translation slot), we paint the body itself; otherwise
        — single-view card whose ``_body`` is the original — we
        append a translated label and recolour it.
        """
        if self._body_is_translated:
            self._body.setText(text)
            self._body.setStyleSheet(_style_transcript_error())
            return
        # Single-view card: ensure a translation slot exists, then
        # replace its content with the styled error text.
        if self._translated is None:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse,
            )
            lbl.setStyleSheet(_style_transcript_error())
            self._content_layout.addWidget(lbl)
            self._translated = lbl
        else:
            self._translated.setText(text)
            self._translated.setStyleSheet(_style_transcript_error())


class _DualPairRow(QWidget):
    """Side-by-side row: chip gutter + source card + translation card.

    The pair row owns the timestamp / speaker chips and the row
    padding; the two inner cards strip their own outer margins and
    just render bodies.  Without the gutter the left card's chips
    would eat into the source column and the right card's chipless
    layout would leave the translation a wider runway — visible as a
    noticeably narrower source body in dual mode.  With chips lifted
    onto the row, source and translation each get an equal
    ``(row_width - chip_gutter - inter_column_gap) / 2`` body.
    """

    def __init__(  # noqa: PLR0913
        self,
        timestamp_text: str,
        speaker_text: str,
        left_card: "_TranscriptCard",
        right_card: "_TranscriptCard",
        *,
        speaker_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("_DualPairRow")
        self._speaker_id = speaker_id
        # Qt only auto-paints QSS ``background-color`` on bare
        # ``QWidget()`` instances; for a QWidget *subclass* the
        # background defaults to transparent and the QSS rule
        # silently no-ops unless ``WA_StyledBackground`` is set.
        # Without this attribute the ``:hover`` rule applied but
        # painted nothing — observable as "hover does nothing" on
        # dual-pair rows (single-card hover still worked because
        # _TranscriptCard inherits from QFrame, which is styled).
        # Same fix the ``_DraggablePanel`` overlay subclass uses.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_style_dual_pair_row())

        self._left_card = left_card
        self._right_card = right_card

        # Cards in a pair drop their own border / hover (which now live
        # on the pair row) and their internal padding (the pair owns
        # the outer breathing room around the divider).  Cards are
        # constructed by the caller with empty chip strings, so their
        # internal layout only contains the body QLabel.
        for card in (left_card, right_card):
            card.setStyleSheet(_style_transcript_card_in_pair())
            inner = card.layout()
            if inner is not None:
                inner.setContentsMargins(0, 0, 0, 0)

        self._chip_container: QWidget | None = None
        self._timestamp_chip: QLabel | None = None
        self._speaker_chip: QLabel | None = None
        self._timestamp_visible = True
        self._speaker_visible = True
        if timestamp_text or speaker_text:
            chip_container = QWidget()
            # No setStyleSheet — explicit ``background: transparent``
            # would cascade into the pill QLabels and clobber their
            # coloured fills (same QSS gotcha as _TranscriptCard).
            chip_row = QHBoxLayout(chip_container)
            chip_row.setContentsMargins(0, 0, 0, 0)
            chip_row.setSpacing(6)
            if timestamp_text:
                ts_chip = _PillLabel(timestamp_text, color("disabled_bg"))
                ts_chip.setStyleSheet(_style_transcript_timestamp_chip())
                ts_chip.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse,
                )
                chip_row.addWidget(ts_chip)
                self._timestamp_chip = ts_chip
            if speaker_text:
                if speaker_id:
                    sp_chip: _PillLabel = _RenamableSpeakerChip(
                        speaker_id,
                        speaker_text,
                        _speaker_chip_color(speaker_text),
                    )
                else:
                    sp_chip = _PillLabel(
                        speaker_text,
                        _speaker_chip_color(speaker_text),
                    )
                    sp_chip.setTextInteractionFlags(
                        Qt.TextInteractionFlag.TextSelectableByMouse,
                    )
                sp_chip.setStyleSheet(_style_transcript_speaker_chip())
                chip_row.addWidget(sp_chip)
                self._speaker_chip = sp_chip
            self._chip_container = chip_container

        # Row layout: [chip gutter] [source card] [gap] [translation card].
        # Padding mirrors _TranscriptCard's (10, 14, 10, 14) so the
        # divider hugs the cards with matching breathing room above
        # and below — the inter-row gap reads as one consistent gutter
        # whether the row is single-card or paired.
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 14, 10, 14)
        h.setSpacing(10)
        # Pin every column to the row's top edge.  Default HBox cell
        # alignment is ``AlignVCenter``, which would let a short
        # source line drift down to the middle when the translation
        # wraps to two lines — chips top, source middle, translation
        # top reads as broken vertical rhythm.  Top-aligning all three
        # makes the first line of each column share the same y so the
        # row scans left-to-right cleanly.
        if self._chip_container is not None:
            h.addWidget(
                self._chip_container,
                0,
                Qt.AlignmentFlag.AlignTop,
            )
        h.addWidget(left_card, 1, Qt.AlignmentFlag.AlignTop)
        h.addSpacing(SPACING_SUBSECTION)
        h.addWidget(right_card, 1, Qt.AlignmentFlag.AlignTop)

    def set_chip_visible(self, visible: bool) -> None:
        """Shows or hides the timestamp chip on this pair-row."""
        self._timestamp_visible = visible
        if self._timestamp_chip is not None:
            self._timestamp_chip.setVisible(visible)
        self._refresh_chip_container_visibility()

    def set_speaker_chip_visible(self, visible: bool) -> None:
        """Shows or hides the speaker chip on this pair-row."""
        self._speaker_visible = visible
        if self._speaker_chip is not None:
            self._speaker_chip.setVisible(visible)
        self._refresh_chip_container_visibility()

    def set_speaker_text(self, text: str) -> None:
        """Updates the speaker chip's visible text without rebuilding.

        Mirror of :meth:`_TranscriptCard.set_speaker_text` for the
        dual-pair gutter.  The page's rename-refresh walks both
        card collections, so each owns its own setter.
        """
        if self._speaker_chip is not None:
            self._speaker_chip.setText(text)

    def _refresh_chip_container_visibility(self) -> None:
        """Hides the chip gutter when neither chip is showing.

        Tracks requested visibility via explicit ``_*_visible`` flags
        rather than reading ``QWidget.isVisible()`` (which is False
        until first shown) — same pattern as _TranscriptCard so a
        toggle applied before the row reaches the screen still wins.
        """
        if self._chip_container is None:
            return
        ts_show = (
            self._timestamp_chip is not None and self._timestamp_visible
        )
        sp_show = (
            self._speaker_chip is not None and self._speaker_visible
        )
        self._chip_container.setVisible(ts_show or sp_show)


# ── Floating overlay window ───────────────────────────────────────────────


class _DraggablePanel(QWidget):
    """The overlay's opaque body — drag-to-move + edge-resize.

    The panel is both **draggable** (interior click → move the window)
    and **resizable** (edge/corner click → resize the window).  Cursor
    behaviour depends on where the pointer sits:

    * Anywhere inside the body → four-arrow move cursor; left-drag
      moves the whole window via WM-native ``startSystemMove``.
    * Within ``_EDGE_MARGIN`` of a single edge → single-axis resize
      (``SizeVerCursor`` / ``SizeHorCursor``).
    * Within ``_CORNER_MARGIN`` of a corner → diagonal resize
      (``SizeFDiagCursor`` / ``SizeBDiagCursor``).

    Both drag and resize prefer the WM-native ``startSystemMove`` /
    ``startSystemResize`` and fall back to manual tracking when the
    platform doesn't expose them — manual tracking calls
    ``window.move()`` / ``window.setGeometry()`` which X11 / Win32 /
    AppKit all honour for our frameless tool window.

    **Known Wayland limitation** (Mutter / KWin compositor):
    initiating a second consecutive drag immediately after
    releasing the previous one requires the user to move the
    cursor a few pixels before the WM acknowledges the new
    ``xdg_toplevel.move`` request.  The press IS delivered and
    ``startSystemMove`` returns True; the compositor just
    silently defers the drag until movement-as-confirmation
    arrives.  Manual fallback can't replace it either —
    ``window.move()`` is a no-op for ``xdg_toplevel`` surfaces
    on Wayland (the compositor owns positioning; see
    ``_OverlayWindow._move_by`` for the same documented
    limitation on the Ctrl+Arrow path).

    ``WA_StyledBackground`` is set so the parent's QSS
    ``background-color`` still paints through the subclass.
    """

    # Separate margins: the corner grab zone is larger so diagonal
    # resize is easier to hit without widening the single-axis edge
    # strips, which would eat into the clickable body area.
    _EDGE_MARGIN = 4  # px from a lone edge (horizontal / vertical resize)
    _CORNER_MARGIN = 8  # px from a corner (diagonal resize)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Enables mouse tracking + styled background; no active drag/resize."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Mouse tracking lets us update the cursor shape as the user
        # merely *hovers* over an edge (no button pressed yet).
        self.setMouseTracking(True)
        # Default interior cursor — four-arrow move affordance.
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        # Fallback-only state.
        self._drag_pos: QPoint | None = None
        self._resize_edges: Qt.Edge | None = None
        self._resize_start_global: QPoint | None = None
        self._resize_start_geom = None

    # ── Edge detection ────────────────────────────────────────────────
    def _edges_at(self, pos: QPoint) -> Qt.Edge:
        """Returns which edges the point *pos* is within the resize margin of.

        Corners use the larger ``_CORNER_MARGIN`` (so diagonal resize is
        easier to grab), while lone-axis edges use the tighter
        ``_EDGE_MARGIN`` — otherwise the edge strips would eat into the
        interior drag area. ``Qt.Edge(0)`` means "interior".
        """
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()

        # Corner-first pass: if we're close to a corner on BOTH axes
        # within the corner margin, commit to a diagonal resize.
        cm = self._CORNER_MARGIN
        near_left = x < cm
        near_right = x >= w - cm
        near_top = y < cm
        near_bottom = y >= h - cm
        if (near_left or near_right) and (near_top or near_bottom):
            edges = Qt.Edge(0)
            if near_left:
                edges |= Qt.Edge.LeftEdge
            else:
                edges |= Qt.Edge.RightEdge
            if near_top:
                edges |= Qt.Edge.TopEdge
            else:
                edges |= Qt.Edge.BottomEdge
            return edges

        # Otherwise fall back to the tighter single-edge margin.
        em = self._EDGE_MARGIN
        edges = Qt.Edge(0)
        if x < em:
            edges |= Qt.Edge.LeftEdge
        elif x >= w - em:
            edges |= Qt.Edge.RightEdge
        if y < em:
            edges |= Qt.Edge.TopEdge
        elif y >= h - em:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for_edges(edges: Qt.Edge) -> Qt.CursorShape:
        """Maps an edge mask to the appropriate resize / move cursor.

        Interior returns the four-arrow move cursor — the panel itself
        is the drag surface for the whole overlay window.
        """
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            top_left = bool(edges & Qt.Edge.TopEdge) and bool(edges & Qt.Edge.LeftEdge)
            bot_right = bool(edges & Qt.Edge.BottomEdge) and bool(
                edges & Qt.Edge.RightEdge,
            )
            if top_left or bot_right:
                return Qt.CursorShape.SizeFDiagCursor
            return Qt.CursorShape.SizeBDiagCursor
        if horizontal:
            return Qt.CursorShape.SizeHorCursor
        if vertical:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.SizeAllCursor

    def cursor_for_pos(self, pos: QPoint) -> Qt.CursorShape:
        """Computes the appropriate cursor for a local ``pos`` on the panel.

        Exposed so ``_DragForwardFilter`` can refresh the viewport's
        cursor without relying on ``self.cursor()`` — that one can be
        stale right after a WM-native ``startSystemMove`` because no
        hover ``mouseMoveEvent`` fires between drag-end and re-press.
        """
        return self._cursor_for_edges(self._edges_at(pos))

    # ── Mouse handlers ────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Starts an edge-resize (near a margin) or window-drag (interior)."""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        win = self.window()
        handle = win.windowHandle()
        edges = self._edges_at(event.position().toPoint())

        # ── Near an edge → resize ────────────────────────────────────
        # We DO still prefer WM-native resize here because (a)
        # edge resize is intrinsically motion-based — the user
        # has to drag the edge to resize — so the Wayland
        # "second press needs movement" quirk that hurt drag is
        # invisible here; (b) WM-side resize plays better with
        # multi-monitor and HiDPI scaling than our manual fallback.
        # The interior drag path (below) is the only one that
        # bypasses the WM helper.
        if edges:
            if handle is not None and hasattr(handle, "startSystemResize"):
                try:
                    if handle.startSystemResize(edges):
                        event.accept()
                        self._resize_edges = None
                        return
                except Exception:  # noqa: BLE001 - platform-specific failures
                    pass
            self._resize_edges = edges
            self._resize_start_global = event.globalPosition().toPoint()
            self._resize_start_geom = win.geometry()
            event.accept()
            return

        # ── Interior → move the whole window ─────────────────────────
        # ``startSystemMove`` is the ONLY portable way to move a
        # top-level window on Wayland — manual ``window.move()``
        # is a silent no-op for ``xdg_toplevel`` surfaces there.
        # On X11 / Win32 / AppKit either path works, so prefer
        # the WM-native one to inherit edge-snapping and HiDPI
        # handling for free.  Wayland's "second consecutive drag
        # needs a few pixels of movement before the WM engages"
        # quirk is unavoidable here — see the class docstring.
        if hasattr(win, "_begin_drag_guard"):
            win._begin_drag_guard()
        if handle is not None and hasattr(handle, "startSystemMove"):
            try:
                if handle.startSystemMove():
                    event.accept()
                    self._drag_pos = None
                    return
            except Exception:  # noqa: BLE001 - platform-specific failures
                pass
        self._drag_pos = event.globalPosition().toPoint() - win.pos()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Updates the cursor on hover and drives fallback drag / resize."""
        # Idle hover: just update the cursor shape so the user sees where
        # resize is available.
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self.setCursor(
                self._cursor_for_edges(self._edges_at(event.position().toPoint()))
            )
            super().mouseMoveEvent(event)
            return

        # Fallback manual resize (only used when startSystemResize is
        # unavailable / failed).
        if (
            self._resize_edges
            and self._resize_start_global is not None
            and self._resize_start_geom is not None
        ):
            delta = event.globalPosition().toPoint() - self._resize_start_global
            geom = self._resize_start_geom
            new_x, new_y = geom.x(), geom.y()
            new_w, new_h = geom.width(), geom.height()
            min_w = self.window().minimumWidth()
            min_h = self.window().minimumHeight()
            if self._resize_edges & Qt.Edge.LeftEdge:
                new_w = max(min_w, geom.width() - delta.x())
                new_x = geom.x() + (geom.width() - new_w)
            elif self._resize_edges & Qt.Edge.RightEdge:
                new_w = max(min_w, geom.width() + delta.x())
            if self._resize_edges & Qt.Edge.TopEdge:
                new_h = max(min_h, geom.height() - delta.y())
                new_y = geom.y() + (geom.height() - new_h)
            elif self._resize_edges & Qt.Edge.BottomEdge:
                new_h = max(min_h, geom.height() + delta.y())
            self.window().setGeometry(new_x, new_y, new_w, new_h)
            event.accept()
            return

        # Fallback manual drag.
        if self._drag_pos is not None:
            self.window().move(
                event.globalPosition().toPoint() - self._drag_pos,
            )
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Ends any drag / resize and persists the window's geometry."""
        was_active = (
            self._drag_pos is not None
            or self._resize_edges is not None
            or self._resize_start_global is not None
        )
        was_drag = self._drag_pos is not None
        self._drag_pos = None
        self._resize_edges = None
        self._resize_start_global = None
        self._resize_start_geom = None
        win = self.window()
        # Always release the drag guard — covers both the WM-native
        # startSystemMove path (which may not deliver a reliable
        # mouseReleaseEvent) and the manual fallback.
        if hasattr(win, "_end_drag_guard"):
            win._end_drag_guard()
        # Refresh cursor to match the current pointer position so the
        # four-arrow / edge-resize cursor shows immediately after a
        # drag ends — without this, the cursor can stick on the system
        # "grabbing" shape until the user moves the pointer.
        self.setCursor(
            self._cursor_for_edges(self._edges_at(event.position().toPoint()))
        )
        if was_active or was_drag:
            save = getattr(win, "_save_geometry", None)
            if callable(save):
                save()
            event.accept()
            return
        # WM-native resize also releases without us seeing it — persist
        # the new geometry best-effort.
        save = getattr(self.window(), "_save_geometry", None)
        if callable(save):
            save()
        super().mouseReleaseEvent(event)


# Ctrl+Arrow nudges the overlay by this many pixels per press.  Qt's
# key auto-repeat produces rapid continuous movement on hold, so 20 px
# strikes a balance between "feels responsive" and "still precise".
_OVERLAY_MOVE_STEP = 20

# Ctrl+0 / Ctrl+9 grow / shrink the overlay by this many pixels per
# press, applied to both width and height for a square adjustment.
_OVERLAY_RESIZE_STEP = 20

# Ctrl+] / Ctrl+[ bump the overlay opacity by this fraction per press.
# 10% steps give eight perceivable levels between the 20% floor and
# fully opaque, matching what users expect from similar bracket-pair
# controls in other tools (brush size, zoom, etc.).
_OVERLAY_OPACITY_STEP = 0.1


class _OverlayArrowFilter(QObject):
    """Application-level event filter for Ctrl+Arrow overlay-move.

    QShortcut — even with ``ApplicationShortcut`` context — loses key-press
    events to focused widgets that veto via ``ShortcutOverride`` (buttons
    and combos do this for arrow keys).  An ``eventFilter`` installed on
    ``QApplication.instance()`` runs before per-widget dispatch, so it
    reliably catches Ctrl+Arrow across every platform and focus state.

    The filter is a no-op unless the owning page's overlay is visible,
    so installing one per page across multiple pages doesn't cause
    double-moves — only the page whose overlay is actually shown moves.
    Text-input focus is honoured too: Ctrl+Arrow keeps its word-level
    cursor meaning inside any ``QLineEdit`` / ``QTextEdit`` subclass.
    """

    _DELTAS = {
        Qt.Key.Key_Up: (0, -_OVERLAY_MOVE_STEP),
        Qt.Key.Key_Down: (0, _OVERLAY_MOVE_STEP),
        Qt.Key.Key_Left: (-_OVERLAY_MOVE_STEP, 0),
        Qt.Key.Key_Right: (_OVERLAY_MOVE_STEP, 0),
    }

    def __init__(self, page: QWidget) -> None:
        super().__init__(page)
        self._page = page

    def eventFilter(  # noqa: N802
        self,
        obj: QObject,
        event: QEvent,
    ) -> bool:
        """Catches Ctrl+Arrow before it reaches any widget."""
        if event.type() != QEvent.Type.KeyPress:
            return False
        # event is a QKeyEvent at this point.
        key = event.key()
        if key not in self._DELTAS:
            return False
        # Require Ctrl and reject every other modifier *except* Keypad,
        # because Qt tags numpad arrows with KeypadModifier even on a
        # non-numpad keypress on some layouts.  The ``~Keypad`` mask
        # strips that bit before comparing.
        mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if mods != Qt.KeyboardModifier.ControlModifier:
            return False
        # Honour in-text navigation: Ctrl+Arrow in any editor means
        # word-level cursor move, which wins over overlay movement.
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QApplication,
            QLineEdit,
            QPlainTextEdit,
            QTextEdit,
        )

        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False

        overlay = getattr(self._page, "_overlay", None)
        if overlay is None or not overlay.isVisible():
            return False

        # Delegate so the page's `_move_overlay` stays the single source
        # of truth for the move semantics (text-input guard, geometry
        # save, Wayland-limitation hint).
        dx, dy = self._DELTAS[key]
        move = getattr(self._page, "_move_overlay", None)
        if callable(move):
            move(dx, dy)
        else:
            overlay.move(overlay.x() + dx, overlay.y() + dy)
            save_fn = getattr(overlay, "_save_geometry", None)
            if callable(save_fn):
                save_fn()
        return True  # consume — no other widget sees the Ctrl+Arrow


_OVERLAY_MIN_FONT_PX = 12
# Headroom up to classroom size — fits two lines (original + translated)
# inside the default 200 px-tall overlay.  Previously 140 (stadium-scale)
# clipped content at the overlay default, so it was a misleading cap.
_OVERLAY_MAX_FONT_PX = 72
_OVERLAY_MIN_OPACITY = 0.2
_OVERLAY_DEFAULT_FONT_PX = 18
_OVERLAY_DEFAULT_OPACITY = 0.85
# Smallest opacity delta worth re-rendering for.  ``QWidget.setWindowOpacity``
# clamps to fp32 internally, so anything below ~1e-6 round-trips back to the
# same visible value — short-circuiting saves a paint pass on repeat keypresses.
_OPACITY_EPSILON = 1e-6
# Fixed height reserved for the top-bar chrome. Kept as a stable slot so
# showing/hiding the controls doesn't make the subtitle area jump.
_CHROME_HEIGHT = 22


class _DragForwardFilter(QObject):
    """Forwards mouse press/move/release from the scroll viewport to ``_bg``.

    After wrapping the subtitle labels in a ``QScrollArea``, the viewport
    sits between the labels and the ``_DraggablePanel`` (``_bg``), eating
    mouse events and leaving the drag cursor / resize cursor / drag
    initiation broken.  This filter puts them back: press / move /
    release are re-dispatched to ``_bg`` with coordinates translated into
    its frame, and the cursor is mirrored so hover over an edge still
    shows the resize cursor.  Wheel events are left alone so mouse-wheel
    scrolling of the transcript continues to work.
    """

    _FORWARD_TYPES = frozenset(
        {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
        },
    )

    def __init__(self, target_panel: QWidget) -> None:
        super().__init__(target_panel)
        self._target = target_panel

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Re-dispatches mouse press/move/release onto ``self._target``."""
        if event.type() not in self._FORWARD_TYPES:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        # Translate pos from *obj*'s frame into the target panel's frame.
        src_pt = event.position().toPoint()
        if isinstance(obj, QWidget):
            global_pt = obj.mapToGlobal(src_pt)
        else:
            global_pt = event.globalPosition().toPoint()
        target_pt = self._target.mapFromGlobal(global_pt)
        translated = QMouseEvent(
            event.type(),
            QPointF(target_pt),
            event.globalPosition(),
            event.button(),
            event.buttons(),
            event.modifiers(),
        )
        QApplication.sendEvent(self._target, translated)
        # Refresh cursor from the translated position directly — relying
        # on ``self._target.cursor()`` misses the window right after a
        # ``startSystemMove`` ends (no hover mouseMove fires between
        # drag-end and the next press, so the target's cursor is stale).
        if isinstance(obj, QWidget) and hasattr(self._target, "cursor_for_pos"):
            obj.setCursor(self._target.cursor_for_pos(target_pt))
        return True


def _style_overlay_timestamp_chip(font_px: int) -> str:
    """QSS for the overlay's timestamp pill text.

    Background is painted by :class:`_PillLabel`; the text colour is
    a translucent white so the chip reads cleanly against the dark
    overlay panel without competing with the body text.  Sized
    ``font_px - 4`` so the chip stays a touch smaller than body text
    (chips are metadata, not content) while keeping it readable at
    the slider's lowest end.
    """
    return (
        " color: rgba(255, 255, 255, 200);"
        " font-family: monospace;"
        f" font-size: {max(_OVERLAY_MIN_FONT_PX - 4, font_px - 4)}px;"
        " font-weight: 600;"
        " letter-spacing: 0.4px;"
        " background: transparent;"
        " border: none;"
    )


def _style_overlay_speaker_chip(font_px: int) -> str:
    """QSS for the overlay's speaker pill text.

    Same pill background pattern as the transcript chip but with the
    chip font tracking the overlay's user-controlled font size so the
    chip never looks tiny next to large subtitle text.  Same
    ``font_px - 4`` differential as the timestamp chip so both pills
    read as the same visual tier.
    """
    return (
        " color: #ffffff;"
        f" font-size: {max(_OVERLAY_MIN_FONT_PX - 4, font_px - 4)}px;"
        " font-weight: 600;"
        " letter-spacing: 0.4px;"
        " background: transparent;"
        " border: none;"
    )


def _style_overlay_entry_original(font_px: int) -> str:
    """QSS for the source-text line inside an overlay entry.

    Source and translation share the same font size on the overlay,
    matching the main-window convention.  The visual hierarchy is
    carried by colour (dimmed white vs full white) and weight
    (400 vs 600) — not by size — so the source reads as secondary
    context without shrinking.
    """
    return (
        "background: transparent;"
        f" color: rgba(255, 255, 255, 135);"
        f" font-size: {font_px}px;"
        " font-weight: 400;"
        " padding: 0 0 2px 0;"
    )


def _style_overlay_entry_translated(font_px: int) -> str:
    """QSS for the translated-text line inside an overlay entry."""
    return (
        "background: transparent;"
        f" color: rgba(255, 255, 255, 240);"
        f" font-size: {font_px}px;"
        " font-weight: 600;"
        " padding: 1px 0;"
        " letter-spacing: 0.2px;"
    )


def _style_overlay_entry_error(font_px: int) -> str:
    """QSS for the translation slot when the LLM failed.

    Muted red — saturated enough to register as a failure marker
    against the dark panel but not so bright that a transient
    error visually screams over the rest of the transcript.
    Italic weight separates it visually from the bold "real
    translation" line above without losing scannability.
    """
    return (
        "background: transparent;"
        " color: rgba(255, 107, 114, 220);"
        f" font-size: {max(_OVERLAY_MIN_FONT_PX, font_px - 2)}px;"
        " font-weight: 500;"
        " font-style: italic;"
        " padding: 1px 0;"
    )


class _OverlayEntry(QFrame):
    """One transcript entry rendered inside the floating overlay.

    Mirrors the main-window :class:`_TranscriptCard` structure (chip
    cluster + source line + translation line) so the overlay shows
    identical content — same timestamp / speaker chips, same source
    + translation pairing, same display-mode-aware visibility — only
    re-styled for the overlay's dark translucent panel.

    Reusing the card directly isn't possible because the card carries
    light-theme QSS that would render as black-on-black against the
    overlay; the layout is the same but every label gets overlay-
    specific styles via :func:`_style_overlay_entry_original` and
    :func:`_style_overlay_entry_translated`.
    """

    def __init__(  # noqa: PLR0913
        self,
        timestamp_text: str,
        speaker_text: str,
        source_text: str,
        font_px: int,
        *,
        speaker_id: str = "",
        pending_translation: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._speaker_id = speaker_id
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # QFrame paints its palette window-fill by default — that
        # showed up as a solid dark rectangle behind any entry whose
        # contents grew tall enough to reveal it (translation
        # arrived) while shorter entries remained "transparent".
        # Force a transparent fill so the only thing rendered is the
        # text labels themselves, matching the overlay's panel.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

        self._font_px = font_px
        self._timestamp_visible = True
        self._speaker_visible = True

        # Vertical layout: small chip row on top, then source +
        # translation stacked below at full width.  Previous design
        # put chips in a fixed-width left column which squeezed the
        # text into a narrow band and looked unbalanced — the chips
        # are *metadata*, so they belong above the body, not flanking
        # it.  Discord / Slack / Google Meet captions follow the
        # same "label-above-body" pattern.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._chip_container: QWidget | None = None
        self._timestamp_chip: _PillLabel | None = None
        self._speaker_chip: _PillLabel | None = None
        if timestamp_text or speaker_text:
            chip_container = QWidget()
            chip_container.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground,
            )
            chip_row = QHBoxLayout(chip_container)
            chip_row.setContentsMargins(0, 0, 0, 0)
            chip_row.setSpacing(6)
            if timestamp_text:
                # Translucent white pill, slightly heavier than the
                # previous 38-alpha so the chip reads cleanly at any
                # opacity level — the dark panel was washing it out.
                ts_chip = _PillLabel(
                    timestamp_text,
                    "rgba(255, 255, 255, 55)",
                )
                ts_chip.setStyleSheet(_style_overlay_timestamp_chip(font_px))
                chip_row.addWidget(ts_chip)
                self._timestamp_chip = ts_chip
            if speaker_text:
                sp_chip = _PillLabel(
                    speaker_text,
                    _speaker_chip_color(speaker_text),
                )
                sp_chip.setStyleSheet(_style_overlay_speaker_chip(font_px))
                chip_row.addWidget(sp_chip)
                self._speaker_chip = sp_chip
            # Trailing stretch keeps the chips left-aligned without
            # forcing the row to fill the full entry width.
            chip_row.addStretch()
            outer.addWidget(chip_container)
            self._chip_container = chip_container

        self._source_label = QLabel(source_text)
        self._source_label.setWordWrap(True)
        self._source_label.setStyleSheet(
            _style_overlay_entry_original(font_px),
        )
        self._source_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True,
        )
        outer.addWidget(self._source_label)

        # Translation slot starts hidden so the entry doesn't reserve
        # space for an empty line before the translation arrives.  The
        # caller fills it via :meth:`set_translation` and the layout
        # snaps to make room then.
        # Pre-fill the translation slot with the placeholder when the
        # caller indicates a translation is in flight — matches the
        # stacked main-window card behaviour so the overlay reads as
        # "translation pending" instead of as a bare source line.
        # Visibility is owned by ``set_mode_visibility`` (display
        # mode might hide translations entirely); we just provide the
        # initial text + initial visible state to match.
        initial_text = _TRANSLATION_PLACEHOLDER if pending_translation else ""
        self._translation_label = QLabel(initial_text)
        self._translation_label.setWordWrap(True)
        self._translation_label.setStyleSheet(
            _style_overlay_entry_translated(font_px),
        )
        self._translation_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True,
        )
        self._translation_label.setVisible(bool(initial_text))
        outer.addWidget(self._translation_label)

    def clear_pending_placeholder(self) -> None:
        """Mirrors ``_TranscriptCard.clear_pending_placeholder``.

        Removes the overlay entry's "…" placeholder when the LLM
        worker was abandoned mid-flight by a Stop click — so the
        overlay doesn't keep showing a stale placeholder for
        cancelled translations after the session ended.
        """
        if self._translation_label.text() == _TRANSLATION_PLACEHOLDER:
            self._translation_label.setText("")
            self._translation_label.setVisible(False)

    def set_translation(self, text: str) -> None:
        """Fills (or replaces) the translation slot on this entry."""
        # Reapply the success style — the slot may have been flipped
        # to the error style by an earlier failed retry and the user
        # has now landed a successful translation for the same entry.
        self._translation_label.setProperty("is_error", False)
        self._translation_label.setStyleSheet(
            _style_overlay_entry_translated(self._font_px),
        )
        self._translation_label.setText(text)
        # Show only when there's content and the current display mode
        # exposes translations; visibility for the latter is owned by
        # :meth:`set_mode_visibility`, which the overlay re-runs after
        # every translation update.
        self._translation_label.setVisible(bool(text))

    def set_error(self, text: str) -> None:
        """Marks the translation slot as failed.

        Reuses the same physical label as :meth:`set_translation` so
        the entry's geometry doesn't reflow when a failure replaces
        the (often-still-pending) translation.  Style is swapped to
        the muted-red error variant so the user can see at a glance
        that the LLM gave up on this sentence instead of staring at
        an empty translation slot wondering if it's still loading.
        ``is_error`` property is the source of truth for
        :meth:`apply_font` — keeps the error styling intact when the
        user nudges the font size after a failure.
        """
        self._translation_label.setProperty("is_error", True)
        self._translation_label.setStyleSheet(
            _style_overlay_entry_error(self._font_px),
        )
        self._translation_label.setText(text)
        self._translation_label.setVisible(bool(text))

    def set_chip_visible(self, visible: bool) -> None:
        """Shows or hides the timestamp chip on this entry."""
        self._timestamp_visible = visible
        if self._timestamp_chip is not None:
            self._timestamp_chip.setVisible(visible)
        self._refresh_chip_container_visibility()

    def set_speaker_chip_visible(self, visible: bool) -> None:
        """Shows or hides the speaker chip on this entry."""
        self._speaker_visible = visible
        if self._speaker_chip is not None:
            self._speaker_chip.setVisible(visible)
        self._refresh_chip_container_visibility()

    def set_speaker_text(self, text: str) -> None:
        """Updates the speaker chip's visible text without rebuilding.

        Overlay chips stay read-only :class:`_PillLabel`s — rename
        is initiated from the main window only — but their text
        still has to track the page's alias map so the overlay's
        captions stay in sync with the main transcript after a
        rename.
        """
        if self._speaker_chip is not None:
            self._speaker_chip.setText(text)

    def set_mode_visibility(self, show_src: bool, show_tgt: bool) -> None:
        """Toggles source / translation lines per the current display mode.

        Derives the entry-level visibility from the *requested* booleans
        rather than reading ``_source_label.isVisible()`` /
        ``_translation_label.isVisible()`` — Qt's ``isVisible()``
        returns False whenever an ancestor is hidden, so an entry
        created during overlay backfill (overlay not yet shown) would
        otherwise see both children report False and hide itself.  The
        next ``show()`` on the overlay then ran against an
        already-hidden entry and the user saw an empty pane despite
        the backlog being in the layout.
        """
        self._source_label.setVisible(show_src)
        has_translation = bool(self._translation_label.text())
        show_translation_label = show_tgt and has_translation
        self._translation_label.setVisible(show_translation_label)
        self.setVisible(show_src or show_translation_label)

    def _refresh_chip_container_visibility(self) -> None:
        """Hides the chip cluster when both chips are invisible."""
        if self._chip_container is None:
            return
        ts_show = (
            self._timestamp_chip is not None and self._timestamp_visible
        )
        sp_show = (
            self._speaker_chip is not None and self._speaker_visible
        )
        self._chip_container.setVisible(ts_show or sp_show)

    def apply_font(self, font_px: int) -> None:
        """Re-applies all child styles at the new font size.

        Preserves the error-vs-success style on the translation slot
        by tracking which variant is currently mounted — re-applying
        the success style blindly would silently wipe an in-flight
        error marker when the user nudges the font size.
        """
        was_error = self._translation_label.property("is_error") is True
        self._font_px = font_px
        if self._timestamp_chip is not None:
            self._timestamp_chip.setStyleSheet(
                _style_overlay_timestamp_chip(font_px),
            )
        if self._speaker_chip is not None:
            self._speaker_chip.setStyleSheet(
                _style_overlay_speaker_chip(font_px),
            )
        self._source_label.setStyleSheet(
            _style_overlay_entry_original(font_px),
        )
        self._translation_label.setStyleSheet(
            _style_overlay_entry_error(font_px) if was_error
            else _style_overlay_entry_translated(font_px),
        )


class _OverlayWindow(QWidget):
    """Floating translucent window for live subtitle display."""

    # Emitted when the overlay window becomes hidden (Esc, X-close, or
    # programmatic ``hide()``).  The Live page connects this so the
    # toolbar's "Overlay ON / OFF" button label tracks the actual
    # visibility — without it, dismissing the overlay via Esc leaves
    # the button stuck on "ON".
    closed = Signal()

    def __init__(self, settings_prefix: str = "live") -> None:  # noqa: PLR0915
        """Initializes the translucent overlay with subtitle layout and drag support.

        Args:
            settings_prefix: Namespace for persisted geometry / opacity /
                font size (``"live"``).  Kept as a parameter so future
                callers can host an independent overlay without
                overwriting the Live page's saved geometry.
        """
        super().__init__(None)
        self._settings_prefix = settings_prefix
        # Placeholder state — refs assigned by ``_ensure_placeholder``
        # so ``set_placeholder_listening`` can swap copy in place and
        # ``_apply_placeholder_font`` can re-size labels when the
        # font slider moves.  ``_placeholder_listening`` remembers
        # the variant so a placeholder that's rebuilt later (after
        # clear_lines) picks up the right copy.
        self._placeholder_icon: QLabel | None = None
        self._placeholder_title: QLabel | None = None
        self._placeholder_hint: QLabel | None = None
        self._placeholder_listening: bool = False
        self.setWindowTitle(tr("live.overlay_title"))
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(400, 100)
        # Cap the overlay at the primary screen's usable area so a stray
        # ``_resize_by(+20)`` or a drag can't balloon it past the visible
        # desktop.  Sampled once at construction — if the user moves to a
        # different monitor later, Qt's built-in constraints still apply
        # and the window simply can't grow beyond the stored cap.
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.setMaximumSize(avail.width(), avail.height())
        # Restore persisted geometry if available, otherwise use defaults.
        self._apply_saved_geometry(default_size=(600, 200))
        # Appearance settings (persisted under the caller's namespace).
        self._font_px: int = self._load_int_setting(
            f"{settings_prefix}/overlay_font_size",
            _OVERLAY_DEFAULT_FONT_PX,
            _OVERLAY_MIN_FONT_PX,
            _OVERLAY_MAX_FONT_PX,
        )
        self._opacity: float = self._load_float_setting(
            f"{settings_prefix}/overlay_opacity",
            _OVERLAY_DEFAULT_OPACITY,
            _OVERLAY_MIN_OPACITY,
            1.0,
        )
        # Minimal-captions mode: when True, the overlay hides the
        # timestamp + speaker chips regardless of the page-level
        # ``show_timestamp`` / ``show_speaker`` preferences.  We
        # track the page's "intent" for each chip separately so a
        # later ``set_minimal_mode(False)`` can restore the user's
        # actual show preference without the page having to re-push
        # it.  Intent defaults to True so the first ``add_entry`` /
        # ``apply_chip_visibility`` call shows chips by default if
        # the page never explicitly disabled them.
        #
        # Imports are consolidated here so the minimal-mode state
        # init and the signal listener below share one import block.
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_FONT_SIZE,
            SETTING_LIVE_OVERLAY_MINIMAL,
            SETTING_LIVE_OVERLAY_OPACITY,
            overlay_appearance_changed,
        )
        from src.utils.config_manager import load_setting  # noqa: PLC0415

        self._minimal_mode: bool = bool(
            load_setting(SETTING_LIVE_OVERLAY_MINIMAL, default=False),
        )
        self._intent_show_timestamp: bool = True
        self._intent_show_speaker: bool = True

        # ── Live-sync with Settings → Live tab sliders ───────────────
        # When the user moves the font-size or opacity slider in
        # Settings, the broadcast updates this overlay in real time.
        # ``emit=False`` on the apply helpers stops the change from
        # round-tripping back through the signal.  We disconnect on
        # destroy so a closed overlay can't be re-styled by a stale
        # listener entry.

        def _on_external_appearance_change(key: str, value: float) -> None:
            if key == SETTING_LIVE_OVERLAY_FONT_SIZE:
                new_px = int(value)
                if new_px != self._font_px:
                    self._set_font_size(new_px, emit=False)
            elif key == SETTING_LIVE_OVERLAY_OPACITY:
                new_opacity = float(value)
                if abs(new_opacity - self._opacity) >= _OPACITY_EPSILON:
                    self._set_opacity(new_opacity, emit=False)
            elif key == SETTING_LIVE_OVERLAY_MINIMAL:
                self.set_minimal_mode(bool(value))

        overlay_appearance_changed.connect(_on_external_appearance_change)
        self.destroyed.connect(
            lambda _=None: overlay_appearance_changed.disconnect(
                _on_external_appearance_change,
            ),
        )

        # ── Opaque background panel ──────────────────────────────────
        # Fully opaque black at 100%; lower opacity reduces the background
        # alpha only.  Text stays fully readable at every opacity level —
        # this is a subtitle tool, so legibility wins over a uniform fade.
        # We avoid ``QGraphicsOpacityEffect`` because it rasterises the
        # panel and breaks ``QSizeGrip`` resize, and we avoid
        # ``setWindowOpacity`` because it fades the text along with the
        # background.
        self._bg = _DraggablePanel(self)
        self._apply_bg_style()
        bg_layout = QVBoxLayout(self._bg)
        bg_layout.setContentsMargins(22, 18, 22, 18)
        bg_layout.setSpacing(6)

        # ── Lines area (only content that lives inside the panel) ────
        # The subtitle labels stack inside a QScrollArea so full session
        # history is retained and the user can scroll back.  Auto-scroll
        # snaps to the bottom on new lines as long as the scrollbar was
        # already parked there — if the user scrolled up to read history,
        # auto-scroll pauses until they scroll back down.
        self._lines_container = QWidget()
        self._lines_container.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
        )
        # Mouse events on empty container space pass through to the
        # scroll viewport, where ``_DragForwardFilter`` re-dispatches
        # them onto ``_bg`` (the draggable panel).
        self._lines_container.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
        )
        self._lines_layout = QVBoxLayout(self._lines_container)
        self._lines_layout.setContentsMargins(0, 0, 0, 0)
        # Wider inter-entry gap so each `[chips][source][translation]`
        # block reads as a discrete unit on the dark panel.  8 px was
        # too tight against the new stacked layout — entries blended
        # into a wall of text.
        self._lines_layout.setSpacing(16)
        # Push all labels to the top of the layout — `addStretch()` here
        # absorbs the remaining vertical space when content is smaller
        # than the viewport.  `add_entry` inserts new widgets *before* this
        # trailing stretch (``insertWidget(count - 1, label)``) so they
        # stack top-down in arrival order.
        self._lines_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._lines_container)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
        )
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            " QScrollArea > QWidget { background: transparent; }"
            " QScrollBar:vertical { background: transparent; width: 8px;"
            " margin: 0; }"
            " QScrollBar::handle:vertical { background: rgba(255, 255, 255, 80);"
            " border-radius: 4px; min-height: 24px; }"
            " QScrollBar::handle:vertical:hover"
            " { background: rgba(255, 255, 255, 140); }"
            " QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            " { height: 0; background: transparent; }"
            " QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            " { background: transparent; }",
        )
        bg_layout.addWidget(self._scroll, 1)

        # Auto-scroll uses signal-based stickiness so the snap doesn't
        # race the (potentially-multi-tick) layout pass for wrapped
        # QLabels: when the scrollbar's range grows (new content) and
        # the user is parked at the bottom, snap to the new maximum.
        # The previous ``QTimer.singleShot(0, …)`` approach read
        # ``sb.maximum()`` one event-loop tick after insert, which was
        # often before the wordWrap-driven layout had settled — the
        # snap then landed short of the actual bottom and new
        # sentences appeared to "stop scrolling".  ``valueChanged``
        # tracks user-initiated scrolls so wheel-up disables auto-
        # snap until the user wheels back down.
        self._stick_to_bottom = True
        sb = self._scroll.verticalScrollBar()
        sb.rangeChanged.connect(self._on_scroll_range_changed)
        sb.valueChanged.connect(self._on_scroll_value_changed)

        # Forward mouse events from the scroll area viewport onto the
        # draggable panel so clicking empty subtitle space still drags
        # the overlay / shows the edge-resize cursor on hover.  Wheel
        # events are left untouched so transcript scroll still works.
        self._drag_forward_filter = _DragForwardFilter(self._bg)
        self._scroll.viewport().setMouseTracking(True)
        self._scroll.viewport().installEventFilter(self._drag_forward_filter)

        # Resize is handled by _DraggablePanel: the pointer near any
        # edge (within _EDGE_MARGIN / _CORNER_MARGIN) switches to a
        # resize cursor and initiates a WM-native resize.

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._bg)

        self._drag_pos = None
        # Drag is handled by _DraggablePanel (on `self._bg`).

        # Show a hint so the user sees *something* in the overlay
        # before Start kicks off.
        self._ensure_placeholder()

        # Own copies of the overlay keyboard shortcuts.  The page also
        # owns them so Ctrl+= / Ctrl+- / Ctrl+Arrow work when the main
        # window is active; these handle the inverse case — when the
        # overlay itself is the active top-level window (after the user
        # clicks it to drag, for instance).  Default ``WindowShortcut``
        # context naturally scopes each copy to its own top-level.
        from src.constants.shortcuts import (  # noqa: PLC0415
            get_shortcut,
            shortcuts_changed,
        )

        self._own_shortcuts: list[QShortcut] = []

        def _bind(shortcut_id: str, handler: Callable[[], None]) -> None:
            sc = QShortcut(QKeySequence(get_shortcut(shortcut_id)), self)
            sc.activated.connect(handler)
            sc.setProperty("shortcut_id", shortcut_id)
            self._own_shortcuts.append(sc)

        # Font shortcuts stay on the overlay because the page's copies
        # use WindowShortcut context and don't fire when the overlay is
        # the active top-level.  Move shortcuts are NOT duplicated here
        # because the page wires them with ApplicationShortcut context,
        # which already fires regardless of which window is active — a
        # duplicate overlay-scoped copy would cause double-moves.
        _bind("common.overlay_font_bigger", lambda: self._change_font(2))
        _bind("common.overlay_font_smaller", lambda: self._change_font(-2))
        _bind(
            "common.overlay_opacity_up",
            lambda: self._change_opacity(_OVERLAY_OPACITY_STEP),
        )
        _bind(
            "common.overlay_opacity_down",
            lambda: self._change_opacity(-_OVERLAY_OPACITY_STEP),
        )

        def _sync() -> None:
            for sc in self._own_shortcuts:
                sc.setKey(
                    QKeySequence(get_shortcut(sc.property("shortcut_id"))),
                )

        shortcuts_changed.connect(_sync)
        # Keep a strong ref so the sync callback isn't GC'd.
        self._own_shortcuts_sync = _sync

    def _geometry_setting_key(self) -> str:
        """Returns the namespaced settings key for this overlay's geometry."""
        return f"{self._settings_prefix}/overlay_geometry"

    def _apply_saved_geometry(self, default_size: tuple[int, int]) -> None:
        """Restores ``(x, y, w, h)`` from settings if present; else uses defaults."""
        saved = load_setting(self._geometry_setting_key(), "")
        if saved:
            try:
                x, y, w, h = (int(p) for p in str(saved).split(","))
                self.setGeometry(x, y, w, h)
                return
            except (ValueError, TypeError):
                logger.warning("Malformed overlay geometry %r; using defaults", saved)
        self.resize(*default_size)
        # No saved position — drop the overlay at the bottom of the
        # primary screen, centred horizontally, like a TV subtitle.
        self._move_to_bottom_center()

    def _move_to_bottom_center(self) -> None:
        """Snaps the overlay to the bottom-centre of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        # Sit ~40 px above the bottom edge of the usable area so the
        # overlay doesn't clip the taskbar on desktops with a dock.
        margin_bottom = 40
        x = avail.x() + (avail.width() - self.width()) // 2
        y = avail.y() + avail.height() - self.height() - margin_bottom
        self.move(max(avail.x(), x), max(avail.y(), y))
        self._save_geometry()

    def _save_geometry(self) -> None:
        """Persists the current position and size to settings."""
        g = self.geometry()
        save_setting(
            self._geometry_setting_key(),
            f"{g.x()},{g.y()},{g.width()},{g.height()}",
        )

    @staticmethod
    def _load_int_setting(key: str, default: int, lo: int, hi: int) -> int:
        """Returns the clamped integer value stored at *key* (or *default*)."""
        raw = load_setting(key, "")
        try:
            value = int(raw) if str(raw).strip() else default
        except (ValueError, TypeError):
            value = default
        return max(lo, min(hi, value))

    @staticmethod
    def _load_float_setting(key: str, default: float, lo: float, hi: float) -> float:
        """Returns the clamped float value stored at *key* (or *default*)."""
        raw = load_setting(key, "")
        try:
            value = float(raw) if str(raw).strip() else default
        except (ValueError, TypeError):
            value = default
        return max(lo, min(hi, value))

    def _apply_bg_style(self) -> None:
        """Writes the panel background with an alpha matching self._opacity.

        100% opacity → solid black; 20% → very transparent black. Text
        colour is unaffected, so subtitles stay readable at any opacity.
        """
        alpha = max(0, min(255, int(self._opacity * 255)))
        self._bg.setStyleSheet(
            f"background-color: rgba(0, 0, 0, {alpha}); border-radius: 16px;",
        )

    def _on_opacity_changed(self, percent: int) -> None:
        """Applies and persists the user's opacity choice (20–100%)."""
        new_opacity = max(
            _OVERLAY_MIN_OPACITY,
            min(1.0, percent / 100.0),
        )
        self._set_opacity(new_opacity, emit=True)

    def _change_opacity(self, delta: float) -> None:
        """Nudges overlay opacity by ``delta`` (fraction), clamped to [min, 1]."""
        new_opacity = max(
            _OVERLAY_MIN_OPACITY,
            min(1.0, self._opacity + delta),
        )
        if abs(new_opacity - self._opacity) < _OPACITY_EPSILON:
            return
        self._set_opacity(new_opacity, emit=True)

    def _set_opacity(self, new_opacity: float, *, emit: bool) -> None:
        """Applies, persists, and (optionally) broadcasts an opacity change.

        Single source of truth for "make the overlay this opaque" so the
        keyboard shortcut, the explicit opacity setter, and the
        ``overlay_appearance_changed`` listener all funnel through the
        same path.  ``emit=False`` is used by the listener so an external
        change doesn't bounce back as another emission.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_OPACITY,
            overlay_appearance_changed,
        )

        self._opacity = new_opacity
        self._apply_bg_style()
        save_setting(
            f"{self._settings_prefix}/overlay_opacity",
            f"{self._opacity:.3f}",
        )
        if emit:
            overlay_appearance_changed.emit(
                SETTING_LIVE_OVERLAY_OPACITY, self._opacity,
            )

    def _move_by(self, dx: int, dy: int) -> None:
        """Nudges the overlay by ``(dx, dy)`` pixels and persists geometry.

        Works on X11 / macOS / Windows.  Silent no-op on Mutter/GNOME
        Wayland: the compositor ignores client-requested repositioning
        for xdg_toplevel windows (even across hide/show round-trips).
        See :class:`_OverlayArrowFilter` for the key-handling path.
        """
        self.move(self.x() + dx, self.y() + dy)
        self._save_geometry()

    def _resize_by(self, dw: int, dh: int) -> None:
        """Grows/shrinks the overlay by ``(dw, dh)`` pixels and persists size.

        Clamps to ``[minimumSize, maximumSize]`` so Ctrl+9 held down
        won't shrink below a usable size and Ctrl+0 held down won't
        grow past the primary screen's usable area.  Works on X11 /
        macOS / Windows.  Silent no-op on Mutter/GNOME Wayland — the
        compositor refuses client-requested size changes for frameless
        Tool windows the same way it refuses repositioning.  The resize
        shortcuts carry ``skip_on_wayland=True`` so they don't appear in
        the Shortcuts tab there; users resize via the mouse on the edges.
        """
        new_w = max(
            self.minimumWidth(),
            min(self.maximumWidth(), self.width() + dw),
        )
        new_h = max(
            self.minimumHeight(),
            min(self.maximumHeight(), self.height() + dh),
        )
        self.resize(new_w, new_h)
        self._save_geometry()

    def _change_font(self, delta: int) -> None:
        """Nudges the subtitle font size by ``delta`` pixels, clamped."""
        new_px = max(
            _OVERLAY_MIN_FONT_PX,
            min(_OVERLAY_MAX_FONT_PX, self._font_px + delta),
        )
        if new_px == self._font_px:
            return
        self._set_font_size(new_px, emit=True)

    def _set_font_size(self, new_px: int, *, emit: bool) -> None:
        """Applies, persists, and (optionally) broadcasts a font-size change.

        Single source of truth for "make the overlay text this big" so
        the in-overlay keyboard shortcut and the
        ``overlay_appearance_changed`` listener funnel through one
        path.  ``emit=False`` is used by the listener so an external
        change doesn't bounce back as another emission.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_FONT_SIZE,
            overlay_appearance_changed,
        )

        self._font_px = new_px
        save_setting(
            f"{self._settings_prefix}/overlay_font_size",
            str(self._font_px),
        )
        # Re-style every existing entry in place.  Entries own their
        # own per-child styling (chips, source, translation), so we
        # forward the new font via ``apply_font`` instead of patching
        # their internals here.
        #
        # NOTE: the empty-state placeholder is sized from overlay
        # *width × height*, NOT this slider — it's UI furniture
        # ("this overlay is empty"), not transcript content.  See
        # ``_apply_placeholder_font`` and ``resizeEvent``.
        for entry in self._iter_entries():
            entry.apply_font(new_px)
        if emit:
            overlay_appearance_changed.emit(
                SETTING_LIVE_OVERLAY_FONT_SIZE, new_px,
            )

    def _line_style(self, is_translated: bool) -> str:
        """Returns the inline QSS for a subtitle label.

        ``background: transparent`` is explicit so the label can never
        inherit a solid fill from the panel's styled background (which
        some Qt styles otherwise propagate to children, drawing a black
        pill around the text).
        """
        if is_translated:
            # Translated text is the primary content — pure white, a hair
            # heavier weight, slight top/bottom breathing room.
            return (
                "background: transparent;"
                " color: rgba(255, 255, 255, 240);"
                f" font-size: {self._font_px}px;"
                " font-weight: 600;"
                " padding: 1px 0;"
                " letter-spacing: 0.2px;"
            )
        # Original text: same size as the translation; the visual
        # hierarchy comes from colour (dimmed) and weight (regular),
        # mirroring the main-window convention.
        return (
            "background: transparent;"
            " color: rgba(255, 255, 255, 135);"
            f" font-size: {self._font_px}px;"
            " font-weight: 400;"
            " padding: 0 0 2px 0;"
        )

    def _on_scroll_range_changed(self, _min: int, max_value: int) -> None:
        """Snaps to the new bottom whenever content grows and we were stuck.

        Connected to ``QScrollBar.rangeChanged`` so the snap fires
        AFTER Qt has finished the layout pass — robust against the
        wordWrap two-step relayout that left the previous deferred-
        QTimer approach reading a stale ``maximum()``.
        """
        if self._stick_to_bottom:
            self._scroll.verticalScrollBar().setValue(max_value)

    def _on_scroll_value_changed(self, value: int) -> None:
        """Updates stickiness based on whether the user is at the bottom."""
        sb = self._scroll.verticalScrollBar()
        self._stick_to_bottom = (
            value >= sb.maximum() - _AUTOSCROLL_BOTTOM_TOLERANCE
        )

    def _insert_line_widget(self, widget: QLabel) -> None:
        """Inserts *widget* before the trailing stretch so lines stack top-down."""
        # Layout is ``[label_0, label_1, …, label_n, stretch]``; the
        # stretch lives at ``count() - 1`` and absorbs extra space
        # beneath the labels.
        insert_index = max(0, self._lines_layout.count() - 1)
        self._lines_layout.insertWidget(insert_index, widget)

    def add_entry(  # noqa: PLR0913
        self,
        timestamp: str,
        speaker: str,
        source_text: str,
        *,
        show_timestamp: bool,
        show_speaker: bool,
        show_src: bool,
        show_tgt: bool,
        speaker_id: str = "",
        pending_translation: bool = False,
    ) -> _OverlayEntry:
        """Adds a transcript entry (chips + source + translation slot).

        Mirrors the main-window card structure so the overlay shows
        identical content for each sentence.  The translation slot
        starts hidden; the caller fills it via
        :meth:`set_last_translation` when the LLM result arrives.

        ``speaker_id`` lets the page-level rename refresh find this
        entry's chip later — the *displayed* chip text in ``speaker``
        may already be a user-chosen alias by the time this entry is
        backfilled.
        """
        # Drop the placeholder hint the moment real content arrives.
        self._remove_placeholder()

        effective_ts, effective_speaker = self._record_chip_intent(
            show_timestamp, show_speaker,
        )

        entry = _OverlayEntry(
            timestamp,
            speaker,
            source_text,
            self._font_px,
            speaker_id=speaker_id,
            pending_translation=pending_translation,
        )
        entry.set_chip_visible(effective_ts)
        entry.set_speaker_chip_visible(effective_speaker)
        entry.set_mode_visibility(show_src, show_tgt)
        self._insert_line_widget(entry)
        # Auto-scroll is wired via the scrollbar's ``rangeChanged``
        # signal in __init__ — when this insert grows the scroll
        # range and we were parked at the bottom, the snap fires
        # AFTER the layout pass instead of racing it.
        return entry

    def set_last_translation(
        self,
        text: str,
        *,
        show_src: bool,
        show_tgt: bool,
    ) -> None:
        """Fills (or replaces) the translation on the most recent entry.

        Used by both the synchronous Soniox path and the streaming
        Whisper path; in streaming mode the call lands repeatedly with
        the accumulated translation so each chunk extends the same
        slot rather than spawning a new line.  Re-applies the display
        mode after the text update so a freshly-arrived translation
        immediately respects an Original-only / Translation-only
        preference.
        """
        entry = self._last_entry()
        if entry is None:
            return
        entry.set_translation(text)
        entry.set_mode_visibility(show_src, show_tgt)

    def set_last_error(
        self,
        text: str,
        *,
        show_src: bool,
        show_tgt: bool,
    ) -> None:
        """Marks the most recent entry's translation slot as failed.

        Mirrors :meth:`set_last_translation` but flips the slot to
        the muted-red error variant.  Without this surface, an
        overlay user staring at the floating panel during a
        presentation has no way to tell a failed translation from a
        slow-to-arrive one — the slot just stays empty forever.
        """
        entry = self._last_entry()
        if entry is None:
            return
        entry.set_error(text)
        entry.set_mode_visibility(show_src, show_tgt)

    def apply_chip_visibility(
        self,
        show_timestamp: bool,
        show_speaker: bool,
    ) -> None:
        """Re-applies the timestamp / speaker chip toggles to every entry.

        Stores the page-side "intent" so that toggling minimal-mode
        on/off later can restore the underlying preference without
        the page having to re-push it.  Effective visibility is
        ``intent AND not minimal_mode``.
        """
        effective_ts, effective_speaker = self._record_chip_intent(
            show_timestamp, show_speaker,
        )
        for entry in self._iter_entries():
            entry.set_chip_visible(effective_ts)
            entry.set_speaker_chip_visible(effective_speaker)

    def _record_chip_intent(
        self,
        show_timestamp: bool,
        show_speaker: bool,
    ) -> tuple[bool, bool]:
        """Stores the page's chip-visibility intent and returns effective state.

        Minimal-mode is an overlay-only override; the page's underlying
        preference persists in ``_intent_show_*`` so flipping minimal
        off later restores chips without the page having to re-push
        them.  Centralised here so ``add_entry``, ``apply_chip_visibility``,
        and any future chip-mutating path share one source of truth.

        Returns:
            ``(effective_timestamp, effective_speaker)`` —
            ``intent AND not minimal_mode``.
        """
        self._intent_show_timestamp = show_timestamp
        self._intent_show_speaker = show_speaker
        return self._effective_chip_visibility()

    def _effective_chip_visibility(self) -> tuple[bool, bool]:
        """Returns the current effective chip visibility.

        Read-only view: applies the minimal-mode override to the
        stored ``_intent_show_*`` state without mutating either.
        Used by ``set_minimal_mode`` to re-style entries when the
        override flips without losing the page's intent.
        """
        return (
            self._intent_show_timestamp and not self._minimal_mode,
            self._intent_show_speaker and not self._minimal_mode,
        )

    def set_minimal_mode(self, enabled: bool) -> None:
        """Hides (or restores) the timestamp + speaker chips on the overlay.

        Minimal-captions mode is an overlay-only override: the
        underlying page-side ``show_timestamp`` / ``show_speaker``
        intent is preserved in ``_intent_show_*``, so flipping
        minimal back off restores chips per the user's original
        preference without the page having to re-push it.
        """
        if enabled == self._minimal_mode:
            return
        self._minimal_mode = enabled
        effective_ts, effective_speaker = self._effective_chip_visibility()
        for entry in self._iter_entries():
            entry.set_chip_visible(effective_ts)
            entry.set_speaker_chip_visible(effective_speaker)

    def apply_mode_visibility(self, show_src: bool, show_tgt: bool) -> None:
        """Re-applies the display-mode (source / translation) to every entry."""
        for entry in self._iter_entries():
            entry.set_mode_visibility(show_src, show_tgt)

    def _iter_entries(self) -> Generator[_OverlayEntry, None, None]:
        """Yields every overlay entry widget in insertion order."""
        for i in range(self._lines_layout.count()):
            item = self._lines_layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, _OverlayEntry):
                yield widget

    def _last_entry(self) -> _OverlayEntry | None:
        """Returns the most recently added entry, or None if there are none."""
        for i in range(self._lines_layout.count() - 1, -1, -1):
            item = self._lines_layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, _OverlayEntry):
                return widget
        return None

    def clear_lines(self) -> None:
        """Removes all entries and restores the placeholder hint."""
        # Iterate widgets only — the trailing stretch at the end of the
        # layout has no widget and must survive.  ``setParent(None)``
        # before ``deleteLater()`` is load-bearing: ``takeAt`` only
        # removes the widget from the *layout*, it stays parented to
        # ``_lines_container`` and Qt keeps painting it at its last
        # geometry until DeferredDelete runs.  Without the reparent,
        # an overlay backfill (which clears + re-adds entries in one
        # turn) would leave the original placeholder QLabel hovering
        # underneath the freshly-inserted entries.
        for i in range(self._lines_layout.count() - 1, -1, -1):
            item = self._lines_layout.itemAt(i)
            widget = item.widget() if item else None
            if widget is not None:
                self._lines_layout.takeAt(i)
                widget.setParent(None)
                widget.deleteLater()
        self._ensure_placeholder()

    def _ensure_placeholder(self) -> None:
        """Shows a muted hint when the overlay has no transcribed lines yet.

        Mirrors the main window's empty-state design: a centred mic
        icon stacked above the title + hint, so the overlay's empty
        look is recognisably the same UI surface (just adapted to the
        dark translucent background with muted-white text instead of
        the page's theme colours).  Storing the title/hint label
        refs lets :meth:`set_placeholder_listening` swap the copy
        between idle and listening variants while the overlay stays
        open.
        """
        # Presence check — any label (placeholder or real) means skip.
        for i in range(self._lines_layout.count()):
            item = self._lines_layout.itemAt(i)
            if item is not None and item.widget() is not None:
                return

        container = QWidget()
        container.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True,
        )
        container.setProperty("is_placeholder", True)
        container.setStyleSheet("background: transparent;")
        # Make the container expand vertically so the equal-stretch
        # padding actually centres the content (otherwise the container
        # would size to its min hint and sit against the top edge of
        # the lines area).
        container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)
        # Equal stretches above and below = true vertical centring.
        layout.addStretch(1)

        icon = QLabel("🎙️")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel(
            tr(
                "live.empty_title_listening"
                if self._placeholder_listening
                else "live.empty_title",
            ),
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Long localised strings (e.g. German) overflow narrow
        # overlays — wrap on word boundaries so the title fits.
        title.setWordWrap(True)
        # State-aware language refresh: ``set_placeholder_listening``
        # picks between idle and listening variants based on
        # ``_placeholder_listening``.  Routing the apply_language
        # callback through it preserves the current state across a
        # locale switch (a naive setText would force the idle text
        # even mid-session).
        title.apply_language = lambda: self.set_placeholder_listening(
            listening=self._placeholder_listening,
        )
        layout.addWidget(title)

        hint = QLabel(
            _bind_last_word(
                tr(
                    "live.empty_hint_listening"
                    if self._placeholder_listening
                    else "live.empty_hint",
                ),
            ),
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        # Same state-aware refresh — hint also has idle/listening variants.
        hint.apply_language = lambda: self.set_placeholder_listening(
            listening=self._placeholder_listening,
        )
        layout.addWidget(hint)
        layout.addStretch(1)

        # Stash refs so set_placeholder_listening can swap copy and
        # ``_apply_placeholder_font`` can re-style them when the
        # overlay is resized.
        self._placeholder_icon = icon
        self._placeholder_title = title
        self._placeholder_hint = hint
        self._apply_placeholder_font()
        # While the placeholder is the only content, suppress the
        # scrollbar — there's nothing to scroll, and tight geometries
        # (minimum 400×100) leave so little vertical room that the
        # icon + title + hint cluster can technically exceed the
        # viewport even with conservative size budgets.  ``ScrollBarAlwaysOff``
        # also reclaims the ~8 px the scrollbar would have stolen on
        # the right side, widening the area the centred placeholder
        # uses.  Restored to ``ScrollBarAsNeeded`` in
        # ``_remove_placeholder`` so transcript content scrolls
        # normally once entries arrive.
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        # Insert with a strong stretch factor so the container claims
        # nearly all the vertical space available in the scroll area.
        # ``_lines_layout`` ends in ``addStretch(1)`` so that entries
        # stack top-down; without our own large stretch here the
        # placeholder would shrink to its sizeHint and sit against the
        # top, not vertically centred.  Combined with the container's
        # own ``addStretch(1)`` above and below its content, this
        # places the icon/title/hint cluster in the true centre of the
        # overlay.
        insert_index = max(0, self._lines_layout.count() - 1)
        self._lines_layout.insertWidget(insert_index, container, 999)

    def _apply_placeholder_font(self) -> None:
        """Sizes placeholder icon / title / hint to fit the overlay's box.

        Decoupled from the transcript-text slider: the placeholder is
        a "this overlay is empty" marker, not transcript content, so
        sizing it from the overlay's current dimensions keeps it
        proportionate to whatever shape the user dragged the window
        into.  Re-invoked on every ``resizeEvent`` for live fit.

        Both width and height bound the title size so the content
        never overflows and triggers a scrollbar.  The icon size is
        also clamped to a fraction of the overlay height — a
        proportional ``title × 2.2`` icon overflows the viewport at
        the minimum overlay geometry (400×100), where ~36 px of
        bg-panel margin leave only 64 px of usable height for the
        whole icon + title + (potentially-wrapped) hint stack.
        """
        if (
            self._placeholder_icon is None
            or self._placeholder_title is None
            or self._placeholder_hint is None
        ):
            return
        width = max(self.width(), self.minimumWidth())
        height = max(self.height(), self.minimumHeight())
        # ``height / 10`` budget accounts for: bg-panel margins (36 px),
        # container margins (16 px), two stretches, and worst-case
        # hint wrap to two lines — leaves slack so a short overlay
        # never overflows.
        title_px = max(11, min(48, round(min(width / 24, height / 10))))
        hint_px = max(9, title_px - 4)
        # Icon is capped both by its proportional target AND by a
        # fraction of overlay height (~⅓), whichever is smaller.  At
        # the minimum 400×100 geometry the height cap dominates so
        # the icon shrinks enough to leave room for title + hint.
        icon_px = min(round(title_px * 1.8), max(18, round(height * 0.30)))
        self._placeholder_icon.setStyleSheet(
            "color: rgba(255, 255, 255, 150);"
            f" font-size: {icon_px}px;"
            " background: transparent;"
            " padding: 0;",
        )
        self._placeholder_title.setStyleSheet(
            "color: rgba(255, 255, 255, 240);"
            f" font-size: {title_px}px;"
            " font-weight: 600;"
            " background: transparent;"
            " padding: 4px 8px 0 8px;",
        )
        self._placeholder_hint.setStyleSheet(
            "color: rgba(255, 255, 255, 160);"
            f" font-size: {hint_px}px;"
            " background: transparent;"
            " padding: 0 16px;",
        )

    def _remove_placeholder(self) -> None:
        """Removes the placeholder hint, if present.

        See :meth:`clear_lines` for why ``setParent(None)`` is required
        before ``deleteLater()`` — the same orphan-still-painted bug
        applies here.
        """
        for i in range(self._lines_layout.count()):
            item = self._lines_layout.itemAt(i)
            widget = item.widget() if item else None
            if widget is not None and widget.property("is_placeholder"):
                self._lines_layout.takeAt(i)
                widget.setParent(None)
                widget.deleteLater()
                self._placeholder_icon = None
                self._placeholder_title = None
                self._placeholder_hint = None
                # Real content is about to arrive — re-enable the
                # scrollbar so transcripts that overflow the viewport
                # become scrollable.  Paired with the ``AlwaysOff``
                # set in ``_ensure_placeholder``.
                self._scroll.setVerticalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAsNeeded,
                )
                return

    def set_placeholder_listening(self, *, listening: bool) -> None:
        """Swaps the placeholder title/hint between idle and listening.

        Mirrors the main window's ``_set_empty_state_listening``:
        once the user clicks Start the placeholder should stop
        contradicting the status pill ("Press Start" → "Listening…").
        Public so the Live page can call it from its start/stop
        handlers.  No-op when no placeholder is currently rendered
        (entries already replaced it).
        """
        self._placeholder_listening = listening
        if self._placeholder_title is None or self._placeholder_hint is None:
            return
        self._placeholder_title.setText(
            tr("live.empty_title_listening" if listening else "live.empty_title"),
        )
        self._placeholder_hint.setText(
            _bind_last_word(
                tr(
                    "live.empty_hint_listening"
                    if listening
                    else "live.empty_hint",
                ),
            ),
        )

    # ── Drag support ─────────────────────────────────────────────────
    def _begin_drag(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def _continue_drag(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _end_drag(self) -> None:
        if self._drag_pos is not None:
            self._drag_pos = None
            self._save_geometry()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Records drag start position."""
        self._begin_drag(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Moves the window during drag."""
        self._continue_drag(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Clears drag state and persists the new position."""
        self._end_drag()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        """Persists the new size and re-fits the placeholder on resize."""
        super().resizeEvent(event)
        # Only save once the widget has been shown (avoids clobbering the
        # saved size during initial layout while geometry is still default).
        if self.isVisible():
            self._save_geometry()
        # Re-fit the empty-state placeholder to the new width — its
        # icon / title / hint sizes are derived from overlay width
        # (not the transcript-text slider), so dragging the overlay
        # corner live-resizes the placeholder to match.
        self._apply_placeholder_font()

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        """Closes the overlay on Esc for keyboard dismissal."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event) -> None:  # noqa: ANN001, N802
        """Emits ``closed`` so callers can sync UI state with visibility.

        Fires on Esc-close, the window's X button, and programmatic
        ``hide()`` — all three paths converge here, so a single signal
        keeps the toolbar button label in sync regardless of how the
        user dismissed the overlay.
        """
        super().hideEvent(event)
        self.closed.emit()


# ── Whisper model preloader ─────────────────────────────────────────────


class _WhisperPreloadWorker(QThread):
    """Background QThread that warms the Whisper model into the engine cache.

    Spawned from ``LivePage.showEvent`` (gated on disk-cache presence so
    we never silently start a download).  Has no signals — the load
    result lives in the ``live_engine._cached_model`` module singleton
    that the live transcriber reads anyway.
    """

    def __init__(self, model_size: str) -> None:
        """Stores the size to preload in ``run``."""
        super().__init__()
        self._model_size = model_size

    def run(self) -> None:
        """Loads the model, swallowing errors (preload is best-effort)."""
        from src.core.live_engine import preload_whisper_model  # noqa: PLC0415

        preload_whisper_model(self._model_size)


# ── Engine teardown worker ────────────────────────────────────────────────


class _EngineStopWorker(QThread):
    """Off-thread engine teardown so Stop never freezes the UI thread.

    ``LiveTranscriber.stop()`` joins the Whisper processing thread with
    a 5-second timeout (faster-whisper has no inference-cancellation
    hook, so the worker has to wait for the current ``model.transcribe``
    call to return).  The Soniox audio-feed teardown adds another
    ``parec.terminate → wait → kill → wait`` chain plus two thread
    joins.  Worst case before this class existed: ~12 s of frozen UI
    on a single Stop click — long enough for Linux window managers to
    flag the app as "Python doesn't respond".

    Every blocking call stays on this worker; the page's ``_stop_listening``
    nulls the engine + audio-feed references on ``self`` before
    spawning us, so the existing late-signal guards (``self._transcriber
    is None`` checks in ``_on_sentence`` / ``_on_status`` / etc.) drop
    any callbacks the engine emits during teardown.
    """

    def __init__(  # noqa: PLR0913, ANN401
        self,
        transcriber: Any,  # noqa: ANN401 — duck-typed STT object
        *,
        soniox_stream: Any = None,  # noqa: ANN401 — sounddevice.InputStream
        soniox_parec: Any = None,  # noqa: ANN401 — subprocess.Popen
        soniox_parec_thread: Any = None,  # noqa: ANN401 — threading.Thread
        soniox_mixer_stop: Any = None,  # noqa: ANN401 — threading.Event
        soniox_mixer_thread: Any = None,  # noqa: ANN401 — threading.Thread
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._transcriber = transcriber
        self._soniox_stream = soniox_stream
        self._soniox_parec = soniox_parec
        self._soniox_parec_thread = soniox_parec_thread
        self._soniox_mixer_stop = soniox_mixer_stop
        self._soniox_mixer_thread = soniox_mixer_thread

    def run(self) -> None:
        """Tears down audio feed first, then the transcriber.

        Order matters: shutting the audio source(s) first stops the
        producer side of the pipeline so the transcriber's read loop
        sees the end-of-stream sentinel and exits cleanly, rather
        than blocking on its full join timeout while still being
        fed bytes.
        """
        import subprocess  # noqa: PLC0415

        # Soniox path: mic InputStream → parec subprocess → reader
        # thread → mixer thread.  Each may be None when the active
        # audio source didn't open it.
        stream = self._soniox_stream
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001 — log + continue cleanup
                logger.debug("soniox stream teardown failed", exc_info=True)

        proc = self._soniox_parec
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(Exception):
                    proc.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=1)
            except Exception:  # noqa: BLE001 — log + continue cleanup
                logger.debug("soniox parec teardown failed", exc_info=True)

        thread = self._soniox_parec_thread
        if thread is not None:
            thread.join(timeout=1)

        stop_event = self._soniox_mixer_stop
        if stop_event is not None:
            stop_event.set()

        mixer = self._soniox_mixer_thread
        if mixer is not None:
            mixer.join(timeout=1)

        # Transcriber: Whisper (joins the processing thread with a
        # 5-second timeout inside) or Soniox (closes the WebSocket
        # and joins its asyncio loop thread).
        transcriber = self._transcriber
        if transcriber is not None:
            try:
                transcriber.stop()
            except Exception:  # noqa: BLE001 — log + continue cleanup
                logger.exception("Transcriber stop failed")


# ── TTS playback worker ───────────────────────────────────────────────────


@dataclass(frozen=True)
class _TTSConfig:
    """Snapshot of TTS-related settings captured at session start.

    Live TTS used to call ``load_setting`` up to 4× per synthesized
    sentence (engine, ElevenLabs key, voice, model, Google key —
    plus one more on the UI thread in ``_process_tts_queue``).  For
    a 50-sentence session that's ~250 redundant INI reads, all
    cacheable.  This frozen snapshot is captured once in
    :meth:`LivePage._start_listening` (and refreshed when the user
    toggles TTS back on) and passed to every :class:`_TTSWorker`,
    cutting the per-sentence INI cost to zero.

    A mid-session settings change is NOT picked up while TTS stays
    enabled — by design.  The Live page locks audio source +
    language combos while running, and the TTS engine is a
    similar "configure first, then start" setting.  Toggling TTS
    off → on refreshes the snapshot, which covers the realistic
    "user changed Settings, then enabled TTS" case.
    """

    method: str
    target_lang: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model: str
    google_api_key: str


class _TTSWorker(QThread):
    """Synthesizes and plays a single sentence via TTS."""

    synthesized = Signal()
    error = Signal(str)

    def __init__(
        self,
        text: str,
        target_lang: str,
        gender: str,
        *,
        config: _TTSConfig | None = None,
    ) -> None:
        """Stores TTS parameters for background synthesis.

        ``config`` is the pre-resolved TTS snapshot from the page
        (see :class:`_TTSConfig`).  When provided, ``run()`` reads
        every setting from the snapshot, skipping per-sentence
        ``load_setting`` calls.  When None (test path / legacy
        callers), falls back to live ``load_setting`` reads — this
        preserves existing test fixtures that mock the function
        directly.
        """
        super().__init__()
        self._text = text
        self._target_lang = target_lang
        self._gender = gender
        self._config = config
        self._temp_file: str | None = None

    def run(self) -> None:  # noqa: PLR0912 — TTS engine dispatch is wide by design
        """Synthesizes text to a temp MP3 file."""
        try:
            from src.constants.settings import (  # noqa: PLC0415
                ELEVENLABS_MODEL_DEFAULT,
                SETTING_ELEVENLABS_API_KEY,
                SETTING_ELEVENLABS_MODEL,
                SETTING_ELEVENLABS_VOICE_ID,
                VOICE_TTS_EDGE,
                VOICE_TTS_ELEVENLABS,
                VOICE_TTS_PIPER,
            )
            from src.core.speech_engine import (  # noqa: PLC0415
                _get_edge_voice,
                _get_tts_language_code,
                _synthesize_chunk,
                _synthesize_chunk_edge,
                _synthesize_chunk_elevenlabs,
                _synthesize_chunk_piper,
                get_piper_voice_for,
                is_piper_voice_installed,
                load_google_cloud_api_key,
            )

            tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                suffix=".mp3",
                delete=False,
                prefix="live_tts_",
            )
            tmp.close()
            self._temp_file = tmp.name
            out = Path(tmp.name)

            cfg = self._config
            if cfg is not None:
                tts_method = cfg.method
            else:
                tts_method = load_setting(
                    SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE,
                )

            if tts_method == VOICE_TTS_ELEVENLABS:
                if cfg is not None:
                    el_key = cfg.elevenlabs_api_key
                    el_voice = cfg.elevenlabs_voice_id
                    el_model = cfg.elevenlabs_model
                else:
                    el_key = load_setting(SETTING_ELEVENLABS_API_KEY, "")
                    el_voice = load_setting(SETTING_ELEVENLABS_VOICE_ID, "")
                    el_model = load_setting(
                        SETTING_ELEVENLABS_MODEL,
                        ELEVENLABS_MODEL_DEFAULT,
                    )
                if el_key:
                    _synthesize_chunk_elevenlabs(
                        self._text,
                        el_key,
                        out,
                        el_voice,
                        model_id=el_model,
                        gender=self._gender,
                    )
                else:
                    voice = _get_edge_voice(self._target_lang, self._gender)
                    _synthesize_chunk_edge(self._text, voice, out)
            elif tts_method == VOICE_TTS_GOOGLE:
                api_key = (
                    cfg.google_api_key
                    if cfg is not None
                    else load_google_cloud_api_key()
                )
                if api_key:
                    lang_code = _get_tts_language_code(self._target_lang)
                    _synthesize_chunk(
                        self._text,
                        lang_code,
                        self._gender,
                        api_key,
                        out,
                    )
                else:
                    voice = _get_edge_voice(self._target_lang, self._gender)
                    _synthesize_chunk_edge(self._text, voice, out)
            elif tts_method == VOICE_TTS_PIPER:
                # Two outcomes for Piper, mirrored from the engine:
                # - Language unsupported by Piper (e.g. Japanese) →
                #   Edge fallback, no warning, session keeps flowing.
                # - Language supported but the user hasn't downloaded
                #   the voice yet → Edge fallback for THIS sentence
                #   so the live session doesn't break.  The Settings
                #   → Voice → Piper panel is where the user installs
                #   voices; surfacing a mid-session error here would
                #   interrupt the live flow.
                voice_id = get_piper_voice_for(
                    self._target_lang, self._gender,
                )
                if voice_id and is_piper_voice_installed(voice_id):
                    _synthesize_chunk_piper(self._text, out, voice_id)
                else:
                    voice = _get_edge_voice(self._target_lang, self._gender)
                    _synthesize_chunk_edge(self._text, voice, out)
            else:
                voice = _get_edge_voice(self._target_lang, self._gender)
                _synthesize_chunk_edge(self._text, voice, out)

            self.synthesized.emit()
        except Exception as exc:
            logger.error("Live TTS error: %s", exc)
            self.error.emit(str(exc))

    @property
    def temp_file(self) -> str | None:
        """Path to the synthesized audio file."""
        return self._temp_file


# ── Background translation worker ─────────────────────────────────────────


class _TranslationWorker(QThread):
    """Translates a single sentence in a background thread.

    Streams chunks from the LLM (``stream_translate_text``) so the
    UI can paint translated text token-by-token rather than waiting
    for the full sentence to land — perceived latency drops from
    "wait then appear" to "watch it form".  Emits:

    - ``partial_translated(orig, accumulated)`` after every chunk so
      the LivePage can update the in-flight target card live.
    - ``translated(orig, full)`` once the stream completes — this is
      the trigger for transcript-record save and TTS enqueue (TTS
      always uses the complete sentence, never a partial chunk).
    - ``error(message)`` on any synthesis failure.  When this fires
      after partial chunks have already painted, ``LivePage`` clears
      the partial text before stamping the failure marker.
    """

    partial_translated = Signal(str, str)  # (original, accumulated_so_far)
    translated = Signal(str, str)  # (original, full_translation)
    error = Signal(str)

    def __init__(  # noqa: PLR0913 — explicit DI for translate_batch params
        self,
        text: str,
        src_lang: str,
        target_lang: str,
        glossary_entries: list[tuple[int, str, str]] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
        context: list[str] | None = None,
    ) -> None:
        """Stores source text and language parameters for background translation.

        *context* is the rolling buffer of recent source sentences from
        the same conversation — the LLM uses it to disambiguate
        pronouns and maintain topic / tone continuity.  None when the
        page hasn't seen any prior sentences yet.
        """
        super().__init__()
        self._text = text
        self._src_lang = src_lang
        self._target_lang = target_lang
        self._glossary_entries = glossary_entries
        self._provider = provider
        self._model = model
        self._context = context

    def run(self) -> None:
        """Streams translation chunks; retries once on transient errors.

        See ``_LIVE_RETRY_*`` constants for the retry policy rationale.
        Retries are skipped when partial chunks have already been
        emitted to the UI — re-streaming would replace painted text
        with possibly-different content and create visual jitter,
        which is worse than surfacing the failure tag.
        """
        from src.core.llm_engine import (  # noqa: PLC0415
            stream_translate_text,
        )

        for attempt in range(_LIVE_RETRY_MAX_ATTEMPTS):
            accumulated = ""
            emitted_any = False
            try:
                for chunk in stream_translate_text(
                    self._text,
                    target_lang=self._target_lang,
                    source_lang=self._src_lang or "",
                    glossary_entries=self._glossary_entries,
                    provider=self._provider,
                    model=self._model,
                    context=self._context,
                ):
                    if not chunk:
                        continue
                    accumulated += chunk
                    emitted_any = True
                    self.partial_translated.emit(self._text, accumulated)
                # Stream closed — emit the canonical-final translation
                # that downstream consumers (transcript record, TTS)
                # treat as authoritative.  Falls back to the original
                # text when the stream produced nothing.
                self.translated.emit(self._text, accumulated or self._text)
                return
            except ValueError as exc:
                tag = str(exc)
                is_transient = any(
                    t in tag for t in _LIVE_RETRY_TRANSIENT_TAGS
                )
                is_last = attempt >= _LIVE_RETRY_MAX_ATTEMPTS - 1
                # Skip the retry when the error isn't transient (auth /
                # quota / invalid request won't self-heal), when we've
                # already painted partial chunks, or when retries are
                # exhausted.  Otherwise sleep briefly and try again.
                if is_last or not is_transient or emitted_any:
                    logger.error("Live translation failed: %s", tag)
                    self.error.emit(tag)
                    return
                logger.warning(
                    "Live translation transient error %r;"
                    " retry %d/%d after %.1fs",
                    tag, attempt + 1, _LIVE_RETRY_MAX_ATTEMPTS - 1,
                    _LIVE_RETRY_BACKOFF_SEC,
                )
                time.sleep(_LIVE_RETRY_BACKOFF_SEC)
            except Exception as exc:
                # Non-ValueError → unexpected programmer bug, never
                # retry.  Surface immediately so the bug is visible.
                logger.error("Live translation error: %s", exc)
                self.error.emit(str(exc))
                return


class _IconOnlyItemDelegate(QStyledItemDelegate):
    """QStyledItemDelegate that suppresses text in dropdown popup rows.

    Returning an empty ``displayText`` keeps Qt's default paint path
    intact for the icon (``Qt.DecorationRole``) but causes the text
    column to render blank.  Item heights still come from the default
    sizeHint so rows remain comfortably tappable, just visually
    flag-only — matching the closed combo face in icon-only mode.
    """

    def displayText(self, value, locale) -> str:  # noqa: ANN001, ARG002, N802
        """Always blank — strips the language label from popup rows."""
        return ""


class _IconOnlyCapableComboBox(QComboBox):
    """QComboBox that can paint icon-only on closed face *and* popup.

    Used by the Live page's source / target language pickers for
    compact-mode display.  ``set_icon_only(True)`` does two things:

    * Blanks ``QStyleOptionComboBox.currentText`` in ``paintEvent`` so
      the closed-state paint skips the label entirely.
    * Installs ``_IconOnlyItemDelegate`` on the popup view so dropdown
      rows render with the flag icon only — visually consistent with
      the closed face.

    ``set_icon_only(False)`` restores the original view delegate so
    full localized names + flags reappear in the popup.

    Item *data* (``itemText``, ``itemData``) is never modified, so
    persistence and selection logic continue to work normally.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon_only = False
        self._icon_only_delegate: _IconOnlyItemDelegate | None = None
        self._default_delegate = self.view().itemDelegate()

    def set_icon_only(self, on: bool) -> None:
        """Toggles icon-only rendering across the combo and its popup."""
        if on == self._icon_only:
            return
        self._icon_only = on
        if on:
            if self._icon_only_delegate is None:
                self._icon_only_delegate = _IconOnlyItemDelegate(self.view())
            self.view().setItemDelegate(self._icon_only_delegate)
        else:
            self.view().setItemDelegate(self._default_delegate)
        self.update()  # repaint closed face with the new option

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        """Draws the closed combo with empty text when icon-only."""
        if not self._icon_only:
            super().paintEvent(event)
            return
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QStyle,
            QStyleOptionComboBox,
            QStylePainter,
        )

        painter = QStylePainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = ""
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, opt)


class _SaveOptionsDialog(BaseDialog):
    """Lets the user pick what to save when clicking the Save button.

    Two checkboxes — Transcript / Audio — each gated by whether the
    item is actually saveable.  Transcript is enabled whenever the
    transcript records list is non-empty; Audio is enabled only
    after a session has finalised and a recording file exists on
    disk (i.e. the user opted into Audio in Auto save).  The
    disabled checkbox carries a tooltip explaining *why* it's grey
    so users don't have to guess.

    **Default state**: both boxes default to checked (when available)
    so the common "save everything I just produced" case is one
    click.  **Preserved selection**: whichever boxes the user last
    clicked Save with are remembered across sessions via
    ``SETTING_LIVE_SAVE_DIALOG_TRANSCRIPT`` /
    ``SETTING_LIVE_SAVE_DIALOG_AUDIO`` — so a user who consistently
    only wants the transcript stops having to uncheck Audio every
    time.  Cancelling the dialog does NOT update the persisted
    preference (the user didn't commit to a choice).

    Returns the user's selection via :meth:`selections` as a tuple
    ``(save_transcript: bool, save_audio: bool)``; the caller is
    responsible for opening the actual file save dialogs and writing
    the chosen artefacts.  ``ask()`` wraps construction + exec + read
    so callers don't have to manage the dialog lifecycle.
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        transcript_available: bool,
        audio_available: bool,
    ) -> None:
        super().__init__(parent, tr("live.save_chooser_title"))
        from PySide6.QtWidgets import QCheckBox  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_SAVE_DIALOG_AUDIO,
            SETTING_LIVE_SAVE_DIALOG_TRANSCRIPT,
        )

        # Load the previously-saved preferences (default True so a
        # first-time user picks Both).  Saved-bool-from-INI comes
        # back as a string ("True" / "False"); compare against
        # "False" so anything else (including missing / corrupt)
        # falls back to True — bias toward saving by default.
        saved_transcript_pref = (
            str(load_setting(SETTING_LIVE_SAVE_DIALOG_TRANSCRIPT, "True"))
            .strip().lower() != "false"
        )
        saved_audio_pref = (
            str(load_setting(SETTING_LIVE_SAVE_DIALOG_AUDIO, "True"))
            .strip().lower() != "false"
        )

        msg = QLabel(tr("live.save_chooser_msg"))
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color: {color('text_primary')}; font-size: 13px;",
        )
        self.layout.addWidget(msg)

        # Transcript checkbox: initial check state = ``available AND
        # saved_pref``.  When the item isn't available we keep it
        # unchecked regardless of saved pref — checking a disabled
        # box would be meaningless and the Save dispatch would skip
        # the empty source anyway.
        self.transcript_cb = QCheckBox(tr("live.save_chooser_transcript"))
        self.transcript_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.transcript_cb.setEnabled(transcript_available)
        self.transcript_cb.setChecked(transcript_available and saved_transcript_pref)
        if not transcript_available:
            self.transcript_cb.setToolTip(tr("live.save_transcript_empty_msg"))
        self.layout.addWidget(self.transcript_cb)

        # Audio checkbox: same gating as transcript.  Default now
        # checked (when available + saved pref) to match the
        # "save Both by default" intent — users who only want
        # transcript-only flip Audio off ONCE and that pref sticks.
        self.audio_cb = QCheckBox(tr("live.save_chooser_audio"))
        self.audio_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audio_cb.setEnabled(audio_available)
        self.audio_cb.setChecked(audio_available and saved_audio_pref)
        if not audio_available:
            self.audio_cb.setToolTip(tr("live.save_audio_empty_msg"))
        self.layout.addWidget(self.audio_cb)

        # Save / Cancel buttons.
        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton(tr("btn.cancel"))
        self.cancel_btn.setFixedHeight(HEIGHT_CONTROL)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(style_secondary_button())
        self.save_btn = QPushButton(tr("live.btn_save"))
        self.save_btn.setFixedHeight(HEIGHT_CONTROL)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(style_primary_button())
        # Save stays disabled until at least one option is checked —
        # otherwise clicking it would be a no-op.
        self.save_btn.setEnabled(
            self.transcript_cb.isChecked() or self.audio_cb.isChecked(),
        )
        self.transcript_cb.toggled.connect(self._refresh_save_btn)
        self.audio_cb.toggled.connect(self._refresh_save_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        self.layout.addLayout(btn_row)

        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self._on_accept)

    def _on_accept(self) -> None:
        """Persists the current selection then accepts the dialog.

        Only DISTINCT user choices update the persisted preference.
        A disabled checkbox carries no user intent — saving its
        ``False`` state would silently overwrite a prior ``True``
        preference, so the user who once saved Both would suddenly
        get Transcript-only defaults the moment they ran a session
        where audio wasn't available (e.g. mid-session crash before
        any audio was recorded).  Preserving the prior preference
        for unavailable items keeps the "remember my choice" promise
        honest across sessions with mixed availability.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_SAVE_DIALOG_AUDIO,
            SETTING_LIVE_SAVE_DIALOG_TRANSCRIPT,
        )

        if self.transcript_cb.isEnabled():
            save_setting(
                SETTING_LIVE_SAVE_DIALOG_TRANSCRIPT,
                str(self.transcript_cb.isChecked()),
            )
        if self.audio_cb.isEnabled():
            save_setting(
                SETTING_LIVE_SAVE_DIALOG_AUDIO,
                str(self.audio_cb.isChecked()),
            )
        self.accept()

    def _refresh_save_btn(self) -> None:
        self.save_btn.setEnabled(
            self.transcript_cb.isChecked() or self.audio_cb.isChecked(),
        )

    def selections(self) -> tuple[bool, bool]:
        """Returns ``(save_transcript, save_audio)`` based on checkbox state."""
        return self.transcript_cb.isChecked(), self.audio_cb.isChecked()

    @staticmethod
    def ask(
        parent: QWidget | None,
        *,
        transcript_available: bool,
        audio_available: bool,
    ) -> tuple[bool, bool, bool]:
        """Shows the chooser dialog and returns the user's choice.

        Returns ``(save_transcript, save_audio, accepted)`` — the
        third element is ``False`` if the user cancelled, in which
        case the first two are also ``False``.
        """
        dlg = _SaveOptionsDialog(
            parent,
            transcript_available=transcript_available,
            audio_available=audio_available,
        )
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        if not accepted:
            return False, False, False
        sel_transcript, sel_audio = dlg.selections()
        return sel_transcript, sel_audio, True


# ── Main page ──────────────────────────────────────────────────────────────


class LivePage(QWidget):
    """Page for live audio transcription and translation."""

    _sentence_received = Signal(str, float, float, str, str)
    _status_received = Signal(str)
    _transcriber_stopped = Signal()
    # Engine-classified fatal STT error.  Args: ``(category_tag, raw_message)``
    # — the tag is one of the ``STT_*`` constants from
    # ``src.core.live_errors`` and resolves through
    # ``src.constants.errors.display_error_message`` to a localised string.
    _stt_error_received = Signal(str, str)

    def __init__(
        self,
        window: QMainWindow,
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the LivePage."""
        super().__init__(parent)
        self.window_context = window
        self._transcriber = None
        # Auto-stop-after-silence timer.  Constructed lazily by
        # ``_start_idle_timer`` on each Start (so a setting change in
        # Settings → Live takes effect on the next session); torn
        # down by ``_stop_idle_timer`` on Stop or idle timeout.
        # ``_idle_minutes`` is the most recent active value, only
        # meaningful while ``_idle_timer is not None``.
        self._idle_timer: QTimer | None = None
        self._idle_minutes: int = 0
        # Off-thread engine teardown worker (see :class:`_EngineStopWorker`).
        # Non-None while a Stop is in flight; the ``finished`` slot
        # ``_on_stop_complete`` clears the ref.
        self._stop_worker: _EngineStopWorker | None = None
        # Session generation counter, bumped by
        # ``_make_filtered_on_stopped`` whenever a new transcriber
        # is constructed.  The closure-tagged callback compares
        # against the current value so a stale ``on_stopped`` from
        # a previous session can't fire the slot after the user
        # has already started a new run.  Init to 0 so the first
        # session captures 1.
        self._session_gen: int = 0
        self._translation_workers: list[_TranslationWorker] = []
        self._tts_enabled = False
        # Bounded FIFO: older sentences are dropped when recognition outpaces
        # TTS so playback stays close to the on-screen text.
        self._tts_queue: deque[str] = deque(maxlen=_MAX_TTS_QUEUE)
        self._tts_worker: _TTSWorker | None = None
        # Frozen snapshot of TTS-related settings — see :class:`_TTSConfig`.
        # Captured once per session in ``_start_listening`` (and
        # refreshed on TTS-off → TTS-on toggle) so each
        # ``_TTSWorker`` skips the per-sentence ``load_setting``
        # round-trips.  ``None`` means no live session is active /
        # TTS has never been enabled this session.
        self._tts_config: _TTSConfig | None = None
        # Transcript accumulator keeps raw (speaker, timestamp, original,
        # translated) tuples for export — the QLabel-based display loses
        # the structure otherwise.
        # 5-tuple: (timestamp, speaker_label, original, translated, is_error).
        # ``is_error=True`` means the LLM translation failed — the
        # ``translated`` slot holds the user-facing error inline
        # message ("⚠ Translation failed — quota exceeded") so an
        # overlay opened after the failure can still surface the
        # error marker via :meth:`_OverlayWindow.set_last_error`.
        # SRT export writes that message into the second cue line
        # so the saved transcript also documents WHY the sentence
        # didn't translate.
        # Records hold the *raw* speaker ID (e.g. ``"speaker_0"``) in
        # the second slot — not the formatted display label — so a
        # subsequent rename retroactively updates the SRT export
        # without having to walk every record and substitute strings.
        # ``_format_transcript_srt`` and the overlay backfill loop
        # both resolve the visible name through ``_display_speaker``.
        self._transcript_records: list[tuple[str, str, str, str, bool]] = []
        # Per-session map of ``speaker_id -> user-chosen display name``
        # set via inline double-click rename.  Cleared on every Start
        # via ``_reset_transcript_state``: Soniox's diarized IDs are
        # session-relative, so an alias from a previous session would
        # almost certainly mis-label new speakers in the next one.
        self._speaker_aliases: dict[str, str] = {}
        # Set True while a sticky error pill (auto-stop path) owns the
        # status label; the post-thread ``_on_transcriber_stopped``
        # callback fires AFTER the error pill is painted and would
        # otherwise overwrite its text with "Ready" via
        # ``_reset_ui_to_ready``.  Cleared on the next Start so a new
        # session begins from a clean neutral pill.
        self._sticky_error_active = False
        # Per-session output paths set by ``_resolve_save_paths`` when
        # ``SETTING_LIVE_SAVE_OUTPUT`` requests audio / text saving.
        # Stay populated after Stop so the status pill can reference
        # them.  Both are cleared after the post-Stop status message.
        self._recording_path: Path | None = None  # WAV (audio mode)
        # True when ``_recording_path`` was reserved under the OS
        # tempdir (Auto save = None / Text-only path).  Drives both:
        # (a) ``_finalise_audio_recording`` skipping the post-encode
        # step — temp WAVs stay raw so manual save can re-encode to
        # whatever the user picks in the file dialog; (b)
        # ``_cleanup_temp_audio`` knowing whether the previous
        # session's file is safe to delete on next Start.
        self._audio_is_temp: bool = False
        # The finalised audio file after a session ends — survives the
        # ``_recording_path = None`` reset so the manual ``Save Audio``
        # button can copy from it.  Set by ``_finalise_audio_recording``
        # whenever a recording actually landed on disk; cleared on next
        # session Start (and the temp WAV deleted, if any).
        self._last_recorded_audio_path: Path | None = None
        # Soniox-only: WAV writer that tees PCM blocks from the audio
        # feed to disk in parallel with sending to Soniox's WebSocket.
        # Whisper has an engine-side equivalent (see
        # ``LiveTranscriber._record_writer``); Soniox doesn't, so this
        # is the only place its audio can be captured for manual
        # Save → Audio.  Opened in ``_open_soniox_recording`` and
        # closed in ``_stop_audio_feed``.
        self._soniox_wav_writer = None
        # Extension matches the user's SETTING_LIVE_TRANSCRIPT_FORMAT pick
        # (.srt / .vtt / .ass / .ssa / .csv) — set in _prepare_recording_paths.
        self._transcript_save_path: Path | None = None
        # Rolling buffer of the last N source-language sentences, fed to
        # the LLM as reference-only context so it can disambiguate
        # pronouns and topic continuity in the current sentence.  Source
        # text only — the model doesn't need its own prior translations
        # to interpret incoming source.  Bounded so token cost stays
        # roughly constant per call.
        self._context_buffer: deque[str] = deque(maxlen=_LIVE_CONTEXT_SENTENCES)
        self._player = None
        self._audio_output = None
        self._overlay: _OverlayWindow | None = None
        # Background QThread that warms the Whisper model on page show.
        # Tracked for shutdown bounded-wait and to skip duplicate spawns.
        self._whisper_preload_worker: QThread | None = None
        self._setup_ui()

        self._sentence_received.connect(self._on_sentence)
        self._status_received.connect(self._on_status)
        self._transcriber_stopped.connect(self._on_transcriber_stopped)
        self._stt_error_received.connect(self._on_stt_error)

        # Live sessions spawn a transcriber thread, a parec subprocess + reader
        # thread, a sounddevice InputStream, any number of translation workers,
        # and a TTS worker. Shut them down explicitly on app exit so nothing
        # keeps running against a torn-down Qt event loop.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_all_workers)

    def _stop_all_workers(self) -> None:
        """Stops every live-session resource before the app exits."""
        if self._transcriber is not None:
            self._stop_listening()
        # ``_stop_listening`` now spawns an off-thread teardown worker
        # so the UI doesn't freeze on regular Stop clicks.  On app
        # quit we DO want the teardown to complete before the
        # interpreter shuts down — otherwise parec / faster-whisper
        # background threads can outlive the process and surface as
        # zombie subprocesses or "QThread destroyed while running"
        # warnings.  Bounded at 15 s (the realistic worst case for
        # whisper join + parec SIGKILL escalation).
        if self._stop_worker is not None:
            self._stop_worker.wait(15000)
            self._stop_worker = None
        if self._tts_worker is not None:
            # TTS worker has no cancel hook; bound the wait so app exit
            # isn't blocked by a hung backend.
            self._tts_worker.wait(2000)
            self._tts_worker = None
        # Per-sentence translation workers are signal-detached on Stop
        # but their ``run()`` may still be inside an LLM HTTP call when
        # ``aboutToQuit`` fires.  Without a bounded wait Qt can surface
        # "QThread destroyed while still running" warnings or, rarely,
        # segfault on shutdown.  Mirror the TTS pattern: 2-second
        # budget per worker, then drop the reference and let interpreter
        # exit reap any stragglers.
        for worker in list(self._translation_workers):
            worker.wait(2000)
        self._translation_workers.clear()
        # Frameless top-level overlay has no parent to clean it up — close
        # it explicitly so it doesn't linger as a zombie window on shutdown.
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        # Whisper preload thread may still be inside the (slow) model
        # constructor when shutdown fires.  Bounded wait — same 2 s
        # contract as the TTS / translation workers — so app exit isn't
        # blocked by a stuck native load.
        if self._whisper_preload_worker is not None:
            self._whisper_preload_worker.wait(2000)
            self._whisper_preload_worker = None
        # Best-effort cleanup of any temp WAV from THIS session that
        # the user didn't manually save.  ``_cleanup_orphan_temp_audio``
        # additionally sweeps stragglers from prior crashed runs.
        self._cleanup_temp_audio()
        _cleanup_orphan_temp_audio()

    def _cleanup_temp_audio(self) -> None:
        """Removes the previous session's temp-WAV if it was a temp recording.

        Called from ``_start_listening`` (before a new session reserves
        its own path) and ``_stop_all_workers`` (app exit).  Auto-save
        files at the user's configured location are NEVER touched —
        we only delete files we created under the OS tempdir with our
        ``_TEMP_AUDIO_PREFIX``.
        """
        path = self._last_recorded_audio_path
        if path is None:
            return
        # Defence in depth: ONLY delete if the path matches our temp
        # convention.  Belt-and-braces guard against a future refactor
        # accidentally pointing ``_last_recorded_audio_path`` at the
        # user's auto-save file and inviting this method to delete it.
        if not path.name.startswith(_TEMP_AUDIO_PREFIX):
            return
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to clean up temp audio %s: %s", path, exc)

    def _setup_ui(self) -> None:  # noqa: PLR0915, PLR0912
        """Builds the page layout."""
        page_container, content_layout = create_page_container(
            tr("page.live"),
            tr_key="page.live",
        )
        # Hide the "Live Translation" page title — the sidebar entry
        # already identifies the page and the header row only adds
        # vertical noise.
        if hasattr(page_container, "header_label"):
            page_container.header_label.setVisible(False)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(20, 10, 20, 10)

        # --- Single outer card wrapping controls + transcript ---
        # The whole page lives inside one rounded card; the standard
        # surface (card frame, two control rows, banners area, divider)
        # is built by :func:`create_controller_card` so future callers
        # can reuse the same chrome.
        from src.ui.components import create_controller_card  # noqa: PLC0415

        controller = create_controller_card()
        self._page_card = controller.card
        page_card_layout = controller.layout
        self._controls_top_row = controller.controls_top_row
        self._controls_btm_row = controller.controls_btm_row
        self._controls_btm_row_parent = controller.btm_row_parent
        self._banners_layout = controller.banners_layout
        # Bottom margin is dynamic — see ``_sync_banners_padding``.
        # When at least one banner is visible we want 12 px of breathing
        # room above the divider; when all banners are hidden (the
        # common happy-path state) we want 0 so the controller doesn't
        # carry dead vertical space below the buttons.  The helper is
        # called from every per-banner sync function so visibility flips
        # immediately propagate to the surrounding margin.

        # Alias for the compatibility of existing add-widget lines
        # below — the labelled combos (audio source, source/target
        # language, display mode, model) go into the top row.  The
        # Start button is added to the bottom row alongside the
        # other actions so the top row reads purely as session
        # config and the bottom row carries every clickable action.
        controls = self._controls_top_row

        self.start_btn = QPushButton(tr("live.btn_start"))
        self.start_btn.setFixedHeight(HEIGHT_CONTROL)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet(style_primary_button())
        self.start_btn.setAccessibleName(tr("live.btn_start"))
        self.start_btn.clicked.connect(self._toggle_listening)

        # Audio source selector
        self._audio_source_items = [
            (AUDIO_SOURCE_MICROPHONE, "live.source_microphone"),
            (AUDIO_SOURCE_SYSTEM, "live.source_system"),
            (AUDIO_SOURCE_BOTH, "live.source_both"),
        ]
        self.audio_source_combo = QComboBox()
        for value, tr_key in self._audio_source_items:
            self.audio_source_combo.addItem(tr(tr_key), value)
        self.audio_source_combo.setFixedHeight(HEIGHT_CONTROL)
        self.audio_source_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audio_source_combo.view().setCursor(
            Qt.CursorShape.PointingHandCursor,
        )
        self.audio_source_combo.setStyleSheet(style_setting_combo())
        # Wide enough to fit "System Audio" + caret without the
        # default content-fit collapsing it to "System Aud…".
        # 200 px matches the display-mode combo to keep the toolbar row
        # reading as a uniform set of controls; the 3 audio-source
        # labels (Microphone / System Audio / Both) all fit comfortably
        # at this width with room for the dropdown arrow.
        self.audio_source_combo.setFixedWidth(200)
        saved_source = load_setting(
            SETTING_LIVE_AUDIO_SOURCE,
            AUDIO_SOURCE_MICROPHONE,
        )
        for i, (value, _) in enumerate(self._audio_source_items):
            if value == saved_source:
                self.audio_source_combo.setCurrentIndex(i)
                break
        self.audio_source_combo.currentIndexChanged.connect(
            self._on_audio_source_changed,
        )
        controls.addWidget(self.audio_source_combo)

        # Source + target language pickers — persist to
        # ``SETTING_LIVE_SOURCE_LANG`` / ``SETTING_LIVE_TARGET_LANG``.
        # Source drives whisper's ``language=`` kwarg (locked vs.
        # auto-detect) and Soniox's ``source_lang``; target
        # drives post-STT LLM translation and Soniox's
        # ``target_lang``.  Without these, whisper auto-detect thrashes
        # and translations never happen — previously only settable by
        # hand-editing ``settings.ini``.
        self.source_lang_combo = self._build_lang_combo(
            include_auto=True,
            include_none=False,
        )
        saved_src = load_setting(SETTING_LIVE_SOURCE_LANG, "")
        self._select_lang_combo(self.source_lang_combo, saved_src)
        self.source_lang_combo.currentIndexChanged.connect(
            self._on_source_lang_changed,
        )
        self._controls_top_row.addWidget(self.source_lang_combo)

        # Thin connector between source and target so the pair reads
        # as "from X to Y" rather than two unrelated pickers.
        arrow = QLabel("→")
        arrow.setStyleSheet(
            f"color: {color('text_secondary')}; font-size: 16px;"
            " font-weight: 600; padding: 0 2px; background: transparent;"
        )
        self._controls_top_row.addWidget(arrow)

        self.target_lang_combo = self._build_lang_combo(
            include_auto=False,
            include_none=True,
        )
        saved_tgt = load_setting(SETTING_LIVE_TARGET_LANG, "")
        self._select_lang_combo(self.target_lang_combo, saved_tgt)
        self.target_lang_combo.currentIndexChanged.connect(
            self._on_target_lang_changed,
        )
        self._controls_top_row.addWidget(self.target_lang_combo)

        # Transcript-display mode picker — only relevant when a target
        # language is set (otherwise there's no translation to show).
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.setFixedHeight(HEIGHT_CONTROL)
        self.display_mode_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.display_mode_combo.view().setCursor(
            Qt.CursorShape.PointingHandCursor,
        )
        self.display_mode_combo.setStyleSheet(style_setting_combo())
        # 200 px fits the longest entry "Both (side by side)" without
        # truncation; 170 px previously clipped to "Both (side by sid".
        self.display_mode_combo.setFixedWidth(200)
        self._display_mode_items = [
            (LIVE_DISPLAY_BOTH, "live.display_both_stacked"),
            (LIVE_DISPLAY_BOTH_DUAL, "live.display_both_dual"),
            (LIVE_DISPLAY_TRANSLATION, "live.display_translation"),
        ]
        for value, tr_key in self._display_mode_items:
            self.display_mode_combo.addItem(tr(tr_key), value)
        current_mode = self._resolve_display_mode()
        for i, (value, _) in enumerate(self._display_mode_items):
            if value == current_mode:
                self.display_mode_combo.setCurrentIndex(i)
                break
        self.display_mode_combo.currentIndexChanged.connect(
            self._on_display_mode_changed,
        )
        self._controls_top_row.addWidget(self.display_mode_combo)

        # Translation-model picker lives in Settings → Live (Whisper
        # tab section) — Soniox translates inside its own session, so
        # the picker only matters for the Whisper backend and would
        # be misleading chrome on the toolbar for the cloud backend.
        # ``load_model_for_feature`` reads the setting fresh at
        # translation time, so the value still flows through here
        # without any toolbar surface.

        # Stretch on the top row so combos hug the left once all four
        # are packed.  Gets replaced by actions/status when collapsing.
        self._controls_top_row.addStretch()

        # --- Bottom row: action buttons with labels + status pill ---
        # Each button is created icon + text.  On collapse we'll clear
        # the text and reparent it up into the top row.
        from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

        def _make_action_btn(
            emoji: str,
            label_key: str,
            style: str,
            handler: Callable[[], None],
        ) -> QPushButton:
            btn = QPushButton(tr(label_key))
            btn.setProperty("action_label_key", label_key)
            btn.setProperty("action_emoji", emoji)
            btn.setIcon(_create_emoji_icon(emoji))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedHeight(HEIGHT_CONTROL)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(style)
            btn.setAccessibleName(tr(label_key))
            btn.clicked.connect(handler)
            return btn

        self.tts_btn = _make_action_btn(
            "\U0001f507",  # 🔇
            "live.btn_tts_off",
            style_secondary_button(),
            self._toggle_tts,
        )
        self.overlay_btn = _make_action_btn(
            "\U0001f5a5",  # 🖥
            "live.btn_overlay_off",  # overlay starts hidden
            style_secondary_button(),
            self._toggle_overlay,
        )
        self.save_btn = _make_action_btn(
            "\U0001f4be",  # 💾
            "live.btn_save",
            style_secondary_button(),
            self._save_now,
        )
        self.clear_btn = _make_action_btn(
            "\U0001f5d1",  # 🗑
            "live.btn_clear",
            style_delete_button(),
            self._clear_log,
        )
        # Timestamp-visibility toggle.  Default ON; user preference is
        # persisted to ``SETTING_LIVE_SHOW_TIMESTAMP``.  Mirrors the TTS
        # / Overlay buttons: text label + icon swap between states
        # (``Timestamps ON`` with 🕒 vs ``Timestamps OFF`` with ⛔)
        # carries the on/off cue, so we use the same plain
        # ``style_secondary_button`` as the other toolbar actions
        # rather than a checkable :checked variant — the explicit
        # ``ON``/``OFF`` text already makes the state unmistakable.
        self._show_timestamp = (
            load_setting(
                SETTING_LIVE_SHOW_TIMESTAMP,
                "true",
            ).lower()
            != "false"
        )
        time_initial_key = (
            "live.btn_timestamps_on"
            if self._show_timestamp
            else "live.btn_timestamps_off"
        )
        time_initial_emoji = "\U0001f552" if self._show_timestamp else "⛔"
        self.time_btn = _make_action_btn(
            time_initial_emoji,  # 🕒 on / ⛔ off
            time_initial_key,
            style_secondary_button(),
            self._toggle_show_timestamp,
        )
        # Speaker-label visibility lives in Settings → Live (not on the
        # toolbar) because it's a Soniox-only, rarely-flipped option.
        # The value is still read here so the live page applies the
        # user's preference to every transcript card it builds.  An
        # ``apply_settings`` hook re-reads on show / language switch so
        # mid-session changes from Settings take effect retroactively.
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_SHOW_SPEAKER,
        )

        self._show_speaker = bool(
            load_setting(SETTING_LIVE_SHOW_SPEAKER, True),
        )

        # Start button anchors the leftmost slot on the bottom row
        # — it's the most important action on the page, so even
        # though it now lives one row below the config selectors it
        # stays at the leftmost edge where the eye lands first.
        self._controls_btm_row.addWidget(self.start_btn)

        self._action_btns = [
            self.overlay_btn,
            self.time_btn,
            self.tts_btn,
            self.save_btn,
            self.clear_btn,
        ]
        for btn in self._action_btns:
            self._controls_btm_row.addWidget(btn)
        # Clear is meaningless against an empty transcript — disable
        # it on construction so the user gets a clear "no content yet"
        # cue instead of a no-op click.  ``_refresh_*`` is re-called
        # from ``_add_original`` and ``_clear_log`` so the state stays
        # in lockstep with the transcript content.
        self._refresh_content_dependent_buttons()

        self._controls_btm_row.addStretch()

        # Use _PillLabel so the rounded background paints reliably —
        # plain QLabel + QSS ``border-radius`` leaves the corners
        # rectangular due to Qt's palette-fallback fill path.  Radius
        # matches the toolbar buttons (``RADIUS_BUTTON``) so the
        # status pill reads as part of the same control row, not as
        # a smaller / different visual family.
        self.status_label = _PillLabel(
            tr("live.status_ready"),
            color("disabled_bg"),
            radius=RADIUS_BUTTON,
            h_padding=12,
            v_padding=6,
        )
        self.status_label.setStyleSheet(_style_status())
        self._controls_btm_row.addWidget(self.status_label)

        # ``create_controller_card`` already added the controls
        # container, the banners area, and the divider to
        # ``page_card_layout`` in that order — banners go into
        # ``self._banners_layout`` below; the transcript area is
        # added directly to ``page_card_layout`` after the divider.

        # Pre-flight banner for the cloud STT backend (Soniox).
        # Visible whenever the configured method needs an API key that
        # isn't set yet — the user sees the issue *before* clicking
        # Start, instead of getting a runtime modal after the
        # fact.  Body carries an internal "Settings" link (handled via
        # ``linkActivated`` below — ``setOpenExternalLinks`` is off so
        # the ``settings://`` href doesn't get handed to the browser).
        # The Start button is disabled while this banner is visible so
        # the user can't fire a known-bad attempt.  Whisper (local)
        # never triggers this — no API key required.
        self._stt_setup_warning, self._stt_setup_warning_label = (
            create_banner(
                "",
                variant="warning",
                rich_text=True,
            )
        )
        self._stt_setup_warning.setVisible(False)
        self._stt_setup_warning_label.setOpenExternalLinks(False)
        self._stt_setup_warning_label.linkActivated.connect(
            self._on_stt_setup_link_clicked,
        )
        # Language-switch hook: window.py walks every QWidget calling
        # ``apply_language``; routing it through the sync method
        # rebuilds the localised body text in the new locale.
        self._stt_setup_warning.apply_language = self._sync_stt_setup_warning
        self._banners_layout.addWidget(self._stt_setup_warning)

        # Format-conditional ffmpeg banner.  Reuses the shared
        # ``create_ffmpeg_install_banner()`` helper (same per-OS
        # install instructions as Voice / Dubbing pages) but with a
        # Live-specific visibility gate: only shown when audio
        # auto-save uses an encoded format (MP3/FLAC/OGG) and ffmpeg
        # is missing.  WAV recording, transcript-only, and no-save
        # modes hide it.  ``_sync_audio_ffmpeg_warning`` re-runs the
        # shared refresh (which sets the per-OS text) and then
        # overrides visibility with the Live-specific predicate.
        from src.ui.components import (  # noqa: PLC0415
            create_ffmpeg_install_banner,
        )

        self._audio_ffmpeg_warning, self._refresh_audio_ffmpeg_banner = (
            create_ffmpeg_install_banner()
        )
        self._audio_ffmpeg_warning.setVisible(False)
        self._banners_layout.addWidget(self._audio_ffmpeg_warning)

        # Inline warning banner shown when the user picks "System Audio"
        # or "Both" and the OS prerequisites for system-audio capture
        # aren't met (Linux: PulseAudio missing; macOS: BlackHole not
        # installed; Windows: WASAPI loopback failed AND no DirectShow
        # virtual cable).  Mirrors the OCR / office "setup hint" banners
        # in the Settings page so users see the install instructions
        # before hitting Start instead of after.  Uses rich-text mode
        # so the per-platform install names render as clickable links
        # (BlackHole / Screen Capture Recorder / VB-Audio Virtual Cable)
        # — clicking opens the install page in the user's browser via
        # ``setOpenExternalLinks(True)`` inside ``create_banner``.
        # Visibility is driven by ``_sync_system_audio_warning`` which
        # we call on init, on combo change, and on ``showEvent``.
        # Capture the inner QLabel so ``_sync_system_audio_warning``
        # can rewrite the body text dynamically — when running on
        # Linux with a recognised package manager, we append the actual
        # ``sudo apt-get install …`` (or dnf / pacman / zypper / apk)
        # command to the Linux line so the user can copy-paste it
        # straight into a terminal.  Don't pass ``tr_key`` to
        # create_banner; the dynamic builder owns the text now and we
        # plug into language change via the override below.
        # Initial body is empty — the banner starts hidden and the
        # first ``_sync_system_audio_warning`` call (on combo change
        # or showEvent) populates the OS-specific text before the
        # banner ever becomes visible.
        self._system_audio_warning, self._system_audio_warning_label = (
            create_banner(
                "",
                variant="warning",
                rich_text=True,
            )
        )
        self._system_audio_warning.setVisible(False)
        # On language switch, window.py walks every QWidget looking for
        # an ``apply_language`` callable.  Re-running our sync rebuilds
        # the dynamic install-hint text in the new language.
        self._system_audio_warning.apply_language = (
            self._sync_system_audio_warning
        )
        self._banners_layout.addWidget(self._system_audio_warning)

        # Mic-capture setup-hint banner — surfaces when PortAudio isn't
        # installed AND the selected source needs the microphone
        # (``AUDIO_SOURCE_MICROPHONE`` or ``AUDIO_SOURCE_BOTH``).  Same
        # rich-text + per-OS dispatcher pattern as the system-audio
        # banner above.  Without this the user would only discover the
        # missing PortAudio at runtime after pressing Start; surfacing
        # it here lets them install BEFORE composing a session.
        self._microphone_warning, self._microphone_warning_label = (
            create_banner(
                "",
                variant="warning",
                rich_text=True,
            )
        )
        self._microphone_warning.setVisible(False)
        self._microphone_warning.apply_language = (
            self._sync_microphone_warning
        )
        self._banners_layout.addWidget(self._microphone_warning)

        # Divider between controller block and transcript area is
        # already drawn by ``create_controller_card`` — no need to
        # build one here.

        # --- Transcript area (single vs dual column, switchable live) ---
        # Single view: one scroll area, entries stack vertically (original →
        # translation → original → …).  Dual view: ONE scroll containing
        # pair-rows (each row = original-card + translation-card in an
        # HBox), so the two columns can never drift out of sync the way
        # two independent scrolls did.  A pending translation shows a
        # subtle "…" placeholder until ``_add_translated`` swaps in the
        # real text.  Both views are populated on every _add_original /
        # _add_translated so switching is instant without reflow.
        self._transcript_stack = QStackedWidget()
        # Transparent so the page card's rounded bottom corners show
        # through — without this the stack paints a solid widget
        # background that clips the parent's border-radius.
        self._transcript_stack.setStyleSheet("background: transparent;")

        self._scroll, self._transcript_layout, self._transcript_container = (
            self._build_transcript_column()
        )
        self._transcript_stack.addWidget(self._scroll)

        (
            self._dual_scroll,
            self._dual_layout,
            _,
        ) = self._build_transcript_column()
        self._transcript_stack.addWidget(self._dual_scroll)

        # Signal-based auto-scroll stickiness for BOTH transcript
        # columns.  The previous ``QTimer.singleShot(0, sb.setValue(
        # sb.maximum()))`` approach in ``_insert_into`` raced the
        # wordWrap two-step layout pass on wide / multi-line entries:
        # the timer fired with the OLD ``maximum()``, snapping the
        # scrollbar one entry short of the actual bottom — visible
        # to the user as "the new sentence arrives but the view only
        # scrolls to N-1."  Wiring ``rangeChanged`` means the snap
        # fires AFTER Qt finishes the layout pass for the inserted
        # widget; ``valueChanged`` keeps the stickiness honest by
        # flipping off when the user wheel-scrolls upward to read
        # history.
        self._stick_single = True
        self._stick_dual = True
        for sb_pair in (
            (self._scroll.verticalScrollBar(), "_stick_single"),
            (self._dual_scroll.verticalScrollBar(), "_stick_dual"),
        ):
            sb, flag_name = sb_pair
            sb.rangeChanged.connect(
                lambda _mn, mx, _sb=sb, _flag=flag_name:
                    self._on_transcript_range_changed(_sb, _flag, mx),
            )
            sb.valueChanged.connect(
                lambda v, _sb=sb, _flag=flag_name:
                    self._on_transcript_value_changed(_sb, _flag, v),
            )

        # Empty-state placeholder, shown until the first transcript
        # entry lands.  Lives in an outer ``QStackedWidget`` alongside
        # the real transcript stack so a single ``setCurrentIndex``
        # toggles between "waiting" and "streaming" views.
        self._empty_state = self._build_empty_state()

        self._transcript_outer = QStackedWidget()
        # Same transparency fix as the inner stack — let the page
        # card's rounded bottom corners stay visible behind the
        # transcript area instead of being painted over.
        self._transcript_outer.setStyleSheet("background: transparent;")
        self._transcript_outer.addWidget(self._empty_state)  # index 0
        self._transcript_outer.addWidget(self._transcript_stack)  # index 1
        self._transcript_outer.setCurrentIndex(0)

        page_card_layout.addWidget(self._transcript_outer, 1)

        content_layout.addWidget(self._page_card, 1)
        self._apply_transcript_layout()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(page_container)

        # Keyboard shortcuts. Keys are looked up in the central registry so
        # the Settings → Shortcuts tab can rebind them without a restart.
        from src.constants.shortcuts import (  # noqa: PLC0415
            get_shortcut,
            shortcuts_changed,
        )

        self._start_shortcut = QShortcut(
            QKeySequence(get_shortcut("live.start_stop")),
            self,
        )
        self._start_shortcut.activated.connect(self._toggle_listening)

        self._clear_shortcut = QShortcut(
            QKeySequence(get_shortcut("live.clear_log")),
            self,
        )
        self._clear_shortcut.activated.connect(self._clear_log)

        # Overlay font size nudge — only fires when the overlay is visible.
        # Attached to the Live page (not the overlay) so users can trigger
        # from anywhere on the page; chromeless overlay can't easily own
        # keyboard focus itself.
        self._overlay_font_bigger_shortcut = QShortcut(
            QKeySequence(get_shortcut("common.overlay_font_bigger")),
            self,
        )
        self._overlay_font_bigger_shortcut.activated.connect(
            lambda: self._nudge_overlay_font(2),
        )
        self._overlay_font_smaller_shortcut = QShortcut(
            QKeySequence(get_shortcut("common.overlay_font_smaller")),
            self,
        )
        self._overlay_font_smaller_shortcut.activated.connect(
            lambda: self._nudge_overlay_font(-2),
        )

        # Ctrl+Arrow nudges the overlay.  Implemented as an application
        # event filter rather than a QShortcut because focused widgets
        # (QPushButton, QComboBox) veto arrow-key shortcuts even with
        # ApplicationShortcut context via ``ShortcutOverride`` — the
        # filter runs earlier in Qt's dispatch and bypasses that path.
        #
        # Skipped on Mutter/GNOME Wayland because the compositor ignores
        # client-requested toplevel repositioning.  The same entries are
        # hidden from Settings → Shortcuts there, so the feature is
        # silently absent rather than visibly broken.
        from src.constants.shortcuts import is_wayland_platform  # noqa: PLC0415

        self._overlay_arrow_filter: _OverlayArrowFilter | None = None
        if not is_wayland_platform():
            self._overlay_arrow_filter = _OverlayArrowFilter(self)
            qapp = QApplication.instance()
            if qapp is not None:
                qapp.installEventFilter(self._overlay_arrow_filter)

        # Ctrl+0 / Ctrl+9 resize.  Skipped on Mutter/GNOME Wayland — the
        # compositor ignores client resize requests for frameless Tool
        # windows exactly like it ignores position requests.  Hidden
        # from the Shortcuts tab there too; users resize via mouse drag
        # on the overlay edges.
        self._overlay_resize_shortcuts: list[QShortcut] = []
        if not is_wayland_platform():
            for shortcut_id, dw, dh in (
                (
                    "common.overlay_resize_grow",
                    _OVERLAY_RESIZE_STEP,
                    _OVERLAY_RESIZE_STEP,
                ),
                (
                    "common.overlay_resize_shrink",
                    -_OVERLAY_RESIZE_STEP,
                    -_OVERLAY_RESIZE_STEP,
                ),
            ):
                sc = QShortcut(QKeySequence(get_shortcut(shortcut_id)), self)
                sc.activated.connect(
                    lambda dw=dw, dh=dh: self._resize_overlay(dw, dh),
                )
                sc.setProperty("shortcut_id", shortcut_id)
                self._overlay_resize_shortcuts.append(sc)

        # Ctrl+] / Ctrl+[ bump overlay background opacity.  Only the
        # panel alpha changes; text stays fully opaque for readability.
        # Works on every platform (no Wayland skip).
        self._overlay_opacity_shortcuts: list[QShortcut] = []
        for shortcut_id, delta in (
            ("common.overlay_opacity_up", _OVERLAY_OPACITY_STEP),
            ("common.overlay_opacity_down", -_OVERLAY_OPACITY_STEP),
        ):
            sc = QShortcut(QKeySequence(get_shortcut(shortcut_id)), self)
            sc.activated.connect(
                lambda delta=delta: self._nudge_overlay_opacity(delta),
            )
            sc.setProperty("shortcut_id", shortcut_id)
            self._overlay_opacity_shortcuts.append(sc)

        def _sync_shortcuts() -> None:
            self._start_shortcut.setKey(
                QKeySequence(get_shortcut("live.start_stop")),
            )
            self._clear_shortcut.setKey(
                QKeySequence(get_shortcut("live.clear_log")),
            )
            self._overlay_font_bigger_shortcut.setKey(
                QKeySequence(get_shortcut("common.overlay_font_bigger")),
            )
            self._overlay_font_smaller_shortcut.setKey(
                QKeySequence(get_shortcut("common.overlay_font_smaller")),
            )
            for sc in self._overlay_resize_shortcuts:
                sc.setKey(
                    QKeySequence(get_shortcut(sc.property("shortcut_id"))),
                )
            for sc in self._overlay_opacity_shortcuts:
                sc.setKey(
                    QKeySequence(get_shortcut(sc.property("shortcut_id"))),
                )

        shortcuts_changed.connect(_sync_shortcuts)
        self._sync_shortcuts = _sync_shortcuts

    # ------------------------------------------------------------------
    # Theme / language
    # ------------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Re-reads the transcript layout preference on every page show.

        The setting is only changed from the Settings tab, so picking up the
        new value whenever the user navigates back here keeps the view
        synced without needing a dedicated change signal.
        """
        super().showEvent(event)
        self._apply_transcript_layout()
        self._update_display_combo_visibility()
        # Re-check system-audio prerequisites — the user may have just
        # installed BlackHole / VB-Audio in another window since the
        # page was last shown, and we want the banner to clear without
        # an app restart.
        self._sync_system_audio_warning()
        # Same idea for the PortAudio / mic-capture path.
        self._sync_microphone_warning()
        # And the encoded-audio-format ffmpeg banner — same rationale.
        self._sync_audio_ffmpeg_warning()
        # Same idea for cloud-STT API keys: the user may have just
        # added a Soniox key in Settings, so re-check on
        # every page show.  Also covers the first show when settings
        # were already populated before navigating to Live.
        self._sync_stt_setup_warning()
        # Re-read the "Show speaker labels" preference in case the user
        # toggled it in Settings → Live since this page was last shown.
        # No explicit signal — settings panels persist on toggle and we
        # pick up the value here.  Only re-applies when changed so a
        # no-op visit doesn't churn the transcript layout.
        self._refresh_speaker_setting_from_disk()
        # Warm the Whisper model so the first sentence after Start
        # doesn't pay the 5-15 s load cost.  Gated on (a) Whisper being
        # the active STT engine, (b) the model already being on disk,
        # so we never silently trigger a multi-hundred-MB download for
        # a user who just opened the page to peek.
        self._maybe_preload_whisper()

    def apply_theme(self) -> None:
        """Re-applies theme-dependent styles."""
        self.start_btn.setStyleSheet(
            style_delete_button()
            if self._transcriber and self._transcriber.is_running
            else style_primary_button()
        )
        self.audio_source_combo.setStyleSheet(style_setting_combo())
        self.tts_btn.setStyleSheet(style_secondary_button())
        self.overlay_btn.setStyleSheet(style_secondary_button())
        # Timestamp button uses the same plain secondary style as TTS /
        # Overlay — its ``ON``/``OFF`` label + icon swap already carry the
        # state, so a separate :checked tint is redundant.
        self.time_btn.setStyleSheet(style_secondary_button())
        self.save_btn.setStyleSheet(style_secondary_button())
        self.clear_btn.setStyleSheet(style_delete_button())
        self.status_label.setStyleSheet(_style_status())

    # Below this width the toolbar's bottom row crowds and labels start
    # truncating (worst observed: "Overlay OFF" → "Overlay OI" at ~860 px).
    # Compact mode hides text on the icon-bearing action buttons and the
    # informational status label, leaving emoji icons that are still
    # recognisable at a glance.  Threshold picked so users at common
    # 1024-wide laptop screens stay in the full layout when the app is
    # maximised; only narrowed / split-screen windows enter compact mode.
    _COMPACT_TOOLBAR_WIDTH_PX = 1024

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        """Toggles the toolbar's compact icon-only layout on resize."""
        super().resizeEvent(event)
        new_compact = self.width() < self._COMPACT_TOOLBAR_WIDTH_PX
        if new_compact != getattr(self, "_compact_toolbar", None):
            self._compact_toolbar = new_compact
            self._apply_compact_toolbar()

    # Closed-state width of language combos in compact mode.  Sized to
    # fit the flag icon (24 px) + chevron sub-control (24 px) + left
    # padding (16 px) + right padding (4 px) + a small visual buffer so
    # Qt doesn't squish or distort the flag rendering.  Sum = 80 px.
    # The combos also flip to ``set_icon_only(True)`` in compact mode
    # so the suppressed text is genuinely not painted, avoiding any
    # clipping artefacts; the width-shrink alone is just to reclaim
    # the empty horizontal space that the blank text would have left.
    _COMPACT_LANG_COMBO_WIDTH_PX = 80
    _FULL_LANG_COMBO_WIDTH_PX = 220

    def _apply_compact_toolbar(self) -> None:
        """Switch the toolbar between full and compact layouts.

        Compact mode:
          * Action buttons (TTS / Overlay / Timestamps / Save / Clear)
            blank their text; their emoji icons stay visible.
          * Language combos shrink to their flag-icon width and flip
            to ``set_icon_only(True)`` so the closed face *and* the
            dropdown popup render flag-only.
          * Start button keeps its text (always short, never truncates).
          * Status label keeps its text — once buttons go icon-only
            there's plenty of horizontal room for the status string.
        """
        compact = getattr(self, "_compact_toolbar", False)
        for btn in (
            self.tts_btn,
            self.overlay_btn,
            self.time_btn,
            self.save_btn,
            self.clear_btn,
        ):
            if compact:
                btn.setText("")
            else:
                key = btn.property("action_label_key")
                if key:
                    btn.setText(tr(key))
        for combo in (
            getattr(self, "source_lang_combo", None),
            getattr(self, "target_lang_combo", None),
        ):
            if combo is None:
                continue
            # ``set_icon_only`` is the load-bearing call here — it stops
            # paintEvent from drawing the language text and installs
            # an empty-displayText delegate on the popup so dropdown
            # rows are also flag-only.  The width shrink reclaims the
            # empty horizontal space the blank text would have left.
            if hasattr(combo, "set_icon_only"):
                combo.set_icon_only(compact)
            combo.setFixedWidth(
                self._COMPACT_LANG_COMBO_WIDTH_PX
                if compact
                else self._FULL_LANG_COMBO_WIDTH_PX,
            )
    def apply_language(self) -> None:  # noqa: PLR0912
        """Re-applies all translatable text."""
        if self._transcriber and self._transcriber.is_running:
            self.start_btn.setText(tr("live.btn_stop"))
        else:
            self.start_btn.setText(tr("live.btn_start"))
        # Update audio source combo labels
        self.audio_source_combo.blockSignals(True)
        for i, (_, tr_key) in enumerate(self._audio_source_items):
            self.audio_source_combo.setItemText(i, tr(tr_key))
        self.audio_source_combo.blockSignals(False)
        tts_key = "live.btn_tts_on" if self._tts_enabled else "live.btn_tts_off"
        time_key = (
            "live.btn_timestamps_on"
            if self._show_timestamp
            else "live.btn_timestamps_off"
        )
        overlay_key = (
            "live.btn_overlay_on"
            if (self._overlay is not None and self._overlay.isVisible())
            else "live.btn_overlay_off"
        )
        compact = getattr(self, "_compact_toolbar", False)
        for btn, key in (
            (self.tts_btn, tts_key),
            (self.overlay_btn, overlay_key),
            (self.time_btn, time_key),
            (self.save_btn, "live.btn_save"),
            (self.clear_btn, "live.btn_clear"),
        ):
            btn.setAccessibleName(tr(key))
            # Skip the text update in compact mode — `_apply_compact_toolbar`
            # owns the text-blanking for that state and re-applying tr()
            # here would resurrect the labels until the next resize.
            if not compact:
                btn.setText(tr(key))
        # TTS / Timestamps / Overlay / Speakers buttons' underlying tr
        # keys are tracked for state-dependent refresh from their
        # respective toggle handlers and here.
        self.tts_btn.setProperty("action_label_key", tts_key)
        self.time_btn.setProperty("action_label_key", time_key)
        self.overlay_btn.setProperty("action_label_key", overlay_key)
        if hasattr(self, "_empty_state_title"):
            # Re-pull the variant-aware copy so the listening hint stays
            # listening after a language switch (and the idle hint stays
            # idle).  ``_set_empty_state_listening`` reads the saved
            # state flag and applies the matching i18n keys.
            self._set_empty_state_listening(
                listening=getattr(self, "_empty_state_listening", False),
            )
        if hasattr(self, "display_mode_combo"):
            self.display_mode_combo.blockSignals(True)
            for i, (_, tr_key) in enumerate(self._display_mode_items):
                self.display_mode_combo.setItemText(i, tr(tr_key))
            self.display_mode_combo.blockSignals(False)
        # Status pill shows ``live.status_ready`` while idle; refresh
        # it so a language switch picks up the new locale's wording.
        # Skip when actively listening / showing an error toast — the
        # current message belongs to a transient state we shouldn't
        # clobber mid-session.
        if not (self._transcriber and self._transcriber.is_running):
            self.status_label.setText(tr("live.status_ready"))
        # Re-render the source / target language combos: re-translate
        # the leading sentinel (Auto detect / No translation) AND
        # rewrite every language row in place.  Display labels are
        # now per-locale via ``format_language_picker_label``, so a
        # UI-language switch has to refresh them all.  Sort order is
        # also locale-driven; we walk the freshly-sorted catalogue and
        # preserve the current selection by canonical English label
        # held in ``itemData``.
        from PySide6.QtGui import QIcon  # noqa: PLC0415

        from src.constants.languages import (  # noqa: PLC0415
            format_language_picker_label as _fmt,
        )
        from src.constants.languages import (  # noqa: PLC0415
            iter_languages_sorted_for_ui as _iter_sorted,
        )
        from src.constants.ui import FLAGS_DIR  # noqa: PLC0415

        for combo, sentinel_key in (
            (self.source_lang_combo, "common.lang_auto_detect"),
            (self.target_lang_combo, "common.lang_no_translation"),
        ):
            saved = combo.currentData()
            combo.blockSignals(True)
            # Sentinel at index 0 (data == "") gets retranslated; if
            # the combo was built without one, every row is a language.
            head_offset = 1 if combo.itemData(0) == "" else 0
            if head_offset:
                combo.setItemText(0, tr(sentinel_key))
            for i, entry in enumerate(_iter_sorted()):
                _l, label, icon, native = entry
                # Update text + data + icon together — sort order is
                # locale-driven; without ``setItemIcon`` the flag stays
                # frozen at the pre-switch position.
                combo.setItemText(i + head_offset, _fmt(label, native))
                combo.setItemData(i + head_offset, label)
                combo.setItemIcon(
                    i + head_offset, QIcon(f"{FLAGS_DIR}/{icon}.png"),
                )
            if saved is not None:
                idx = combo.findData(saved)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        # Refresh the Clear tooltip text — it depends on
        # ``live.btn_clear`` / ``live.save_transcript_empty_msg``
        # which both just got re-translated.
        self._refresh_content_dependent_buttons()

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def _toggle_listening(self) -> None:
        """Starts or stops live transcription."""
        if self._transcriber and self._transcriber.is_running:
            self._stop_listening()
        else:
            self._start_listening()

    def _on_audio_source_changed(self, index: int) -> None:
        """Persists the selected audio source and re-checks prerequisites."""
        from src.core.live_engine import invalidate_audio_caches  # noqa: PLC0415

        value = self.audio_source_combo.itemData(index)
        if value:
            save_setting(SETTING_LIVE_AUDIO_SOURCE, value)
        # Source combo change is a user-intent re-probe point: drop
        # the cached pactl / ffmpeg result so a user who installed
        # BlackHole / VB-Audio in another window between probes
        # gets a fresh diagnosis on the very next ``check_system_
        # audio_available()`` call below.
        invalidate_audio_caches()
        # Surface or hide the system-audio warning banner immediately
        # — picking "System Audio" or "Both" without the OS plumbing in
        # place would otherwise only fail on Start.
        self._sync_system_audio_warning()
        # Mirror for the mic-capture path so picking "Microphone" or
        # "Both" surfaces the PortAudio install hint the same way.
        self._sync_microphone_warning()

    def _sync_stt_setup_warning(self) -> None:
        """Toggles the cloud-STT setup-hint banner and gates Start.

        Visibility: shown only when the configured ``SETTING_LIVE_STT_METHOD``
        is a cloud backend (Soniox) AND the corresponding
        API key isn't set.  Whisper is local — no key needed, banner
        stays hidden.

        Side effect: when the banner is visible AND we aren't already
        listening, the Start button is disabled so the user can't fire
        a doomed attempt.  Re-enabled the moment the banner clears
        (e.g. after returning to the page with a freshly-saved key).
        Skipped while listening because the button reads "Stop" then
        and must stay clickable so the user can end the session.
        """
        from src.utils import config_manager  # noqa: PLC0415

        method = load_setting(SETTING_LIVE_STT_METHOD, LIVE_STT_WHISPER)
        if method == LIVE_STT_SONIOX and not config_manager.check_soniox_setup():
            body = tr("live.warning_no_soniox_key")
        else:
            self._stt_setup_warning.setVisible(False)
            self._sync_banners_padding()
            # Only re-enable Start when not already listening — avoids
            # clobbering the "Stop" state mid-session.
            if not (self._transcriber and self._transcriber.is_running):
                self.start_btn.setEnabled(True)
            return

        # Replicate create_banner's paragraph wrapping so the rich-text
        # body's line spacing matches the rest of the app's banners.
        lines = body.split("\n")
        html = "".join(
            f"<p style='margin:0 0 {BANNER_LINE_SPACING}px 0;'>{line}</p>"
            for line in lines
        )
        self._stt_setup_warning_label.setText(html)
        self._stt_setup_warning.setVisible(True)
        self._sync_banners_padding()
        if not (self._transcriber and self._transcriber.is_running):
            self.start_btn.setEnabled(False)

    def _on_stt_setup_link_clicked(self, href: str) -> None:
        """Handles internal ``settings://`` links in the STT-setup banner.

        Soniox key → Service tab (index 2).  Index matches the
        ``_tab_specs`` order in ``settings.py``; if it moves, update
        both ends together.
        """
        target = (
            2 if href == "settings://service"
            else 4 if href == "settings://llm"
            else None
        )
        if target is None:
            return
        window = self.window_context
        if hasattr(window, "navigate_to_settings_tab"):
            window.navigate_to_settings_tab(target)

    def _maybe_preload_whisper(self) -> None:
        """Spawns a background Whisper-model load when conditions are right.

        Skips silently when:
          * Whisper isn't the configured STT engine,
          * the engine cache already holds the requested size (the
            cheap helper short-circuits inside ``preload_whisper_model``
            too, but pre-checking here avoids spawning a thread just
            to do nothing),
          * a previous preload thread is still running, or
          * the model files aren't already on disk (we won't trigger
            a multi-hundred-MB download as a side effect of opening
            the page).
        """
        from src.core.live_engine import (  # noqa: PLC0415
            _cached_model,
            _cached_model_size,
            is_whisper_model_cached,
        )

        method = load_setting(SETTING_LIVE_STT_METHOD, LIVE_STT_WHISPER)
        if method != LIVE_STT_WHISPER:
            return
        model_size = str(load_setting(SETTING_LIVE_WHISPER_MODEL, "tiny"))
        if _cached_model is not None and _cached_model_size == model_size:
            return
        if (
            self._whisper_preload_worker is not None
            and self._whisper_preload_worker.isRunning()
        ):
            return
        if not is_whisper_model_cached(model_size):
            return
        worker = _WhisperPreloadWorker(model_size)
        # Drop the reference once the thread finishes so a future page
        # show with a different model size can spawn a fresh worker.
        worker.finished.connect(self._on_whisper_preload_finished)
        self._whisper_preload_worker = worker
        worker.start()

    def _on_whisper_preload_finished(self) -> None:
        """Clears the worker reference after preload completes."""
        self._whisper_preload_worker = None

    def _sync_system_audio_warning(self) -> None:
        """Toggles the system-audio warning banner and rebuilds its text.

        Visibility: shown only when the picked source needs system
        audio (``AUDIO_SOURCE_SYSTEM`` or ``AUDIO_SOURCE_BOTH``) AND
        ``check_system_audio_available()`` reports the OS prerequisites
        aren't met.  Re-evaluating on page-show means a user who
        installs BlackHole / VB-Audio in another window doesn't have
        to restart the app — switching tabs once clears the banner.

        Body text: tailored to the current OS.  Linux gets a single
        line with the auto-detected ``apt-get`` / ``dnf`` / ``pacman``
        / ``zypper`` / ``apk`` command inlined; macOS gets a BlackHole
        link; Windows gets Screen Capture Recorder + VB-Audio links.
        Showing only the relevant section avoids dumping irrelevant
        cross-platform instructions (the user is on one OS at a time).
        Also doubles as the language-change hook (registered as
        ``apply_language`` on the banner) so the new-locale text is
        rebuilt with the OS-specific install hint intact.
        """
        import platform  # noqa: PLC0415

        from src.core.live_engine import (  # noqa: PLC0415
            _get_pulseaudio_install_hint,
            check_system_audio_available,
        )
        from src.utils.install_hints import format_install_clause  # noqa: PLC0415

        source = self.audio_source_combo.currentData()
        needs_system = source in (AUDIO_SOURCE_SYSTEM, AUDIO_SOURCE_BOTH)
        # Skip the (potentially shell-out) availability check entirely
        # when the user picked microphone-only — saves a subprocess
        # spawn on every page show.
        show = needs_system and not check_system_audio_available()
        self._system_audio_warning.setVisible(show)
        self._sync_banners_padding()
        if not show:
            return

        # Pick the right per-OS message.  The Linux branch additionally
        # inlines the detected package-manager command via the shared
        # ``format_install_clause`` helper so the user can copy-paste
        # the exact install command — and the banner reads cleanly on
        # unrecognised distros (helper returns empty string).
        system = platform.system()
        if system == "Linux":
            body = tr(
                "live.warning_no_system_audio_linux",
                linux_install=format_install_clause(_get_pulseaudio_install_hint()),
            )
        elif system == "Darwin":
            body = tr("live.warning_no_system_audio_macos")
        elif system == "Windows":
            body = tr("live.warning_no_system_audio_windows")
        else:
            body = tr("live.warning_no_system_audio_unsupported")

        # Banner's rich-text mode normally wraps each \n-split line in
        # its own <p> via ``create_banner._format_text``.  We bypass
        # that by setting text directly (we own the dynamic body now,
        # no tr_key on the banner) — replicate the same paragraph
        # wrapping here so visual line spacing matches the original.
        lines = body.split("\n")
        html = "".join(
            f"<p style='margin:0 0 {BANNER_LINE_SPACING}px 0;'>{line}</p>"
            for line in lines
        )
        self._system_audio_warning_label.setText(html)

    def _sync_microphone_warning(self) -> None:
        """Toggles the PortAudio (mic) setup-hint banner.

        Mirrors ``_sync_system_audio_warning`` but for the microphone
        path: shown only when the picked source needs the mic
        (``AUDIO_SOURCE_MICROPHONE`` or ``AUDIO_SOURCE_BOTH``) AND
        ``check_audio_available()`` reports PortAudio is missing.  A
        missing-mic-device result (``live.error_no_mic``) is a hardware
        problem with no install hint — that case stays as the runtime
        error message; this banner only fires for the installable case.
        """
        import platform  # noqa: PLC0415

        from src.core.live_engine import (  # noqa: PLC0415
            _get_portaudio_install_hint,
            check_audio_available,
        )
        from src.utils.install_hints import format_install_clause  # noqa: PLC0415

        source = self.audio_source_combo.currentData()
        needs_mic = source in (AUDIO_SOURCE_MICROPHONE, AUDIO_SOURCE_BOTH)
        # Only fire the (potentially shell-out) audio probe when mic is
        # actually selected — same optimisation as the system-audio
        # sibling above.
        show = needs_mic and check_audio_available() == "live.error_no_portaudio"
        self._microphone_warning.setVisible(show)
        self._sync_banners_padding()
        if not show:
            return

        system = platform.system()
        if system == "Linux":
            body = tr(
                "live.warning_no_portaudio_linux",
                linux_install=format_install_clause(_get_portaudio_install_hint()),
            )
        elif system == "Darwin":
            body = tr("live.warning_no_portaudio_macos")
        elif system == "Windows":
            body = tr("live.warning_no_portaudio_windows")
        else:
            body = tr("live.warning_no_portaudio_unsupported")

        lines = body.split("\n")
        html = "".join(
            f"<p style='margin:0 0 {BANNER_LINE_SPACING}px 0;'>{line}</p>"
            for line in lines
        )
        self._microphone_warning_label.setText(html)

    def _build_lang_combo(
        self,
        *,
        include_auto: bool,
        include_none: bool,
    ) -> QComboBox:
        """Creates a flag-iconed language combo for the toolbar.

        Stores each item's value as ``itemData`` — empty string for the
        auto-detect / no-translation entry, the canonical language
        label (e.g. ``"Vietnamese"``) otherwise.  Keeps UI text
        translated via ``tr`` while persistence stays stable.
        """
        from src.constants.languages import (  # noqa: PLC0415
            format_language_picker_label,
            iter_languages_sorted_for_ui,
        )

        combo = _IconOnlyCapableComboBox()
        combo.setFixedHeight(HEIGHT_CONTROL)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.view().setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setStyleSheet(style_setting_combo())
        combo.setIconSize(QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT))
        # 220 px fits the longest language label "Portuguese (Brazil)"
        # plus the flag icon without truncation; 180 px clipped it.
        # In compact-toolbar mode the page calls ``set_icon_only(True)``
        # which blanks the closed-face text; the width is also
        # tightened then so the empty space doesn't waste real estate.
        combo.setFixedWidth(220)
        # Emoji icons for the sentinel entries match the dialog
        # convention (🌐 for auto-detect, 🚫 for no-translation) so
        # those rows don't look misaligned next to the flag-iconed
        # language entries.
        from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

        if include_auto:
            combo.addItem(_create_emoji_icon(), tr("common.lang_auto_detect"), "")
        if include_none:
            combo.addItem(
                _create_emoji_icon("\U0001f6ab"),
                tr("common.lang_no_translation"),
                "",
            )
        for _locale, label, icon, native in iter_languages_sorted_for_ui():
            combo.addItem(
                QIcon(f"{FLAGS_DIR}/{icon}.png"),
                format_language_picker_label(label, native),
                label,
            )
        return combo

    @staticmethod
    def _select_lang_combo(combo: QComboBox, value: str) -> None:
        """Selects the combo item whose ``itemData`` matches *value*."""
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        # Unknown value — leave at index 0 (auto / no-translation).
        combo.setCurrentIndex(0)

    def _on_source_lang_changed(self, index: int) -> None:
        """Persists the source language picked from the toolbar."""
        save_setting(
            SETTING_LIVE_SOURCE_LANG,
            self.source_lang_combo.itemData(index) or "",
        )

    def _on_target_lang_changed(self, index: int) -> None:
        """Persists the target language picked from the toolbar.

        Also retoggles display-mode-combo visibility: when the user
        switches to "No translation" the dual-view modes are
        irrelevant and shouldn't clutter the toolbar.
        """
        save_setting(
            SETTING_LIVE_TARGET_LANG,
            self.target_lang_combo.itemData(index) or "",
        )
        self._update_display_combo_visibility()

    def _resolve_display_mode(self) -> str:
        """Returns the current transcript-display setting.

        Four-value combo folded together: source / translation on / off
        plus the stacked-vs-dual layout choice for the "both" case.
        Migrates from the older two-setting world (``show_original``
        boolean + ``transcript_layout`` single/dual) when no explicit
        value has been written.
        """
        valid = (
            LIVE_DISPLAY_BOTH,
            LIVE_DISPLAY_BOTH_DUAL,
            LIVE_DISPLAY_TRANSLATION,
        )
        explicit = load_setting(SETTING_LIVE_TRANSCRIPT_DISPLAY, "").strip().lower()
        if explicit in valid:
            return explicit
        # Migration: derive from the legacy pair.
        legacy_show = load_setting(SETTING_LIVE_SHOW_ORIGINAL, "true").lower()
        if legacy_show != "true":
            return LIVE_DISPLAY_TRANSLATION
        legacy_layout = load_setting(
            SETTING_LIVE_TRANSCRIPT_LAYOUT,
            LIVE_LAYOUT_SINGLE,
        )
        return (
            LIVE_DISPLAY_BOTH_DUAL
            if legacy_layout == LIVE_LAYOUT_DUAL
            else LIVE_DISPLAY_BOTH
        )

    @staticmethod
    def _mode_shows_source(mode: str) -> bool:
        """True when *mode* renders the source text in the transcript."""
        return mode in (
            LIVE_DISPLAY_BOTH,
            LIVE_DISPLAY_BOTH_DUAL,
        )

    @staticmethod
    def _mode_shows_target(mode: str) -> bool:
        """True when *mode* renders the translated text in the transcript."""
        return mode in (
            LIVE_DISPLAY_BOTH,
            LIVE_DISPLAY_BOTH_DUAL,
            LIVE_DISPLAY_TRANSLATION,
        )

    @staticmethod
    def _mode_is_dual(mode: str) -> bool:
        """True when *mode* uses the side-by-side two-column layout."""
        return mode == LIVE_DISPLAY_BOTH_DUAL

    def _toggle_show_timestamp(self) -> None:
        """Toggles the timestamp chip on transcript cards on/off.

        Persists to ``SETTING_LIVE_SHOW_TIMESTAMP`` and updates the
        visibility of the chip on every existing card so switching
        mid-session doesn't leave older entries out of sync.  The
        action button's label + tooltip swap between "Show" / "Hide"
        variants to communicate the *next* action.
        """
        self._show_timestamp = not self._show_timestamp
        save_setting(
            SETTING_LIVE_SHOW_TIMESTAMP,
            "true" if self._show_timestamp else "false",
        )
        # Swap text + icon to communicate the new state.  No ``setChecked``
        # toggle: the button is no longer ``checkable`` because the explicit
        # ``ON``/``OFF`` label already carries the state (matches the TTS /
        # Overlay button pattern).
        time_key = (
            "live.btn_timestamps_on"
            if self._show_timestamp
            else "live.btn_timestamps_off"
        )
        if not getattr(self, "_compact_toolbar", False):
            self.time_btn.setText(tr(time_key))
        self.time_btn.setAccessibleName(tr(time_key))
        self.time_btn.setProperty("action_label_key", time_key)
        from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

        self.time_btn.setIcon(
            _create_emoji_icon("\U0001f552" if self._show_timestamp else "⛔"),
        )
        self.time_btn.setProperty(
            "action_emoji",
            "\U0001f552" if self._show_timestamp else "⛔",
        )
        # Refresh all existing transcript cards so the visibility
        # change is retroactive, not just on future entries.
        self._refresh_timestamp_visibility()

    def _refresh_timestamp_visibility(self) -> None:
        """Shows / hides the timestamp chip on every existing row.

        Walks single-view cards AND dual-view pair rows — dual chips
        now live on the pair wrapper (not its inner cards), so a
        card-only walk would skip half the transcript.  The overlay
        is updated too so it stays a perfect mirror of the main
        window's chip state.
        """
        for card in self._iter_all_cards():
            card.set_chip_visible(self._show_timestamp)
        for pair in self._iter_dual_pairs():
            pair.set_chip_visible(self._show_timestamp)
        if self._overlay is not None:
            self._overlay.apply_chip_visibility(
                self._show_timestamp, self._show_speaker,
            )

    def _refresh_speaker_visibility(self) -> None:
        """Shows / hides the speaker chip on every existing row.

        Walks single-view cards AND dual-view pair rows for the same
        reason as :meth:`_refresh_timestamp_visibility` — dual chips
        live on the pair wrapper now.  Overlay entries get the same
        toggle so its content mirrors the main window.
        """
        for card in self._iter_all_cards():
            card.set_speaker_chip_visible(self._show_speaker)
        for pair in self._iter_dual_pairs():
            pair.set_speaker_chip_visible(self._show_speaker)
        if self._overlay is not None:
            self._overlay.apply_chip_visibility(
                self._show_timestamp, self._show_speaker,
            )

    def _refresh_speaker_setting_from_disk(self) -> None:
        """Re-applies the Settings-tab "Show speaker labels" preference.

        Called on every :meth:`showEvent` so a toggle made in Settings
        (where the option lives now that the toolbar Speakers button
        is gone) takes effect retroactively against already-rendered
        cards without requiring a session restart.  No-op when the
        value hasn't changed so revisiting the page doesn't churn the
        transcript layout.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_SHOW_SPEAKER,
        )

        new_val = bool(load_setting(SETTING_LIVE_SHOW_SPEAKER, True))
        if new_val == self._show_speaker:
            return
        self._show_speaker = new_val
        self._refresh_speaker_visibility()

    def _iter_dual_pairs(self) -> Generator[_DualPairRow, None, None]:
        """Yields every dual-view pair-row in the dual scroll.

        Used by chip-visibility refreshes; dual pairs own the chip
        cluster directly (not the inner cards), so card-only walks
        miss them.
        """
        for i in range(self._dual_layout.count()):
            item = self._dual_layout.itemAt(i)
            pair = item.widget() if item else None
            if isinstance(pair, _DualPairRow):
                yield pair

    def _iter_all_cards(self) -> Generator[_TranscriptCard, None, None]:
        """Yields every visible transcript card across both views.

        Single-view cards live directly inside ``_transcript_layout``;
        dual-view cards are nested inside pair-row wrappers in
        ``_dual_layout`` (each pair-row exposes ``_left_card`` and
        ``_right_card`` attributes).  Centralising the walk here keeps
        chip / display-mode refreshes from drifting as the layout
        evolves.
        """
        for i in range(self._transcript_layout.count()):
            item = self._transcript_layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, _TranscriptCard):
                yield widget
        for i in range(self._dual_layout.count()):
            item = self._dual_layout.itemAt(i)
            pair = item.widget() if item else None
            if pair is None:
                continue
            left = getattr(pair, "_left_card", None)
            right = getattr(pair, "_right_card", None)
            if isinstance(left, _TranscriptCard):
                yield left
            if isinstance(right, _TranscriptCard):
                yield right

    def _apply_display_mode_to_cards(self) -> None:
        """Updates source / translation visibility on every card.

        Run after ``_apply_transcript_layout`` so a mid-session change
        between the four display modes (Both stacked / Both dual /
        Original / Translation) retroactively affects already-rendered
        cards — content is always kept in memory per card and just
        hidden/shown here.  Overlay entries get the same toggle so the
        floating window keeps mirroring the main window.
        """
        mode = self._resolve_display_mode()
        show_src = self._mode_shows_source(mode)
        show_tgt = self._mode_shows_target(mode)
        for card in self._iter_all_cards():
            card.set_mode_visibility(show_src, show_tgt)
        if self._overlay is not None:
            self._overlay.apply_mode_visibility(show_src, show_tgt)

    def _on_display_mode_changed(self, index: int) -> None:
        """Persists the user's transcript-display choice and re-applies layout.

        Applies both the column layout (single / dual) and the per-card
        source/translation visibility on the fly so changes take effect
        immediately against already-rendered cards.
        """
        value = self.display_mode_combo.itemData(index) or LIVE_DISPLAY_BOTH
        save_setting(SETTING_LIVE_TRANSCRIPT_DISPLAY, value)
        self._apply_transcript_layout()
        self._apply_display_mode_to_cards()

    def _refresh_content_dependent_buttons(self) -> None:
        """Disables Save / Clear when the transcript is empty.

        Both actions are no-ops without content — Save would refuse
        to write an empty file (already handled with a "Nothing to
        save" dialog), Clear would have nothing to remove.  Greying
        them out gives a clearer affordance than letting the user
        click and get a confirmation dialog about emptiness.

        Hooked from ``_add_original`` (content just appeared) and
        ``_clear_log`` (content just emptied), plus once at
        construction time for the initial empty state.  Tooltip text
        comes from the same i18n key that powers the
        already-existing "nothing to save" dialog so the wording
        stays consistent.
        """
        if not hasattr(self, "clear_btn"):
            return
        has_transcript = bool(self._transcript_records)
        self.clear_btn.setEnabled(has_transcript)
        if hasattr(self, "save_btn"):
            # Save covers BOTH transcript and audio.  Audio is ready
            # whenever there's a recording file on disk — either the
            # session has stopped and ``_last_recorded_audio_path``
            # has been finalised, OR the session is still running and
            # the engine is appending to ``_recording_path`` (mid-
            # session save snapshots the in-progress WAV; see
            # :meth:`_save_audio_now`).  Enable Save whenever EITHER
            # source has content — the chooser dialog gates per-item.
            audio_path = (
                getattr(self, "_last_recorded_audio_path", None)
                or getattr(self, "_recording_path", None)
            )
            audio_ready = audio_path is not None and audio_path.exists()
            self.save_btn.setEnabled(has_transcript or audio_ready)

    def _update_display_combo_visibility(self) -> None:
        """Hides target-language-dependent toolbar widgets when no target is set.

        Two widgets are gated on the target-language pick:

        - ``display_mode_combo`` — single-vs-dual transcript layout.
          Without a translation column, the layout choice is moot.
        - ``tts_btn`` — TTS narrates the *translated* text.  Without
          a translation, there's nothing meaningful to speak; hiding
          the button matches the display-combo's behaviour and
          removes a misleading no-op control.
        """
        target_lang = (
            self.target_lang_combo.itemData(
                self.target_lang_combo.currentIndex(),
            )
            if hasattr(self, "target_lang_combo")
            else ""
        )
        has_target = bool(target_lang)
        if hasattr(self, "display_mode_combo"):
            self.display_mode_combo.setVisible(has_target)
        if hasattr(self, "tts_btn"):
            self.tts_btn.setVisible(has_target)

    def _toggle_tts(self) -> None:
        """Toggles TTS narration on/off.

        When enabling, surfaces a warning if the user picked ElevenLabs
        without providing an API key — previously we silently fell back
        to Edge TTS, leaving the user confused about which engine ran.
        """
        self._tts_enabled = not self._tts_enabled
        # Icon toggles between speaker-on and speaker-muted.  Rendered
        # via ``_create_emoji_icon`` for the same font-fallback reason
        # as initial button setup.
        from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

        self.tts_btn.setIcon(
            _create_emoji_icon(
                "\U0001f50a" if self._tts_enabled else "\U0001f507",
            ),
        )
        tts_key = "live.btn_tts_on" if self._tts_enabled else "live.btn_tts_off"
        self.tts_btn.setAccessibleName(tr(tts_key))
        self.tts_btn.setProperty("action_label_key", tts_key)
        if not getattr(self, "_compact_toolbar", False):
            self.tts_btn.setText(tr(tts_key))
        if self._tts_enabled:
            # OFF → ON transition is the user's "I'm using TTS now"
            # signal; refresh the snapshot so a Settings change that
            # happened while TTS was off is picked up on the very
            # next synthesized sentence.
            self._tts_config = self._capture_tts_config()
            self._warn_if_elevenlabs_fallback()

    def _warn_if_elevenlabs_fallback(self) -> None:
        """Shows a one-time status-label warning when ElevenLabs has no key."""
        from src.constants.settings import SETTING_ELEVENLABS_API_KEY  # noqa: PLC0415

        method = load_setting(SETTING_VOICE_TTS_METHOD, "Edge TTS")
        if method != VOICE_TTS_ELEVENLABS:
            return
        if load_setting(SETTING_ELEVENLABS_API_KEY, "").strip():
            return
        self.status_label.setText(tr("live.tts_elevenlabs_fallback"))

    def _toggle_overlay(self) -> None:
        """Shows or hides the floating overlay window.

        On the hidden → visible transition, replays the existing
        transcript into the overlay so opening it mid-session shows
        the same content as the main window instead of an empty pane
        (entries are only forwarded to the overlay while it's
        visible, so prior sentences would otherwise be lost).
        """
        if self._overlay is None:
            self._overlay = _OverlayWindow()
            # Sync the toolbar label whenever the overlay is dismissed
            # by means other than this button (Esc inside the overlay,
            # window X-close).  Without the connect, the button stays
            # stuck on "Overlay ON" after an Esc-close.
            self._overlay.closed.connect(self._refresh_overlay_button_label)
            # Seed the placeholder's listening copy with the page's
            # current state so opening the overlay AFTER Start shows
            # "Listening…" instead of contradicting the running pill.
            self._overlay.set_placeholder_listening(
                listening=getattr(self, "_empty_state_listening", False),
            )
        if self._overlay.isVisible():
            self._overlay.hide()
        else:
            self._backfill_overlay()
            self._overlay.show()
        self._refresh_overlay_button_label()

    def _backfill_overlay(self) -> None:
        """Rebuilds the overlay's entries from ``_transcript_records``.

        Called right before showing the overlay (toggle on or auto-
        show on first transcript) so an overlay opened mid-session
        starts populated.  Clearing first is necessary because the
        overlay may have accumulated entries from an earlier visible
        period; replaying without clearing would duplicate them.
        """
        if self._overlay is None:
            return
        mode = self._resolve_display_mode()
        show_src = self._mode_shows_source(mode)
        show_tgt = self._mode_shows_target(mode)
        # Force auto-snap stickiness on every re-show.  If the user
        # had scrolled up to read history during a prior visible
        # period, ``valueChanged`` flipped ``_stick_to_bottom`` to
        # False — without re-arming it here, the backfill would
        # populate the overlay but leave the scrollbar parked at the
        # stale offset.  A re-show is a "fresh look at the live
        # transcript" intent; honour that by always landing at the
        # newest entry.
        self._overlay._stick_to_bottom = True
        self._overlay.clear_lines()
        for record in self._transcript_records:
            timestamp, speaker_id, original, translated, is_error = record
            display = self._display_speaker(speaker_id) if speaker_id else ""
            self._overlay.add_entry(
                timestamp,
                display,
                original,
                show_timestamp=self._show_timestamp,
                show_speaker=self._show_speaker,
                show_src=show_src,
                show_tgt=show_tgt,
                speaker_id=speaker_id,
            )
            if not translated:
                continue
            # Failed translations carry the same inline ⚠ marker
            # the user saw at failure time; route them through
            # ``set_last_error`` so the overlay paints the muted-
            # red error style instead of the success style.
            if is_error:
                self._overlay.set_last_error(
                    translated,
                    show_src=show_src,
                    show_tgt=show_tgt,
                )
            else:
                self._overlay.set_last_translation(
                    translated,
                    show_src=show_src,
                    show_tgt=show_tgt,
                )

    def _refresh_overlay_button_label(self) -> None:
        """Writes the overlay button's text/accessible name/key from visibility.

        Mirrors the ``_toggle_tts`` / ``_toggle_show_timestamp`` pattern
        of inline state-flip refresh (avoids the full ``apply_language``
        rebuild for a single button).  Reused by both the toolbar
        click path and the overlay's ``closed`` signal.
        """
        visible = self._overlay is not None and self._overlay.isVisible()
        overlay_key = "live.btn_overlay_on" if visible else "live.btn_overlay_off"
        if not getattr(self, "_compact_toolbar", False):
            self.overlay_btn.setText(tr(overlay_key))
        self.overlay_btn.setAccessibleName(tr(overlay_key))
        self.overlay_btn.setProperty("action_label_key", overlay_key)

    def _nudge_overlay_font(self, delta: int) -> None:
        """Bumps the overlay subtitle font size; no-op when overlay is hidden."""
        if self._overlay is not None and self._overlay.isVisible():
            self._overlay._change_font(delta)

    def _move_overlay(self, dx: int, dy: int) -> None:
        """Nudges the overlay window by ``(dx, dy)`` pixels.

        Skipped when a text-entry widget owns keyboard focus so
        Ctrl+Arrow retains its word-level-cursor meaning there.  No-op
        when no overlay is visible.
        """
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QApplication,
            QLineEdit,
            QPlainTextEdit,
            QTextEdit,
        )

        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return
        if self._overlay is None or not self._overlay.isVisible():
            return
        # Wayland: the event filter isn't installed, so this path is
        # unreachable. X11/macOS/Windows: move is honoured by the WM.
        self._overlay._move_by(dx, dy)

    def _resize_overlay(self, dw: int, dh: int) -> None:
        """Grows or shrinks the overlay by ``(dw, dh)`` pixels.

        Wayland compositors honour size requests for xdg_toplevel, so
        this works cross-platform without the Mutter-ignores-move quirk.
        No-op when no overlay is visible; text-input focus does not
        apply (numeric keys aren't semantic inside editors the way
        Ctrl+Arrow is).
        """
        if self._overlay is None or not self._overlay.isVisible():
            return
        self._overlay._resize_by(dw, dh)

    def _nudge_overlay_opacity(self, delta: float) -> None:
        """Bumps overlay opacity by ``delta``; no-op when overlay is hidden."""
        if self._overlay is None or not self._overlay.isVisible():
            return
        self._overlay._change_opacity(delta)

    def _show_audio_error(self, error_key: str, install_hint: str) -> None:
        """Shows an audio error dialog, appending an install command if known.

        Args:
            error_key: i18n key for the base error message.
            install_hint: Distro-specific install command, or empty string.
        """
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        msg = tr(error_key)
        if install_hint:
            msg += tr("live.hint_run_command").format(cmd=install_hint)

        CustomMessageDialog.show_message(
            self.window_context,
            tr("live.error_title"),
            msg,
            copy_text=install_hint,
        )

    def _start_listening(self) -> None:
        """Starts live audio capture and transcription."""
        # Delete the prior session's TEMP-WAV (if any) — once the new
        # session starts, the previous unsaved recording is no longer
        # accessible via the Save button, so we shouldn't leave it
        # sitting in /tmp forever.  Auto-saved files at the user's
        # configured path are NEVER touched by this helper (see the
        # prefix-guard in ``_cleanup_temp_audio``).
        self._cleanup_temp_audio()
        # Clear the finalised-path pointer regardless — the new
        # session will re-set it when it produces its own recording.
        # Save Audio stays disabled until that happens.
        self._last_recorded_audio_path = None
        # Re-evaluate Save enabled state — clearing the path above AND
        # the about-to-be-running session both flip its gating.
        self._refresh_content_dependent_buttons()
        # Clear any sticky error pill from a previous auto-stopped
        # session — a fresh Start means the prior error is no longer
        # the current state and the user has chosen to retry.
        self._reset_status_to_neutral()
        # Auto-clear the previous session's transcript / overlay /
        # records.  Engine timestamps are session-relative (each
        # session begins at 00:00:00) so keeping the prior content
        # would land two collisioning 00:00 baselines side by side —
        # confusing for the eye and broken for the SRT export.  The
        # auto-save setting already persists the prior session on
        # Stop, so this reset isn't destroying unsaved work for users
        # who chose to save.
        self._reset_transcript_state()
        # Session-start hooks: aliases + TTS snapshot.  Both live
        # here (not in ``_reset_transcript_state``) because Clear
        # Log shares that helper but is a mid-session action —
        # clearing them on Clear would lose the user's speaker
        # renames AND silently revert TTS to per-sentence INI
        # reads for the still-running session.
        # ``_speaker_aliases``: drop every alias the user set in
        # the PRIOR session.  Soniox's diarized IDs are session-
        # relative, so "speaker_0" in this new run is almost
        # certainly a different person; carrying aliases across
        # would silently mis-label new chips.
        self._speaker_aliases.clear()
        # ``_tts_config``: force a fresh snapshot below.  See the
        # ``_capture_tts_config`` call lower in this method.
        self._tts_config = None
        # Pre-validate audio system before doing anything else
        from src.core.live_engine import (  # noqa: PLC0415
            _get_portaudio_install_hint,
            _get_pulseaudio_install_hint,
            check_audio_available,
            check_system_audio_available,
            invalidate_audio_caches,
        )

        # Start is a user-intent re-probe point: discard cached
        # availability so the user gets a fresh diagnosis if they
        # just plugged in / installed a device since the last show.
        invalidate_audio_caches()

        audio_err = check_audio_available()
        if audio_err:
            self._show_audio_error(
                audio_err,
                _get_portaudio_install_hint(),
            )
            return

        # Validate system audio capture if needed
        audio_source = load_setting(
            SETTING_LIVE_AUDIO_SOURCE,
            AUDIO_SOURCE_MICROPHONE,
        )
        if (
            audio_source in (AUDIO_SOURCE_SYSTEM, AUDIO_SOURCE_BOTH)
            and not check_system_audio_available()
        ):
            self._show_audio_error(
                "live.error_no_system_audio",
                _get_pulseaudio_install_hint(),
            )
            return

        # Validate the auto-save audio format / ffmpeg pairing.  If the
        # user picked MP3 / FLAC / OGG for auto-save AND ffmpeg isn't
        # on PATH, the post-encode step on Stop would fail — we now
        # raise instead of silently falling back to WAV, so block the
        # session here with the install dialog rather than letting
        # the user record an hour-long session and then discover the
        # output is the wrong format.
        if not self._validate_ffmpeg_for_audio_save():
            return

        stt_method = load_setting(SETTING_LIVE_STT_METHOD, LIVE_STT_WHISPER)
        target_lang = load_setting(SETTING_LIVE_TARGET_LANG, "")
        src_lang = load_setting(SETTING_LIVE_SOURCE_LANG, "")

        # Capture TTS-related settings in one shot for the session.
        # Each ``_TTSWorker`` then reads from the snapshot instead of
        # re-hitting the INI on every sentence — see ``_TTSConfig``.
        self._tts_config = self._capture_tts_config()

        if stt_method == LIVE_STT_SONIOX:
            self._start_soniox(src_lang, target_lang, audio_source)
        else:
            # Whisper mode: require LLM if target lang is set
            if target_lang:
                from src.ui.dialogs import require_setup  # noqa: PLC0415
                from src.utils.config_manager import (  # noqa: PLC0415
                    check_llm_setup,
                )

                if not require_setup(
                    self.window_context,
                    check_llm_setup,
                    "dialog.llm_required_title",
                    "dialog.llm_required_msg",
                    4,
                ):
                    return
            self._start_whisper(src_lang, audio_source)

        self.start_btn.setText(tr("live.btn_stop"))
        self.start_btn.setStyleSheet(style_delete_button())
        self.audio_source_combo.setEnabled(False)
        self.source_lang_combo.setEnabled(False)
        self.target_lang_combo.setEnabled(False)
        # Swap the empty-state copy from "Press Start..." to "Listening,
        # capturing audio…" so the placeholder stops contradicting the
        # status pill once the user has clicked Start.  Mirror the
        # swap into the floating overlay placeholder too, so its
        # empty state stays in lockstep with the main window's.
        self._set_empty_state_listening(listening=True)
        if self._overlay is not None:
            self._overlay.set_placeholder_listening(listening=True)

        # Auto-stop-after-silence timer.  Single-shot; restarted by
        # ``_on_sentence`` every time a sentence finalises, so the
        # window represents "minutes since the last spoken sentence"
        # not "minutes since session start."  0 = disabled.
        self._start_idle_timer()

    def _start_idle_timer(self) -> None:
        """Arms the auto-stop timer based on the persisted setting.

        Idempotent: re-arms a single-shot ``QTimer`` if the setting
        is > 0, otherwise nulls ``self._idle_timer`` so the rest of
        the page can detect "no auto-stop active" via ``is None``.
        Reads the setting at every Start so a mid-session change to
        the spinbox takes effect on the next session.
        """
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_AUTO_STOP_MINUTES,
        )

        try:
            minutes = int(load_setting(SETTING_LIVE_AUTO_STOP_MINUTES, 0))
        except (TypeError, ValueError):
            minutes = 0
        if minutes <= 0:
            self._idle_timer = None
            self._idle_minutes = 0
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(minutes * 60 * 1000)
        timer.timeout.connect(self._on_idle_timeout)
        timer.start()
        self._idle_timer = timer
        self._idle_minutes = minutes

    def _stop_idle_timer(self) -> None:
        """Disarms the auto-stop timer cleanly.

        Called on user-driven Stop AND on idle-timeout-driven stop
        so the timer never survives a session.  ``deleteLater``
        guards against orphan timers on the QObject tree.
        """
        timer = getattr(self, "_idle_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        self._idle_timer = None
        self._idle_minutes = 0

    def _on_idle_timeout(self) -> None:
        """Stops the session and surfaces a user-facing notice.

        Mirrors the user-clicked Stop path (calls ``_stop_listening``
        which handles all the worker teardown), then shows a sticky
        status banner explaining why the session ended.  The user
        may be away — the sticky banner is the only signal they'll
        see when they return.
        """
        minutes = self._idle_minutes
        self._stop_listening()
        self._show_status_error(
            tr("live.auto_stopped_msg", minutes=minutes),
            sticky=True,
        )

    @staticmethod
    def _capture_tts_config() -> _TTSConfig:
        """Reads every TTS-related setting once and freezes them into a snapshot.

        Called on Start and on TTS-off → TTS-on toggle.  Centralising
        the reads here keeps the per-setting key names in one place
        and matches the eager-resolution pattern :data:`_tts_config`
        was added for — see :class:`_TTSConfig` for the rationale.
        """
        from src.constants.settings import (  # noqa: PLC0415
            ELEVENLABS_MODEL_DEFAULT,
            SETTING_ELEVENLABS_API_KEY,
            SETTING_ELEVENLABS_MODEL,
            SETTING_ELEVENLABS_VOICE_ID,
            VOICE_TTS_EDGE,
        )
        from src.utils.config_manager import (  # noqa: PLC0415
            load_google_cloud_api_key,
        )

        return _TTSConfig(
            method=load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE),
            target_lang=load_setting(SETTING_LIVE_TARGET_LANG, ""),
            elevenlabs_api_key=load_setting(SETTING_ELEVENLABS_API_KEY, ""),
            elevenlabs_voice_id=load_setting(SETTING_ELEVENLABS_VOICE_ID, ""),
            elevenlabs_model=load_setting(
                SETTING_ELEVENLABS_MODEL,
                ELEVENLABS_MODEL_DEFAULT,
            ),
            google_api_key=load_google_cloud_api_key(),
        )

    @staticmethod
    def _load_glossary() -> list[tuple[int, str, str]]:
        """Fetches active glossary entries from the database."""
        from src.core.database import (  # noqa: PLC0415
            get_active_glossary_sets,
            get_glossary_entries,
        )

        entries: list[tuple[int, str, str]] = []
        for set_id, _ in get_active_glossary_sets():
            entries.extend(get_glossary_entries(set_id))
        return entries

    # ------------------------------------------------------------------
    # Speaker rename — alias map + chip-refresh plumbing
    # ------------------------------------------------------------------

    def _display_speaker(self, speaker_id: str) -> str:
        """Returns the user-chosen alias for *speaker_id*, falling back to default.

        The single source of truth for "how do we render this
        speaker's chip text" — used both at sentence-arrival time
        (so a previously-renamed speaker's next chip lands with the
        alias already applied) and at overlay-backfill / save-
        transcript time (so reopened views and exports match).
        """
        if not speaker_id:
            return ""
        alias = self._speaker_aliases.get(speaker_id)
        if alias:
            return alias
        return _format_speaker(speaker_id)

    @Slot(str, str)
    def _on_speaker_renamed(self, speaker_id: str, new_name: str) -> None:
        """Slot wired to every renamable chip's ``renamed`` signal.

        Stores (or clears) the alias, then walks every visible chip
        across the single transcript, the dual pair, and the open
        overlay to update the label in place.  The records that
        backed the cards keep their raw IDs untouched — only the
        chips' visible text moves.

        Empty / whitespace-only / equals-default inputs drop the
        alias, restoring the formatted ``Speaker N`` label.  This
        lets the user "undo" a rename by clearing the field.

        Defensive: silently ignore an empty *speaker_id*.  In
        practice ``_RenamableSpeakerChip`` is only created when the
        chip has a non-empty raw ID (see ``_TranscriptCard.__init__``
        and ``_DualPairRow.__init__``); the guard exists so a future
        caller that bypasses those constructors can't poison the
        alias map with a ``""`` key.
        """
        if not speaker_id:
            return
        cleaned = new_name.strip()
        default = _format_speaker(speaker_id)
        if cleaned and cleaned != default:
            self._speaker_aliases[speaker_id] = cleaned
        else:
            self._speaker_aliases.pop(speaker_id, None)
        display = self._display_speaker(speaker_id)
        self._refresh_speaker_chips(speaker_id, display)

    def _refresh_speaker_chips(self, speaker_id: str, display: str) -> None:
        """Updates every visible chip that belongs to *speaker_id*.

        Walks the single-card transcript layout, the dual-pair
        layout, and the overlay's lines so a rename instantly
        propagates to every surface.  No-op for cards / pairs /
        entries whose stored ``_speaker_id`` doesn't match — Whisper
        cards (empty ID) never collide with any rename either way.
        """
        for layout in (self._transcript_layout, self._dual_layout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item is None:
                    continue
                widget = item.widget()
                if widget is None:
                    continue
                if getattr(widget, "_speaker_id", None) != speaker_id:
                    continue
                if hasattr(widget, "set_speaker_text"):
                    widget.set_speaker_text(display)
        if self._overlay is not None:
            for entry in self._overlay._iter_entries():
                if getattr(entry, "_speaker_id", None) == speaker_id:
                    entry.set_speaker_text(display)

    def _resolve_save_paths(self) -> Path | None:
        """Reads ``SETTING_LIVE_SAVE_OUTPUT`` and reserves session paths.

        Returns the audio recording path (always non-None) so the
        caller can pass it to ``LiveTranscriber.record_to``.  As a
        side effect, also reserves the transcript path on
        ``self._transcript_save_path`` when text saving is
        requested.  Audio and text share a timestamp so the pair
        lands as ``live_audio_<ts>.<ext>`` +
        ``live_transcript_<ts>.<ext>``.

        **Audio is ALWAYS recorded**, regardless of the user's Auto
        save pick.  When Auto save = None or Text-only, audio is
        written to an OS-tempdir file (`ai_translate_live_audio_*
        .wav`) so the manual Save → Audio path can still copy /
        encode it on demand.  These temp files are cleaned up on the
        next session Start (see :meth:`_cleanup_temp_audio`) and on
        a best-effort basis at app exit; in the worst-case (crash
        before cleanup) the OS tempdir reaper handles them.  When
        Auto save = Audio / Both, the file lands at the user's
        configured output folder as before; no temp involvement.

        Transcript extension comes from
        ``SETTING_LIVE_TRANSCRIPT_FORMAT``.  Audio extension is
        always ``.wav`` here — the engine writes WAV incrementally;
        post-encoding to MP3 / FLAC / OGG happens on Stop when the
        user opted into auto-save audio (see
        :meth:`_finalise_audio_recording`).
        """
        import tempfile  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            LIVE_SAVE_AUDIO,
            LIVE_SAVE_NONE,
            LIVE_SAVE_TEXT,
            LIVE_SAVE_TEXT_AUDIO,
            LIVE_TRANSCRIPT_FORMAT_ASS,
            LIVE_TRANSCRIPT_FORMAT_CSV,
            LIVE_TRANSCRIPT_FORMAT_SRT,
            LIVE_TRANSCRIPT_FORMAT_SSA,
            LIVE_TRANSCRIPT_FORMAT_VTT,
            SETTING_LIVE_SAVE_OUTPUT,
            SETTING_LIVE_TRANSCRIPT_FORMAT,
        )

        self._recording_path = None
        self._transcript_save_path = None
        # Flag the temp-audio case so ``_finalise_audio_recording``
        # knows to skip the post-encode step (we keep raw WAV for
        # the manual save path).
        self._audio_is_temp = False

        mode = str(
            load_setting(SETTING_LIVE_SAVE_OUTPUT, LIVE_SAVE_NONE),
        ).strip().lower()
        save_audio = mode in (LIVE_SAVE_AUDIO, LIVE_SAVE_TEXT_AUDIO)
        save_text = mode in (LIVE_SAVE_TEXT, LIVE_SAVE_TEXT_AUDIO)

        # Shared timestamp pairs the audio + text files when both
        # modes are active.  Saving only one is fine — the timestamp
        # then just identifies the single file.
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        from src.utils.path_manager import (  # noqa: PLC0415
            generate_live_session_output_path,
        )

        if save_audio:
            try:
                # Engine writes WAV unconditionally; post-encode to
                # MP3 (if user requested) happens on Stop.
                self._recording_path = generate_live_session_output_path(
                    extension=".wav",
                    stem_prefix="live_audio",
                    timestamp=timestamp,
                )
            except OSError as exc:
                logger.warning(
                    "Live recording: cannot prepare audio path (%s); skipping",
                    exc,
                )
        else:
            # No auto-save audio requested, but we still record to a
            # temp WAV so manual Save → Audio works.  ``mkstemp``
            # returns a fresh path under the OS tempdir; the empty
            # file it creates is overwritten when the engine opens
            # the WAV stream a moment later.  Prefix matches the
            # cleanup helper so orphan files from prior runs can be
            # swept on app startup.
            try:
                fd, tmp_path = tempfile.mkstemp(
                    suffix=".wav", prefix=_TEMP_AUDIO_PREFIX,
                )
                import os as _os  # noqa: PLC0415
                _os.close(fd)
                self._recording_path = Path(tmp_path)
                self._audio_is_temp = True
                logger.info(
                    "Live: reserved temp audio path for manual save: %s",
                    self._recording_path,
                )
            except OSError as exc:
                logger.warning(
                    "Live recording: cannot reserve temp audio path (%s);"
                    " manual Save → Audio will be unavailable",
                    exc,
                )
        if save_text:
            fmt = str(load_setting(
                SETTING_LIVE_TRANSCRIPT_FORMAT, LIVE_TRANSCRIPT_FORMAT_SRT,
            )).strip().lower()
            valid_fmts = (
                LIVE_TRANSCRIPT_FORMAT_SRT,
                LIVE_TRANSCRIPT_FORMAT_VTT,
                LIVE_TRANSCRIPT_FORMAT_ASS,
                LIVE_TRANSCRIPT_FORMAT_SSA,
                LIVE_TRANSCRIPT_FORMAT_CSV,
            )
            if fmt not in valid_fmts:
                fmt = LIVE_TRANSCRIPT_FORMAT_SRT  # corrupt setting → safe default
            try:
                self._transcript_save_path = generate_live_session_output_path(
                    extension=f".{fmt}",
                    stem_prefix="live_transcript",
                    timestamp=timestamp,
                )
            except OSError as exc:
                logger.warning(
                    "Live recording: cannot prepare transcript path (%s); skipping",
                    exc,
                )
        return self._recording_path

    def _make_filtered_on_stopped(self) -> Callable[[], None]:
        """Returns an ``on_stopped`` callback tagged to the current session.

        Engines fire ``on_stopped`` from a background thread; the
        callback emits the page's ``_transcriber_stopped`` signal
        which is queued back to the UI thread.  When the user
        clicks Stop and starts a NEW session before the OLD
        engine's queued signal arrives, the OLD callback would
        otherwise wipe the NEW session's ``_transcriber`` reference
        (and worse, flip the button to "Start" mid-stream).

        Solution: bump a per-page session generation counter and
        capture it in a closure here.  Each new session captures a
        new generation; the OLD callback's gen no longer matches
        so its emit is skipped.  The slot ``_on_transcriber_stopped``
        therefore only ever runs for the SAME transcriber that
        owned the callback — legitimate self-terminate paths still
        work because the matching gen is the active one.
        """
        self._session_gen = getattr(self, "_session_gen", 0) + 1
        my_gen = self._session_gen

        def _on_stopped() -> None:
            if self._session_gen == my_gen:
                self._transcriber_stopped.emit()
            # Else: an OLD transcriber fired after a NEW session
            # started.  Drop the signal so the new session's UI
            # state stays intact.

        return _on_stopped

    def _start_whisper(self, src_lang: str, audio_source: str) -> None:
        """Starts the Whisper-based local transcriber."""
        from src.core.live_engine import LiveTranscriber  # noqa: PLC0415

        model_size = load_setting(SETTING_LIVE_WHISPER_MODEL, "tiny")

        # faster-whisper's ``language=`` parameter only accepts 2-letter
        # ISO codes (``vi``, ``en``, …) — passing a UI label like
        # ``"Vietnamese"`` raises at transcribe() time.  Convert here so
        # the setting can stay label-based (matching the rest of the
        # app) while the engine gets what it expects.  Empty string
        # passes through unchanged → whisper auto-detects.
        src_code = _lang_to_code(src_lang) if src_lang else ""

        # Wrap callback to pad speaker/translated args for the 5-arg signal
        def _on_whisper_sentence(
            text: str,
            start: float,
            end: float,
        ) -> None:
            self._sentence_received.emit(text, start, end, "", "")

        self._transcriber = LiveTranscriber(
            on_sentence=_on_whisper_sentence,
            on_status=self._status_received.emit,
            on_stopped=self._make_filtered_on_stopped(),
            model_size=model_size,
            language=src_code,
            audio_source=audio_source,
            record_to=self._resolve_save_paths(),
        )
        self._transcriber.start()

    def _start_soniox(
        self,
        src_lang: str,
        target_lang: str,
        audio_source: str,
    ) -> None:
        """Starts the Soniox cloud transcriber."""
        from src.core.soniox_engine import SonioxTranscriber  # noqa: PLC0415

        # Pre-flight gating happens at the UI layer via the
        # ``_stt_setup_warning`` banner + disabled Start button — by
        # the time we get here, the key is expected to be present.
        # The empty-key short-circuit stays as a defence-in-depth
        # guard (early return instead of reaching the SDK with empty
        # creds and getting a less-actionable runtime error).
        api_key = load_setting(SETTING_SONIOX_API_KEY, "")
        if not api_key:
            return

        # Convert language labels to 2-letter codes for Soniox
        src_code = _lang_to_code(src_lang)
        tgt_code = _lang_to_code(target_lang)

        # Build glossary terms for Soniox translation context
        glossary = self._load_glossary()
        translation_terms = (
            [{"source": src, "target": tgt} for _, src, tgt in glossary]
            if glossary
            else None
        )

        self._transcriber = SonioxTranscriber(
            api_key=api_key,
            on_sentence=self._sentence_received.emit,
            on_status=self._status_received.emit,
            on_stopped=self._make_filtered_on_stopped(),
            on_error=self._stt_error_received.emit,
            source_lang=src_code,
            target_lang=tgt_code,
            translation_terms=translation_terms,
        )
        self._transcriber.start()

        # Feed audio to Soniox from microphone/system capture
        self._start_audio_feed(audio_source)

    def _start_audio_feed(self, audio_source: str) -> None:
        """Starts audio capture and feeds PCM bytes to the streaming STT engine.

        Dispatches by source so only the streams we need are opened:

        * ``microphone`` — mic-only ``sounddevice.InputStream``.
        * ``system``     — parec subprocess against the default sink
          monitor; no mic stream at all (avoids pushing silent mic bytes
          to the backend, which previously happened unconditionally).
        * ``both``       — both sources are captured into separate
          queues and a mixer thread combines them per block before
          forwarding the merged PCM to the transcriber, mirroring the
          semantics of :class:`LiveTranscriber`'s internal mixer for
          whisper mode.

        Prior to the dispatch, Soniox received mic bytes and system
        bytes *interleaved* into the same ``send_audio`` queue in
        "both" mode — the backend effectively saw two unrelated audio
        streams multiplexed and produced garbled transcripts.
        """
        transcriber = self._transcriber
        if transcriber is None:
            return

        # Defensive teardown: if a previous call left streams / parec /
        # mixer running (e.g. caller skipped ``_stop_audio_feed``),
        # release them first so the new dispatch doesn't orphan the
        # old ``InputStream`` / ``Popen`` / thread references.
        self._stop_audio_feed()

        # Reserve + open the WAV recording file for THIS Soniox session.
        # Soniox itself only streams PCM to its WebSocket — no engine-
        # side disk write — so the audio feed is the only place that can
        # tee the bytes to a file.  Reuses the same path-reservation
        # logic Whisper uses (always returns a path now: configured
        # location when Auto save = Audio / Both, OS-tempdir WAV
        # otherwise) so manual Save → Audio works for Soniox sessions
        # too.  No-op on path-reservation failure — recording is a
        # best-effort side channel; the live session itself must still
        # run.
        self._open_soniox_recording()

        if audio_source == AUDIO_SOURCE_MICROPHONE:
            self._start_mic_feed(transcriber)
        elif audio_source == AUDIO_SOURCE_SYSTEM:
            self._start_parec_feed(transcriber)
        elif audio_source == AUDIO_SOURCE_BOTH:
            self._start_mixed_feed(transcriber)

    def _open_soniox_recording(self) -> None:
        """Opens a WAV writer for the current Soniox session's audio.

        Called once per session from ``_start_audio_feed``.  The
        writer is closed in ``_stop_audio_feed``.  Sample rate /
        channel count match what the engine sends on the wire so the
        recorded WAV is faithful to what Soniox transcribed.
        """
        import wave  # noqa: PLC0415

        from src.core.live_engine import (  # noqa: PLC0415
            _CHANNELS,
            _SAMPLE_RATE,
        )

        path = self._resolve_save_paths()
        self._soniox_wav_writer = None
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            writer = wave.open(str(path), "wb")  # noqa: SIM115
            writer.setnchannels(_CHANNELS)
            writer.setsampwidth(2)  # s16le = 2 bytes/sample
            writer.setframerate(_SAMPLE_RATE)
            self._soniox_wav_writer = writer
        except OSError as exc:
            logger.warning(
                "Soniox WAV recording failed to open %s: %s — "
                "continuing without recording",
                path, exc,
            )

    def _record_soniox_pcm(self, pcm: bytes) -> None:
        """Tees a PCM chunk into the Soniox WAV recording.

        Called from the audio-feed callbacks (mic / parec / mixer)
        right after ``transcriber.send_audio``.  No-op when no
        writer is open (recording reservation failed or session is
        Whisper, which has its own engine-side writer).  Errors are
        logged once per session and the writer is dropped — audio
        capture should never abort the live session.
        """
        writer = self._soniox_wav_writer
        if writer is None:
            return
        try:
            writer.writeframes(pcm)
        except (OSError, ValueError) as exc:
            import contextlib  # noqa: PLC0415
            logger.warning("Soniox WAV write failed: %s — disabling recording", exc)
            with contextlib.suppress(OSError, ValueError):
                writer.close()
            self._soniox_wav_writer = None

    def _start_mic_feed(self, transcriber: Any) -> None:  # noqa: ANN401
        """Mic-only path: sounddevice stream → transcriber.send_audio."""
        import numpy as np  # noqa: PLC0415
        import sounddevice as sd  # noqa: PLC0415

        from src.core.live_engine import (  # noqa: PLC0415
            _BLOCK_SIZE,
            _CHANNELS,
            _SAMPLE_RATE,
        )

        def _mic_callback(
            indata: object,
            _frames: int,
            _time: object,
            _status: object,
        ) -> None:
            if transcriber and transcriber.is_running:
                # Flatten to (N,) before ``.tobytes()`` so the output is
                # sample-order PCM regardless of the array's (N, C)
                # shape.  For ``channels=1`` the flat and (N, 1) layouts
                # happen to coincide, but spelling it explicitly
                # matches ``_start_mixed_feed`` and keeps a future
                # channel-count change from silently interleaving.
                pcm = (indata * 32767).astype(np.int16).reshape(-1).tobytes()
                transcriber.send_audio(pcm)
                self._record_soniox_pcm(pcm)

        self._soniox_stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            blocksize=_BLOCK_SIZE,
            dtype="float32",
            callback=_mic_callback,
        )
        self._soniox_stream.start()

    def _start_parec_feed(self, transcriber: Any) -> None:  # noqa: ANN401
        """System-only path: parec subprocess → transcriber.send_audio."""
        import subprocess  # noqa: PLC0415
        import threading  # noqa: PLC0415

        from src.core.live_engine import (  # noqa: PLC0415
            _BLOCK_SIZE,
            _SAMPLE_RATE,
            _get_default_monitor_source,
        )

        monitor = _get_default_monitor_source()
        if not monitor:
            # No PulseAudio monitor source — surface this to the user
            # instead of silently running the transcriber on no audio.
            self._status_received.emit(tr("live.error_no_system_audio"))
            return

        self._soniox_parec = subprocess.Popen(  # noqa: S603, S607
            [
                "parec",
                f"--device={monitor}",
                "--format=s16le",
                "--channels=1",
                f"--rate={_SAMPLE_RATE}",
                "--raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        bytes_per_block = _BLOCK_SIZE * 2  # 16-bit = 2 bytes/sample

        def _reader() -> None:
            proc = self._soniox_parec
            while transcriber.is_running and proc and proc.poll() is None:
                data = proc.stdout.read(bytes_per_block)
                if not data:
                    break
                transcriber.send_audio(data)
                self._record_soniox_pcm(data)

        self._soniox_parec_thread = threading.Thread(
            target=_reader,
            daemon=True,
        )
        self._soniox_parec_thread.start()

    def _start_mixed_feed(self, transcriber: Any) -> None:  # noqa: ANN401
        """Both-mode path: mic + system captured separately, mixed per block.

        A mic-silence gate drops silent mic blocks *before* the sum so
        room hiss can't pollute clean system audio (a common scenario:
        user watching a video with the laptop mic open).  Samples are
        kept in ``int16`` to match the backends' PCM s16le expectation;
        the sum is done in ``int32`` and clipped back to int16 range
        to avoid wrap-around when both sources happen to be loud.
        """
        import queue as _queue  # noqa: PLC0415
        import subprocess  # noqa: PLC0415
        import threading  # noqa: PLC0415

        import numpy as np  # noqa: PLC0415
        import sounddevice as sd  # noqa: PLC0415

        from src.core.live_engine import (  # noqa: PLC0415
            _BLOCK_SIZE,
            _CHANNELS,
            _QUEUE_MAX_BLOCKS,
            _SAMPLE_RATE,
            _SILENCE_THRESHOLD,
            _get_default_monitor_source,
            _put_drop_oldest,
            next_block,
        )

        # Early-out when no system-audio monitor is present: the mixer
        # would otherwise waste 500 ms per iteration in ``next_block``
        # on a sys queue that will never produce, halving mic
        # throughput and growing the mic queue without bound.  Degrade
        # to the mic-only feed and surface why to the user.
        if _get_default_monitor_source() is None:
            self._status_received.emit(tr("live.error_no_system_audio"))
            self._start_mic_feed(transcriber)
            return

        # Bounded queues + drop-oldest producer pattern — same rationale
        # as ``LiveTranscriber._audio_queue``: keeps backlog capped
        # when the transcription backend (Soniox) or the
        # mixer itself can't keep up with capture.
        mic_q: _queue.Queue[np.ndarray] = _queue.Queue(maxsize=_QUEUE_MAX_BLOCKS)
        sys_q: _queue.Queue[np.ndarray] = _queue.Queue(maxsize=_QUEUE_MAX_BLOCKS)

        def _mic_callback(
            indata: object,
            _frames: int,
            _time: object,
            _status: object,
        ) -> None:
            if transcriber and transcriber.is_running:
                _put_drop_oldest(
                    mic_q,
                    (indata * 32767).astype(np.int16).reshape(-1),
                )

        self._soniox_stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            blocksize=_BLOCK_SIZE,
            dtype="float32",
            callback=_mic_callback,
        )
        self._soniox_stream.start()

        # Monitor availability was checked at the top of the method;
        # if we're here, parec is expected to work.
        monitor = _get_default_monitor_source()
        self._soniox_parec = subprocess.Popen(  # noqa: S603, S607
            [
                "parec",
                f"--device={monitor}",
                "--format=s16le",
                "--channels=1",
                f"--rate={_SAMPLE_RATE}",
                "--raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        bytes_per_block = _BLOCK_SIZE * 2

        def _parec_reader() -> None:
            proc = self._soniox_parec
            while transcriber.is_running and proc and proc.poll() is None:
                data = proc.stdout.read(bytes_per_block)
                if not data:
                    break
                _put_drop_oldest(sys_q, np.frombuffer(data, dtype=np.int16))

        self._soniox_parec_thread = threading.Thread(
            target=_parec_reader,
            daemon=True,
        )
        self._soniox_parec_thread.start()

        # Mixer thread: pull newest block from each queue, silence-gate
        # mic, sum, clip, forward.  Mirrors ``LiveTranscriber._read_block``.
        int16_max = np.iinfo(np.int16).max  # 32767

        # Explicit stop event so the mixer exits deterministically when
        # ``_stop_audio_feed`` runs.  We can't rely on
        # ``transcriber.is_running`` alone: ``_stop_listening`` calls
        # ``_stop_audio_feed`` *before* ``transcriber.stop()``, so the
        # flag is still True during the join window and the mixer can
        # block on ``next_block``'s 0.5 s timeout past our 1 s join.
        stop_event = threading.Event()
        self._soniox_mixer_stop = stop_event

        def _mixer() -> None:
            while not stop_event.is_set() and transcriber and transcriber.is_running:
                mic_block = next_block(mic_q, timeout=0.5)
                sys_block = next_block(sys_q, timeout=0.5)

                if mic_block is not None:
                    # Compute RMS in [-1, 1] domain for threshold parity
                    # with the whisper-internal mixer.
                    mic_f = mic_block.astype(np.float32) / (int16_max + 1)
                    if float(np.sqrt(np.mean(mic_f**2))) < _SILENCE_THRESHOLD:
                        mic_block = None

                if mic_block is not None and sys_block is not None:
                    mixed = np.clip(
                        mic_block.astype(np.int32) + sys_block.astype(np.int32),
                        -int16_max - 1,
                        int16_max,
                    ).astype(np.int16)
                else:
                    mixed = mic_block if mic_block is not None else sys_block

                if mixed is not None:
                    pcm = mixed.tobytes()
                    transcriber.send_audio(pcm)
                    self._record_soniox_pcm(pcm)

        self._soniox_mixer_thread = threading.Thread(
            target=_mixer,
            daemon=True,
        )
        self._soniox_mixer_thread.start()

    def _stop_audio_feed(self) -> None:
        """Synchronous audio-feed teardown for the defensive-cleanup path.

        ``_start_audio_feed`` calls this before opening a fresh feed
        in case the page somehow still holds stale stream / parec /
        thread references (programmer error — the normal Stop path
        already routes everything through :class:`_EngineStopWorker`
        and clears these slots).  Bounded with the same short
        timeouts the worker uses so this defensive cleanup can't
        freeze the UI for long even if it's reached.
        """
        import subprocess  # noqa: PLC0415

        stream = getattr(self, "_soniox_stream", None)
        if stream is not None:
            stream.stop()
            stream.close()
            self._soniox_stream = None
        proc = getattr(self, "_soniox_parec", None)
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1)
            self._soniox_parec = None
        thread = getattr(self, "_soniox_parec_thread", None)
        if thread is not None:
            thread.join(timeout=1)
            self._soniox_parec_thread = None
        stop_event = getattr(self, "_soniox_mixer_stop", None)
        if stop_event is not None:
            stop_event.set()
            self._soniox_mixer_stop = None
        mixer = getattr(self, "_soniox_mixer_thread", None)
        if mixer is not None:
            mixer.join(timeout=1)
            self._soniox_mixer_thread = None
        # Close the WAV writer LAST so any final blocks queued by the
        # reader / mixer threads above flushed through before the file
        # is closed.  Errors are logged but never raised — recording is
        # a best-effort side channel.  ``self._recording_path`` itself
        # stays set so the post-Stop finalise loop in ``_reset_ui_to_
        # ready`` picks the file up and stashes it on
        # ``_last_recorded_audio_path`` (which drives Save → Audio).
        writer = getattr(self, "_soniox_wav_writer", None)
        if writer is not None:
            try:
                writer.close()
            except (OSError, ValueError) as exc:
                logger.warning("Soniox WAV close failed: %s", exc)
            self._soniox_wav_writer = None

    def _stop_listening(self) -> None:
        """Initiates non-blocking engine teardown.

        The blocking parts (transcriber processing-thread join, parec
        SIGTERM→SIGKILL escalation, reader / mixer thread joins) run
        in :class:`_EngineStopWorker` on a background thread — they
        used to block the UI thread for up to ~12 s on the worst-case
        Stop click and routinely triggered window-manager
        "application not responding" hints.

        The UI is updated synchronously:

        1. The auto-stop QTimer is disarmed (it lives on the UI
           thread and must be torn down here, not in the worker).
        2. Engine + audio-feed references are snapshotted, then
           nulled on ``self`` so late signals from the engine drop
           through the existing ``self._transcriber is None`` guards
           in ``_on_sentence`` / ``_on_status`` / etc.
        3. The Start button is disabled and flipped to "Stopping…"
           with a matching status pill so the user gets immediate
           feedback that the click registered.
        4. The worker is started; its ``finished`` signal lands on
           :meth:`_on_stop_complete` which flips the UI back to
           Ready.

        Idempotent against a teardown already in flight (the button
        is disabled while ``_stop_worker.isRunning()``, but the
        keyboard shortcut path and tests may still re-enter).
        """
        # Disarm the auto-stop timer before tearing down anything
        # else: idempotent against the idle-timeout path (which
        # also calls ``_stop_listening``) and prevents a stale
        # ``timeout`` signal from firing after the session ends.
        self._stop_idle_timer()

        # Already stopping → no-op.  The in-flight worker owns the
        # captured refs and will fire ``_on_stop_complete`` when it
        # finishes; spawning a second worker would race the first.
        existing = getattr(self, "_stop_worker", None)
        if existing is not None and existing.isRunning():
            return

        # Capture every blocking-teardown reference, then null them
        # on ``self`` synchronously so the page presents as already
        # stopped to any late signal that arrives during teardown.
        transcriber = self._transcriber
        soniox_stream = getattr(self, "_soniox_stream", None)
        soniox_parec = getattr(self, "_soniox_parec", None)
        soniox_parec_thread = getattr(self, "_soniox_parec_thread", None)
        soniox_mixer_stop = getattr(self, "_soniox_mixer_stop", None)
        soniox_mixer_thread = getattr(self, "_soniox_mixer_thread", None)

        self._transcriber = None
        self._soniox_stream = None
        self._soniox_parec = None
        self._soniox_parec_thread = None
        self._soniox_mixer_stop = None
        self._soniox_mixer_thread = None

        # Nothing to tear down (no engine and no audio feed) → skip
        # the worker entirely and flip to Ready immediately.  Keeps
        # the test path simple for ``_stop_listening`` calls against
        # a page that never started a session.
        if (
            transcriber is None
            and soniox_stream is None
            and soniox_parec is None
            and soniox_parec_thread is None
            and soniox_mixer_thread is None
        ):
            self._reset_ui_to_ready()
            return

        # Transitional UI: disabled "Stopping…" button + matching
        # status pill so the user sees the click registered even
        # when teardown takes seconds.  Re-enabled in
        # ``_on_stop_complete``.
        self.start_btn.setEnabled(False)
        self.start_btn.setText(tr("live.btn_stopping"))
        self.status_label.setText(tr("live.status_stopping"))

        worker = _EngineStopWorker(
            transcriber,
            soniox_stream=soniox_stream,
            soniox_parec=soniox_parec,
            soniox_parec_thread=soniox_parec_thread,
            soniox_mixer_stop=soniox_mixer_stop,
            soniox_mixer_thread=soniox_mixer_thread,
        )
        worker.finished.connect(self._on_stop_complete)
        self._stop_worker = worker
        worker.start()

    @Slot()
    def _on_stop_complete(self) -> None:
        """Fired when :class:`_EngineStopWorker` finishes its teardown.

        Re-enables the Start button and runs the standard Ready
        reset (which handles transcript auto-save + status pill
        restoration).  Drops the worker reference so a subsequent
        Stop can spawn a fresh one.

        Race guard: a user who keyboard-shortcuts Stop → Start
        within milliseconds (or whose Start follows an auto-stop)
        can have a NEW session running by the time this slot fires
        for the OLD worker.  Resetting the UI then would flip the
        button to "Start" while a live session is active — visibly
        wrong.  When ``self._transcriber`` is already non-None we
        know a fresh session has begun; skip the UI reset and just
        free the worker reference.
        """
        worker = getattr(self, "_stop_worker", None)
        self._stop_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._transcriber is not None:
            # A new session beat us to it — leave the live UI alone.
            return
        self.start_btn.setEnabled(True)
        self._reset_ui_to_ready()

    @Slot()
    def _on_transcriber_stopped(self) -> None:
        """Called (via signal) when the background thread exits.

        Triggered either by user-initiated Stop (via the engine
        teardown worker calling ``transcriber.stop()``) or by an
        unexpected self-termination (engine crash, WebSocket close,
        etc.).  Stale callbacks from OLD transcribers can't reach
        this slot because the ``on_stopped`` wrapper installed in
        ``_start_whisper`` / ``_start_soniox`` only forwards to the
        signal when ``self._transcriber`` still points at the SAME
        instance that owned the callback.  See those methods for
        the closure-based identity check.
        """
        self._transcriber = None
        self._reset_ui_to_ready()

    def _reset_ui_to_ready(self) -> None:
        """Resets control bar to the idle / ready state."""
        self.start_btn.setText(tr("live.btn_start"))
        self.start_btn.setStyleSheet(style_primary_button())
        self.audio_source_combo.setEnabled(True)
        self.source_lang_combo.setEnabled(True)
        self.target_lang_combo.setEnabled(True)
        self._set_empty_state_listening(listening=False)
        if self._overlay is not None:
            self._overlay.set_placeholder_listening(listening=False)
        # Auto-save the transcript when text save was requested AND we
        # accumulated at least one record.  Empty-record sessions skip
        # the write so we don't litter the output folder with empty
        # ``.txt`` files for false-start Stop clicks.
        text_saved: Path | None = None
        if (
            self._transcript_save_path is not None
            and self._transcript_records
            and self._write_transcript_to(self._transcript_save_path)
        ):
            text_saved = self._transcript_save_path
        # The audio file is written incrementally by the engine; here
        # we only confirm it actually landed (the engine's open / write
        # path may have failed silently and disabled itself).  When
        # the user picked MP3, we also post-encode the WAV to MP3
        # via ffmpeg now that the engine has finished writing.
        audio_saved: Path | None = None
        if self._recording_path is not None and self._recording_path.exists():
            audio_saved = self._finalise_audio_recording(self._recording_path)
            # Stash the finalised path for the manual ``Save Audio``
            # button.  Survives the ``self._recording_path = None``
            # reset below so the user can save to a different location
            # AFTER the session ends.
            self._last_recorded_audio_path = audio_saved
        else:
            # Diagnostic for the "audio greyed-out in Save chooser" bug
            # path: if we expected a recording (either auto-save audio
            # OR always-on temp WAV) but the file isn't on disk, that
            # means the engine's write side disabled itself silently —
            # log enough state for triage.  Most likely cause is the
            # engine's ``_open_recording`` failing on the very first
            # write block (e.g. the path was unwriteable).
            logger.info(
                "Live: no audio file at session end "
                "(_recording_path=%s, exists=%s, _audio_is_temp=%s) — "
                "manual Save → Audio will be disabled this session",
                self._recording_path,
                self._recording_path.exists()
                if self._recording_path else "n/a",
                getattr(self, "_audio_is_temp", "n/a"),
            )
        # Surface what was saved on the status pill so the user knows
        # where to look without hunting through Settings.  When both
        # land, point at the audio file (the .txt sibling lives next
        # to it under the same timestamp).  Sticky-error sessions
        # (auto-stop path) skip the rewrite entirely: the red error
        # pill is the more important signal and clobbering it with
        # "Ready" / a save-path toast would lose that context.
        if self._sticky_error_active:
            pass
        elif audio_saved is not None:
            self._reset_status_to_neutral()
            self.status_label.setText(
                tr("live.recording_saved_status", path=str(audio_saved)),
            )
        elif text_saved is not None:
            self._reset_status_to_neutral()
            self.status_label.setText(
                tr("live.recording_saved_status", path=str(text_saved)),
            )
        else:
            # Reset the status pill; stale "Listening..." or a TTS-error
            # message from the just-ended session shouldn't linger.  We
            # call the full neutral-reset helper so the pill style + bg
            # also revert (a previous TTS error may have left them red).
            self._reset_status_to_neutral()
            self.status_label.setText(tr("live.status_ready"))
        # Clear the per-session paths so the next Start re-resolves
        # them based on the (possibly-changed) save mode.
        self._recording_path = None
        self._transcript_save_path = None
        # Sweep any "…" placeholders left behind by LLM workers whose
        # results were dropped post-Stop (see ``_on_translated``'s
        # ``self._transcriber is None`` early-return).  Without this,
        # the user sees stale placeholders in the transcript and any
        # saved export carries them as the translation text — both
        # surfaces would silently misrepresent "translation cancelled"
        # as "translation = …".
        self._sweep_pending_placeholders()
        # Refresh content-dependent buttons so Save Audio flips from
        # disabled (running) to enabled (we just finalised a recording).
        # Save / Clear also depend on the running flag indirectly via
        # ``_transcriber.is_running``, so the same call updates them.
        self._refresh_content_dependent_buttons()

    def _sweep_pending_placeholders(self) -> None:
        """Clears "…" placeholders on cards whose translation never arrived.

        Iterates the single-view transcript, the dual-view layout,
        AND the overlay (when present) and calls
        ``clear_pending_placeholder`` on each card / entry — a no-op
        for cards that already have real translation text, so safe
        to run unconditionally after every Stop.

        Also patches ``_transcript_records`` so the saved transcript
        export reflects the cancelled state (empty ``tgt``) rather
        than carrying the placeholder symbol as fake translation
        content.  Records were stashed with ``tgt=""`` on insert and
        only get the placeholder text in the on-screen card; the
        records themselves are already correct, so no patching is
        strictly required there — but we add a sanity pass anyway in
        case a future change starts writing placeholder text back to
        records.
        """
        for layout in (self._transcript_layout, self._dual_layout):
            for i in range(layout.count()):
                item = layout.itemAt(i)
                widget = item.widget() if item is not None else None
                if widget is None:
                    continue
                # Single-view card: direct.  Dual-view: pair row
                # holds two ``_TranscriptCard`` children; iterate.
                if hasattr(widget, "clear_pending_placeholder"):
                    widget.clear_pending_placeholder()
                else:
                    for child in widget.findChildren(_TranscriptCard):
                        child.clear_pending_placeholder()
        if self._overlay is not None:
            for entry in self._overlay._iter_entries():
                if hasattr(entry, "clear_pending_placeholder"):
                    entry.clear_pending_placeholder()

    def _save_now(self) -> None:
        """Save button entry point — opens the chooser, dispatches per pick.

        The chooser disables options that have no content (no
        transcript → Transcript greyed; no recorded audio file →
        Audio greyed).  When both are unavailable, the button itself
        was disabled by ``_refresh_content_dependent_buttons`` so
        this method is unreachable in that state.

        After the chooser closes with at least one selection, the
        appropriate per-artefact save handler runs — each opens its
        own file-save dialog so the user can pick distinct locations.
        Cancelling either inner dialog still allows the other write
        to proceed.
        """
        transcript_ok = bool(self._transcript_records)
        # Audio source for both post-session save and mid-session
        # snapshot save: finalised path takes precedence (already
        # contains a valid WAV header), with in-progress recording
        # path as fallback for mid-session clicks.
        audio_path = (
            self._last_recorded_audio_path or self._recording_path
        )
        audio_ok = audio_path is not None and audio_path.exists()
        sel_transcript, sel_audio, accepted = _SaveOptionsDialog.ask(
            self.window_context,
            transcript_available=transcript_ok,
            audio_available=audio_ok,
        )
        if not accepted:
            return
        if sel_transcript:
            self._save_transcript_now()
        if sel_audio:
            self._save_audio_now()

    def _save_transcript_now(self) -> None:
        """Opens a Save File dialog and writes the transcript to disk.

        Default extension comes from the user's ``SETTING_LIVE_
        TRANSCRIPT_FORMAT`` pick on the Settings page (SRT / VTT /
        ASS / SSA / CSV) — same setting that powers the auto-save
        path during session finalisation.  Default directory comes
        from ``SETTING_LIVE_OUTPUT_PATH`` (or the platform default
        when empty).  Empty transcripts show a "Nothing to save"
        dialog rather than writing a 0-byte file.
        """
        from PySide6.QtWidgets import QFileDialog  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            LIVE_TRANSCRIPT_FORMAT_SRT,
            SETTING_LIVE_OUTPUT_PATH,
            SETTING_LIVE_TRANSCRIPT_FORMAT,
        )
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415
        from src.utils.path_manager import (  # noqa: PLC0415
            get_default_live_output_dir,
        )

        if not self._transcript_records:
            CustomMessageDialog.show_message(
                self.window_context,
                tr("live.save_transcript_empty_title"),
                tr("live.save_transcript_empty_msg"),
            )
            return

        fmt = str(load_setting(
            SETTING_LIVE_TRANSCRIPT_FORMAT, LIVE_TRANSCRIPT_FORMAT_SRT,
        )).strip().lower() or LIVE_TRANSCRIPT_FORMAT_SRT
        out_dir = str(
            load_setting(SETTING_LIVE_OUTPUT_PATH, "")
            or get_default_live_output_dir(),
        )
        # Mirror the auto-save filename convention so users recognise
        # both routes write the same shape of artefact.
        from datetime import datetime  # noqa: PLC0415
        suggested = (
            Path(out_dir)
            / f"live_transcript_{datetime.now():%Y%m%d_%H%M%S}.{fmt}"
        )
        # ``getSaveFileName`` returns ("", "") on cancel — short-circuit.
        chosen, _ = QFileDialog.getSaveFileName(
            self.window_context,
            tr("live.btn_save_transcript"),
            str(suggested),
            f"*.{fmt}",
        )
        if not chosen:
            return
        target = Path(chosen)
        # If the user typed a path with no extension, append the chosen
        # format so ``_write_transcript_to`` resolves the right serializer.
        if not target.suffix:
            target = target.with_suffix(f".{fmt}")
        if self._write_transcript_to(target):
            CustomMessageDialog.show_message(
                self.window_context,
                tr("live.save_transcript_ok_title"),
                tr(
                    "live.save_transcript_ok_msg",
                    count=len(self._transcript_records),
                    path=str(target),
                ),
            )
        else:
            CustomMessageDialog.show_message(
                self.window_context,
                tr("live.save_transcript_failed_title"),
                tr(
                    "live.save_transcript_failed_msg",
                    error=f"could not write {target}",
                ),
            )

    def _save_audio_now(self) -> None:
        """Opens a Save File dialog and writes the recorded audio.

        Source resolution: prefer ``_last_recorded_audio_path``
        (finalised, valid WAV header) — that's the post-session
        case.  Fall back to ``_recording_path`` for the **mid-
        session** case: the engine is still appending blocks, so we
        snapshot the file via :meth:`_snapshot_in_progress_wav`
        which copies the current PCM bytes and patches the WAV
        header to reflect the actual data size on disk (the wave
        module only writes correct sizes on ``close()``; mid-stream
        the header carries placeholder zeros that most players
        refuse).

        Encoding rules: when source is WAV and the user wants MP3 /
        FLAC / OGG, route through ``post_encode_audio``.  Same
        format → ``shutil.copy2``.  Mid-session snapshots are
        always WAV and follow the same encode-or-copy choice.

        Default dialog extension follows the user's ``SETTING_LIVE
        _AUDIO_FORMAT`` so saved files land typed consistently with
        their preference.
        """
        import shutil  # noqa: PLC0415

        from PySide6.QtWidgets import QFileDialog  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            LIVE_AUDIO_FORMAT_MP3,
            LIVE_AUDIO_FORMAT_WAV,
            SETTING_LIVE_AUDIO_FORMAT,
            SETTING_LIVE_OUTPUT_PATH,
        )
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415
        from src.utils.path_manager import (  # noqa: PLC0415
            get_default_live_output_dir,
        )

        # Resolve which file to read from.  Post-session: finalised
        # path.  Mid-session: in-progress recording path (file is
        # being appended; we'll snapshot it below).
        is_running = bool(
            self._transcriber and self._transcriber.is_running,
        )
        source = self._last_recorded_audio_path
        if (source is None or not source.exists()) and is_running:
            source = self._recording_path
        if source is None or not source.exists():
            CustomMessageDialog.show_message(
                self.window_context,
                tr("live.save_audio_empty_title"),
                tr("live.save_audio_empty_msg"),
            )
            return

        source_ext = source.suffix.lstrip(".").lower() or "wav"
        target_fmt = str(load_setting(
            SETTING_LIVE_AUDIO_FORMAT, LIVE_AUDIO_FORMAT_MP3,
        )).strip().lower() or LIVE_AUDIO_FORMAT_MP3
        default_ext = (
            source_ext if source_ext == target_fmt else target_fmt
        )

        out_dir = str(
            load_setting(SETTING_LIVE_OUTPUT_PATH, "")
            or get_default_live_output_dir(),
        )
        suggested = str(Path(out_dir) / f"{source.stem}.{default_ext}")
        chosen, _ = QFileDialog.getSaveFileName(
            self.window_context,
            tr("live.btn_save_audio"),
            suggested,
            f"*.{default_ext}",
        )
        if not chosen:
            return
        target = Path(chosen)
        if not target.suffix:
            target = target.with_suffix(f".{default_ext}")
        target_ext = target.suffix.lstrip(".").lower()

        # If the session is still running, the source WAV has a
        # placeholder header.  Snapshot it into a temp WAV with a
        # patched header so downstream copy / encode sees a valid
        # WAV.  The snapshot is deleted in the ``finally`` below.
        snapshot_path: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            effective_source = source
            if is_running and source_ext == LIVE_AUDIO_FORMAT_WAV:
                snapshot_path = self._snapshot_in_progress_wav(source)
                effective_source = snapshot_path
            if (
                source_ext == LIVE_AUDIO_FORMAT_WAV
                and target_ext != LIVE_AUDIO_FORMAT_WAV
            ):
                # Re-encode WAV → encoded.  ``delete_source=False`` so
                # the (snapshot or finalised) WAV stays around — useful
                # if the user invokes Save again with a different
                # chosen format AND it lets the mid-session snapshot
                # cleanup run in the ``finally`` below.
                from src.utils.audio_encoding import (  # noqa: PLC0415
                    post_encode_audio,
                )

                post_encode_audio(
                    effective_source,
                    target_ext,
                    output_path=target,
                    delete_source=False,
                )
            else:
                # Same format (or non-WAV source) → byte-for-byte copy.
                shutil.copy2(effective_source, target)
        except (OSError, RuntimeError) as exc:
            logger.warning("Failed to save audio to %s: %s", target, exc)
            CustomMessageDialog.show_message(
                self.window_context,
                tr("live.save_audio_failed_title"),
                tr("live.save_audio_failed_msg", error=str(exc)),
            )
            return
        finally:
            # Mid-session snapshot lives in tempdir; clean it up after
            # the copy / encode is done.  The original recording path
            # is left untouched (the engine is still writing to it).
            if snapshot_path is not None:
                try:
                    snapshot_path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning(
                        "Mid-session snapshot cleanup failed for %s: %s",
                        snapshot_path, exc,
                    )
        CustomMessageDialog.show_message(
            self.window_context,
            tr("live.save_audio_ok_title"),
            tr("live.save_audio_ok_msg", path=str(target)),
        )

    @staticmethod
    def _snapshot_in_progress_wav(source: Path) -> Path:
        """Snapshots an in-progress WAV into a temp file with patched header.

        Python's ``wave.Wave_write`` writes placeholder zero sizes
        for the RIFF and ``data`` chunks at open time and only
        overwrites them with the real counts on ``close()``.  A mid-
        session copy therefore has correct PCM bytes BUT bogus
        size headers — most players see "0 bytes of audio" and
        refuse to play.

        This helper:
        1. ``shutil.copy2``-clones the live WAV into a fresh
           tempfile (captures whatever the engine has flushed to
           disk at this instant; new writes go to the original
           file unaffected).
        2. Computes the actual data size from the snapshot's file
           size minus the 44-byte standard PCM header.
        3. Patches bytes 4..8 (RIFF chunk size = file_size - 8) and
           bytes 40..44 (data chunk size) so the snapshot parses as
           a valid WAV.

        Returns the snapshot path.  Caller is responsible for
        deleting it once the copy / encode is done.
        """
        import shutil  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        fd, tmp = tempfile.mkstemp(
            suffix=".wav", prefix=_TEMP_AUDIO_PREFIX + "snapshot_",
        )
        import os as _os  # noqa: PLC0415
        _os.close(fd)
        snapshot = Path(tmp)
        shutil.copy2(source, snapshot)

        # Standard PCM WAV header is 44 bytes; anything shorter
        # means the engine hadn't even finished writing the header
        # — leave the snapshot as-is and let the caller's encode /
        # copy step surface the error.
        _wav_header_min = 44
        size = snapshot.stat().st_size
        if size < _wav_header_min:
            return snapshot
        data_size = size - _wav_header_min
        # Trim any half-written sample frame so the data chunk size
        # stays aligned to ``BlockAlign`` (2 bytes for s16 mono).
        data_size -= data_size % 2
        with snapshot.open("r+b") as f:
            # RIFF chunk size = total file size - 8.
            f.seek(4)
            f.write((data_size + 36).to_bytes(4, "little"))
            # Data chunk size = PCM bytes.
            f.seek(40)
            f.write(data_size.to_bytes(4, "little"))
        return snapshot

    def _clear_log(self) -> None:
        """Clears the transcript log, overlay, and pending TTS queue."""
        overlay_has_lines = (
            self._overlay is not None and self._overlay._lines_layout.count() > 0
        )
        # Nothing to clear — quietly skip.
        if (
            not self._transcript_records
            and self._transcript_layout.count() <= 1
            and not self._tts_queue
            and not overlay_has_lines
        ):
            return

        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        if not CustomConfirmDialog.confirm(
            self.window_context,
            tr("live.clear_confirm_title"),
            tr("live.clear_confirm_msg"),
            is_danger=True,
            # "Clear" matches the action verb in the title — using the
            # global ``btn.delete`` default mislabelled the operation
            # as a permanent delete when it's really an empty-the-view
            # action.  Reuses ``live.btn_clear`` (already translated
            # to "Clear" / locale equivalent across all 20 locales).
            confirm_text=tr("live.btn_clear"),
        ):
            return

        self._reset_transcript_state()

    def _reset_transcript_state(self) -> None:
        """Wipes transcript widgets, records, overlay, TTS, and trackers.

        The shared wipe body used by both :meth:`_clear_log` (after a
        confirm) and :meth:`_start_listening` (silent — auto-clear on
        Start, to avoid mixing two session-relative timestamp lines
        whose 00:00:00 baselines would collide).
        """
        for layout in (self._transcript_layout, self._dual_layout):
            while layout.count() > 1:
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        if self._overlay:
            self._overlay.clear_lines()
        # Drop queued TTS so the user isn't hearing stale translations for
        # text that's no longer on screen.
        self._tts_queue.clear()
        self._transcript_records.clear()
        # Reset the context buffer so the next translation isn't anchored
        # against sentences from a since-cleared conversation.
        self._context_buffer.clear()
        # Reset card / pair tracking so the next translation doesn't
        # attach to an already-deleted widget.
        self._current_single_card = None
        self._current_dual_pair = None
        # NB: ``_speaker_aliases`` and ``_tts_config`` are NOT reset
        # here.  Both are session-level state (one Start → one set of
        # diarized IDs, one TTS engine choice), but this method also
        # backs the user-facing "Clear Log" button which empties the
        # transcript mid-session — keeping the engine running.
        # Clearing aliases on Clear Log would lose the user's
        # "Alice" rename for the SAME speaker, and clearing the TTS
        # config would silently fall back to per-sentence INI reads.
        # Session-start resets live in ``_start_listening`` instead.
        # Reveal the placeholder again — the transcript just emptied.
        self._show_empty_state()
        # Disable Save / Clear again — there's nothing to save / clear.
        self._refresh_content_dependent_buttons()

    def _iter_transcript_cues(
        self,
    ) -> Generator[tuple[int, str, str, list[str]], None, None]:
        """Yields ``(index, start, end, cue_lines)`` per transcript record.

        Shared front-end for the SRT / VTT / TXT formatters: each
        per-format function decides how to wrap the timing + lines,
        but the cue-line construction (speaker alias, bilingual
        layout, malformed-record skip) lives here in one place.
        """
        for i, record in enumerate(self._transcript_records):
            # Records are 5-tuples since the LLM-error backfill fix;
            # the ``is_error`` flag isn't needed by the export (the
            # inline error message in ``translated`` already
            # documents the failure), so we destructure and drop it.
            timestamp, speaker_id, original, translated, _is_error = record
            # Apply the page's alias map at save time so the exported
            # cues show the user-chosen names ("[Alice]") rather than
            # the raw IDs we store in the record.  Records hold the
            # ID so a rename retroactively flows into every prior cue.
            speaker_display = (
                self._display_speaker(speaker_id) if speaker_id else ""
            )
            # ``timestamp`` shape from ``_format_timestamp``:
            # "00:00:00 → 00:00:02".  Split on the arrow so the
            # caller can format start/end per its own spec.
            parts = timestamp.split(" → ")
            if len(parts) != 2:  # noqa: PLR2004 — sentinel for malformed input
                continue
            start, end = parts
            cue_lines: list[str] = []
            if original:
                if speaker_display:
                    cue_lines.append(f"[{speaker_display}] {original}")
                else:
                    cue_lines.append(original)
            if translated:
                cue_lines.append(translated)
            if not cue_lines:
                continue
            yield i, start, end, cue_lines

    def _format_transcript_srt(self) -> str:
        """Formats ``_transcript_records`` as an SRT file body.

        Each record becomes one cue with ``HH:MM:SS,000`` timing
        (ms padded to zero since the records don't carry sub-second
        precision).  Bilingual layout: speaker-prefixed original on
        line 1, translation on line 2 when present.  This is the
        conventional SRT pattern players display as stacked
        dual-language captions.
        """
        from src.utils.subtitle_utils import (  # noqa: PLC0415
            SubtitleEntry,
            serialize_srt,
        )

        entries = [
            SubtitleEntry(
                index=i,
                start=f"{start},000",
                end=f"{end},000",
                text="\n".join(cue_lines),
            )
            for i, start, end, cue_lines in self._iter_transcript_cues()
        ]
        return serialize_srt(entries)

    def _format_transcript_vtt(self) -> str:
        """Formats ``_transcript_records`` as a WebVTT file body.

        Same cue layout as SRT but VTT timing uses a ``.`` decimal
        separator and the file starts with ``WEBVTT`` (the spec
        requires the header — ``serialize_vtt`` only emits one when
        the ``header`` kwarg is set).
        """
        from src.utils.subtitle_utils import (  # noqa: PLC0415
            SubtitleEntry,
            serialize_vtt,
        )

        entries = [
            SubtitleEntry(
                index=i,
                start=f"{start}.000",
                end=f"{end}.000",
                text="\n".join(cue_lines),
            )
            for i, start, end, cue_lines in self._iter_transcript_cues()
        ]
        return serialize_vtt(entries, header="WEBVTT")

    def _format_transcript_csv(self) -> str:
        """Formats ``_transcript_records`` as a 5-column CSV with a header row.

        Columns: ``start, end, speaker, original, translated``.
        Useful for spreadsheet / data-analysis workflows — each
        cue gets its own row so users can filter or sort without
        parsing multi-line cells.  Uses :mod:`csv` so commas /
        quotes / newlines inside translated text are correctly
        escaped per RFC 4180.  Empty cells where applicable
        (e.g. Whisper sentences have no speaker; the no-target
        path has no translation).
        """
        import csv  # noqa: PLC0415
        import io  # noqa: PLC0415

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["start", "end", "speaker", "original", "translated"])
        # Reach past ``_iter_transcript_cues`` (which fuses
        # speaker + original into one cue line) — CSV wants the
        # fields separated so analysis tools can sort / filter on
        # speaker independently.
        for record in self._transcript_records:
            timestamp, speaker_id, original, translated, _is_error = record
            parts = timestamp.split(" → ")
            if len(parts) != 2:  # noqa: PLR2004 — sentinel for malformed input
                continue
            start, end = parts
            speaker_display = (
                self._display_speaker(speaker_id) if speaker_id else ""
            )
            writer.writerow([start, end, speaker_display, original, translated])
        return buf.getvalue()

    def _format_transcript_ass(self, fmt: str) -> str:
        r"""Formats ``_transcript_records`` as an ASS/SSA script body.

        Each cue becomes one ``Dialogue:`` line.  Speaker (when known)
        rides in the ``Name`` field — players like Aegisub surface this
        in the editor.  Cue text is the bilingual ``original\Ntranslated``
        layout (``\N`` is the ASS hard line break) so a media player
        renders both lines stacked, same as the SRT export.  *fmt* picks
        between ``"ass"`` / ``"ssa"`` so a single helper covers both —
        the file header changes but the Dialogue lines are identical.
        """
        from src.utils.subtitle_utils import (  # noqa: PLC0415
            SubtitleEntry,
            serialize_subtitle,
        )

        def _to_ass_ts(t: str) -> str:
            """``HH:MM:SS`` → ASS ``H:MM:SS.cc`` (centisecond precision)."""
            h, m, s = t.split(":")
            return f"{int(h)}:{int(m):02d}:{int(s):02d}.00"

        # Reach past ``_iter_transcript_cues`` so the speaker rides in
        # the ASS ``Name`` field separately from the cue text (the
        # iter version glues speaker into the first cue line).
        entries: list[SubtitleEntry] = []
        speaker_per_cue: list[str] = []
        index = 0
        for record in self._transcript_records:
            timestamp, speaker_id, original, translated, _is_error = record
            parts = timestamp.split(" → ")
            if len(parts) != 2:  # noqa: PLR2004 — malformed-record sentinel
                continue
            start, end = parts
            text_lines: list[str] = []
            if original:
                text_lines.append(original)
            if translated:
                text_lines.append(translated)
            if not text_lines:
                continue
            entries.append(
                SubtitleEntry(
                    index=index,
                    start=_to_ass_ts(start),
                    end=_to_ass_ts(end),
                    text="\\N".join(text_lines),
                ),
            )
            speaker_per_cue.append(
                self._display_speaker(speaker_id) if speaker_id else "",
            )
            index += 1

        header_lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, "
                "SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
                "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
                "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
                "MarginV, Encoding"
            ),
            (
                "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,"
                "&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1"
            ),
            "",
            "[Events]",
            (
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
                "MarginV, Effect, Text"
            ),
        ]
        for entry, speaker in zip(entries, speaker_per_cue, strict=True):
            header_lines.append(
                f"Dialogue: 0,{entry.start},{entry.end},Default,"
                f"{speaker},0,0,0,,__SUB_{entry.index}__",
            )

        target_ext = f".{fmt}"
        return serialize_subtitle(entries, header_lines, target_ext)

    def _resolve_transcript_format(self) -> str:
        """Returns the saved transcript format (defaults to SRT)."""
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_TRANSCRIPT_FORMAT_SRT,
            SETTING_LIVE_TRANSCRIPT_FORMAT,
        )

        return str(load_setting(
            SETTING_LIVE_TRANSCRIPT_FORMAT, LIVE_TRANSCRIPT_FORMAT_SRT,
        ))

    def _format_transcript(self, fmt: str | None = None) -> str:
        """Dispatches to the per-format formatter based on *fmt*.

        When *fmt* is None, reads the saved
        ``SETTING_LIVE_TRANSCRIPT_FORMAT`` so the Save Transcript
        toolbar button writes the user's chosen format too.
        Unknown values fall back to SRT (the default).
        """
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_TRANSCRIPT_FORMAT_ASS,
            LIVE_TRANSCRIPT_FORMAT_CSV,
            LIVE_TRANSCRIPT_FORMAT_SSA,
            LIVE_TRANSCRIPT_FORMAT_VTT,
        )

        if fmt is None:
            fmt = self._resolve_transcript_format()
        if fmt == LIVE_TRANSCRIPT_FORMAT_VTT:
            return self._format_transcript_vtt()
        if fmt in (LIVE_TRANSCRIPT_FORMAT_ASS, LIVE_TRANSCRIPT_FORMAT_SSA):
            return self._format_transcript_ass(fmt)
        if fmt == LIVE_TRANSCRIPT_FORMAT_CSV:
            return self._format_transcript_csv()
        return self._format_transcript_srt()

    def _write_transcript_to(self, file_path: Path) -> bool:
        """Writes the current transcript to *file_path*.

        Format is inferred from the file's extension (``.srt`` /
        ``.vtt`` / ``.txt``); the caller is responsible for picking
        the extension that matches the user's chosen format via
        :meth:`_resolve_transcript_format`.
        """
        ext = file_path.suffix.lower().lstrip(".")
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(
                self._format_transcript(ext or None),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            logger.warning("Failed to save transcript to %s: %s", file_path, exc)
            return False

    def _sync_audio_ffmpeg_warning(self) -> None:
        """Refreshes the ffmpeg install banner.

        Reuses the shared ``create_ffmpeg_install_banner()`` helper,
        which sets the per-OS install text and toggles visibility
        purely on ffmpeg-on-PATH availability — banner shows whenever
        ffmpeg is missing, regardless of save mode / audio format /
        backend engine.  Matches the Voice / Dubbing pages' "always
        require ffmpeg" stance for consistency.
        """
        self._refresh_audio_ffmpeg_banner()
        self._sync_banners_padding()

    def _sync_banners_padding(self) -> None:
        """Toggles the banners-layout bottom margin based on visibility.

        12 px when at least one banner is visible (gives the bottom-
        most banner breathing room from the divider below); 0 when
        every banner is hidden (common happy-path state — controls
        sit tight against the divider instead of floating above an
        empty reservation of vertical space).  Called from every per-
        banner sync function (`_sync_stt_setup_warning`,
        `_sync_system_audio_warning`, `_sync_microphone_warning`,
        `_sync_audio_ffmpeg_warning`) so visibility flips propagate
        to the margin immediately.
        """
        banners = (
            getattr(self, "_stt_setup_warning", None),
            getattr(self, "_system_audio_warning", None),
            getattr(self, "_microphone_warning", None),
            getattr(self, "_audio_ffmpeg_warning", None),
        )
        any_visible = any(b is not None and not b.isHidden() for b in banners)
        bottom = 12 if any_visible else 0
        self._banners_layout.setContentsMargins(14, 0, 14, bottom)

    def _validate_ffmpeg_for_audio_save(self) -> bool:
        """Returns True when ffmpeg is on PATH; False after showing dialog.

        Unconditional check — fires regardless of save mode / audio
        format / backend engine — matches the ffmpeg requirement on
        Voice / Dubbing pages.  Shared ``voice.ffmpeg_required_*``
        dialog so the wording stays consistent across the three
        audio-handling pages.
        """
        import shutil  # noqa: PLC0415

        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        if shutil.which("ffmpeg") is not None:
            return True

        from src.utils.install_hints import (  # noqa: PLC0415
            build_ffmpeg_install_message,
        )

        CustomMessageDialog.show_message(
            self.window(),
            tr("voice.ffmpeg_required_title"),
            build_ffmpeg_install_message(),
        )
        return False

    def _finalise_audio_recording(self, wav_path: Path) -> Path:
        """Post-encodes the engine's WAV to the user-chosen audio format.

        The engine always writes WAV (incremental ``wave.open`` from
        the audio thread; that's the only streaming-write format
        Python's stdlib supports).  When the user picked one of the
        encoded formats (MP3 / FLAC / OGG) in Settings → Live →
        Auto save, the shared ``post_encode_audio`` helper transcodes
        the WAV via ffmpeg now that the session has finished, then
        deletes the WAV on success.

        **Temp-WAV path** (Auto save = None / Text-only): skip the
        post-encode entirely.  The raw WAV stays at its tempdir
        location so the manual Save → Audio path can read it and
        encode on demand into whatever extension the user picks in
        the file dialog.  Encoding eagerly here would force a format
        the user hasn't asked for yet; deferring also avoids paying
        for ffmpeg when the user ends up not saving.

        Failure handling: ``post_encode_audio`` now raises on any
        failure (no more silent WAV fallback).  On
        ``FFMPEG_NOT_FOUND`` we surface the install dialog so the
        user knows their MP3/FLAC/OGG preference couldn't be honoured
        and points at the WAV they actually got.  The Start pre-check
        should normally prevent this path; the catch here is defence
        in depth for the rare "ffmpeg disappeared mid-session" race.
        """
        if getattr(self, "_audio_is_temp", False):
            # Temp WAV — manual save will encode on demand; leave raw.
            return wav_path

        from src.constants.settings import (  # noqa: PLC0415
            LIVE_AUDIO_FORMAT_MP3,
            SETTING_LIVE_AUDIO_FORMAT,
        )
        from src.utils.audio_encoding import post_encode_audio  # noqa: PLC0415

        fmt = str(load_setting(
            SETTING_LIVE_AUDIO_FORMAT, LIVE_AUDIO_FORMAT_MP3,
        )).strip().lower()
        try:
            return post_encode_audio(wav_path, fmt)
        except RuntimeError as exc:
            sentinel = str(exc)
            logger.warning(
                "Live audio post-encode failed (%s); keeping WAV at %s",
                sentinel, wav_path,
            )
            if sentinel == "FFMPEG_NOT_FOUND":
                # Surface the install dialog on the UI thread.  The
                # session has already stopped at this point, so a
                # modal won't interrupt audio capture.
                from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415
                from src.utils.install_hints import (  # noqa: PLC0415
                    build_ffmpeg_install_message,
                )

                CustomMessageDialog.show_message(
                    self.window(),
                    tr("voice.ffmpeg_required_title"),
                    build_ffmpeg_install_message(),
                )
            return wav_path

    # ------------------------------------------------------------------
    # Transcript handling
    # ------------------------------------------------------------------

    @Slot(str, float, float, str, str)
    def _on_sentence(
        self,
        text: str,
        start_sec: float,
        end_sec: float,
        speaker: str = "",
        translated: str = "",
    ) -> None:
        """Called when a sentence is recognized.

        Args:
            text: Original transcribed text.
            start_sec: Start time in seconds.
            end_sec: End time in seconds.
            speaker: Speaker label (e.g. "speaker_0"), empty if unavailable.
            translated: Pre-translated text from Soniox, empty for Whisper mode.
        """
        # Drop late sentences emitted by the engine thread after Stop:
        # ``_stop_listening`` nulls ``_transcriber`` synchronously,
        # but the background WS / audio loops may have already
        # produced sentences whose queued signals fire on the UI
        # thread *after* the user clicked Stop.  Without this guard
        # the user sees "Ready" on the toolbar AND new transcript
        # entries scrolling in below — same pattern the
        # ``_on_translated`` / ``_on_translation_error`` handlers
        # already use.
        if self._transcriber is None:
            return
        # Auto-stop heartbeat: a finalised sentence means the user is
        # still talking — reset the countdown so the session doesn't
        # time out while someone's actively speaking.
        timer = getattr(self, "_idle_timer", None)
        if timer is not None:
            timer.start()  # single-shot restart preserves the interval
        timestamp = _format_timestamp(start_sec, end_sec)
        # Resolve via the page's alias map so a previously-renamed
        # speaker's NEW sentences land with the alias already applied —
        # without this the chip would render the default "Speaker N"
        # and only get the alias on the NEXT rename refresh.
        speaker_label = self._display_speaker(speaker) if speaker else ""

        target_lang = load_setting(SETTING_LIVE_TARGET_LANG, "")

        if translated:
            # Cloud mode: translation already provided (Soniox).
            # Always add both source + translation so the card has the
            # content in memory; ``_apply_display_mode_to_cards`` then
            # controls which labels are visible per the user's current
            # display choice, updatable on the fly.
            self._add_original(text, timestamp, speaker_label, speaker_id=speaker)
            self._add_translated(translated)
            self._transcript_records.append(
                (timestamp, speaker, text, translated, False),
            )
            if self._tts_enabled:
                self._enqueue_tts(translated)
        elif target_lang:
            # Whisper mode: need LLM translation — always add source
            # now, translation arrives later via ``_on_translated`` and
            # attaches to the SAME card / pair captured at this moment.
            # Pinning the targets up front (rather than relying on
            # ``self._current_*`` at translation-arrival time) is the
            # load-bearing fix for the dual-view drift bug: when
            # several originals queue up before any translations come
            # back, the late-arriving translations would otherwise all
            # land on the most recent pair-row.
            sc, dp = self._add_original(
                text, timestamp, speaker_label,
                speaker_id=speaker,
                pending_translation=True,
            )

            src_lang = load_setting(SETTING_LIVE_SOURCE_LANG, "")
            glossary = self._load_glossary()

            # Resolve the model from the feature-specific setting so Live's
            # choice is independent of Translate Text / Subtitle / etc.
            from src.constants.settings import (  # noqa: PLC0415
                SETTING_LLM_MODEL_LIVE,
            )
            from src.utils.config_manager import (  # noqa: PLC0415
                load_model_for_feature,
                parse_model_id,
            )

            live_model_id = load_model_for_feature(SETTING_LLM_MODEL_LIVE)
            live_provider, live_model = (
                parse_model_id(live_model_id) if live_model_id else (None, None)
            )

            # Snapshot the context buffer BEFORE adding this sentence so
            # the LLM sees only earlier sentences (the current ``text``
            # would be redundant inside its own translation request).
            ctx_snapshot = list(self._context_buffer) or None

            worker = _TranslationWorker(
                text,
                src_lang,
                target_lang,
                glossary_entries=glossary or None,
                provider=live_provider,
                model=live_model,
                context=ctx_snapshot,
            )
            # Append THIS sentence to the rolling buffer for the NEXT
            # worker.  Done after the snapshot above so the current
            # request stays clean.  Buffer is bounded (deque maxlen),
            # so older sentences fall off automatically.
            self._context_buffer.append(text)
            # Bind the per-sentence card / pair targets via default-arg
            # closure so each worker's signals route to its own row.
            # functools.partial would also work; the lambda form keeps
            # the read-line short and avoids the import.
            worker.partial_translated.connect(
                lambda orig, accum, sc=sc, dp=dp:
                    self._on_partial_translation(orig, accum, sc, dp),
            )
            worker.translated.connect(
                lambda orig, transl, sc=sc, dp=dp:
                    self._on_translated(orig, transl, sc, dp),
            )
            worker.error.connect(
                lambda msg, sc=sc, dp=dp:
                    self._on_translation_error(msg, sc, dp),
            )
            worker.finished.connect(
                lambda w=worker: self._cleanup_worker(w),
            )
            self._translation_workers.append(worker)
            worker.start()
            # Transcript entry is finalised in _on_translated once the
            # translated text is available; stash the header now.
            self._transcript_records.append(
                (timestamp, speaker, text, "", False),
            )
        else:
            self._add_original(text, timestamp, speaker_label, speaker_id=speaker)
            self._transcript_records.append(
                (timestamp, speaker, text, "", False),
            )

    @Slot(str)
    def _on_status(self, message: str) -> None:
        """Updates the status label.

        Drops late status pushes from the engine thread when the
        session has already been stopped — e.g. a "Connecting…" or
        "Listening…" emitted from the WS loop's final iteration
        would otherwise overwrite the "Ready — press Start" copy
        and make the toolbar lie about the session state.  The
        transcriber is assigned BEFORE ``.start()`` runs, so this
        guard never drops a legitimate session-start status push.
        """
        if self._transcriber is None:
            return
        # ``_on_status`` only carries non-failure copy (Listening… /
        # Ready / Connecting…) so re-apply the neutral pill in case a
        # prior error toast left the pill flipped to the danger
        # variant and its 5 s reset hasn't fired yet.
        self._reset_status_to_neutral()
        self.status_label.setText(message)

    def _show_status_error(self, message: str, *, sticky: bool = False) -> None:
        """Flips the status pill to the danger variant.

        Failures (translation / STT) need a higher signal-to-noise
        ratio than the muted neutral pill provides — without the
        colour flip a user mid-conversation might miss a quota /
        auth error entirely.  The pill uses a **translucent** error
        tint for the background and the **solid error** colour for
        the text — softer than white-on-saturated-red and still
        clearly distinct from the neutral pill.

        When *sticky* is False (the default — translation errors), a
        parented ``QTimer`` restores the neutral look after
        ``_TRANSLATION_ERROR_STATUS_MS`` so a transient failure
        doesn't permanently pin the bar.  When True (STT failures
        that just stopped the session), the pill stays red until the
        user starts a new session — they need to actually see *why*
        the session ended, and a flashing-then-gone toast would be
        easy to miss next to a freshly-idled toolbar.
        """
        from PySide6.QtGui import QColor as _QColor  # noqa: PLC0415

        tint = _QColor(color("error"))
        # ~15 % alpha keeps the bg readable as a "tinted pill" rather
        # than a fully saturated alert; combined with the solid-error
        # text colour the chip reads as "warning area" without harshness.
        tint.setAlpha(38)
        self.status_label.set_bg(tint)
        self.status_label.setStyleSheet(_style_status_error())
        self.status_label.setText(message)
        if sticky:
            # Guard the pill against later ``_reset_ui_to_ready``
            # callbacks (notably the engine's ``on_stopped`` →
            # ``_on_transcriber_stopped``) that would otherwise
            # rewrite the text to "Ready" while leaving the red
            # styling in place — observed bug: "Ready" in red.
            self._sticky_error_active = True
            return
        # Parented to ``self`` so the deferred reset is auto-cancelled
        # if the page is destroyed first (anti-crash pattern shared
        # with about.py / other transient-status callsites).
        QTimer.singleShot(
            _TRANSLATION_ERROR_STATUS_MS,
            self,
            self._reset_status_to_ready,
        )

    def _reset_status_to_neutral(self) -> None:
        """Restores the status pill's neutral bg + text colours.

        Also clears the ``_sticky_error_active`` guard — explicit
        neutral resets always take precedence over a previous sticky
        flag (the caller has decided the error toast is no longer
        relevant).
        """
        self._sticky_error_active = False
        self.status_label.set_bg(color("disabled_bg"))
        self.status_label.setStyleSheet(_style_status())

    def _reset_status_to_ready(self) -> None:
        """Restores the neutral pill, picking the copy from session state.

        Used as the deferred callback for the 5 s error-toast timeout.
        LLM translation errors don't stop the session, so on the
        clear we need to revert to "Listening…" (the active-session
        copy) — writing "Ready — press Start to begin" against a
        still-running session was confusing and made users press
        Start a second time thinking the session had died.
        """
        self._reset_status_to_neutral()
        listening = bool(
            self._transcriber is not None
            and getattr(self._transcriber, "is_running", False)
        )
        self.status_label.setText(
            tr("live.status_listening" if listening else "live.status_ready"),
        )

    # Soniox error categories that route the auto-stop dialog to
    # Settings → Service (tab 2) for the user to fix.  Both auth
    # variants emitted by ``src/core/live_errors.py``:
    #   * ``STT_AUTH_INVALID``  — 401, bad / missing API key.
    #   * ``STT_AUTH_FORBIDDEN`` — 403, key lacks access (rare, but
    #     "check the key" is still the right first step).
    # Other categories get the plain OK dialog — Settings can't fix a
    # network outage, and the billing/quota CTA would point at the
    # wrong destination (Soniox dashboard, not our app).
    _SETTINGS_FIX_CATEGORIES = frozenset({
        "STT_AUTH_INVALID",
        "STT_AUTH_FORBIDDEN",
    })
    _SETTINGS_TAB_SERVICE = 2

    def _show_auto_stop_dialog(self, category: str, reason: str) -> None:
        """Modal feedback for the auto-stop path (STT fatal errors).

        Complements the sticky red status pill: the pill keeps the
        reason visible on the toolbar, the modal forces an
        acknowledgement so a backgrounded window can't silently die
        on the user.  AUTH_ERROR / NO_SONIOX_KEY offer a "Go to
        Settings" jump straight to the Service tab where the Soniox
        API key lives; other errors get a plain OK button.
        """
        from src.ui.dialogs import (  # noqa: PLC0415
            CustomConfirmDialog,
            CustomMessageDialog,
        )

        title = tr("live.auto_stop_title")
        message = tr("live.auto_stop_msg", reason=reason)
        window = self.window_context
        if category in self._SETTINGS_FIX_CATEGORIES:
            confirmed = CustomConfirmDialog.confirm(
                window,
                title,
                message,
                confirm_text=tr("btn.go_to_settings"),
                cancel_text=tr("btn.close"),
            )
            if confirmed and hasattr(window, "navigate_to_settings_tab"):
                window.navigate_to_settings_tab(self._SETTINGS_TAB_SERVICE)
            return
        # Non-actionable errors (network / timeout / quota): plain
        # informational modal — there's nothing the user can fix
        # from Settings, so a "Go to Settings" button would dead-end.
        CustomMessageDialog.show_message(window, title, message)

    def _on_partial_translation(
        self,
        original: str,
        accumulated: str,
        single_card: _TranscriptCard | None = None,
        dual_pair: QWidget | None = None,
    ) -> None:
        """Live updates the in-flight target card as stream chunks arrive.

        Called for every chunk emitted by ``_TranslationWorker``'s
        streaming run; the accumulated text replaces the placeholder
        so the user watches the translation form.  No transcript
        record / TTS side effects — those run only once on the final
        ``translated`` signal.  Late chunks after Stop are dropped
        the same way ``_on_translated`` drops late results.
        """
        if self._transcriber is None:
            return
        if not accumulated:
            return
        self._add_translated(
            accumulated, single_card=single_card, dual_pair=dual_pair,
        )

    def _on_translated(
        self,
        original: str,
        translated: str,
        single_card: _TranscriptCard | None = None,
        dual_pair: QWidget | None = None,
    ) -> None:
        """Attaches translated text to its originating card pair.

        *single_card* / *dual_pair* are captured by default-arg
        lambda closures when ``_on_sentence`` connects the worker's
        ``translated`` signal — they pin the targets so a translation
        arriving after several newer originals lands on the row that
        owns the source text, not the most recent one.  Without this,
        the ``_current_*`` pointers race with new originals and the
        dual-view translations drift off their originals.
        """
        # Translation workers run a blocking LLM call that can't be
        # cancelled. If the user hit Stop before the call returned, drop
        # the result so the transcript and TTS don't keep updating after
        # listening ended.
        if self._transcriber is None:
            return
        # Always attach the translation to the card; visibility is
        # handled by ``_apply_display_mode_to_cards`` so the user can
        # flip between Original / Translation / Both on the fly.
        self._add_translated(
            translated, single_card=single_card, dual_pair=dual_pair,
        )

        # Update the corresponding transcript record (Whisper mode) — we
        # stashed it with empty ``translated`` + ``is_error=False`` when
        # the sentence arrived.  Walk back from the newest record so a
        # repeat of the same source (rare but possible) attaches the
        # translation to the most-recent pending row.
        for i in range(len(self._transcript_records) - 1, -1, -1):
            ts, spk, orig, tgt, err = self._transcript_records[i]
            if not tgt and not err and orig == original:
                self._transcript_records[i] = (
                    ts, spk, orig, translated, False,
                )
                break

        # TTS: queue the translated text for playback
        if self._tts_enabled:
            self._enqueue_tts(translated)

    def _on_translation_error(
        self,
        error_msg: str,
        single_card: _TranscriptCard | None = None,
        dual_pair: QWidget | None = None,
    ) -> None:
        """Surfaces the LLM translation failure to the user.

        *single_card* / *dual_pair* are captured by default-arg
        lambda closures when ``_on_sentence`` connects the worker's
        ``error`` signal — same row-pinning rationale as
        ``_on_translated`` so the ⚠ marker lands on the sentence that
        actually failed, not on whatever happens to be the most
        recent one when the error bubbles up.

        Two surfaces:

        - **Inline** — paints the failing entry's translation slot
          with ``⚠ Translation failed`` in the error colour, so the
          user can tell at a glance which sentence didn't translate
          (instead of the silent-forever placeholder behavior the
          page used to ship with).
        - **Status label** — a one-shot toast with the underlying
          tag mapped via ``display_error_message`` (so AUTH_ERROR /
          QUOTA_ERROR / TIMEOUT_ERROR etc. show the same localised
          text the rest of the app uses), auto-clearing after ~5 s
          so it doesn't pin the bottom bar forever.
        """
        from shiboken6 import isValid  # noqa: PLC0415

        from src.constants.errors import display_error_message  # noqa: PLC0415

        if self._transcriber is None:
            return
        logger.error("Live translation failed: %s", error_msg)

        # Resolve the user-friendly reason once — same mapping used by
        # the status-pill toast so the inline marker and the toast
        # carry the same wording for the same failure.
        reason = display_error_message(error_msg) or error_msg

        # Inline marker on the failing entry — single-view card AND
        # dual-view pair (whichever exists).  Explicit targets pin
        # the row; fall back to ``_current_*`` for callers that don't
        # supply them.  ``isValid`` guards against widgets the user
        # already cleared.  We include the resolved reason so a user
        # scrolling back through the transcript can still see why the
        # row failed (the status pill auto-clears after ~5 s).
        inline = tr("live.translation_failed_inline", reason=reason)
        target_single = single_card if single_card is not None else getattr(
            self, "_current_single_card", None,
        )
        target_pair = dual_pair if dual_pair is not None else getattr(
            self, "_current_dual_pair", None,
        )
        if target_single is not None and isValid(target_single):
            target_single.set_error(inline)
        if target_pair is not None and isValid(target_pair):
            right = getattr(target_pair, "_right_card", None)
            if right is not None and isValid(right):
                right.set_error(inline)

        # Overlay surface: an overlay-only user (presenting / on a
        # call with the main window hidden) would otherwise see the
        # source sentence land then silence forever, with no way to
        # distinguish "LLM still working" from "LLM gave up".  Same
        # localised reason as the inline / status messages.
        if self._overlay and self._overlay.isVisible():
            mode = self._resolve_display_mode()
            self._overlay.set_last_error(
                inline,
                show_src=self._mode_shows_source(mode),
                show_tgt=self._mode_shows_target(mode),
            )

        # Mark the failed record so a future overlay backfill can
        # re-paint the ⚠ marker for this sentence.  Without this, the
        # record stays as ``(ts, spk, orig, "", False)`` and the next
        # ``_backfill_overlay`` treats it as "translation still
        # pending" → no error indicator shown.  Match by the source
        # text pulled from the failing card (the same text the
        # original was added with) — same row-pinning pattern
        # ``_on_translated`` uses, but pulling the source from the
        # pinned target instead of needing it as a signal arg.
        if target_single is not None and isValid(target_single):
            failing_source = target_single._body.text()
            for i in range(len(self._transcript_records) - 1, -1, -1):
                ts, spk, orig, tgt, err = self._transcript_records[i]
                if not tgt and not err and orig == failing_source:
                    self._transcript_records[i] = (
                        ts, spk, orig, inline, True,
                    )
                    break

        # Status-bar toast with the same reason — first-glance feedback
        # when the failure happens, before the user has scrolled back.
        # Danger pill (red bg + white text) so the toast doesn't blend
        # in with the muted neutral pill used for the "Listening…" /
        # "Ready" status copy.
        self._show_status_error(
            tr("live.translation_failed_status", reason=reason),
        )

    @Slot(str, str)
    def _on_stt_error(self, category: str, raw_message: str) -> None:
        """Surfaces a fatal STT engine error (Soniox) and stops the session.

        Mirrors ``_on_translation_error`` but skips the inline-marker
        surface — STT failures kill the whole session (no transcript
        means no row to mark).  The session is actively stopped here
        instead of leaving a frozen "Listening…" indicator: an
        AUTH_ERROR / QUOTA_ERROR from the STT engine is non-recoverable
        within this session, so continuing to hold the audio stream
        would waste the user's mic / CPU for no transcript.

        Translation (LLM) failures do NOT stop the session — the
        source transcript still has value even if the LLM can't
        translate.  The asymmetry is deliberate: STT down = session
        dead; LLM down = session degraded but still useful.

        Status pill stays *sticky* (no 5 s auto-clear) so the reason
        the session ended remains visible on the now-idle toolbar
        until the user starts a fresh session.

        ``raw_message`` is logged but not shown — the localised
        category text is enough for the user; the raw exception text
        survives in app.log for diagnostics.

        Drops late errors when the session is already stopped: the
        Soniox engine can emit multiple error signals during
        teardown (payload-level error → connection close → final
        cleanup), and we already showed the dialog + stopped the
        session on the first one.  Without this guard the user
        could see the same modal pop twice in quick succession.
        """
        if self._transcriber is None:
            return
        from src.constants.errors import display_error_message  # noqa: PLC0415

        logger.error(
            "Live STT failed: %s (raw: %s)", category, raw_message,
        )

        reason = display_error_message(category) or category
        # ``_stop_listening`` calls ``_reset_ui_to_ready`` which writes
        # "Ready" into the status pill — we have to show the error
        # AFTER the reset or it gets clobbered.
        self._stop_listening()
        self._show_status_error(
            tr("live.translation_failed_status", reason=reason),
            sticky=True,
        )
        # Modal so a user with the window in the background can't miss
        # that the session ended — the sticky pill is easy to overlook
        # on a wide monitor.  Auth / missing-key errors offer a direct
        # "Go to Settings → Service" jump; everything else gets a
        # plain OK dialog.
        self._show_auto_stop_dialog(category, reason)

    def _cleanup_worker(self, worker: _TranslationWorker) -> None:
        """Removes finished worker from the list."""
        if worker in self._translation_workers:
            self._translation_workers.remove(worker)

    # ------------------------------------------------------------------
    # TTS playback
    # ------------------------------------------------------------------

    def _enqueue_tts(self, text: str) -> None:
        """Queue a sentence for live TTS, preempting on backlog overflow.

        FIFO is the normal path: append + drain.  But when the queue is
        already at ``_MAX_TTS_QUEUE`` capacity and a new sentence
        arrives, the bounded ``deque`` would silently drop the oldest
        pending item — meaning we'd play stale audio while newer
        sentences pile up further behind.  Instead we preempt: cancel
        the current synthesis (signal-detach + abandon-and-drain its
        temp file), stop the player, drop everything pending, and start
        fresh with just the new sentence.  Result: when the user is
        speaking faster than TTS can keep up, audio jumps to the latest
        sentence instead of falling further behind.
        """
        if (
            self._tts_queue.maxlen is not None
            and len(self._tts_queue) >= self._tts_queue.maxlen
        ):
            self._preempt_tts()
        self._tts_queue.append(text)
        self._process_tts_queue()

    def _preempt_tts(self) -> None:
        """Cancels in-flight synthesis + playback and clears pending queue.

        ``_TTSWorker`` doesn't support mid-flight cancellation (HTTP /
        engine calls aren't easily abortable), so we detach its signals
        and re-route ``finished`` to a temp-file cleanup handler.  The
        worker keeps running in the background until its current call
        returns; its output is dropped.  The player is stopped
        immediately and the queue is cleared.
        """
        import contextlib  # noqa: PLC0415

        worker = self._tts_worker
        if worker is not None:
            self._tts_worker = None
            # Detach the result-handlers so ``synthesized`` / ``error``
            # don't trigger ``_process_tts_queue`` (which would start a
            # stale item from the now-cleared queue).
            with contextlib.suppress(RuntimeError, TypeError):
                worker.synthesized.disconnect()
            with contextlib.suppress(RuntimeError, TypeError):
                worker.error.disconnect()
            # Clean up the temp file when the orphaned worker finishes
            # so the abandoned synthesis doesn't leak disk space.
            worker.finished.connect(
                lambda w=worker: self._cleanup_orphaned_tts_worker(w),
            )
        if self._player is not None:
            self._player.stop()
            src = self._player.source()
            if src and src.isLocalFile():
                tmp = Path(src.toLocalFile())
                if tmp.exists() and tmp.name.startswith("live_tts_"):
                    tmp.unlink(missing_ok=True)
            # Reset the source so the next setSource doesn't trigger a
            # stray ``EndOfMedia`` for the just-stopped clip.
            self._player.setSource(QUrl())
        self._tts_queue.clear()

    @staticmethod
    def _cleanup_orphaned_tts_worker(worker: "_TTSWorker") -> None:
        """Removes a preempted worker's temp file once its run completes."""
        tmp_path = worker.temp_file
        if tmp_path:
            tmp = Path(tmp_path)
            if tmp.exists() and tmp.name.startswith("live_tts_"):
                tmp.unlink(missing_ok=True)

    def _process_tts_queue(self) -> None:
        """Processes the next item in the TTS queue."""
        if self._tts_worker is not None:
            return  # Already playing
        if not self._tts_queue:
            return

        text = self._tts_queue.popleft()
        # Use the cached snapshot whenever available so this path
        # avoids the INI round-trip too.  Fall back to a live read
        # for callers (mostly tests) that enqueue TTS without a
        # full session start.
        if self._tts_config is not None:
            target_lang = self._tts_config.target_lang
        else:
            target_lang = load_setting(SETTING_LIVE_TARGET_LANG, "")

        self._tts_worker = _TTSWorker(
            text, target_lang, "FEMALE", config=self._tts_config,
        )
        self._tts_worker.synthesized.connect(self._on_tts_synthesized)
        self._tts_worker.error.connect(self._on_tts_error)
        self._tts_worker.start()

    def _on_tts_synthesized(self) -> None:
        """Plays the synthesized audio."""
        from PySide6.QtMultimedia import (  # noqa: PLC0415
            QAudioOutput,
            QMediaPlayer,
        )

        worker = self._tts_worker
        self._tts_worker = None

        if worker and worker.temp_file and Path(worker.temp_file).exists():
            if self._player is None:
                self._player = QMediaPlayer(self)
                self._audio_output = QAudioOutput(self)
                self._player.setAudioOutput(self._audio_output)
                self._player.mediaStatusChanged.connect(
                    self._on_playback_status,
                )

            self._player.setSource(
                QUrl.fromLocalFile(worker.temp_file),
            )
            self._player.play()
        else:
            # No file, process next
            self._process_tts_queue()

    def _on_playback_status(self, status: object) -> None:
        """Cleans up temp file and processes next TTS item when playback finishes.

        Both ``EndOfMedia`` (normal end) and ``InvalidMedia`` (corrupt or
        unloadable file) must drain the queue — otherwise a single bad
        chunk freezes TTS for the rest of the session.
        """
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        end_statuses = {
            QMediaPlayer.MediaStatus.EndOfMedia,
            QMediaPlayer.MediaStatus.InvalidMedia,
        }
        if status not in end_statuses:
            return

        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            logger.warning("Live TTS: InvalidMedia — skipping chunk")
            self.status_label.setText(tr("live.tts_playback_failed"))

        # Clean up the temp audio file regardless of reason.
        if self._player is not None:
            src = self._player.source()
            if src and src.isLocalFile():
                tmp = Path(src.toLocalFile())
                if tmp.exists() and tmp.name.startswith("live_tts_"):
                    tmp.unlink(missing_ok=True)
        self._process_tts_queue()

    def _on_tts_error(self, error_msg: str) -> None:
        """Handles TTS error, surfaces it in the status label, continues queue."""
        self._tts_worker = None
        logger.error("Live TTS failed: %s", error_msg)
        # Make the failure visible — silent errors look like a bug to the user.
        self.status_label.setText(
            tr("live.tts_failed_status", error=error_msg),
        )
        self._process_tts_queue()

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _build_empty_state(self) -> QWidget:
        """Placeholder shown when the transcript has no entries yet.

        A centred microphone glyph plus a short hint — dramatically
        better than the empty-void look from before and tells the
        user what this page will do once they press Start.
        """
        outer = QWidget()
        outer.setStyleSheet("background: transparent;")
        v = QVBoxLayout(outer)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addStretch(1)

        icon = QLabel("🎙️")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {color('text_secondary')}; font-size: 56px;"
            " background: transparent; padding: 0;"
        )
        v.addWidget(icon)

        title = QLabel(tr("live.empty_title"))
        # State-aware refresh: ``_set_empty_state_listening`` swaps
        # between ``live.empty_title`` (idle) and
        # ``live.empty_title_listening`` (recording) based on
        # ``_empty_state_listening``.  A naive ``setText(tr("…_title"))``
        # would force the idle text even mid-session, so we re-run the
        # state-aware setter to preserve which variant is active.
        title.apply_language = lambda: self._set_empty_state_listening(
            listening=self._empty_state_listening,
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {color('text_primary')}; font-size: 17px;"
            " font-weight: 600; background: transparent; padding: 6px 0 0 0;"
        )
        v.addWidget(title)

        hint = QLabel(tr("live.empty_hint"))
        # Same state-aware refresh — hint also has idle vs
        # listening variants (``live.empty_hint`` / ``live.empty_hint_listening``).
        hint.apply_language = lambda: self._set_empty_state_listening(
            listening=self._empty_state_listening,
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet(_style_transcript_empty_hint())
        v.addWidget(hint)

        v.addStretch(2)
        self._empty_state_title = title
        self._empty_state_hint = hint
        # Track whether the placeholder is currently in the
        # "listening" variant so language changes pick the right
        # i18n key on retranslation.
        self._empty_state_listening = False
        return outer

    def _set_empty_state_listening(self, *, listening: bool) -> None:
        """Swaps the empty-state title + hint between idle and listening."""
        self._empty_state_listening = listening
        if not hasattr(self, "_empty_state_title"):
            return
        title_key = "live.empty_title_listening" if listening else "live.empty_title"
        hint_key = "live.empty_hint_listening" if listening else "live.empty_hint"
        self._empty_state_title.setText(tr(title_key))
        self._empty_state_hint.setText(tr(hint_key))

    def _show_transcript_view(self) -> None:
        """Switch the outer stack to the populated transcript view."""
        if (
            hasattr(self, "_transcript_outer")
            and self._transcript_outer.currentIndex() != 1
        ):
            self._transcript_outer.setCurrentIndex(1)

    def _show_empty_state(self) -> None:
        """Switch the outer stack back to the placeholder."""
        if (
            hasattr(self, "_transcript_outer")
            and self._transcript_outer.currentIndex() != 0
        ):
            self._transcript_outer.setCurrentIndex(0)

    def _build_transcript_column(self) -> tuple[QScrollArea, QVBoxLayout, QWidget]:
        """Builds one scroll column used by both single and dual transcript views."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # Transparent viewport so the parent page card's rounded
        # bottom corners stay visible — a solid viewport background
        # would paint over them and leave square corners.
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            " QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.viewport().setAutoFillBackground(False)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        # Side padding so flat transcript rows don't crash into the
        # outer page card's rounded edges.  Top is 0 so the first row's
        # hover background hugs the toolbar divider — each card already
        # carries 14 px internal top padding, which provides the
        # breathing room a layout-level top margin would have given but
        # without leaving an unhoverable gutter above row #1.
        layout.setContentsMargins(12, 0, 12, 10)
        # Zero inter-card spacing — the per-row breathing room lives
        # INSIDE each card now (as bottom padding) so the hover-
        # background fills the whole row including the gap above the
        # divider.  A layout-level spacing would sit outside any
        # widget and leave an unhighlighted strip between cards.
        layout.setSpacing(0)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll, layout, container

    def _apply_transcript_layout(self) -> None:
        """Flips the transcript stack based on the current display mode.

        ``LIVE_DISPLAY_BOTH_DUAL`` is the only mode that renders the
        side-by-side two-column view; every other mode uses the
        stacked single-column view.
        """
        idx = 1 if self._mode_is_dual(self._resolve_display_mode()) else 0
        self._transcript_stack.setCurrentIndex(idx)

    def _build_dual_pair_row(  # noqa: PLR0913
        self,
        timestamp_text: str,
        speaker_text: str,
        left_card: _TranscriptCard,
        right_card: _TranscriptCard,
        *,
        speaker_id: str = "",
    ) -> _DualPairRow:
        """Bundles a left+right card into a chip-gutter-led pair row.

        See :class:`_DualPairRow` for the chip-on-row rationale.  The
        method is a thin factory that also wires the per-pair chip
        visibility to the current page-level toggle state, so a row
        inserted mid-session immediately respects the user's existing
        Timestamps / Speakers choices.
        """
        pair = _DualPairRow(
            timestamp_text,
            speaker_text,
            left_card,
            right_card,
            speaker_id=speaker_id,
        )
        pair.set_chip_visible(self._show_timestamp)
        pair.set_speaker_chip_visible(self._show_speaker)
        if speaker_id and pair._speaker_chip is not None and isinstance(
            pair._speaker_chip, _RenamableSpeakerChip,
        ):
            pair._speaker_chip.renamed.connect(self._on_speaker_renamed)
        return pair

    def _add_original(
        self,
        text: str,
        timestamp: str = "",
        speaker: str = "",
        *,
        speaker_id: str = "",
        pending_translation: bool = False,
    ) -> tuple[_TranscriptCard, QWidget]:
        """Adds an original (source) text entry, rendered as a card.

        The same sentence goes into two card structures — one for the
        single (unified) view, and one paired with a translation
        placeholder for the dual view.

        Returns the ``(single_card, dual_pair)`` tuple so the caller
        can pin the targets when an asynchronous translation arrives
        later — without this, ``self._current_*`` pointers race with
        new originals and the late translation lands in the wrong
        row (the symptom: dual-view translations drifted off their
        originals as the user scrolled through a long Whisper-mode
        session).  ``self._current_*`` are still updated as a
        convenience for the synchronous Soniox path that calls
        ``_add_translated`` back-to-back without explicit targets.

        ``pending_translation`` (Whisper path only) seeds a "…"
        placeholder in the single-view card AND the overlay entry so
        both surfaces read as "translation in flight" until
        ``_add_translated`` swaps in the real text.  The dual-view
        right card already uses the placeholder unconditionally as
        its body (see ``_TRANSLATION_PLACEHOLDER`` below).
        """
        self._show_transcript_view()
        mode = self._resolve_display_mode()
        show_src = self._mode_shows_source(mode)
        show_tgt = self._mode_shows_target(mode)

        single_card = _TranscriptCard(
            timestamp, speaker, text,
            speaker_id=speaker_id,
            pending_translation=pending_translation,
        )
        single_card.set_chip_visible(self._show_timestamp)
        single_card.set_speaker_chip_visible(self._show_speaker)
        single_card.set_mode_visibility(show_src, show_tgt)
        # Wire the chip's rename signal so a double-click on this
        # card's speaker chip propagates to every sibling chip via
        # ``_on_speaker_renamed``.  The chip is a
        # :class:`_RenamableSpeakerChip` only when ``speaker_id`` was
        # provided; otherwise it's a plain pill and the connect would
        # raise.  The isinstance guard mirrors the dual-pair path.
        if speaker_id and isinstance(
            single_card._speaker_chip, _RenamableSpeakerChip,
        ):
            single_card._speaker_chip.renamed.connect(self._on_speaker_renamed)
        self._insert_into(self._transcript_layout, self._scroll, single_card)
        self._current_single_card = single_card

        # Dual-view: build the pair as ``[chip-gutter | source | translation]``
        # in the same scroll, so the two sides stay row-aligned even
        # when translation arrives seconds after the original.  Cards
        # here carry *no* chips — the pair row owns the gutter so both
        # body columns share the same width (otherwise the left card's
        # chips eat into the source body and the source reads as
        # narrower than the chipless translation).
        left = _TranscriptCard("", "", text)
        left.set_mode_visibility(show_src, show_tgt)

        right = _TranscriptCard(
            "", "", _TRANSLATION_PLACEHOLDER, body_is_translated=True,
        )
        right.set_mode_visibility(show_src, show_tgt)

        pair = self._build_dual_pair_row(
            timestamp, speaker, left, right, speaker_id=speaker_id,
        )
        self._insert_into(self._dual_layout, self._dual_scroll, pair)
        self._current_dual_pair = pair

        # Overlay mirrors the same entry structure as the main window
        # so the floating subtitle view shows identical content: chips,
        # source, and a placeholder translation slot ready for
        # ``set_last_translation`` to fill in once the LLM returns.
        if self._overlay and self._overlay.isVisible():
            self._overlay.add_entry(
                timestamp,
                speaker,
                text,
                show_timestamp=self._show_timestamp,
                show_speaker=self._show_speaker,
                show_src=show_src,
                show_tgt=show_tgt,
                speaker_id=speaker_id,
                pending_translation=pending_translation,
            )

        # First entry → flip Save / Clear from disabled to enabled.
        # Cheap to call on every entry; no-op when state is unchanged.
        self._refresh_content_dependent_buttons()

        return single_card, pair

    def _add_translated(
        self,
        text: str,
        *,
        single_card: _TranscriptCard | None = None,
        dual_pair: QWidget | None = None,
    ) -> None:
        """Fills in the translation for a previously-added original.

        Pins the translation onto explicit targets when *single_card*
        / *dual_pair* are provided — that's the Whisper path where
        the LLM call returns seconds after the source sentence and
        ``self._current_*`` may have moved on to a newer entry.
        Falls back to the current-pointer path when no targets are
        passed (Soniox path: original + translation arrive together).

        Either path uses ``shiboken6.isValid`` to guard against the
        user clearing the log between the original landing and the
        translation arriving — touching a deleted widget would crash.
        """
        from shiboken6 import isValid  # noqa: PLC0415

        mode = self._resolve_display_mode()
        show_src = self._mode_shows_source(mode)
        show_tgt = self._mode_shows_target(mode)

        # Resolve targets — explicit caller args win, fall back to the
        # current-pointer attributes for the synchronous Soniox path.
        target_card = single_card if single_card is not None else getattr(
            self, "_current_single_card", None,
        )
        target_pair = dual_pair if dual_pair is not None else getattr(
            self, "_current_dual_pair", None,
        )

        if target_card is not None and isValid(target_card):
            target_card.set_translated(text)
            # Re-apply visibility so the newly-appended translation
            # label matches the current display mode.
            target_card.set_mode_visibility(show_src, show_tgt)
        elif single_card is None and dual_pair is None:
            # Fallback: translation arrived with no prior original AND
            # no explicit targets (shouldn't happen via ``_on_sentence``
            # but guard anyway).  Skip the orphan when explicit targets
            # WERE provided but got cleared — the user clicked Clear,
            # don't resurrect a row.
            orphan = _TranscriptCard("", "", text, body_is_translated=True)
            orphan.set_mode_visibility(show_src, show_tgt)
            self._insert_into(self._transcript_layout, self._scroll, orphan)

        # Dual-view: replace the placeholder ("…") in the captured
        # pair-row with the real translation.  No new card insertion —
        # rows stay one-to-one with originals.
        if target_pair is not None and isValid(target_pair):
            right = getattr(target_pair, "_right_card", None)
            if right is not None and isValid(right):
                right.set_body(text)
                right.set_mode_visibility(show_src, show_tgt)

        # Overlay: extend the most recent entry's translation slot in
        # place rather than appending a new line.  Streaming chunks
        # land here repeatedly with growing accumulated text, so a
        # per-chunk append would visibly spam the overlay; the entry's
        # in-place update keeps source + translation on one row.
        if self._overlay and self._overlay.isVisible():
            self._overlay.set_last_translation(
                text,
                show_src=show_src,
                show_tgt=show_tgt,
            )

    def _insert_into(
        self,
        layout: QVBoxLayout,
        scroll: QScrollArea,
        widget: QWidget,  # noqa: ARG002
    ) -> None:
        """Inserts a widget before the stretch, trims to `_MAX_LOG_ENTRIES`.

        Auto-scroll is wired via the scrollbar's ``rangeChanged``
        signal in ``__init__`` — when this insert grows the scroll
        range and the user is parked at the bottom, the snap fires
        AFTER the layout pass instead of racing it.  ``scroll`` is
        kept as a parameter for backward-compat with callers that
        pass a specific column; the signal already knows which
        column it belongs to.
        """
        idx = layout.count() - 1
        layout.insertWidget(idx, widget)

        while layout.count() > _MAX_LOG_ENTRIES + 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_transcript_range_changed(
        self,
        sb: "QScrollBar",
        flag_attr: str,
        max_value: int,
    ) -> None:
        """Snaps to the new bottom when the column was stuck and grew.

        Wired via ``QScrollBar.rangeChanged`` so the snap fires
        AFTER Qt has finished the layout pass — robust against the
        wordWrap two-step relayout that left the prior deferred-
        QTimer approach reading a stale ``maximum()``.
        """
        if getattr(self, flag_attr, True):
            sb.setValue(max_value)

    def _on_transcript_value_changed(
        self,
        sb: "QScrollBar",
        flag_attr: str,
        value: int,
    ) -> None:
        """Tracks whether the user has scrolled away from the bottom.

        Wheel-up disables auto-snap for this column until the user
        wheels back down (sticking when value reaches ``maximum`` —
        the tolerance allows for ~4 px drift from Qt's last layout).
        """
        setattr(
            self,
            flag_attr,
            value >= sb.maximum() - _AUTOSCROLL_BOTTOM_TOLERANCE,
        )


def create_live_page(window: QMainWindow) -> QWidget:
    """Creates the Live Translation page."""
    return LivePage(window)
