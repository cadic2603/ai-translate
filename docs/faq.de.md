---
description: "Häufige Fragen zu AI Translate: unterstützte Dateiformate, kostenlose vs. kostenpflichtige Funktionen, Offline-Nutzung, LLM-Anbieterauswahl und OCR-Engine-Wahl."
---

# Häufig gestellte Fragen

## Allgemein

### Funktioniert es offline?

Größtenteils ja. Konkret:

- **Übersetzung** benötigt einen LLM. Die kostenlose Gemini-API ist
  online; **lokales Ollama / LM Studio** über die
  Custom-Provider-Einstellungen ist vollständig offline.
- **OCR** mit **Tesseract** oder **EasyOCR** ist offline.
- **STT** mit **Whisper** (Standard) ist offline.
- **TTS** mit **Edge TTS** (Standard) ist online; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** sind online (kostenlos oder
  kostenpflichtig); **Piper TTS** ist vollständig offline-fähiges
  neuronales TTS — kein Schlüssel, keine Netzwerkaufrufe, sobald die
  pro Sprache gewünschte Stimme (~25–60 MB ONNX-Datei) über
  **Einstellungen → Stimme → Piper TTS → Stimmen jetzt herunterladen**
  geladen wurde.

Für ein vollständig air-gapped Setup: Custom-Provider → lokaler LLM,
Tesseract oder EasyOCR für OCR, Whisper für STT und Piper TTS für
Sprachausgabe.

### Wo werden meine übersetzten Dateien gespeichert?

Standardmäßig neben dem Original mit dem Suffix `_translated_<src>_<tgt>`
(z. B. `report_translated_en_fr.docx`). Pro Funktion in
**Einstellungen → Allgemein → Übersetzungs-Speicherpfad** überschreiben.

### Wo werden meine Einstellungen gespeichert?

INI-Datei unter:

| OS | Pfad |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

API-Schlüssel liegen im OS-Schlüsselbund (nicht im INI). Der
Übersetzungsverlauf liegt in einer SQLite-DB im Datenverzeichnis.

### Wie werden meine Daten verarbeitet?

- **Local-first** — Text verlässt Ihre Maschine nie, es sei denn, Sie
  rufen einen Cloud-LLM-/OCR-/STT-/TTS-Dienst auf.
- **Keine Telemetrie** — die App phone-home't nicht. Die einzige
  ausgehende Anfrage, die die App selbst stellt, ist die optionale
  GitHub-Releases-Update-Prüfung (Toggle in
  **Einstellungen → Allgemein**); Cloud-Backends rufen nur ihre
  jeweiligen Anbieter auf.
- **API-Schlüssel** — gespeichert im OS-Schlüsselbund. Der
  Schlüsselbund-Fallback der Desktop-App ist eine Klartext-INI, wenn
  kein Schlüsselbund-Daemon verfügbar ist.

### Kann ich ein Google Doc / eine Notion-Seite übersetzen?

Nicht direkt. Exportieren Sie zuerst nach `.docx`, übersetzen Sie,
importieren Sie dann die übersetzte Datei zurück. Dasselbe für Notion
(Export als Markdown / HTML), Confluence (Export als `.docx`), etc.

## Modelle / Engines wählen

### Welches LLM-Modell soll ich verwenden?

Für die meisten Benutzer:

- **Jede Gemini-Flash-Variante** — kostenlose Stufe, schnell,
  überraschend gut. Für tägliche Übersetzungen verwenden. Namen sehen
  aus wie `gemini-2.5-flash`, `gemini-3-flash-preview`, etc., je
  nachdem, was aktuell verfügbar ist.
- **Jede Gemini-Pro-Variante** — Pay-per-Token, höhere Qualität. Für
  wichtige Dokumente verwenden (rechtlich, technisch, kundenorientiert).
- **Lokales Ollama** mit einem 7B-13B-Modell — wenn Sie Offline /
  Privatsphäre brauchen.

Die Modellauswahl pro Funktion bedeutet, dass Sie ein schnelles Modell
für Chat-ähnliche Übersetzungen verwenden und das teure für Dokumente
reservieren können.

### Welche OCR-Engine soll ich verwenden?

- **Tesseract** für sauberen gedruckten Text in den Hauptskripten.
  Kostenlos, offline, schnell.
- **EasyOCR** für nicht-lateinische Skripte (besonders CJK) und
  rauschende Bilder.
- **Google Cloud Vision** für Handschrift, gemischte Skripte und
  höchste Genauigkeit, wenn Sie zahlen können.

### Welche STT-Methode soll ich verwenden?

- **Whisper local** für Offline / Privatsphäre.
- **Soniox** für Mehr-Sprecher-Aufnahmen — Sprecherlabels machen den
  Round-Trip in Ihre SRT.
- **Google Cloud STT** für Telefonie / medizinisches Audio (deren
  Domänenmodelle sind gut).
- **Gemini Live** für Echtzeit-Speech-to-Speech-Übersetzung.

### Welches TTS-Backend?

- **Edge TTS** für kostenlose, hochwertige Stimmen.
- **ElevenLabs** für Premium / Branded / geklonte Stimmen.
- **Google Cloud TTS** für WaveNet-Stimmen in Long-Tail-Sprachen, wo
  Edge dünne Abdeckung hat.
- **Gemini TTS** für kostenlose natürliche prebuilt-Stimmen, die Ihren
  bestehenden Gemini-API-Schlüssel wiederverwenden.
- **Piper TTS**, wenn Sie **Offline / Air-Gapped**-Sprachausgabe
  brauchen. Trade-off: jede Sprache benötigt einen einmaligen
  Stimm-Download von ~25–60 MB über
  **Einstellungen → Stimme → Piper TTS → Stimmen jetzt herunterladen**,
  und 13 der 45 Sprachen der App haben keine Piper-Stimme (diese
  fallen still auf Edge TTS zurück).

## Workflow

### Wie übersetze ich einen ganzen Ordner?

Ziehen Sie den Ordner in die Drop-Zone von **Dokument übersetzen**.
Unterstützte Dateien darin (rekursiv) werden in die Warteschlange
gesetzt; alles andere wird stillschweigend übersprungen. Es gibt eine
Obergrenze von 100 Dateien pro Drop; größere Batches → in mehrere
Drops aufteilen.

### Kann ich Übersetzungen pausieren und fortsetzen?

Ja. Beenden Sie die App jederzeit — Pending- / Translating-Aufgaben
werden beim nächsten Start fortgesetzt. Pro-Aufgabe-Checkpointing
bedeutet, dass Seite 47 von 100 eines PDF beim Fortsetzen nicht erneut
gemacht wird.

### Kann ich eine Übersetzung von Hand bearbeiten?

Für **Text übersetzen** — ja, klicken Sie auf das rechte Panel und
tippen Sie. Die Bearbeitung wird automatisch im Verlaufseintrag
gespeichert.

Für **Dokument übersetzen** — öffnen Sie die übersetzte Datei in
Ihrem üblichen Editor (Word, LibreOffice, etc.) und bearbeiten Sie
dort. Die App macht keinen Round-Trip der Bearbeitungen zurück in den
Verlauf.

### Kann ich eine Liste von Strings massenweise übersetzen?

Verwenden Sie den CLI:

```bash
ait *.txt --target French
```

Oder für In-Process-Strings (z. B. UI-Strings aus Code extrahiert),
rufen Sie das MCP-Tool `translate_text` mit einer Liste auf, oder
verwenden Sie die Python-API direkt:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glossar

### Warum verwendet der LLM mein Glossar nicht?

Drei Dinge zu prüfen:

1. Das Set ist **aktiv** (Häkchen gesetzt).
2. Der Quellbegriff in Ihrem Glossar erscheint tatsächlich im
   Quelltext (die Pro-Aufruf-Komprimierung sendet dem LLM nur Einträge,
   die zum Batch-Text passen — spart Tokens, bedeutet aber, dass ein
   verschriebener Quellbegriff unsichtbar ist).
3. Das Modell ist stark genug — `flash-lite` ignoriert manchmal
   Hinweise, die `flash` und `pro` befolgen.

### Werden Glossarbegriffe akzent-unabhängig abgeglichen?

Ja. Sowohl Glossarsuche als auch das Suchfeld auf der Glossar-Seite
verwenden eine Normalisierungsfunktion, die Akzente und Groß-/Kleinschreibung
entfernt. So passen `cafe`, `Café` und `CAFE` alle zu einem Eintrag,
dessen Quelle `Café` ist.

## Privatsphäre

### Sammeln Sie Nutzungsdaten?

Nein. Die App hat kein Analytics-SDK. Die optionale Update-Prüfung
fragt einen einzelnen GitHub-Releases-Endpoint beim Start ab; sie ist
unter **Einstellungen → Allgemein** umschaltbar.

### Sind meine API-Schlüssel sicher?

Sie werden in Ihrem OS-Schlüsselbund gespeichert (Keychain auf macOS,
Credential Manager auf Windows, Secret Service auf Linux). Andere
Prozesse können sie ohne Ihre ausdrückliche Erlaubnis nicht lesen.
Der Fallback (wenn kein Schlüsselbund-Daemon verfügbar ist —
typischerweise Headless-Linux-Server) ist eine Klartext-INI unter dem
Konfigurationsverzeichnis Ihres Benutzers; in diesem Modus sind die
Schlüssel durch Dateiberechtigungen geschützt, aber nicht
kryptografisch verschlüsselt.
