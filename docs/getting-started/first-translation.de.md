---
description: Übersetzen Sie Ihr erstes Dokument mit AI Translate in 5 Minuten — ziehen Sie ein PDF per Drag-and-Drop, wählen Sie eine Zielsprache und laden Sie die übersetzte Kopie herunter.
---

# Ihre erste Übersetzung

Ein schneller End-to-End-Durchlauf — unter 5 Minuten, sobald die
Einrichtung erledigt ist.

!!! abstract "Bevor Sie beginnen"
    Sie müssen die [Installation](installation.md) abgeschlossen und
    einen LLM-API-Schlüssel konfiguriert haben. Die kostenlose
    Google-Gemini-Stufe reicht für einen ersten Versuch.

## Ein Word-Dokument übersetzen

1. Starten Sie die Desktop-App:

    ```bash
    uv run python -m src.main
    ```

2. Klicken Sie in der linken Seitenleiste auf **Dokument übersetzen**.

3. Ziehen Sie eine beliebige `.docx`-Datei in die Drop-Zone — oder
   klicken Sie auf **Durchsuchen**, um eine auszuwählen.

4. Die Datei erscheint in der Warteschlange. Wählen Sie oben eine Zielsprache:

    - Quelle: `Auto-Erkennung` (Standard — meist korrekt)
    - Ziel: z. B. `Französisch`, `Vietnamesisch`, `Japanisch`, `Chinesisch (vereinfacht)`

5. Klicken Sie auf **Übersetzen** (oder drücken Sie `Strg+Eingabe`).

6. Beobachten Sie den Fortschrittsbalken in der Verlaufstabelle unten
   auf der Seite. Wenn er 100 % erreicht, klicken Sie in der Zeile auf
   **Öffnen**, um die übersetzte Datei zu öffnen — sie wird neben dem
   Original mit dem Suffix `_translated_<src>_<tgt>` gespeichert.

## Was gerade passiert ist

- Ihre `.docx` wurde in einen pro-Aufgabe-Speicherordner kloniert,
  damit das Original unberührt bleibt.
- Der Text wurde extrahiert, in LLM-freundliche Chunks gebatcht,
  übersetzt und dann mit allen Formatierungen erhalten wieder ins
  Dokument injiziert (fett, kursiv, Schriftarten, Farben, Kopfzeilen,
  Fußnoten, Hyperlinks…).
- Ein Verlaufseintrag wurde in eine SQLite-Datenbank geschrieben,
  sodass Sie die Datei später erneut öffnen, ausführen oder
  übersetzen können.

## Probieren Sie als nächstes diese Quick Wins

=== "Klartext übersetzen"

    Springen Sie in der Seitenleiste zu **Text übersetzen**. Fügen Sie
    irgendetwas ein, wählen Sie ein Ziel, drücken Sie Eingabe.
    Streaming-Ausgabe, Sprachwechsel (`Strg+L`), Bearbeitungsmodus,
    TTS-Wiedergabe.

=== "Untertitel erzeugen"

    **Untertitel erzeugen** — eine `.mp4` einwerfen. Sie erhalten
    eine `.srt` in der Quellsprache zurück. (Um das Video _und_ zu
    synchronisieren, verwenden Sie stattdessen die Synchronisations-Seite.)

=== "Live-Mikrofon-Übersetzung"

    **Live-Übersetzung** — Mikrofon oder System-Audio wählen, ein Ziel
    wählen, Start. Ein schwebendes Overlay-Fenster zeigt Untertitel
    in Echtzeit.

## Wohin als nächstes

- Siehe den [Funktions-Index](../index.md#headline-features) für das, was jede Seite macht.
- Verbinden Sie [weitere Anbieter](../setup/llm-providers.md) (benutzerdefinierte Endpunkte, ElevenLabs, Soniox, Google Cloud).
- Probieren Sie das [CLI](../cli.md) für Batch- / skriptgesteuerte Läufe.
