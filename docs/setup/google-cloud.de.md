---
description: Verbinde Google Cloud mit AI Translate für Vision OCR, Speech-to-Text und Text-to-Speech — richte einen API-Schlüssel ein und aktiviere die relevanten Dienste.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Ein einzelner Google-Cloud-API-Schlüssel treibt drei optionale Backends:

- **Vision OCR** — kostenpflichtige OCR-Engine (1.000 kostenlos / Monat)
- **Speech-to-Text v1** — kostenpflichtiges STT (60 Minuten / Monat
  kostenlos)
- **Text-to-Speech v1** — kostenpflichtiges TTS (1 M Zeichen / Monat
  kostenlos für WaveNet)

Du musst nur die APIs aktivieren, die du tatsächlich verwendest.

## API-Schlüssel besorgen

1. [Erstelle ein Google-Cloud-Projekt](https://console.cloud.google.com/projectcreate)
2. Öffne die API-Bibliothek: <https://console.cloud.google.com/apis/library>
3. Aktiviere eine von:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Erstelle einen API-Schlüssel](https://console.cloud.google.com/apis/credentials):
   klicke **+ Create Credentials → API key**
5. Kopiere den Schlüssel (sieht aus wie `AIza...`).

!!! tip "Schlüssel einschränken"
    Auf der Detailseite des API-Schlüssels, unter **API restrictions**,
    beschränke den Schlüssel nur auf die APIs, die du aktiviert hast.
    So kann ein durchgesickerter Schlüssel keine Rechnungen für
    Dienste auflaufen lassen, die du nicht verwenden wolltest.

## In der App konfigurieren

In **Einstellungen → Service**:

1. Füge in **Google-Cloud-API-Schlüssel** ein → **Speichern**

Dieser einzelne Schlüssel ist jetzt für alle drei Google-Dienste
verfügbar.

## Jeden Dienst aktivieren

### Vision OCR

In **Einstellungen → OCR → OCR-Methode = Google Cloud OCR**.

Das war's — er verwendet denselben Schlüssel aus Service.

### Speech-to-Text

In **Einstellungen → Untertitel → STT-Methode = Google Cloud** (für
die Untertitel- / Stimme-Seiten) oder **Einstellungen → Live →
STT-Methode = Google Cloud** (für die Live-Seite).

In **Einstellungen → Untertitel → Google-STT-Modell**, wähle das
Erkennungsmodell:

| Modell | Am besten für |
|---|---|
| `latest_long` (Standard) | Lange Audio-Form (Interviews, Vorlesungen) |
| `latest_short` | Sprachbefehle, kurze Phrasen |
| `phone_call` | Telefonie-Audio (8 kHz) |
| `medical_dictation` / `medical_conversation` | Audio aus dem medizinischen Bereich |

### Text-to-Speech

In **Einstellungen → Stimme → TTS-Methode = Google Cloud TTS**.

Standardmäßig wählt der Server eine Stimme basierend auf Sprache und
Geschlecht — das ist, was die meisten Benutzer brauchen. Das
Anpinnen einer bestimmten Google-Stimme (z. B.
`en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`) wird von der Engine
unterstützt, ist aber noch nicht als Einstellungsfeld exponiert; es
kann durch direktes Bearbeiten von `voice/google_tts_voice_name` in
`settings.ini` gesetzt werden. Stimm-IDs sind unter
<https://cloud.google.com/text-to-speech/docs/voices> aufgelistet.

## Häufige Fehler

| Fehler | Wahrscheinliche Ursache |
|---|---|
| `AUTH_ERROR` | Falscher / abgelaufener Schlüssel. Erneut in Einstellungen → Service einfügen. |
| `API not enabled` | Du hast die spezifische API (Vision / Speech / TTS) auf diesem Cloud-Projekt nicht aktiviert. |
| `QUOTA_ERROR` | Limit der kostenlosen Stufe für diese API erreicht. Warte oder upgrade die Abrechnung. |
| `INVALID_ARGUMENT_ERROR` | Stimmname existiert nicht in der gewählten Sprache. |

## Kostenwächter

!!! warning
    Alle drei Google-APIs sind nachträglich bezahlt — sobald du die
    kostenlose Stufe überschreitest, wirst du ohne Stopp abgerechnet.
    Lege eine [Budget-Warnung](https://console.cloud.google.com/billing/budgets)
    auf dem Cloud-Projekt fest, bevor du Arbeit mit hohem Volumen
    erledigst.
