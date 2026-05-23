---
description: "Dubbinguj filmy end-to-end: transkrybuj audio, przetłumacz napisy, syntetyzuj mowę w języku docelowym i miksuj z powrotem do oryginalnego wideo."
---

# Dubbing wideo

Pełny potok **STT → Translate → TTS → Mix**, który tworzy plik wideo
w innym języku z zastąpionym torem głosu. Oryginalne audio jest
porzucone; nowy tor dubbingu jest taktowany do napisów.

## Czego potrzebujesz

- **FFmpeg** w `PATH` — zobacz
  [konfigurację FFmpeg](../setup/ffmpeg.md).
- Backend STT (domyślnie lokalny Whisper, bez konfiguracji)
- Backend TTS — Edge TTS (domyślnie), ElevenLabs, Google Cloud TTS,
  Gemini TTS lub **Piper TTS** (całkowicie offline; głosy per-język
  pobierane raz przez **Settings → Voice → Piper TTS → Download
  voices now**)
- Skonfigurowany **LLM** dla kroku tłumaczenia

## Krok po kroku

1. Kliknij **Dubbing** w pasku bocznym.
2. Upuść jeden lub więcej plików wideo (`.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`).
3. Wybierz **język źródłowy** (język *mówiony* w wideo) i **język
   docelowy** do dubbingu.
4. Kliknij **Start Dubbing** (`Ctrl+Enter`).
5. Obserwuj postęp per-task w tabeli historii. Przechodzi przez
   cztery fazy:

| Faza | Zakres | Co się dzieje |
|---|---|---|
| **STT** | 5–25% | Transkrybowanie audio źródłowego |
| **Tłumaczenie** | 25–50% | LLM tłumaczy każdą linię napisów |
| **TTS** | 50–90% | Syntetyzowanie głosu w języku docelowym dla każdej linii |
| **Miks** | 90–100% | FFmpeg zastępuje ścieżkę audio |

6. Po zakończeniu kliknij **Otwórz** w wierszu, aby odtworzyć
   zdubbingowane wideo.

## Wyjścia

Dla każdego wejściowego wideo otrzymujesz cztery pliki w katalogu
wyjściowym:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← zdubbingowane wideo
movie_subtitle_en.srt               ← napisy w języku oryginalnym
movie_subtitle_fr.srt               ← przetłumaczone napisy
movie_voice_fr.mp3                  ← syntetyzowany tor głosu
```

## Wznawianie wstrzymanego / zawieszonego uruchomienia

Potok punktów kontrolnych po każdej fazie. Jeśli naciśniesz **Stop**,
wyjdziesz z aplikacji lub zawiesisz, naciśnięcie **Continue** w
wierszu wznawia od ostatnio zakończonej fazy — nie płacisz ponownie
za STT lub tłumaczenie, jeśli już zostały wykonane.

Kliknij prawym przyciskiem wpis Done / Failed dla tych opcji:

- **Continue** — wznów od ostatniego punktu kontrolnego bez ponownego
  pytania.
- **Re-dub** — ponownie otwórz wybór języka; jeśli wybierzesz nowy
  cel, punkty kontrolne tłumaczenia i TTS zostaną porzucone (nie
  płacisz ponownie za STT). Wybranie tego samego celu skutecznie
  uruchamia ponownie od ostatniego punktu kontrolnego, tak samo jak
  Continue.
- **Open** — odtwórz zdubbingowane wideo.

## Zastrzeżenia

!!! warning "Lip sync"
    Dubbing dopasowuje *znaczniki czasu* audio źródłowego, nie ruchy
    warg. Przetłumaczone linie znacznie dłuższe od oryginalnych będą
    brzmieć pospiesznie; znacznie krótsze linie pozostawią ciszę.
    W przypadku profesjonalnego dubbingu zwykle ręcznie re-czasujesz
    po tym przejściu — to przyszła funkcja.

!!! tip "Sprawdzenia pre-flight"
    Strona waliduje FFmpeg + klucze backendu TTS przed startem.
    Brakujący klucz → przyjazny dialog, brak pół-uruchomionego
    dubbingu. Z wybranym **Piper TTS**, sprawdza również, czy głos
    Piper per-język znajduje się na dysku; brakujący głos → modal
    z przyciskiem **Open Settings**, który przenosi cię do biblioteki
    głosów, więc nie spalasz czasu STT + tłumaczenia tylko po to, by
    zawieść w kroku TTS.

!!! tip "Zmiana języka docelowego"
    Przy re-targecie potok porzuca punkty kontrolne tłumaczenia +
    TTS (ich zawartość nie jest już ważna dla nowego języka), ale
    zachowuje punkt kontrolny STT — oszczędzasz koszt transkrypcji.

## Skróty

| Skrót | Akcja |
|---|---|
| `Ctrl+Enter` | Start Dubbing |
| `Ctrl+O` | Przeglądaj |
| `Ctrl+F` | Skupienie na wyszukiwaniu historii |
| `Ctrl+P` | Wstrzymaj aktywną kolejkę |
| `Ctrl+G` | Kontynuuj aktywną kolejkę |

`Ctrl+P` / `Ctrl+G` są tłumione, gdy pole tekstowe ma fokus, więc
nie kolidują z pisaniem.
