"""Settings keys for persistent INI-based storage via config_manager."""

from src.constants._signal import CallbackSignal

# OCR Settings
SETTING_OCR_METHOD = "ocr/method"

# Google Cloud (shared key for Vision OCR, Speech-to-Text, TTS)
SETTING_GOOGLE_CLOUD_API_KEY = "cloud/google_api_key"

# General Settings
SETTING_THEME = "app/theme"
SETTING_LIBREOFFICE_PATH = "office/libreoffice_path"
SETTING_AUTO_SAVE = "app/auto_save"
SETTING_AUTO_REMOVE_HISTORY = "app/auto_remove_history"
SETTING_STORAGE_PATH = "app/storage_path"

# LLM Settings
SETTING_LLM_METHOD = "llm/method"
SETTING_LLM_GEMINI_API_KEY = "llm/gemini_api_key"
SETTING_LLM_GEMINI_MODEL = "llm/gemini_model"

# Vertex AI mode for the Gemini provider.  When enabled, requests go
# through Google Cloud Vertex AI (using the user's GCP project + ADC or
# a service-account JSON file) instead of the public Gemini Developer
# API.  Same SDK, different client constructor and auth path.
SETTING_LLM_GEMINI_USE_VERTEX = "llm/gemini_use_vertex"
SETTING_LLM_VERTEX_PROJECT = "llm/vertex_project"
SETTING_LLM_VERTEX_LOCATION = "llm/vertex_location"
# Path to a service-account JSON file.  When empty, the SDK falls back
# to Application Default Credentials (gcloud user creds, env var, or
# instance metadata).  Stored in the OS keychain via the secure-keys
# allowlist in config_manager.
SETTING_LLM_VERTEX_CREDENTIALS = "llm/vertex_credentials"
VERTEX_DEFAULT_LOCATION = "us-central1"
# Common Vertex AI regions for Gemini deployments.  Keep ordered by
# rough usage frequency so the dropdown defaults to the most common
# choice (us-central1).
VERTEX_LOCATIONS: tuple[str, ...] = (
    "us-central1",
    "us-east1",
    "us-east4",
    "us-east5",
    "us-west1",
    "us-west4",
    "europe-west1",
    "europe-west2",
    "europe-west3",
    "europe-west4",
    "europe-west9",
    "asia-east1",
    "asia-northeast1",
    "asia-northeast3",
    "asia-southeast1",
    "australia-southeast1",
)
SETTING_LLM_CUSTOM_API_KEY = "llm/custom_api_key"
SETTING_LLM_CUSTOM_MODEL = "llm/custom_model"
SETTING_LLM_CUSTOM_ENDPOINT = "llm/custom_endpoint"
SETTING_LLM_CUSTOM_PROVIDERS = "llm/custom_providers"
SETTING_LLM_LAST_MODEL = "llm/last_model"
# Per-feature model preferences.  Each feature reads its own key first,
# then falls back to ``SETTING_LLM_LAST_MODEL`` so first-time users don't
# have to pick a model separately in every screen.  Users who want cost /
# speed trade-offs (fast Flash for Live, Pro for documents, etc.) get that
# by picking a different model inside the feature's own picker.
SETTING_LLM_MODEL_TRANSLATE_TEXT = "llm/model_translate_text"
SETTING_LLM_MODEL_TRANSLATE_DOCUMENT = "llm/model_translate_document"
SETTING_LLM_MODEL_SUBTITLE = "llm/model_subtitle"
SETTING_LLM_MODEL_DUBBING = "llm/model_dubbing"
SETTING_LLM_MODEL_LIVE = "llm/model_live"
SETTING_LLM_MODEL_SCREEN = "llm/model_screen"
SETTING_LLM_MODEL_EXTRACT = "llm/model_extract"

# UI Language
SETTING_UI_LANGUAGE = "app/ui_language"

# Glossary
SETTING_GLOSSARY_SPLITTER_SIZES = "glossary_splitter_sizes"

# Translation Settings
SETTING_LAST_SOURCE_LANGUAGE = "translation/last_source_language"
SETTING_LAST_TARGET_LANGUAGE = "translation/last_target_language"
SETTING_LAST_EXTRACT_LANGUAGE = "extraction/last_source_language"
SETTING_LAST_EXTRACT_FORMAT = "extraction/last_output_format"
SETTING_EXTRACT_STORAGE_PATH = "extraction/storage_path"
SETTING_EXTRACT_AUTO_REMOVE = "extraction/auto_remove_history"
SETTING_EXTRACT_METHOD = "extraction/method"
# Extraction method values
EXTRACT_METHOD_OCR = "OCR"
EXTRACT_METHOD_LLM = "LLM"

# Subtitle Settings
SETTING_SUBTITLE_STT_METHOD = "subtitle/stt_method"
SETTING_WHISPER_MODEL = "subtitle/whisper_model"
# STT method values
STT_WHISPER = "Whisper"
STT_GOOGLE = "Google Cloud"
SETTING_GOOGLE_STT_MODEL = "subtitle/google_stt_model"
SETTING_SUBTITLE_STORAGE_PATH = "subtitle/storage_path"
SETTING_SUBTITLE_AUTO_REMOVE = "subtitle/auto_remove_history"
SETTING_LAST_SUBTITLE_LANGUAGE = "subtitle/last_source_language"
SETTING_LAST_SUBTITLE_TARGET = "subtitle/last_target_language"
SETTING_LAST_SUBTITLE_FORMAT = "subtitle/last_output_format"

# Voice (TTS) Settings
SETTING_VOICE_TTS_METHOD = "voice/tts_method"
# TTS method values
VOICE_TTS_EDGE = "Edge TTS"
VOICE_TTS_GOOGLE = "Google Cloud TTS"
VOICE_TTS_ELEVENLABS = "ElevenLabs"
VOICE_TTS_GEMINI = "Gemini TTS"
VOICE_TTS_PIPER = "Piper TTS"
# Selected Piper voice ID (e.g. "en_US-amy-medium").  Picked from the
# Voice settings combo; used by the engine in preference to the
# language+gender resolver.  Empty falls back to the gender default
# for the current target language so a fresh install still produces
# audio without forcing the user to pick a voice first.
SETTING_LAST_PIPER_VOICE = "voice/piper_voice_id"

# ElevenLabs API
SETTING_ELEVENLABS_API_KEY = "service/elevenlabs_api_key"
SETTING_ELEVENLABS_VOICE_ID = "voice/elevenlabs_voice_id"
# ElevenLabs model ID (see https://elevenlabs.io/docs/overview/models).
# Defaults to eleven_multilingual_v2 (stable, production-quality).
# Users can select eleven_v3 (highest quality, GA 2026-03) or
# eleven_flash_v2_5 (ultra-low latency for Live/Dubbing).
SETTING_ELEVENLABS_MODEL = "voice/elevenlabs_model"
ELEVENLABS_MODEL_MULTILINGUAL_V2 = "eleven_multilingual_v2"
ELEVENLABS_MODEL_V3 = "eleven_v3"
ELEVENLABS_MODEL_FLASH_V2_5 = "eleven_flash_v2_5"
ELEVENLABS_MODEL_DEFAULT = ELEVENLABS_MODEL_MULTILINGUAL_V2
# Optional override for Gemini TTS prebuilt voice name (e.g. "Aoede",
# "Charon").  When empty, ``_get_gemini_voice`` returns the gender-
# default — Kore (female) or Puck (male).
SETTING_GEMINI_TTS_VOICE_NAME = "voice/gemini_tts_voice_name"
SETTING_VOICE_STORAGE_PATH = "voice/storage_path"
SETTING_LAST_VOICE_LANGUAGE = "voice/last_language"
SETTING_LAST_VOICE_GENDER = "voice/last_gender"
SETTING_LAST_VOICE_FORMAT = "voice/last_output_format"
SETTING_VOICE_AUTO_REMOVE = "voice/auto_remove_history"
# Voice gender values
VOICE_GENDER_FEMALE = "FEMALE"
VOICE_GENDER_MALE = "MALE"

# Dubbing Settings
SETTING_DUBBING_STORAGE_PATH = "dubbing/storage_path"
SETTING_DUBBING_AUTO_REMOVE = "dubbing/auto_remove_history"
SETTING_LAST_DUBBING_SRC_LANG = "dubbing/last_source_language"
SETTING_LAST_DUBBING_TGT_LANG = "dubbing/last_target_language"

# Translate Text Settings
SETTING_TRANSLATE_TEXT_SRC_LANG = "translate_text/source_language"
SETTING_TRANSLATE_TEXT_TGT_LANG = "translate_text/target_language"
SETTING_TRANSLATE_TEXT_AUTO_SAVE = "translate_text/auto_save_history"
SETTING_TRANSLATE_TEXT_TTS_STORAGE = "translate_text/tts_storage_path"

# Live Translation Settings
SETTING_LIVE_SOURCE_LANG = "live/source_language"
SETTING_LIVE_TARGET_LANG = "live/target_language"
SETTING_LIVE_WHISPER_MODEL = "live/whisper_model"
SETTING_LIVE_SHOW_ORIGINAL = "live/show_original"
# What the transcript (and overlay) renders when translation is on.
# Replaces the older boolean ``show_original``; the old key is still
# read as a fallback so existing user configs keep working.
SETTING_LIVE_SHOW_TIMESTAMP = "live/show_timestamp"
# Speaker-label visibility on Live transcript cards.  Only meaningful
# when the active STT method emits speaker IDs (Soniox); the toggle
# button is hidden for Whisper, but the setting itself is persisted
# so a user switching back to Soniox sees their last preference.
SETTING_LIVE_SHOW_SPEAKER = "live/show_speaker"
SETTING_LIVE_TRANSCRIPT_DISPLAY = "live/transcript_display"
LIVE_DISPLAY_BOTH = "both"  # source + translation, stacked (single column)
LIVE_DISPLAY_BOTH_DUAL = "both_dual"  # source + translation, side-by-side (dual column)
LIVE_DISPLAY_TRANSLATION = "translation"
# General: startup update check against GitHub Releases.
SETTING_AUTO_UPDATE_CHECK = "general/auto_update_check"
SETTING_LAST_UPDATE_CHECK = "general/last_update_check"
# When tracking a new upstream owner/repo, update these constants — an empty
# repo short-circuits the check entirely so the app stays quiet offline.
UPDATE_REPO_OWNER = "cadic2603"
UPDATE_REPO_NAME = "ai-translate"

# ── Public URLs surfaced in the About page ─────────────────────────────
# All four are derived from the repo coords above except DOCS_URL, which
# follows the GitHub Pages convention for the same repo.  Keeping them
# as constants (instead of hard-coding into the About page) means
# forking the project for a different upstream is a one-place edit.
REPO_URL = f"https://github.com/{UPDATE_REPO_OWNER}/{UPDATE_REPO_NAME}"
ISSUES_URL = f"{REPO_URL}/issues"
LICENSE_URL = f"{REPO_URL}/blob/main/LICENSE"
DOCS_URL = f"https://{UPDATE_REPO_OWNER}.github.io/{UPDATE_REPO_NAME}/"
LICENSE_NAME = "AGPL-3.0-or-later"
COPYRIGHT_HOLDER = "cadic2603"

SETTING_LIVE_AUDIO_SOURCE = "live/audio_source"
SETTING_LIVE_STT_METHOD = "live/stt_method"
# Live session auto-save mode (privacy: defaults to ``LIVE_SAVE_NONE``).
# Combo on Settings → Live → Audio Recording.  On session stop the page
# writes whichever artefacts the chosen mode requests, into the folder
# at ``SETTING_LIVE_OUTPUT_PATH`` (falls back to app-data ``live_audio/``).
SETTING_LIVE_SAVE_OUTPUT = "live/save_output_mode"
SETTING_LIVE_OUTPUT_PATH = "live/output_path"
LIVE_SAVE_NONE = "none"
LIVE_SAVE_TEXT = "text"
LIVE_SAVE_AUDIO = "audio"
LIVE_SAVE_TEXT_AUDIO = "text_audio"
# Live transcript output format.  SRT (default) is widely supported by
# video players + matches the Subtitle page's default; VTT for web /
# HTML5; TXT for note-taking workflows that don't want cue timecodes.
SETTING_LIVE_TRANSCRIPT_FORMAT = "live/transcript_format"
LIVE_TRANSCRIPT_FORMAT_SRT = "srt"
LIVE_TRANSCRIPT_FORMAT_VTT = "vtt"
LIVE_TRANSCRIPT_FORMAT_ASS = "ass"
LIVE_TRANSCRIPT_FORMAT_SSA = "ssa"
LIVE_TRANSCRIPT_FORMAT_CSV = "csv"
# Live audio output format.  WAV (default) is written incrementally by
# the engine via Python's ``wave`` module; MP3 post-encodes the WAV to
# a much smaller file via ffmpeg on session stop, then deletes the
# WAV.  MP3 needs ffmpeg on PATH — the page surfaces a setup hint
# when the user picks it without ffmpeg installed.
SETTING_LIVE_AUDIO_FORMAT = "live/audio_format"
LIVE_AUDIO_FORMAT_WAV = "wav"
LIVE_AUDIO_FORMAT_MP3 = "mp3"
LIVE_AUDIO_FORMAT_FLAC = "flac"  # lossless, ~50% of WAV size
LIVE_AUDIO_FORMAT_OGG = "ogg"  # lossy (Vorbis), open codec
# Audio formats that require an external encoder (currently
# ffmpeg).  The settings page checks this set when deciding
# whether to surface the "ffmpeg missing" warning banner; if
# the user picks any of these and ffmpeg isn't on PATH, the
# post-encode silently falls back to WAV.
LIVE_AUDIO_FORMATS_REQUIRING_FFMPEG = frozenset(
    {
        LIVE_AUDIO_FORMAT_MP3,
        LIVE_AUDIO_FORMAT_FLAC,
        LIVE_AUDIO_FORMAT_OGG,
    }
)
# Live transcript layout: "single" (interleaved log) or "dual" (side-by-side).
SETTING_LIVE_TRANSCRIPT_LAYOUT = "live/transcript_layout"
LIVE_LAYOUT_SINGLE = "single"
LIVE_LAYOUT_DUAL = "dual"
# Overlay window geometry as "x,y,w,h" — persisted across sessions so the
# user's chosen position and size stick.
SETTING_LIVE_OVERLAY_GEOMETRY = "live/overlay_geometry"
# Overlay appearance. Opacity is a float between 0.2 and 1.0; font size
# is a pixel integer for the translated text (original text is two smaller).
SETTING_LIVE_OVERLAY_OPACITY = "live/overlay_opacity"
SETTING_LIVE_OVERLAY_FONT_SIZE = "live/overlay_font_size"
# Minimal-captions toggle: when True, the floating overlay hides the
# timestamp + speaker chips regardless of the page-level "Speaker
# labels" / show-timestamp preferences.  Useful for presenter / screen-
# sharing scenarios where the overlay is shown to an audience while the
# main window keeps its full metadata visible.  Decoupled per surface
# rather than four toggles (timestamp × surface, speaker × surface).
SETTING_LIVE_OVERLAY_MINIMAL = "live/overlay_minimal"
# Auto-stop the live session after N minutes of silence (no finalised
# sentences from the STT backend).  0 = disabled.  Prevents users from
# forgetting the Live page is running and bleeding cloud minutes
# overnight.  The timer resets on every ``_on_sentence`` so as long as
# someone speaks within the window the session continues.
SETTING_LIVE_AUTO_STOP_MINUTES = "live/auto_stop_minutes"

# Persisted checkbox state for the manual Save chooser dialog on the
# Live page.  Both default to True so a first-time user (or one who
# wiped their config) picks the maximally-informative save by default
# — and subsequent opens remember whatever they last clicked.  We save
# on dialog accept only; cancelling preserves the prior preference.
SETTING_LIVE_SAVE_DIALOG_TRANSCRIPT = "live/save_dialog_transcript"
SETTING_LIVE_SAVE_DIALOG_AUDIO = "live/save_dialog_audio"

# Emitted whenever an overlay-appearance setting (font size or opacity)
# changes from any surface — the Settings → Live tab sliders, the
# in-overlay ``+`` / ``-`` / opacity keyboard shortcuts, or any future
# entry point.  Listeners receive ``(key, value)`` where ``key`` is one
# of ``SETTING_LIVE_OVERLAY_FONT_SIZE`` / ``SETTING_LIVE_OVERLAY_OPACITY``
# and ``value`` is the parsed numeric value (int for font_size, float
# for opacity).  Both directions of live-sync flow through this signal
# so the open overlay updates in real time when the slider moves, and
# the slider catches up when the user nudges font size or opacity from
# inside the overlay.  Listeners must filter on ``key`` and apply only
# when the new value differs from their current state, to avoid feedback
# loops.
overlay_appearance_changed = CallbackSignal()
# Live STT method values
LIVE_STT_WHISPER = "whisper"
LIVE_STT_SONIOX = "soniox"
# Audio source values
AUDIO_SOURCE_MICROPHONE = "microphone"
AUDIO_SOURCE_SYSTEM = "system"
AUDIO_SOURCE_BOTH = "both"

# Soniox API
SETTING_SONIOX_API_KEY = "service/soniox_api_key"

# Document translation feature toggles
SETTING_TRANSLATE_DOC_IMAGES = "translation/translate_doc_images"
SETTING_TRANSLATE_DOC_COMMENTS = "translation/translate_doc_comments"
SETTING_TRANSLATE_DOC_SHAPES = "translation/translate_doc_shapes"
SETTING_TRANSLATE_DOC_NOTES = "translation/translate_doc_notes"
SETTING_TRANSLATE_SHEET_NAMES = "translation/translate_sheet_names"
SETTING_AUTO_CONVERT_LEGACY = "translation/auto_convert_legacy"
SETTING_AUTO_CONVERT_ODF = "translation/auto_convert_odf"
