---
description: Konwertuj napisy na mówione audio z Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS lub offline Piper TTS — zachowuje taktowanie SRT dla generowania głosu jakości dubbingowej.
---

# Generuj głos (TTS)

Syntetyzuj pliki napisów (z taktowaniem) lub dowolny tekst do audio
MP3 / WAV. Pięć backendów TTS: Edge TTS (darmowy), ElevenLabs (wysoka
jakość), Google Cloud TTS, Gemini TTS (poziom darmowy) i Piper TTS
(offline).

## Czego potrzebujesz

- **FFmpeg** w `PATH` — zobacz
  [konfigurację FFmpeg](../setup/ffmpeg.md).
- Backend TTS, jeden z:
    - **Edge TTS** — darmowy, bez klucza, domyślny. Używa głosów
      chmurowych Microsoft Edge.
    - **ElevenLabs** — płatny, najwyższa jakość. Zobacz
      [konfigurację ElevenLabs](../setup/elevenlabs.md).
    - **Google Cloud TTS** — płatny, bardzo dobry. Zobacz
      [konfigurację Google Cloud](../setup/google-cloud.md).
    - **Gemini TTS** — poziom darmowy, naturalne prebuilty głosów.
      Wykorzystuje istniejący klucz Gemini API z zakładki LLM —
      bez dodatkowej konfiguracji.
    - **Piper TTS** — całkowicie offline neuronowe TTS. Bez klucza
      API, bez wywołań sieciowych — głosy to pliki ONNX o rozmiarze
      ~25–60 MB pobierane raz przez **Settings → Voice → Piper TTS
      → Download voices now**. 32 z 45 języków aplikacji ma głos
      Piper dzisiaj; języki bez pokrycia Piper cicho fallbackują
      na Edge TTS w czasie syntezy.

## Krok po kroku

1. Kliknij **Generuj głos** w pasku bocznym.
2. Upuść jeden lub więcej plików napisów `.srt` / `.vtt` / `.ass` /
   `.ssa`.
3. Wybierz **Język** (auto-wykrywany z nazwy pliku napisów, gdy to
   możliwe — np. `_translated_en_fr.srt` jest wykrywany jako
   francuski).
4. Wybierz **Płeć głosu** — `Female` lub `Male`.
5. Wybierz **Format wyjściowy** — `.mp3` (domyślnie) lub `.wav`.
6. Kliknij **Generuj** (lub `Ctrl+Enter`).
7. Kliknij **Open** w wierszu po zakończeniu — odtwarza się w
   twojej domyślnej aplikacji audio.

## Wyjście

Otrzymujesz pojedynczy plik audio z torami głosu umieszczonymi w
timestampie każdego napisu. Ciche luki wypełniają czas między cue,
więc audio pozostaje w synchronizacji z oryginalnym taktowaniem.

## Wybór backendu TTS

| Backend | Koszt | Głosy | Notatki |
|---|---|---|---|
| **Edge TTS** | Darmowy | Setki, wszystkie główne języki | Domyślny. Bez konfiguracji. |
| **ElevenLabs** | Płatny (~$5/mies. poziom wejściowy) | Premium głosy neuronowe, klonowanie głosu | Najwyższa jakość. Voice ID ustawione w Settings → Service. |
| **Google Cloud TTS** | Płatny (~$4/M znaków; 1 M darmowych / miesiąc) | Głosy WaveNet / Studio w 50+ językach | Silne głosy WaveNet dla języków europejskich. Domyślnie serwer wybiera głos na podstawie języka + płci. |
| **Gemini TTS** | Poziom darmowy (limity Developer API) | Naturalne prebuilty głosów w 24+ językach — `Kore` (domyślnie żeński) / `Puck` (domyślnie męski) | Wykorzystuje klucz Gemini API z zakładki LLM. Wyjście per-call ograniczone do ~30 s; długie teksty automatycznie dzielą się na granicach zdań. |
| **Piper TTS** | Darmowy, **offline** | Głosy neuronowe w 32 z 45 języków aplikacji | Bez klucza, bez sieci. Głos per-język pobierany na żądanie z **Settings → Voice → Piper TTS → Download voices now** (~25–60 MB każdy). Pre-flight wychwytuje brakujący głos przed startem pracy. |

Przełącz w **Settings → Voice → TTS method**.

## Specyfika Piper TTS

Piper to jedyny w pełni offline backend TTS w aplikacji. Kilka
rzeczy do wiedzenia:

- **Dialog biblioteki głosów** — otwórz przez **Settings → Voice →
  Piper TTS → Download voices now**. Każdy wiersz języka pokazuje
  przycisk pobierania `Female voice` i / lub `Male voice` (niektóre
  języki są jednopłciowe). Głosy pochodzą z katalogu HuggingFace
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- **Pokrycie** — 32 z 45 języków aplikacji ma głos Piper. 13 bez
  pokrycia (białoruski, bengalski, chiński (tradycyjny), chorwacki,
  estoński, hebrajski, japoński, khmerski, koreański, litewski,
  malajski, mongolski, tajski) cicho fallbackują na Edge TTS w
  czasie syntezy, więc synteza nigdy nie zawiedzie twardo na
  brakującym głosie.
- **Rozwiązywanie płci** — gdy wybierzesz `Female`, silnik najpierw
  próbuje głos żeński dla tego języka; jeśli istnieje tylko głos
  męski, używa go zamiast (i odwrotnie). Logowane na poziomie INFO.
- **Brama pre-flight** — przed uruchomieniem Voice strona
  sprawdza, czy głos Piper per-język jest na dysku. Jeśli brakuje,
  otrzymujesz modal z przyciskiem **Open Settings**, który
  prowadzi cię prosto do biblioteki głosów, więc możesz pobrać go
  bez utraty kolejki.

## Specyfika Gemini TTS

Gemini TTS używa `gemini-2.5-flash-preview-tts` przez Developer API.
Kilka rzeczy do wiedzenia:

- **Wybór głosu** jest dziś według płci — Female mapuje na `Kore`,
  Male na `Puck`. Oba to wyraźne, neutralne głosy, które działają
  w różnych językach, nie brzmiąc zbyt charakterystycznie.
- **Limit długości wyjścia** — każde wywołanie API Gemini zwraca
  najwyżej ~30 s mowy. Aplikacja dzieli tekst wejściowy poniżej
  `_GEMINI_TTS_MAX_BYTES` (~2000 bajtów ≈ 30 s) na granicach zdań,
  potem łączy fragmenty przez FFmpeg. Nie napotkasz obcięcia na
  normalnym tekście napisów.
- **Format audio** — Gemini emituje surowe PCM przy 24 kHz mono
  s16le; aplikacja transkoduje per-fragment do MP3 (lub WAV, jeśli
  wybrałeś), aby końcowy plik pasował do wybranego formatu wyjścia.
- **Vertex AI nie jest jeszcze obsługiwane dla TTS** — nawet jeśli
  twoja zakładka LLM jest skonfigurowana dla Vertex, Gemini TTS
  nadal potrzebuje klucza Developer API. Aplikacja podnosi
  `AUTH_ERROR` z góry, jeśli brakuje.

## Modele ElevenLabs

Trzy modele eksponowane:

| Model | Latencja | Jakość | Użyj do |
|---|---|---|---|
| `eleven_multilingual_v2` (domyślnie) | Średnia | Wysoka | Ogólne TTS |
| `eleven_v3` | Średnia | Najwyższa | Studio / produkcja |
| `eleven_flash_v2_5` | Niska | Dobra | Czasu rzeczywistego / tryb Live |

Skonfiguruj w **Settings → Voice → ElevenLabs model**.

## Wskazówki

!!! tip "Re-generuj"
    Kliknij prawym wiersz → **Re-generate**, aby zamienić płeć
    głosu / metodę TTS / format bez ponownego uruchamiania
    tłumaczenia.

!!! tip "Sprawdzenia pre-flight"
    Strona waliduje klucz ElevenLabs API (gdy wybrany) i dostępność
    FFmpeg przed startem. Zobaczysz przyjazny dialog, jeśli czegoś
    brakuje.

!!! warning "Stop jest atomowy"
    Naciśnij **Stop** podczas syntezy, a nie otrzymasz pół-zapisanego
    MP3 w katalogu wyjściowym — plik jest najpierw zapisywany w
    lokalizacji tymczasowej, a następnie przenoszony na miejsce
    tylko po sukcesie.

## Skróty

| Skrót | Akcja |
|---|---|
| `Ctrl+Enter` | Generuj |
| `Ctrl+O` | Przeglądaj |
| `Ctrl+F` | Skupienie wyszukiwania historii |
