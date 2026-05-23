---
description: "Częste pytania o AI Translate: obsługiwane formaty plików, funkcje darmowe vs płatne, użycie offline, wybory dostawców LLM i wybór silnika OCR."
---

# Często zadawane pytania

## Ogólne

### Czy działa offline?

Głównie tak. Konkretnie:

- **Tłumaczenie** wymaga LLM. Darmowe Gemini API jest online; **lokalny
  Ollama / LM Studio** przez ustawienia Custom Provider jest w pełni
  offline.
- **OCR** z **Tesseract** lub **EasyOCR** jest offline.
- **STT** z **Whisper** (domyślny) jest offline.
- **TTS** z **Edge TTS** (domyślny) jest online; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** są online (darmowe lub
  płatne); **Piper TTS** to w pełni offline neuronowe TTS — bez
  klucza, bez wywołań sieciowych po pobraniu głosu dla danego języka
  (~25–60 MB plik ONNX) przez **Settings → Voice → Piper TTS →
  Download voices now**.

Dla w pełni izolowanej konfiguracji: Custom Provider → lokalny LLM,
Tesseract lub EasyOCR dla OCR, Whisper dla STT i Piper TTS dla
wyjścia głosowego.

### Gdzie zapisywane są moje przetłumaczone pliki?

Domyślnie obok oryginału, z sufiksem `_translated_<src>_<tgt>` (np.
`report_translated_en_fr.docx`). Nadpisz per-funkcję w **Settings →
General → Translation storage path**.

### Gdzie przechowywane są moje ustawienia?

Plik INI w:

| OS | Ścieżka |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

Klucze API żyją w keychainie OS (nie w INI). Historia tłumaczeń żyje
w bazie SQLite w katalogu danych.

### Jak obsługiwane są moje dane?

- **Local-first** — tekst nigdy nie opuszcza twojej maszyny, chyba że
  wywołujesz usługę chmurową LLM / OCR / STT / TTS.
- **Brak telemetrii** — aplikacja nie dzwoni do domu. Jedyne wyjściowe
  zapytanie, które aplikacja sama wykonuje, to opcjonalne sprawdzanie
  aktualizacji GitHub-Releases (przełącznik w **Settings →
  General**); backendy chmurowe wywołują tylko swoich odpowiednich
  dostawców.
- **Klucze API** — przechowywane w keychainie OS. Fallback aplikacji
  desktopowej dla keychain to plaintext INI, gdy żaden daemon
  keychain nie jest dostępny.

### Czy mogę przetłumaczyć Google Doc / stronę Notion?

Nie bezpośrednio. Najpierw eksportuj do `.docx`, przetłumacz, potem
zaimportuj przetłumaczony plik z powrotem. To samo dla Notion
(eksport jako Markdown / HTML), Confluence (eksport jako `.docx`)
itd.

## Wybieranie modeli / silników

### Którego modelu LLM powinienem użyć?

Dla większości użytkowników:

- **Dowolny wariant Gemini Flash** — darmowy poziom, szybki, zaskakująco
  dobry. Używaj do codziennych tłumaczeń. Nazwy wyglądają jak
  `gemini-2.5-flash`, `gemini-3-flash-preview` itp., w zależności od
  tego, co jest aktualnie dostępne.
- **Dowolny wariant Gemini Pro** — pay-per-token, wyższa jakość.
  Używaj do ważnych dokumentów (prawnych, technicznych, dla klientów).
- **Lokalny Ollama** z modelem 7B-13B — gdy potrzebujesz offline /
  prywatności.

Wybór modelu per-funkcję oznacza, że możesz używać szybkiego modelu
do tłumaczenia w stylu czatu i zarezerwować droższy do dokumentów.

### Którego silnika OCR powinienem użyć?

- **Tesseract** dla czystego drukowanego tekstu w głównych skryptach.
  Darmowy, offline, szybki.
- **EasyOCR** dla skryptów nielatynowych (zwłaszcza CJK) i bardziej
  hałaśliwych obrazów.
- **Google Cloud Vision** dla pisma odręcznego, mieszanych skryptów i
  najwyższej dokładności, gdy możesz zapłacić.

### Której metody STT powinienem użyć?

- **Whisper lokalny** dla offline / prywatności.
- **Soniox** dla nagrań wielomówcowych — etykiety mówcy round-trip
  do twojego SRT.
- **Google Cloud STT** dla telefonii / audio medycznego (ich modele
  domenowe są dobre).
- **Gemini Live** dla tłumaczenia mowy na mowę w czasie rzeczywistym.

### Który backend TTS?

- **Edge TTS** dla darmowych, wysokiej jakości głosów.
- **ElevenLabs** dla premium / brandowanych / klonowanych głosów.
- **Google Cloud TTS** dla głosów WaveNet w językach long-tail, gdzie
  Edge ma cienkie pokrycie.
- **Gemini TTS** dla darmowych, naturalnych prebuildów głosów,
  wykorzystując twój istniejący klucz Gemini API.
- **Piper TTS**, gdy potrzebujesz wyjścia głosowego **offline /
  izolowanego**. Trade-off: każdy język wymaga jednorazowego pobrania
  głosu ~25–60 MB przez **Settings → Voice → Piper TTS → Download
  voices now**, a 13 z 45 języków aplikacji nie ma głosu Piper (te
  cicho fallbackują na Edge TTS).

## Workflow

### Jak przetłumaczyć cały folder?

Upuść folder do strefy upuszczania **Translate Document**. Obsługiwane
pliki wewnątrz (rekursywnie) są kolejkowane; wszystko inne jest
cicho pomijane. Jest limit 100 plików; większe partie → podziel na
wiele upuszczeń.

### Czy mogę zatrzymać i wznowić tłumaczenia?

Tak. Wyjdź z aplikacji w dowolnym momencie — zadania Pending /
Translating wznawiają się przy następnym uruchomieniu. Per-task
checkpointing oznacza, że strona PDF 47 z 100 nie jest ponownie
wykonywana, gdy wznawiasz.

### Czy mogę edytować tłumaczenie ręcznie?

Dla **Translate Text** — tak, kliknij prawy panel i pisz. Edycja
auto-zapisuje się do rekordu historii wpisu.

Dla **Translate Document** — otwórz przetłumaczony plik w swoim
zwykłym edytorze (Word, LibreOffice itp.) i edytuj tam. Aplikacja
nie roundtripuje edycji z powrotem do historii.

### Czy mogę masowo przetłumaczyć listę stringów?

Użyj CLI:

```bash
ait *.txt --target French
```

Lub dla stringów w procesie (np. stringów UI wyodrębnionych z kodu),
wywołaj narzędzie MCP `translate_text` z listą, lub użyj Python API
bezpośrednio:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glosariusz

### Dlaczego LLM nie używa mojego glosariusza?

Trzy rzeczy do sprawdzenia:

1. Zestaw jest **aktywny** (checkbox zaznaczony).
2. Termin źródłowy w twoim glosariuszu rzeczywiście pojawia się w
   tekście źródłowym (kompresja per-call wysyła do LLM tylko wpisy
   pasujące do tekstu partii — oszczędza tokeny, ale oznacza, że
   źle wpisany termin źródłowy jest niewidoczny).
3. Model jest wystarczająco silny — `flash-lite` czasami ignoruje
   wskazówki, które `flash` i `pro` honorują.

### Czy terminy glosariusza są dopasowywane bez uwzględniania akcentów?

Tak. Zarówno wyszukiwanie glosariusza, jak i pole wyszukiwania na
stronie Glossary używają funkcji normalizacji, która usuwa akcenty
i wielkość liter. Więc `cafe`, `Café` i `CAFE` wszystkie pasują do
wpisu, którego źródło to `Café`.

## Prywatność

### Czy zbieracie jakieś dane użycia?

Nie. Aplikacja nie ma SDK analityki. Opcjonalne sprawdzanie aktualizacji
poluje pojedynczy endpoint GitHub Releases przy starcie; jest
przełączalne w **Settings → General**.

### Czy moje klucze API są bezpieczne?

Są przechowywane w keychainie twojego OS (Keychain na macOS,
Credential Manager na Windows, Secret Service na Linux). Inne
procesy nie mogą ich odczytać bez twojej wyraźnej zgody. Fallback
(gdy żaden daemon keychain nie jest dostępny — zwykle bezgłowe
serwery Linux) to plaintext INI pod katalogiem konfiguracyjnym
twojego użytkownika; w tym trybie klucze są chronione uprawnieniami
pliku, ale nie są kryptograficznie szyfrowane.
