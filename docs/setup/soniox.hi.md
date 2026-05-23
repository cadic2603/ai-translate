---
description: AI Translate के Live पेज में real-time speech-to-text के लिए Soniox configure करें — speaker diarisation, glossary terms, और live translation का support।
---

# Soniox (STT)

Soniox WebSocket API के माध्यम से real-time speech-to-text। STT
method के रूप में Soniox चुनने पर **[Subtitle](../features/generate-subtitle.md)**
और **[Live Translation](../features/live-translation.md)** पेज
उपयोग करते हैं।

## Soniox क्यों

- **Real-time** — speaker के बात करते हुए ही tokens आ जाते हैं।
- **Speaker diarization** — per-token speaker labels (जैसे
  _Speaker 1: Hi…_)।
- **In-stream translation** — Soniox transcribe करते समय अनुवाद कर
  सकता है, एक extra LLM round trip बचाता है।
- **Multi-language** — mid-stream में भी source language को
  auto-detect करता है।

## API key प्राप्त करें

1. <https://console.soniox.com> पर sign up करें
2. **API keys** → **Create new API key** खोलें
3. Copy करें (`Bearer ...` जैसा दिखता है; केवल token को `Bearer `
   prefix के बिना copy करें)।

Pricing audio के per minute metered है (writing के समय ~$0.005 /
minute) — देखें <https://soniox.com/pricing>।

## ऐप में configure करें

**Settings → Service** में:

1. Key को **Soniox API key** में paste करें → **Save**

**Settings → Live** *(live translation के लिए)* या **Settings →
Subtitle** *(subtitle generation के लिए)* में:

1. **STT method** को **Soniox** पर set करें

## यह क्या powers देता है

| Page | कब Soniox उपयोग करें |
|---|---|
| **Subtitle** | Multi-speaker recordings (interviews, panels, meetings) जहाँ आप SRT में speaker labels चाहते हैं |
| **Live Translation** | Real-time meeting captioning, विशेष रूप से कई speakers के साथ |

## Glossary terms

Soniox WebSocket recognition को bias करने के लिए terms का एक
glossary स्वीकार करता है। ऐप automatically आपकी active glossary
entries को forward करता है — brand names / proper nouns / jargon
अधिक reliably recognize होते हैं।

## Caveats

!!! warning "केवल Online"
    Soniox cloud-only है; यदि आपका audio sensitive है (medical,
    legal), तो Whisper (local) का उपयोग करें।

!!! info "Reconnection"
    WebSocket transient failures पर exponential backoff के साथ
    auto-reconnect करता है। Long sessions brief network blips के
    माध्यम से connected रहती हैं।

## Common errors

| Error | Likely cause |
|---|---|
| `AUTH_ERROR` | गलत / expired API key। Settings → Service में फिर से paste करें। |
| `QUOTA_ERROR` | Plan limit exceeded। |
| `CONNECTION_ERROR` | Network blocked / firewall। एक different network से फिर से try करें। |
