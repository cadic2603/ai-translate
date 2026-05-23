---
description: Usa l'interfaccia a riga di comando ait per tradurre file headless — supporta PDF, documenti Office, sottotitoli e 45+ lingue da uno script o job CI.
---

# Riga di comando (`ait`)

Traduzione headless — la stessa pipeline dell'app desktop, nessun
display richiesto. Utile per CI, job batch, server e workflow scriptati.

## Avvio rapido

```bash
ait report.docx --target French
```

L'output atterra accanto alla sorgente come
`report_translated_<src>_<tgt>.docx`.

## Ricette comuni

### File multipli

```bash
ait *.pdf --target Japanese
```

L'espansione glob è compito della shell (Unix). Su Windows / `cmd.exe`,
elenca i file esplicitamente o usa PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Directory di output personalizzata

```bash
ait report.docx --target French --output ./translated/
```

La directory viene creata se non esiste. Se non può essere creata
(permesso negato, ecc.) ricevi un errore chiaro e codice di uscita 2 —
nessuna esecuzione parziale.

### Specificare la lingua sorgente

```bash
ait letter.txt --target German --source "English (US)"
```

Il matching della sorgente è case-insensitive. "Chinese" da solo
stampa un suggerimento:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Scegliere un modello specifico

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# O qualsiasi altro Provider:model_name registrato nel tab LLM dell'app desktop.
```

Il formato è strettamente `Provider:model_name`. Due punti mancanti
→ exit 2 con un messaggio chiaro invece di ricadere silenziosamente
sul modello Gemini di default.

### Opzioni Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` richiede OCR configurato (vedi
[Motori OCR](setup/ocr-engines.md)).

### Auto-conversione di formati legacy

```bash
ait old-doc.doc --target French --convert-legacy
```

La pipeline converte `.doc` → `.docx` prima (migliore fedeltà), traduce
la copia moderna, riconverte. Stessa cosa per `--convert-odf` e
`.odt` / `.ods` / `.odp`.

### Silenzioso / verboso

```bash
ait report.docx --target French --quiet      # solo errori
ait report.docx --target French --verbose    # firehose DEBUG completo
```

Modalità default stampa un banner e progresso per task su stderr;
dettagli completi (dump body HTTP, log retry) atterrano nella directory
di log dell'app della piattaforma indipendentemente dalla verbosità
della console (vedi
[Risoluzione problemi → Dove sono i log?](troubleshooting.md#where-are-the-logs)
per il percorso sul tuo OS).

### Elenca lingue supportate

```bash
ait --list-languages
```

Stampa tutte le 45 lingue supportate. Utile per piping in cicli shell.

### Versione

```bash
ait --version
# ait 0.1.0
```

## Codici di uscita

| Codice | Significato |
|---|---|
| `0` | Tutti i task riusciti |
| `2` | Errore di argomento (lingua sconosciuta, target mancante, modello malformato, output non scrivibile, estensione file non supportata) |
| `3` | LLM non configurato |
| `4` | Fallimento parziale (alcuni riusciti, altri no) |
| `5` | Tutti falliti |
| `130` | Interrotto (`Ctrl+C`) |

## Cancellazione

`Ctrl+C` una volta — cancellazione cooperativa. Il checkpoint del task
corrente viene salvato, la pipeline esce in modo pulito al successivo
boundary di polling.

`Ctrl+C` di nuovo — interruzione hard. Usa con parsimonia; file
parziali possono rimanere in stato a metà scrittura.

## Riferimento completo dei flag

```bash
ait --help
```

Mostra ogni flag con il suo default. Lo stesso contenuto riassunto qui:

| Flag | Default | Note |
|---|---|---|
| `--target / -t LANG` | _richiesto_ | Case-insensitive |
| `--source / -s LANG` | auto-rilevamento | Case-insensitive |
| `--output / -o DIR` | parent della sorgente | Creato se mancante |
| `--model / -m PROVIDER:MODEL` | default desktop | Formato strict |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | Richiede OCR configurato |
| `--translate-comments` | off | Commenti Office |
| `--translate-shapes` | off | Forme / caselle di testo |
| `--translate-notes` | off | Note dell'oratore PowerPoint |
| `--translate-sheet-names` | off | Tab fogli Excel |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → formato moderno |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | Mantieni voci cronologia dopo completamento |
| `--quiet / -q` | off | Solo errori sulla console |
| `--verbose / -v` | off | Firehose DEBUG |
| `--list-languages` | — | Stampa 45 lingue ed esce |
| `--version` | — | Stampa versione ed esce |

## Suggerimenti

!!! tip "Configura una volta, usa ovunque"
    Il CLI condivide le sue chiavi API e impostazioni con l'app
    desktop — configura tutto una volta nella GUI, poi automatizza
    con `ait` da lì.

!!! tip "Cache endpoint cold-start"
    Per ogni coppia `(endpoint, modello)`, la scelta
    chat-vs-responses-API e la variante di payload funzionante sono
    persistite in `llm_endpoint_cache.json` nella directory cache OS
    (`~/.cache/ai-translate/` su Linux,
    `~/Library/Caches/ai-translate/` su macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` su Windows). Le invocazioni
    CLI cold-start saltano interamente il probe di auto-rilevamento
    dopo la prima chiamata riuscita — utile quando si scriptano contro
    deployment Azure / vLLM / OpenRouter / Anthropic / DeepSeek che
    necessitano tuning di payload specifico al provider. La cache è
    sicura multi-processo e multi-thread (read-merge-write sotto RLock
    con rename atomico).

!!! tip "Stream di output"
    Modalità default stampa il banner, lista task in coda, e progresso
    per task su **stdout** (line-buffered per intersecarsi correttamente
    con gli errori); messaggi di errore e record di log vanno su
    **stderr**. Combina con `--quiet` per sopprimere stdout interamente
    per piping pulito:

    ```bash
    ait --list-languages | grep -i japanese    # dati su stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
