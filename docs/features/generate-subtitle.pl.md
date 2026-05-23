---
description: Generuj napisy SRT, VTT, ASS lub SSA z dowolnego audio lub wideo — używa Whisper lub Google Cloud Speech-to-Text dla wysokiej jakości transkrypcji.
---

# Generuj napisy (STT)

Transkrybuj audio lub wideo do napisów z taktowaniem. Wychwytuje
mowę i emituje SRT / VTT / ASS / SSA — z opcjonalnym tłumaczeniem
w tym samym przebiegu.

## Czego potrzebujesz

- **FFmpeg** w `PATH` do dekodowania audio/wideo — zobacz
  [konfigurację FFmpeg](../setup/ffmpeg.md).
- Backend transkrypcji, jeden z:
    - **faster-whisper** — lokalny, offline, darmowy (domyślny; bez
      konfiguracji)
    - **Google Cloud Speech-to-Text** — chmurowy, płatny, dokładniejszy
      przy hałaśliwym audio. Zobacz
      [konfigurację Google Cloud](../setup/google-cloud.md).
    - **Soniox** — chmurowy, płatny, czasu rzeczywistego i
      diaryzacja mówcy. Zobacz
      [konfigurację Soniox](../setup/soniox.md).

## Krok po kroku

1. Kliknij **Generuj napisy** w pasku bocznym.
2. Upuść jeden lub więcej plików audio / wideo (`.mp3`, `.wav`,
   `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`).
3. Wybierz **język źródłowy** (język *mówiony* w audio) — pozostaw
   na `Auto-detect`, aby Whisper to wymyślił.
4. Wybierz **język docelowy** — wybierz `No translation` dla
   zwykłej transkrypcji lub jeden z 45 obsługiwanych języków, aby
   uzyskać przetłumaczoną transkrypcję w tym samym przebiegu.
5. Wybierz **format wyjściowy** (SRT / VTT / ASS / SSA).
6. Kliknij **Generuj** (lub `Ctrl+Enter`).
7. Obserwuj kolejkę. Kliknij **Otwórz** w wierszu po zakończeniu.

## Wybór formatu

| Format | Najlepszy do |
|---|---|
| **SRT** | Uniwersalny — prawie każdy odtwarzacz go obsługuje |
| **VTT** | Elementy HTML5 `<video>` `<track>` |
| **ASS / SSA** | Karaoke, stylizowane napisy, przepływy fansub |

Cztery formaty round-tripują przez ten sam parser, więc możesz
przełączać format wyjściowy przy ponownym tłumaczeniu bez utraty
taktowania.

## Rozmiar modelu Whisper

Przełącz w **Settings → Subtitle**:

| Model | Rozmiar | Szybkość | Dokładność |
|---|---|---|---|
| `tiny` | ~75 MB | bardzo szybki | niska |
| `base` (domyślny) | ~150 MB | szybki | przyzwoita |
| `small` | ~500 MB | średni | dobry |
| `medium` | ~1.5 GB | wolny | wysoka |
| `large` | ~3 GB | bardzo wolny | najlepszy |

Modele pobierają się przy pierwszym użyciu i są buforowane lokalnie.
Na wolnym połączeniu pierwsze uruchomienie wydaje się długie;
kolejne są szybkie.

## Porównanie metod STT

| Backend | Koszt | Online? | Diaryzacja mówcy | Języki |
|---|---|---|---|---|
| **Whisper** (lokalny) | Darmowy | Nie | Nie | 99 |
| **Google Cloud STT** | Płatny | Tak | Tak (model `latest_long`) | 125+ |
| **Soniox** | Płatny | Tak | Tak (etykiety mówcy per-token) | 60+ |

Przełącz w **Settings → Subtitle → STT method**.

## Wskazówki

- **Przycisk Stop** — przerwij partię w toku. Pliki w kolejce za
  aktywnym pozostają w kolejce; możesz wznowić później.
- **Re-generuj** — kliknij prawym przyciskiem wpis Done, aby
  uruchomić ponownie z innym formatem / językiem / metodą STT.
- **Długie audio** — Whisper dobrze obsługuje godziny audio;
  zaplanuj ~1 minutę przetwarzania na minutę audio dla modelu CPU
  `base`.

## Skróty

| Skrót | Akcja |
|---|---|
| `Ctrl+Enter` | Generuj |
| `Ctrl+O` | Przeglądaj |
| `Ctrl+F` | Skupienie na wyszukiwaniu historii |
