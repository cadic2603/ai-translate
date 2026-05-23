---
description: Connect Google Cloud to AI Translate for Vision OCR, Speech-to-Text, and Text-to-Speech — set up an API key and enable the relevant services.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

A single Google Cloud API key powers three optional backends:

- **Vision OCR** — paid OCR engine (1,000 free / month)
- **Speech-to-Text v1** — paid STT (60 minutes / month free)
- **Text-to-Speech v1** — paid TTS (1 M characters / month free for
  WaveNet)

You only need to enable the APIs you actually use.

## Get an API key

1. [Create a Google Cloud project](https://console.cloud.google.com/projectcreate)
2. Open the API library: <https://console.cloud.google.com/apis/library>
3. Enable any of:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Create an API key](https://console.cloud.google.com/apis/credentials):
   click **+ Create Credentials → API key**
5. Copy the key (looks like `AIza...`).

!!! tip "Restrict the key"
    On the API-key detail page, under **API restrictions**, restrict the
    key to just the APIs you've enabled. That way a leaked key can't
    rack up bills on services you didn't intend to use.

## Configure in the app

In **Settings → Service**:

1. Paste into **Google Cloud API key** → **Save**

This single key is now available to all three Google services.

## Enable each service

### Vision OCR

In **Settings → OCR → OCR method = Google Cloud OCR**.

That's it — it'll use the same key from Service.

### Speech-to-Text

In **Settings → Subtitle → STT method = Google Cloud** (for the
Subtitle / Voice pages) or **Settings → Live → STT method = Google
Cloud** (for the Live page).

In **Settings → Subtitle → Google STT model**, pick the recognition
model:

| Model | Best for |
|---|---|
| `latest_long` (default) | Long-form audio (interviews, lectures) |
| `latest_short` | Voice commands, short phrases |
| `phone_call` | Telephony audio (8 kHz) |
| `medical_dictation` / `medical_conversation` | Medical-domain audio |

### Text-to-Speech

In **Settings → Voice → TTS method = Google Cloud TTS**.

By default the server picks a voice based on language and gender — that's
all most users need. Pinning a specific Google voice (e.g.
`en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`) is supported by the engine
but not yet exposed as a Settings field; it can be set by editing
`voice/google_tts_voice_name` in `settings.ini` directly. Voice IDs are
listed at <https://cloud.google.com/text-to-speech/docs/voices>.

## Common errors

| Error | Likely cause |
|---|---|
| `AUTH_ERROR` | Wrong / expired key. Re-paste in Settings → Service. |
| `API not enabled` | You haven't enabled the specific API (Vision / Speech / TTS) on this Cloud project. |
| `QUOTA_ERROR` | Free-tier limit reached for this API. Wait, or upgrade billing. |
| `INVALID_ARGUMENT_ERROR` | Voice name doesn't exist in the language you picked. |

## Cost guard

!!! warning
    All three Google APIs are post-paid — once you exceed the free tier
    you start being billed without a stop. Set a [budget alert](https://console.cloud.google.com/billing/budgets)
    on the Cloud project before doing high-volume work.
