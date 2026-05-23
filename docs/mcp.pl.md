---
description: Udostępnij AI Translate jako narzędzia Model Context Protocol, aby Claude Desktop, Claude Code i inni klienci MCP mogli tłumaczyć tekst, pliki i audio.
---

# Serwer MCP (`ait-mcp`)

Udostępnia potok tłumaczenia jako narzędzia **Model Context Protocol**,
aby agenci AI tacy jak Claude Desktop i Claude Code mogli go napędzać
bezpośrednio — "Przetłumacz ten PDF na francuski" staje się wywołaniem
narzędzia, a nie kopiowaniem-wklejaniem.

## Dostępne narzędzia

Dziewięć narzędzi:

| Narzędzie | Cel |
|---|---|
| `translate_text` | Tłumaczenie listy stringów |
| `translate_document` | Kolejkowanie zadań tłumaczenia plików (zwraca ID zadań) |
| `get_task_status` | Pollowanie statusu zadania |
| `cancel_task` | Bezpieczne anulowanie zadań w toku |
| `extract_image_text` | OCR lub LLM vision |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Tekst → MP3 / WAV |
| `query_glossary` | Listowanie zestawów / wpisów glosariusza |
| `list_languages` | Wszystkie 45 obsługiwanych języków |

## Uruchom serwer

```bash
ait-mcp                       # transport stdio (domyślny dla agentów desktopowych)
ait-mcp --transport sse       # Server-Sent Events dla klientów webowych
ait-mcp --transport sse --port 9000
```

`stdio` to to, czego oczekuje każdy klient MCP, chyba że jawnie
podłączysz SSE.

## Dodaj do Claude Desktop

1. Otwórz Claude Desktop → **Settings → Developer → Edit Config**
2. Dodaj ten wpis pod `mcpServers`:

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

    Zastąp `/absolute/path/to/ai-translate` ścieżką sklonowanego repo.

3. Wyjdź i ponownie otwórz Claude Desktop. Ikona młotka powinna teraz
   pokazywać "ai-translate" ze wszystkimi 9 narzędziami. Spróbuj:

    > "Przetłumacz ten PDF (`/home/me/report.pdf`) na francuski —
    > zapisz wyjście obok źródła."

## Dodaj do Claude Code

`~/.config/claude-code/mcp_servers.json` (lub `claude mcp add` z
wnętrza Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Zrestartuj Claude Code. Te same 9 narzędzi staje się wywoływalne.

## Dodaj do innych klientów MCP

Każdy klient kompatybilny z MCP ma podobną postać:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (domyślnie)

Dla klientów opartych na HTTP / SSE uruchom
`ait-mcp --transport sse --port 9000` i wskaż klienta na
`http://localhost:9000`.

## Gwarancje walidacji

Każde narzędzie zwraca ten sam kształt przy błędach, aby agenci mogli
spójnie obsługiwać niepowodzenia:

| Złe wejście | Odpowiedź narzędzia |
|---|---|
| Nieznany język | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM nieskonfigurowany | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Nieobsługiwany typ pliku | `ValueError` listujący dozwolone rozszerzenia |
| Niepoprawny `model="…"` (bez `:`) | `ValueError` zamiast cicho używać domyślnego |
| Nieznane ID zadań w `cancel_task` | Zwracane w tablicy `unknown` — bez błędu |
| Brak FFmpeg w `transcribe_audio` | `RuntimeError: FFmpeg is required…` (przepakowane z gołego tagu `FFMPEG_NOT_FOUND` silnika) |

Agenci wywołujący te narzędzia mogą polegać na tych kontraktach.

## Współbieżność

`translate_document` uruchamia potok w wątku daemon. Każda partia
otrzymuje własne zdarzenie anulowania, więc anulowanie jednej partii
nie zakłóca innej. Serwer MCP śledzi aktywne potoki w mapie lokalnej
dla procesu (czyszczona automatycznie po zakończeniu potoku).

## Przypadki użycia

- **"Przetłumacz dokumentację tego codebase na wietnamski"** — wskaż
  agenta na folder dokumentów, on dzieli wywołania
  `translate_document` na partie i polluje `get_task_status`, aż
  każde z nich się zakończy.
- **"Jakie języki obsługujesz?"** — agent wywołuje `list_languages`,
  czyta odpowiedź.
- **"Przetłumacz ten japoński paragon"** — agent wywołuje
  `extract_image_text` na zdjęciu, potem `translate_text` na wyniku.
- **"Wygeneruj wietnamskie napisy do tego nagrania Zoom"** — agent
  wywołuje `transcribe_audio`, aby uzyskać SRT w języku źródłowym,
  potem `translate_text` na każdej sygnaturze, aby zlokalizować, i
  ponownie składa SRT.

!!! note "Dubbing wideo nie jest narzędziem MCP"
    Pełny potok STT → translate → TTS → mux (strona **Dubbing**
    aplikacji desktopowej) jest obecnie dostępny tylko przez GUI. Z
    MCP możesz skomponować odpowiednik samodzielnie z
    `transcribe_audio` + `translate_text` + `synthesize_speech`, ale
    będziesz musiał obsłużyć krok mux uwzględniający taktowanie
    (FFmpeg) na zewnątrz.

## Wskazówki

!!! tip "Konfiguruj raz, agenci działają wszędzie"
    Serwer MCP dzieli klucze API i ustawienia z aplikacją desktopową
    i CLI. Skonfiguruj swoje LLM / OCR / TTS raz w GUI, potem każdy
    agent rozmawiający z `ait-mcp` dziedziczy tę samą konfigurację.

!!! tip "Cache endpointów przy zimnym starcie"
    Dla każdej pary `(endpoint, model)` wybór API chat-vs-responses
    i działający wariant payloadu są utrzymywane w
    `llm_endpoint_cache.json` w katalogu cache OS
    (`~/.cache/ai-translate/` na Linuxie,
    `~/Library/Caches/ai-translate/` na macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` na Windows). Świeże procesy
    `ait-mcp` całkowicie pomijają sondę auto-detekcji po pierwszym
    udanym wywołaniu — agenci, którzy spawnują serwer na żądanie, nie
    płacą za rundy detekcji wariantu przy każdym wywołaniu. Cache jest
    bezpieczny wieloprocesowo i wielowątkowo (read-merge-write pod
    RLock z atomową zmianą nazwy).

!!! tip "Wybór modelu per-narzędzie"
    Narzędzia `translate_text` i `translate_document` akceptują
    opcjonalny parametr `model` — agenci mogą wybierać szybki model
    do szybkich zwrotów i cięższy do wyjścia produkcyjnego bez potrzeby
    rekonfiguracji aplikacji desktopowej przez użytkownika.

!!! warning "Długo działające potoki"
    `translate_document` natychmiast zwraca z ID zadań. Oczekuje się,
    że agent będzie pollował `get_task_status`, aż każde zadanie
    osiągnie `Done` lub `Failed`. Nie czekaj synchronicznie wewnątrz
    wywołania narzędzia; to ryzykuje uruchomienie timeoutu klienta
    MCP.
