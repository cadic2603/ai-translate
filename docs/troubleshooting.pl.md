---
description: Diagnozuj problemy AI Translate — brakujące czcionki, błędy FFmpeg, problemy z konwerterem LibreOffice, niepowodzenia konfiguracji OCR i autoryzację LLM API.
---

# Rozwiązywanie problemów

Częste błędy, co oznaczają i jak je naprawić.

## Błędy konfiguracji

### "LLM is not configured"

Nie dodałeś jeszcze klucza API. Otwórz aplikację desktopową →
**Settings → LLM** → wklej klucz. Zobacz [Dostawcy LLM](setup/llm-providers.md)
po pełny przewodnik.

### `AUTH_ERROR`

Klucz LLM API jest błędny lub wygasł.

- **Gemini** — wygeneruj nowy klucz na
  <https://aistudio.google.com/apikey>, wklej ponownie w
  **Settings → LLM**.
- **Niestandardowy dostawca** — zweryfikuj, że klucz jest poprawny
  (curl endpoint ręcznie z tym samym nagłówkiem
  `Authorization: Bearer …`). Jeśli endpoint się zmienił,
  zaktualizuj również pole **API endpoint**.

### `QUOTA_ERROR`

Osiągnąłeś limit darmowego poziomu lub planu płatnego.

- **Darmowy poziom Gemini** — dzienny limit zapytań różni się dla
  każdego modelu (zobacz
  <https://ai.google.dev/gemini-api/docs/rate-limits>). Poczekaj
  dzień lub przejdź na płatny.
- **OpenAI / inni** — sprawdź swój panel rozliczeniowy. Wielu
  dostawców ma "spend caps", które wstrzymują zapytania, gdy je
  osiągasz.

### `MODEL_NOT_FOUND`

Wybrana nazwa modelu jest niedostępna.

- Niestandardowi dostawcy — upewnij się, że model znajduje się na
  liście **Models** oddzielonej przecinkami w **Settings → LLM**.
- Wbudowana lista Gemini — przełącz na udokumentowany model w
  **Settings → LLM → Default Gemini model**.

### `VISION_NOT_SUPPORTED`

Wybrałeś model bez vision i próbowałeś przetłumaczyć obraz / zeskanowany
PDF. Przełącz na model, którego nazwa zawiera `flash`, `pro` lub
`vision` (np. `gpt-4o` dla OpenAI, dowolny aktualny wariant Gemini
Flash lub Pro dla Gemini).

## Błędy audio / wideo

### `FFMPEG_NOT_FOUND`

FFmpeg nie jest na PATH. Zobacz [konfigurację FFmpeg](setup/ffmpeg.md)
po polecenie instalacji dla swojego OS.

Serwer MCP przepakowuje to jako: *"FFmpeg is required to decode this
audio/video file but is not installed or not on PATH."*

### Strona Live nie pokazuje napisów

- **Złe źródło dźwięku** — otwórz **Settings → Live → Audio source**
  i upewnij się, że odpowiada temu, co rzeczywiście chcesz
  (Microphone / System / Both).
- **Mikrofon wyciszony** — sprawdź ustawienia dźwięku OS; aplikacja
  używa domyślnego urządzenia wejściowego.
- **Dźwięk systemowy nie jest skonfigurowany** — zobacz
  [przechwytywanie dźwięku systemowego](setup/system-audio.md) po
  kroki loopback dla macOS / Windows.

### Wyjście głosowe jest ciche / puste

- **ElevenLabs bez klucza** — strona Voice pokazuje przyjazny
  dialog pre-flight; jeśli przemknął, plik może być pustymi bajtami.
  Sprawdź **Settings → Service → ElevenLabs API key**.
- **Błąd sieci Edge TTS** — Edge TTS wymaga internetu; jeśli
  twoja firewall blokuje `speech.platform.bing.com`, przełącz na
  ElevenLabs, Google Cloud TTS lub **Piper TTS** (całkowicie
  offline).

### Dialog "Piper voice not installed"

Strony Voice / Dubbing / Translate Text pre-flight, że głos Piper
dla twojego języka docelowego znajduje się na dysku przed
uruchomieniem jakiegokolwiek workera. Jeśli nie ma, zobaczysz
modal z przyciskiem **Open Settings**.

Aby pobrać głos:

1. Kliknij **Open Settings** w dialogu (lub otwórz **Settings →
   Voice** ręcznie).
2. Upewnij się, że **TTS method** jest ustawione na **Piper TTS**.
3. Kliknij **Download voices now**, aby otworzyć dialog biblioteki
   głosów.
4. Znajdź wiersz swojego języka docelowego, następnie kliknij
   **Female voice** lub **Male voice** obok niego. Głosy to pliki
   ONNX o rozmiarze ~25–60 MB pobierane z HuggingFace; jednorazowo
   na język.
5. Zamknij dialog i uruchom ponownie zadanie tłumaczenia / głosu /
   dubbingu.

Jeśli twojego języka docelowego nie ma na liście, nie ma pokrycia
Piper — silnik cicho fallbackuje na Edge TTS w czasie syntezy, więc
nie musisz nic pobierać. 13 języków bez głosów Piper dzisiaj:
białoruski, bengalski, chiński (tradycyjny), chorwacki, estoński,
hebrajski, japoński, khmerski, koreański, litewski, malajski,
mongolski, tajski.

Strona **Live Translation** to jedyne miejsce, które *nie* pokaże
tego dialogu — przerwanie strumienia na żywo modałem byłoby
gorsze niż fallback, więc przypadki brakującego głosu tam są
cicho kierowane do Edge TTS.

## Błędy tłumaczenia dokumentów

### Tłumaczenie PDF zawodzi na konkretnej stronie

PDF-y używają checkpointów na stronę — udane strony nie są
ponownie wykonywane. Strona, która zawiodła, loguje stos do
`app.log`; częste przyczyny:

- Strona to **skan bez warstwy tekstowej** i OCR nie jest
  skonfigurowany. Skonfiguruj **Settings → OCR** (zobacz
  [silniki OCR](setup/ocr-engines.md)).
- Strona zawiera **złożony układ matematyczny**, który LLM
  zniekształcił. Spróbuj silniejszego modelu (wariant Pro
  zamiast Flash).

### Tłumaczenie Office łamie formatowanie

- **Nowoczesne formaty** (`.docx`, `.xlsx`, `.pptx`) — formatowanie
  jest zachowane per-run przez HTML round-trip. Jeśli widzisz
  porzucone tagi `<b>` w wyjściu, LLM ich nie zamknął — uruchom
  ponownie z silniejszym modelem.
- **Stare formaty** (`.doc`, `.xls`, `.ppt`) — włącz **Settings →
  Translation → Auto-convert legacy** dla znacznie lepszej
  wierności. Potok najpierw konwertuje do `.docx`, tłumaczy,
  konwertuje z powrotem.

### Kolejka tłumaczenia zatrzymuje się w środku partii

Wyjdź z aplikacji i sprawdź bazę danych:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

Wiersze `Translating`, które nie były dotknięte od kilku minut,
oznaczają, że worker cicho się zawiesił. Uruchom ponownie aplikację
desktopową — automatycznie wznawia zadania Pending / Translating
przy starcie.

## Problemy ogólne

### Wiele plików na raz cicho tłumaczy się jako jeden

Upuszczaj jeden plik na raz LUB sprawdź kolumnę **Files** w nagłówku
kolejki — powinna pokazywać liczbę, którą upuszczasz. Limit 100
plików pokazuje powiadomienie po przekroczeniu.

### Pasek boczny pokazuje spinner w nieskończoność

Wskazuje, że worker jest nadal oznaczony jako działający. Wyjdź z
aplikacji czysto (bez SIGKILL) — autouse cleanup hooks resetują
flagi. Jeśli SIGKILL pozostawił stan zacięty, wyczyść workerów DB
ręcznie:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Gdzie są logi?

| OS | Ścieżka |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Logi zawsze przechwytują DEBUG+ niezależnie od poziomu szczegółowości
konsoli. Wyjście konsoli to domyślnie INFO+; przekaż `--verbose` do
CLI, aby odzwierciedlać pełny log pliku na stdout.

## Wciąż utknąłeś?

- Zobacz [FAQ](faq.md) po pytania na poziomie projektowym.
- Zgłoś problem na <https://github.com/cadic2603/ai-translate/issues> z:
  OS, wersja Python, polecenie, które zawiodło, odpowiedni fragment
  `app.log` i opis tego, czego oczekiwałeś.
