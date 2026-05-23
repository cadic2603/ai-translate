---
description: Übersetzen Sie Textausschnitte sofort in über 45 Sprachen mit AI Translate — einfügen, tippen oder sprechen; unterstützt Bearbeitungsmodus, TTS-Wiedergabe und Sprachtausch.
---

# Text übersetzen

Sofortige LLM-Übersetzung mit Auto-Erkennung, Sprachtausch,
Streaming-Ausgabe und TTS-Wiedergabe. Am besten für kurze Ausschnitte,
Chat-Stil und das Testen Ihrer LLM-Einrichtung.

## Schritt-für-Schritt

1. Klicken Sie in der Seitenleiste auf **Text übersetzen**.
2. Tippen oder fügen Sie Ihren Quelltext ins linke Panel ein.
3. Die **Quell**sprache wird beim Tippen automatisch erkannt
   (powered by `langdetect`).
4. Wählen Sie eine **Ziel**sprache aus dem rechten Dropdown.
5. Klicken Sie auf **Übersetzen** (oder drücken Sie `Strg+Eingabe`).
6. Die Übersetzung streamt token-für-token ins rechte Panel.

## Was Sie bekommen

- **Streaming-Ausgabe** — die Übersetzung erscheint, während der LLM
  sie generiert, kein Warten auf die ganze Antwort.
- **Auto-Erkennung der Quelle** — der Quellpicker aktualisiert sich
  in Echtzeit. Klicken zum Überschreiben.
- **Bearbeitungsmodus** — klicken Sie aufs rechte Panel, um die
  Übersetzung manuell zu bearbeiten. Drücken Sie `Esc` zum Abbrechen
  einer laufenden Übersetzung; nochmal drücken zum Verlassen des
  Bearbeitungsmodus.
- **Verlauf-Wiederverwendung** — jede Übersetzung wird gespeichert.
  Klicken Sie auf einen Eintrag im Textübersetzungs-Verlaufspanel
  unten, um beide Panels neu zu laden; Bearbeitungen aktualisieren den
  Originaleintrag, statt ein Duplikat zu erstellen.
- **TTS-Wiedergabe** — klicken Sie auf **Anhören** neben einem Panel,
  um es vorlesen zu hören. Respektiert Ihre Auswahl in
  **Einstellungen → Stimme → TTS-Methode** — Edge TTS (Standard),
  ElevenLabs, Google Cloud TTS, Gemini TTS oder **Piper TTS**
  (vollständig offline). Mit Piper ausgewählt führt der Anhören-Button
  denselben Pre-Flight wie die Stimmen-Seite aus: eine fehlende
  Per-Sprach-Stimme zeigt einen Modal-Dialog mit einem
  **Einstellungen öffnen**-Button zum Herunterladen. Cache-Treffer
  überspringen den Pre-Flight komplett.
- **Modellauswahl pro Funktion** — wenn mehr als ein LLM konfiguriert
  ist, lässt ein Dropdown Sie ein schnelles Flash-Modell für Tempo
  oder ein schwereres Pro-Modell für Qualität wählen, nur für diese
  Seite.

## Tastenkürzel

| Kürzel | Aktion |
|---|---|
| `Strg+Eingabe` | Übersetzen |
| `Strg+L` | Quelle ↔ Ziel tauschen |
| `Esc` | Laufende Übersetzung abbrechen oder Bearbeitungsmodus verlassen |
| `Strg+F` | Fokus auf Verlaufssuche |

## Tipps

!!! tip "RTL-Sprachen"
    Übersetzungen ins **Arabische**, **Hebräische** oder **Persische**
    werden automatisch von rechts nach links im Ausgabepanel gerendert.
    Dieselbe RTL-Behandlung überträgt sich auf die Dateiausgabe in
    jedem Format auf der Seite
    [Dokument übersetzen](translate-document.md) (PDF, DOCX, PPTX,
    XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), und Persisch erhält eine
    native `fa-IR`-Stimme für die Edge-TTS-Wiedergabe.

!!! tip "Anhören-Button-Cache"
    Beim ersten Klick auf Anhören für ein gegebenes (Text, Sprache)-Paar
    wird das Audio synthetisiert und auf der Festplatte gecacht.
    Spätere Wiedergaben sind sofort. Der Cache wird beim App-Start
    geleert, sodass jede Sitzung neu beginnt.

!!! tip "Wo die Schlüssel hingehen"
    Die Seite „Text übersetzen" liest dieselben Schlüsselbund-Einträge
    wie der Rest der App — siehe
    [LLM-Anbieter](../setup/llm-providers.md).
