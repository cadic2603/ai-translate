---
description: Verwenden Sie die ait-Kommandozeilenschnittstelle, um Dateien headless zu übersetzen — unterstützt PDFs, Office-Dokumente, Untertitel und 45+ Sprachen aus einem Skript oder CI-Job.
---

# Kommandozeile (`ait`)

Headless-Übersetzung — dieselbe Pipeline wie die Desktop-App, kein
Display erforderlich. Nützlich für CI, Batch-Jobs, Server und
skriptgesteuerte Workflows.

## Schnellstart

```bash
ait report.docx --target French
```

Die Ausgabe landet neben der Quelle als
`report_translated_<src>_<tgt>.docx`.

## Häufige Rezepte

### Mehrere Dateien

```bash
ait *.pdf --target Japanese
```

Glob-Expansion ist Aufgabe der Shell (Unix). Auf Windows / `cmd.exe`
listen Sie Dateien explizit auf oder verwenden Sie PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Benutzerdefiniertes Ausgabeverzeichnis

```bash
ait report.docx --target French --output ./translated/
```

Das Verzeichnis wird erstellt, wenn es nicht existiert. Wenn es nicht
erstellt werden kann (Berechtigung verweigert, etc.), erhalten Sie
einen klaren Fehler und Exit-Code 2 — keine halbfertige Ausführung.

### Quellsprache angeben

```bash
ait letter.txt --target German --source "English (US)"
```

Quellabgleich ist case-insensitiv. Bloßes "Chinese" gibt einen Hinweis aus:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Bestimmtes Modell wählen

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Oder jeder andere Provider:model_name, der im LLM-Tab der Desktop-App registriert ist.
```

Format ist strikt `Provider:model_name`. Fehlender Doppelpunkt → Exit
2 mit klarer Nachricht statt stillschweigend auf das
Standard-Gemini-Modell zurückzufallen.

### Office-Optionen

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` benötigt konfiguriertes OCR (siehe
[OCR-Engines](setup/ocr-engines.md)).

### Auto-Konvertierung von Legacy-Formaten

```bash
ait old-doc.doc --target French --convert-legacy
```

Die Pipeline konvertiert `.doc` → `.docx` zuerst (bessere Genauigkeit),
übersetzt die moderne Kopie, konvertiert zurück. Dasselbe für
`--convert-odf` und `.odt` / `.ods` / `.odp`.

### Leise / ausführlich

```bash
ait report.docx --target French --quiet      # nur Fehler
ait report.docx --target French --verbose    # vollständiger DEBUG-Schwall
```

Der Standardmodus gibt einen Banner und Fortschritt pro Aufgabe an
stderr aus; volle Details (HTTP-Body-Dumps, Retry-Logs) landen im
App-Log-Verzeichnis der Plattform unabhängig von der Konsolen-Ausführlichkeit
(siehe
[Fehlerbehebung → Wo sind die Logs?](troubleshooting.md#where-are-the-logs)
für den Pfad auf Ihrem OS).

### Unterstützte Sprachen auflisten

```bash
ait --list-languages
```

Gibt alle 45 unterstützten Sprachen aus. Nützlich zum Pipen in Shell-Schleifen.

### Version

```bash
ait --version
# ait 0.1.0
```

## Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | Alle Aufgaben erfolgreich |
| `2` | Argumentfehler (unbekannte Sprache, fehlendes Ziel, fehlerhaft formatiertes Modell, nicht beschreibbare Ausgabe, nicht unterstützte Dateiendung) |
| `3` | LLM nicht konfiguriert |
| `4` | Teilweiser Fehler (einige erfolgreich, einige nicht) |
| `5` | Alle fehlgeschlagen |
| `130` | Unterbrochen (`Ctrl+C`) |

## Abbruch

`Ctrl+C` einmal — kooperativer Abbruch. Der Checkpoint der aktuellen
Aufgabe wird gespeichert, die Pipeline beendet sauber an der nächsten
Polling-Grenze.

`Ctrl+C` erneut — harter Interrupt. Sparsam verwenden; teilweise
Dateien können in einem halbfertigen Zustand zurückbleiben.

## Vollständige Flag-Referenz

```bash
ait --help
```

Zeigt jedes Flag mit Standardwert. Derselbe Inhalt hier zusammengefasst:

| Flag | Standard | Hinweise |
|---|---|---|
| `--target / -t LANG` | _erforderlich_ | Case-insensitiv |
| `--source / -s LANG` | Auto-Erkennung | Case-insensitiv |
| `--output / -o DIR` | Quell-Elternverzeichnis | Wird erstellt, falls fehlend |
| `--model / -m PROVIDER:MODEL` | Desktop-Standard | Striktes Format |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | aus | Benötigt konfiguriertes OCR |
| `--translate-comments` | aus | Office-Kommentare |
| `--translate-shapes` | aus | Formen / Textfelder |
| `--translate-notes` | aus | PowerPoint-Sprechernotizen |
| `--translate-sheet-names` | aus | Excel-Blatt-Tabs |
| `--convert-legacy` | aus | `.doc`/`.xls`/`.ppt` → modernes Format |
| `--convert-odf` | aus | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | aus | Verlaufseinträge nach Abschluss behalten |
| `--quiet / -q` | aus | Nur Fehler auf der Konsole |
| `--verbose / -v` | aus | DEBUG-Schwall |
| `--list-languages` | — | Gibt 45 Sprachen aus und beendet |
| `--version` | — | Gibt Version aus und beendet |

## Tipps

!!! tip "Einmal einrichten, überall verwenden"
    Der CLI teilt seine API-Schlüssel und Einstellungen mit der
    Desktop-App — alles einmal in der GUI einrichten, dann mit `ait`
    automatisieren.

!!! tip "Cold-Start-Endpunkt-Cache"
    Für jedes `(Endpunkt, Modell)`-Paar werden die
    chat-vs-responses-API-Wahl und die funktionierende Payload-Variante
    in `llm_endpoint_cache.json` im OS-Cache-Verzeichnis persistiert
    (`~/.cache/ai-translate/` auf Linux,
    `~/Library/Caches/ai-translate/` auf macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` auf Windows). Cold-Start
    CLI-Aufrufe überspringen den Auto-Detection-Probe nach dem ersten
    erfolgreichen Aufruf vollständig — nützlich beim Skripten gegen
    Azure / vLLM / OpenRouter / Anthropic / DeepSeek-Bereitstellungen,
    die anbieterspezifisches Payload-Tuning benötigen. Der Cache ist
    multi-prozess- und multi-thread-sicher (read-merge-write unter
    RLock mit atomarem Rename).

!!! tip "Ausgabe-Streams"
    Standardmodus gibt Banner, in der Warteschlange befindliche Aufgaben
    und Fortschritt pro Aufgabe an **stdout** aus (line-buffered, damit
    es korrekt mit Fehlern verschachtelt); Fehlermeldungen und
    Log-Einträge gehen an **stderr**. Kombinieren Sie mit `--quiet`,
    um stdout für sauberes Piping vollständig zu unterdrücken:

    ```bash
    ait --list-languages | grep -i japanese    # Daten auf stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
