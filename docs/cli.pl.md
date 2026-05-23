---
description: Użyj interfejsu wiersza poleceń ait do bezgłowego tłumaczenia plików — obsługuje PDF-y, dokumenty Office, napisy i ponad 45 języków ze skryptu lub zadania CI.
---

# Wiersz poleceń (`ait`)

Bezgłowe tłumaczenie — ten sam potok co aplikacja desktopowa, brak
wymaganego wyświetlacza. Przydatne dla CI, zadań wsadowych, serwerów
i zautomatyzowanych przepływów pracy.

## Szybki start

```bash
ait report.docx --target French
```

Wyjście pojawia się obok źródła jako
`report_translated_<src>_<tgt>.docx`.

## Częste przepisy

### Wiele plików

```bash
ait *.pdf --target Japanese
```

Rozszerzanie Glob to zadanie shella (Unix). Na Windows / `cmd.exe`
wypisz pliki jawnie lub użyj PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Niestandardowy katalog wyjściowy

```bash
ait report.docx --target French --output ./translated/
```

Katalog jest tworzony, jeśli nie istnieje. Jeśli nie można go
utworzyć (odmowa uprawnień itd.), otrzymasz jasny błąd i kod wyjścia
2 — bez pół-uruchomienia.

### Określ język źródłowy

```bash
ait letter.txt --target German --source "English (US)"
```

Dopasowanie źródła nie rozróżnia wielkości liter. Samo "Chinese"
drukuje wskazówkę:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Wybierz konkretny model

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Lub dowolny inny Provider:model_name zarejestrowany w zakładce LLM aplikacji desktopowej.
```

Format jest ściśle `Provider:model_name`. Brak dwukropka → wyjście
2 z jasnym komunikatem zamiast cichego fallbacku do domyślnego
modelu Gemini.

### Opcje Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` wymaga skonfigurowanego OCR (zobacz
[Silniki OCR](setup/ocr-engines.md)).

### Auto-konwersja starych formatów

```bash
ait old-doc.doc --target French --convert-legacy
```

Potok najpierw konwertuje `.doc` → `.docx` (lepsza wierność),
tłumaczy nowoczesną kopię, konwertuje z powrotem. To samo dla
`--convert-odf` i `.odt` / `.ods` / `.odp`.

### Cichy / szczegółowy

```bash
ait report.docx --target French --quiet      # tylko błędy
ait report.docx --target French --verbose    # pełny firehose DEBUG
```

Tryb domyślny drukuje banner i postęp per-task na stderr; pełne
szczegóły (zrzuty HTTP body, logi powtórzeń) trafiają do katalogu
log aplikacji platformy niezależnie od poziomu szczegółowości
konsoli (zobacz
[Troubleshooting → Where are the logs?](troubleshooting.md#where-are-the-logs)
po ścieżkę dla swojego OS).

### Wymień obsługiwane języki

```bash
ait --list-languages
```

Drukuje wszystkie 45 obsługiwanych języków. Przydatne do potokowania
do pętli shellowych.

### Wersja

```bash
ait --version
# ait 0.1.0
```

## Kody wyjścia

| Kod | Znaczenie |
|---|---|
| `0` | Wszystkie zadania powiodły się |
| `2` | Błąd argumentu (nieznany język, brakujący cel, niepoprawny model, niezapisywalne wyjście, nieobsługiwane rozszerzenie pliku) |
| `3` | LLM nieskonfigurowany |
| `4` | Częściowe niepowodzenie (niektóre się powiodły, niektóre nie) |
| `5` | Wszystkie zawiodły |
| `130` | Przerwane (`Ctrl+C`) |

## Anulowanie

`Ctrl+C` raz — bezpieczne anulowanie (cooperative cancel). Checkpoint bieżącego
zadania jest zapisany, potok kończy się czysto przy następnej
granicy pollowania.

`Ctrl+C` ponownie — wymuszone przerwanie (strong interrupt). Używaj oszczędnie; częściowe
pliki mogą pozostać w stanie pół-zapisanym.

## Pełne odniesienie do flag

```bash
ait --help
```

Pokazuje każdą flagę z jej domyślną wartością. Ta sama treść
podsumowana tutaj:

| Flag | Default | Notes |
|---|---|---|
| `--target / -t LANG` | _wymagane_ | Nie rozróżnia wielkości liter |
| `--source / -s LANG` | auto-detect | Nie rozróżnia wielkości liter |
| `--output / -o DIR` | rodzic źródła | Tworzony, jeśli brak |
| `--model / -m PROVIDER:MODEL` | desktop default | Ścisły format |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | Wymaga skonfigurowanego OCR |
| `--translate-comments` | off | Komentarze Office |
| `--translate-shapes` | off | Kształty / pola tekstowe |
| `--translate-notes` | off | Notatki prezentera PowerPoint |
| `--translate-sheet-names` | off | Karty arkuszy Excel |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → format nowoczesny |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | Zachowaj wpisy historii po zakończeniu |
| `--quiet / -q` | off | Tylko błędy na konsoli |
| `--verbose / -v` | off | Firehose DEBUG |
| `--list-languages` | — | Drukuj 45 języków i wyjdź |
| `--version` | — | Drukuj wersję i wyjdź |

## Wskazówki

!!! tip "Konfiguruj raz, używaj wszędzie"
    CLI dzieli swoje klucze API i ustawienia z aplikacją desktopową —
    skonfiguruj wszystko raz w GUI, potem automatyzuj z `ait` stamtąd.

!!! tip "Cache endpointów przy zimnym starcie"
    Dla każdej pary `(endpoint, model)` wybór API chat-vs-responses
    i działający wariant payloadu są utrzymywane w
    `llm_endpoint_cache.json` w katalogu cache OS
    (`~/.cache/ai-translate/` na Linuxie,
    `~/Library/Caches/ai-translate/` na macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` na Windows). Wywołania CLI
    przy zimnym starcie całkowicie pomijają sondę auto-detekcji po
    pierwszym udanym wywołaniu — przydatne przy skryptowaniu wobec
    wdrożeń Azure / vLLM / OpenRouter / Anthropic / DeepSeek, które
    wymagają specyficznego dla dostawcy strojenia payloadu. Cache
    jest bezpieczny wieloprocesowo i wielowątkowo (read-merge-write
    pod RLock z atomową zmianą nazwy).

!!! tip "Strumienie wyjściowe"
    Tryb domyślny drukuje banner, listę zadań w kolejce i postęp
    per-task na **stdout** (buforowany liniowo, więc poprawnie
    przeplata się z błędami); komunikaty błędów i rekordy logów idą
    do **stderr**. Połącz z `--quiet`, aby całkowicie stłumić stdout
    dla czystego potokowania:

    ```bash
    ait --list-languages | grep -i japanese    # dane na stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
