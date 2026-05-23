---
description: Diagnostizieren Sie Probleme mit AI Translate — fehlende Schriftarten, FFmpeg-Fehler, LibreOffice-Konverter-Probleme, OCR-Setup-Fehler und LLM-API-Authentifizierung.
---

# Fehlerbehebung

Häufige Fehler, was sie bedeuten und wie man sie behebt.

## Setup-Fehler

### "LLM is not configured"

Sie haben noch keinen API-Schlüssel hinzugefügt. Öffnen Sie die
Desktop-App → **Einstellungen → LLM** → fügen Sie einen Schlüssel ein.
Siehe [LLM-Anbieter](setup/llm-providers.md) für die vollständige Anleitung.

### `AUTH_ERROR`

Der LLM-API-Schlüssel ist falsch oder abgelaufen.

- **Gemini** — generieren Sie einen neuen Schlüssel unter
  <https://aistudio.google.com/apikey>, fügen Sie ihn neu in
  **Einstellungen → LLM** ein.
- **Custom Provider** — überprüfen Sie, dass der Schlüssel gültig ist
  (curlen Sie den Endpoint manuell mit demselben
  `Authorization: Bearer …`-Header). Wenn der Endpoint umgezogen ist,
  aktualisieren Sie auch das Feld **API-Endpoint**.

### `QUOTA_ERROR`

Sie haben ein Limit der kostenlosen Stufe oder des kostenpflichtigen
Plans erreicht.

- **Gemini kostenlose Stufe** — das tägliche Anfrage-Quota variiert je
  Modell (siehe <https://ai.google.dev/gemini-api/docs/rate-limits>).
  Warten Sie einen Tag oder upgraden Sie auf kostenpflichtig.
- **OpenAI / andere** — prüfen Sie Ihr Billing-Dashboard. Viele
  Anbieter haben "Spend Caps", die Anfragen pausieren, wenn Sie sie
  erreichen.

### `MODEL_NOT_FOUND`

Der gewählte Modellname ist nicht verfügbar.

- Custom Providers — stellen Sie sicher, dass das Modell in der
  komma-separierten **Models**-Liste in **Einstellungen → LLM** steht.
- Eingebaute Gemini-Liste — wechseln Sie zu einem dokumentierten
  Modell in **Einstellungen → LLM → Standard-Gemini-Modell**.

### `VISION_NOT_SUPPORTED`

Sie haben ein Nicht-Vision-Modell gewählt und versucht, ein Bild /
gescanntes PDF zu übersetzen. Wechseln Sie zu einem Modell, dessen
Name `flash`, `pro` oder `vision` enthält (z. B. `gpt-4o` für OpenAI,
jede aktuelle Gemini Flash- oder Pro-Variante für Gemini).

## Audio- / Video-Fehler

### `FFMPEG_NOT_FOUND`

FFmpeg ist nicht im PATH. Siehe
[FFmpeg-Setup](setup/ffmpeg.md) für den Installationsbefehl Ihres OS.

Der MCP-Server umhüllt dies als: *"FFmpeg is required to decode this
audio/video file but is not installed or not on PATH."*

### Live-Seite zeigt keine Untertitel

- **Falsche Audioquelle** — öffnen Sie **Einstellungen → Live →
  Audioquelle** und stellen Sie sicher, dass es dem entspricht, was
  Sie wirklich wollen (Mikrofon / System / Beide).
- **Mikrofon stummgeschaltet** — prüfen Sie OS-Soundeinstellungen;
  die App verwendet Ihr Standard-Eingabegerät.
- **Systemaudio nicht eingerichtet** — siehe
  [Systemaudio-Aufnahme](setup/system-audio.md) für die macOS- /
  Windows-Loopback-Schritte.

### Sprachausgabe ist still / leer

- **ElevenLabs ohne Schlüssel** — die Voice-Seite zeigt einen
  freundlichen Pre-Flight-Dialog; falls durchgerutscht, kann die
  Datei leere Bytes enthalten. Prüfen Sie
  **Einstellungen → Service → ElevenLabs API key**.
- **Edge-TTS-Netzwerkfehler** — Edge TTS benötigt Internet; wenn Ihre
  Firewall `speech.platform.bing.com` blockiert, wechseln Sie zu
  ElevenLabs, Google Cloud TTS oder **Piper TTS** (vollständig offline).

### Dialog "Piper voice not installed"

Die Seiten Voice / Dubbing / Translate Text prüfen pre-flight, dass
die Piper-Stimme für Ihre Zielsprache auf der Festplatte ist, bevor
ein Worker startet. Falls nicht, sehen Sie ein Modal mit einem
**Einstellungen öffnen**-Button.

So laden Sie die Stimme herunter:

1. Klicken Sie im Dialog auf **Einstellungen öffnen** (oder öffnen Sie
   **Einstellungen → Stimme** manuell).
2. Stellen Sie sicher, dass **TTS-Methode** auf **Piper TTS** gesetzt ist.
3. Klicken Sie auf **Stimmen jetzt herunterladen**, um den
   Stimmen-Bibliotheks-Dialog zu öffnen.
4. Finden Sie die Zeile Ihrer Zielsprache, dann klicken Sie auf
   **Female voice** oder **Male voice** daneben. Stimmen sind
   ONNX-Dateien von ~25–60 MB, von HuggingFace heruntergeladen; einmal
   pro Sprache.
5. Schließen Sie den Dialog und führen Sie Ihren
   Übersetzungs-/Voice-/Dub-Job erneut aus.

Wenn Ihre Zielsprache nicht in der Liste ist, hat sie keine
Piper-Abdeckung — die Engine fällt zur Synthesezeit still auf Edge
TTS zurück, also müssen Sie tatsächlich nichts herunterladen. Die 13
Sprachen ohne Piper-Stimmen heute: Belarussisch, Bengalisch, Chinesisch
(Traditionell), Kroatisch, Estnisch, Hebräisch, Japanisch, Khmer,
Koreanisch, Litauisch, Malaiisch, Mongolisch, Thai.

Die Seite **Live-Übersetzung** ist der einzige Ort, der diesen Dialog
*nicht* anzeigt — einen Live-Stream mit einem Modal zu unterbrechen
wäre schlimmer als der Fallback, also gehen Fälle fehlender Stimmen
dort still zu Edge TTS.

## Dokumentübersetzungs-Fehler

### PDF-Übersetzung schlägt auf einer bestimmten Seite fehl

PDFs verwenden Pro-Seite-Checkpointing — erfolgreiche Seiten werden
nicht erneut bearbeitet. Die fehlgeschlagene Seite loggt einen Stack
in `app.log`; übliche Übeltäter:

- Die Seite ist ein **Scan ohne Textebene** und OCR ist nicht
  konfiguriert. Richten Sie **Einstellungen → OCR** ein (siehe
  [OCR-Engines](setup/ocr-engines.md)).
- Die Seite enthält **komplexes mathematisches Layout**, das der LLM
  zerstückelt hat. Versuchen Sie ein stärkeres Modell (eine Pro-Variante
  statt Flash).

### Office-Übersetzung zerstört Formatierung

- **Moderne Formate** (`.docx`, `.xlsx`, `.pptx`) — die Formatierung
  wird pro Run via HTML-Round-Trip erhalten. Wenn Sie verirrte
  `<b>`-Tags in der Ausgabe sehen, hat der LLM sie nicht geschlossen
  — erneut mit einem stärkeren Modell ausführen.
- **Legacy-Formate** (`.doc`, `.xls`, `.ppt`) — aktivieren Sie
  **Einstellungen → Übersetzung → Auto-convert legacy** für deutlich
  bessere Genauigkeit. Die Pipeline konvertiert zuerst zu `.docx`,
  übersetzt, konvertiert zurück.

### Übersetzungs-Warteschlange stoppt mitten im Batch

Beenden Sie die App und prüfen Sie die Datenbank:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

`Translating`-Zeilen, die seit Minuten nicht angefasst wurden,
bedeuten, dass ein Worker still abgestürzt ist. Starten Sie die
Desktop-App neu — sie setzt Pending- / Translating-Aufgaben beim
Start automatisch fort.

## Übergreifende Probleme

### Mehrere Dateien gleichzeitig werden still als eine übersetzt

Lassen Sie eine Datei nach der anderen fallen, ODER prüfen Sie die
Spalte **Files** im Warteschlangen-Header — sie sollte die Anzahl
zeigen, die Sie fallen gelassen haben. Die 100-Datei-Obergrenze zeigt
eine Benachrichtigung, wenn überschritten.

### Sidebar zeigt für immer einen Spinner

Zeigt an, dass ein Worker noch als laufend markiert ist. Beenden Sie
die App sauber (kein SIGKILL) — die Autouse-Cleanup-Hooks setzen die
Flags zurück. Wenn ein SIGKILL Zustand stecken gelassen hat, räumen
Sie die DB-Worker manuell auf:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Wo sind die Logs? {: #where-are-the-logs }

| OS | Pfad |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Logs erfassen immer DEBUG+ unabhängig von der Konsolen-Ausführlichkeit.
Die Konsolen-Ausgabe ist standardmäßig INFO+; übergeben Sie
`--verbose` an den CLI, um das vollständige Datei-Log auf stdout zu
spiegeln.

## Immer noch festgefahren?

- Siehe die [FAQ](faq.md) für Fragen auf Design-Ebene.
- Reichen Sie ein Issue ein bei
  <https://github.com/cadic2603/ai-translate/issues> mit: OS,
  Python-Version, dem fehlschlagenden Befehl, dem relevanten Ausschnitt
  von `app.log` und einer Beschreibung dessen, was Sie erwartet haben.
