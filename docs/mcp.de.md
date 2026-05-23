---
description: Stellen Sie AI Translate als Model-Context-Protocol-Tools bereit, sodass Claude Desktop, Claude Code und andere MCP-Clients Text, Dateien und Audio übersetzen können.
---

# MCP-Server (`ait-mcp`)

Stellt die Übersetzungspipeline als **Model Context Protocol**-Tools
bereit, sodass KI-Agenten wie Claude Desktop und Claude Code sie direkt
ansteuern können — „Übersetze dieses PDF ins Französische" wird zu
einem Tool-Aufruf statt eines Copy-Paste.

## Was bereitgestellt wird

Neun Tools:

| Tool | Zweck |
|---|---|
| `translate_text` | Eine Liste von Strings übersetzen |
| `translate_document` | Datei-Übersetzungs-Tasks einreihen (gibt Task-IDs zurück) |
| `get_task_status` | Task-Status abfragen |
| `cancel_task` | Kooperative Stornierung laufender Tasks |
| `extract_image_text` | OCR oder LLM-Vision |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Text → MP3 / WAV |
| `query_glossary` | Glossar-Sets / -Einträge auflisten |
| `list_languages` | Alle 45 unterstützten Sprachen |

## Server starten

```bash
ait-mcp                       # stdio-Transport (Standard für Desktop-Agenten)
ait-mcp --transport sse       # Server-Sent Events für Web-Clients
ait-mcp --transport sse --port 9000
```

`stdio` ist das, was jeder MCP-Client erwartet, sofern Sie SSE nicht
explizit konfiguriert haben.

## Zu Claude Desktop hinzufügen

1. Öffnen Sie Claude Desktop → **Settings → Developer → Edit Config**
2. Fügen Sie diesen Eintrag unter `mcpServers` hinzu:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    Ersetzen Sie `/absolute/path/to/ai-translate` durch den Pfad zum geklonten Repo.

3. Beenden und öffnen Sie Claude Desktop neu. Das Hammer-Icon sollte
   jetzt „ai-translate" mit allen 9 Tools anzeigen. Versuchen Sie:

    > „Übersetze dieses PDF (`/home/me/report.pdf`) ins Französische —
    > speichere die Ausgabe neben der Quelle."

## Zu Claude Code hinzufügen

`~/.config/claude-code/mcp_servers.json` (oder `claude mcp add` aus
Claude Code heraus):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Starten Sie Claude Code neu. Dieselben 9 Tools werden aufrufbar.

## Zu anderen MCP-Clients hinzufügen

Jeder MCP-kompatible Client hat eine ähnliche Form:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (Standard)

Für HTTP- / SSE-basierte Clients führen Sie
`ait-mcp --transport sse --port 9000` aus und richten den Client auf
`http://localhost:9000` aus.

## Validierungsgarantien

Jedes Tool gibt bei Fehlern dieselbe Form zurück, damit Agenten
Fehler einheitlich behandeln können:

| Fehlerhafte Eingabe | Tool-Antwort |
|---|---|
| Unbekannte Sprache | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM nicht konfiguriert | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Nicht unterstützter Dateityp | `ValueError` mit erlaubten Erweiterungen |
| Fehlerhaft formatierter `model="…"` (ohne `:`) | `ValueError` statt stillschweigender Standard-Verwendung |
| Unbekannte Task-IDs in `cancel_task` | Im `unknown`-Array zurückgegeben — kein Fehler |
| FFmpeg fehlt bei `transcribe_audio` | `RuntimeError: FFmpeg is required…` (umgewickelt vom rohen `FFMPEG_NOT_FOUND`-Tag der Engine) |

Agenten, die diese Tools aufrufen, können sich auf diese Verträge verlassen.

## Nebenläufigkeit

`translate_document` führt die Pipeline in einem Daemon-Thread aus.
Jeder Batch erhält sein eigenes Cancel-Event, daher stört das Stornieren
eines Batches keinen anderen. Der MCP-Server verfolgt aktive Pipelines
in einer prozesslokalen Map (automatisch aufgeräumt, wenn die Pipeline
endet).

## Anwendungsfälle

- **„Übersetze die Docs dieser Codebase ins Vietnamesische"** — zeigen
  Sie dem Agenten den Docs-Ordner, er batcht `translate_document`-Aufrufe
  und ruft `get_task_status` ab, bis jeder fertig ist.
- **„Welche Sprachen unterstützt ihr?"** — der Agent ruft
  `list_languages` auf und liest die Antwort.
- **„Übersetze diese japanische Quittung"** — der Agent ruft
  `extract_image_text` auf das Foto, dann `translate_text` auf das
  Ergebnis.
- **„Erzeuge vietnamesische Untertitel für diese Zoom-Aufnahme"** —
  der Agent ruft `transcribe_audio` auf, um eine SRT in der
  Quellsprache zu erhalten, dann `translate_text` auf jeden Cue zum
  Lokalisieren, und stellt die SRT wieder zusammen.

!!! note "Video-Synchronisation ist kein MCP-Tool"
    Die vollständige STT → übersetzen → TTS → mux-Pipeline (die
    **Synchronisations**-Seite der Desktop-App) ist derzeit nur über
    die GUI verfügbar. Aus MCP können Sie das Äquivalent selbst mit
    `transcribe_audio` + `translate_text` + `synthesize_speech`
    zusammensetzen, müssen aber den timing-bewussten mux-Schritt
    (FFmpeg) extern handhaben.

## Tipps

!!! tip "Einmal einrichten, Agenten funktionieren überall"
    Der MCP-Server teilt API-Schlüssel und Einstellungen mit der
    Desktop-App und dem CLI. Konfigurieren Sie Ihren LLM / OCR / TTS
    einmal in der GUI, dann erbt jeder Agent, der mit `ait-mcp`
    spricht, dieselbe Einrichtung.

!!! tip "Cold-Start-Endpunkt-Cache"
    Für jedes `(Endpunkt, Modell)`-Paar werden die
    chat-vs-responses-API-Wahl und die funktionierende Payload-Variante
    in `llm_endpoint_cache.json` im OS-Cache-Verzeichnis persistiert
    (`~/.cache/ai-translate/` auf Linux,
    `~/Library/Caches/ai-translate/` auf macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` auf Windows). Frische
    `ait-mcp`-Prozesse überspringen den Auto-Detection-Probe nach dem
    ersten erfolgreichen Aufruf vollständig — Agenten, die den Server
    auf Anforderung spawnen, zahlen die Variant-Detection-Round-Trips
    nicht bei jeder Invokation. Der Cache ist multi-prozess- und
    multi-thread-sicher (read-merge-write unter RLock mit atomarem Rename).

!!! tip "Modellauswahl pro Tool"
    Die Tools `translate_text` und `translate_document` akzeptieren
    einen optionalen `model`-Parameter — Agenten können ein schnelles
    Modell für schnelle Runden und ein schwereres für Produktionsausgabe
    wählen, ohne dass der Benutzer die Desktop-App neu konfigurieren muss.

!!! warning "Lang laufende Pipelines"
    `translate_document` gibt sofort mit Task-IDs zurück. Es wird
    erwartet, dass der Agent `get_task_status` abfragt, bis jede Task
    `Done` oder `Failed` erreicht. Warten Sie nicht synchron innerhalb
    des Tool-Aufrufs; das riskiert das Auslösen des Timeouts des
    MCP-Clients.
