---
description: Verbinde ElevenLabs mit AI Translate für hochwertiges neuronales TTS — generiere Voiceovers in mehr als 30 Sprachen mit realistischer, expressiver Sprache.
---

# ElevenLabs (TTS)

Premium neuronales Text-to-Speech. Verwendet von den Seiten
**[Stimme generieren](../features/generate-voice.md)**,
**[Synchronisation](../features/dubbing.md)** und
**[Live-Übersetzung](../features/live-translation.md)**, wenn du
ElevenLabs als TTS-Methode wählst.

## API-Schlüssel besorgen

1. Registriere dich auf <https://elevenlabs.io>
2. Öffne <https://elevenlabs.io/app/settings/api-keys>
3. Klicke auf **+ Create New Key**, benenne ihn (z. B. „ai-translate"),
   kopiere den Schlüssel (sieht aus wie `sk_...`)

Die kostenlose Stufe gibt dir ~10.000 Zeichen / Monat, genug zum
Testen. Die Produktionsnutzung beginnt bei etwa 5 $/Monat.

## In der App konfigurieren

In **Einstellungen → Service**:

1. Füge den Schlüssel in **ElevenLabs-API-Schlüssel** → **Speichern**
2. Trage deine bevorzugte **Voice-ID** in **Voice-ID** ein (finde IDs
   auf <https://elevenlabs.io/app/voice-lab>; kopiere die ID aus der
   URL einer Stimme). Lasse leer, damit ElevenLabs eine Standardstimme
   auswählt.

In **Einstellungen → Stimme**:

1. Setze **TTS-Methode** auf **ElevenLabs**
2. Wähle das **ElevenLabs-Modell**:

    | Modell | Am besten für |
    |---|---|
    | `eleven_multilingual_v2` (Standard) | Allgemeine Nutzung, ausgewogene Latenz/Qualität |
    | `eleven_v3` | Höchste Qualität (für Produktionssynchronisationen) |
    | `eleven_flash_v2_5` | Geringste Latenz (für Live-Übersetzung) |

## Was es antreibt

| Seite | Verwende ElevenLabs, wenn |
|---|---|
| **Stimme generieren** | Du Premium-Qualitäts-Voiceovers aus Untertiteldateien willst |
| **Synchronisation** | Du eine hochwertige Sync-Spur auf einem übersetzten Video willst |
| **Live-Übersetzung** | Du gesprochene Wiedergabe von übersetzten Untertiteln in Echtzeit willst |

## Stimmenklonen

ElevenLabs unterstützt benutzerdefiniertes Stimmenklonen
(kostenpflichtiger Plan). Sobald du eine Stimme auf der ElevenLabs-
Site geklont hast, füge ihre Voice-ID in **Einstellungen → Service →
Voice-ID** ein, und die Synchronisations- / Sprachgenerierungs-
Pipeline wird sie verwenden.

## Hinweise

!!! warning "Pre-Flight-Prüfung"
    Die Stimme- / Synchronisations-Seiten prüfen, dass dein
    ElevenLabs-API-Schlüssel gesetzt ist, *bevor* die Arbeit beginnt.
    Wenn er fehlt, bekommst du einen freundlichen Dialog, der dich zu
    den Einstellungen führt, keine halb-ausgeführte Aufgabe.

!!! tip "Live-Modus fällt automatisch zurück"
    Auf der Seite **Live-Übersetzung** fällt die App, wenn du
    ElevenLabs ausgewählt, aber keinen Schlüssel konfiguriert hast,
    auf **Edge TTS** (kostenlos) zurück und kündigt den Fallback im
    Statuslabel an, damit du es bei Gelegenheit beheben kannst.

!!! info "FFmpeg weiterhin erforderlich"
    ElevenLabs gibt Audio-Bytes zurück; die App verwendet FFmpeg
    immer noch, um zwischen Formaten zu konvertieren und zeitlich
    abgestimmte Clips zu einer Datei zu kombinieren. Siehe
    [FFmpeg-Setup](ffmpeg.md).

## Häufige Fehler

| Fehler | Wahrscheinliche Ursache |
|---|---|
| `AUTH_ERROR` | Falscher / abgelaufener API-Schlüssel. Erneut in Einstellungen → Service einfügen. |
| `QUOTA_ERROR` | Zeichenlimit der kostenlosen Stufe erreicht oder kostenpflichtiger Plan erschöpft. |
| `MODEL_NOT_FOUND` | Das ausgewählte ElevenLabs-Modell ist nicht mehr verfügbar; wähle ein anderes in Einstellungen → Stimme. |
