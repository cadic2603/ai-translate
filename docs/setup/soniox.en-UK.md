---
description: Configure Soniox for real-time speech-to-text in AI Translate's Live page — supports speaker diarisation, glossary terms, and live translation.
---

# Soniox (STT)

Real-time speech-to-text via the Soniox WebSocket API. Used by the
**[Subtitle](../features/generate-subtitle.md)** and **[Live Translation](../features/live-translation.md)**
pages when you pick Soniox as the STT method.

## Why Soniox

- **Real-time** — tokens arrive while the speaker is still talking.
- **Speaker diarization** — per-token speaker labels (e.g. _Speaker 1: Hi…_).
- **In-stream translation** — Soniox can translate while transcribing,
  saving an extra LLM round trip.
- **Multi-language** — auto-detects the source language even mid-stream.

## Get an API key

1. Sign up at <https://console.soniox.com>
2. Open **API keys** → **Create new API key**
3. Copy it (looks like `Bearer ...`; copy just the token without the
   `Bearer ` prefix).

Pricing is metered per minute of audio (~$0.005 / minute at the time of
writing) — see <https://soniox.com/pricing>.

## Configure in the app

In **Settings → Service**:

1. Paste the key into **Soniox API key** → **Save**

In **Settings → Live** *(for live translation)* or **Settings → Subtitle**
*(for subtitle generation)*:

1. Set **STT method** to **Soniox**

## What it powers

| Page | Use Soniox when |
|---|---|
| **Subtitle** | Multi-speaker recordings (interviews, panels, meetings) where you want speaker labels in the SRT |
| **Live Translation** | Real-time meeting captioning, especially with multiple speakers |

## Glossary terms

The Soniox WebSocket accepts a glossary of terms to bias recognition
toward. The app forwards your active glossary entries automatically —
brand names / proper nouns / jargon get recognised more reliably.

## Caveats

!!! warning "Online only"
    Soniox is cloud-only; if your audio is sensitive (medical, legal),
    use Whisper (local) instead.

!!! info "Reconnection"
    The WebSocket auto-reconnects on transient failures with exponential
    backoff. Long sessions stay connected through brief network blips.

## Common errors

| Error | Likely cause |
|---|---|
| `AUTH_ERROR` | Wrong / expired API key. Re-paste in Settings → Service. |
| `QUOTA_ERROR` | Plan limit exceeded. |
| `CONNECTION_ERROR` | Network blocked / firewall. Try again from a different network. |
