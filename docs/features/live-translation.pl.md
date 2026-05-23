---
description: "Tłumaczenie mowy w czasie rzeczywistym: transkrybuj i tłumacz mikrofon lub dźwięk systemowy na żywo z backendami Whisper lub Soniox."
---

# Tłumaczenie na żywo

Napisy i tłumaczenia w czasie rzeczywistym z mikrofonu, dźwięku
systemowego lub obu — z opcjonalnym oknem overlay zawsze na wierzchu,
więc napisy znajdują się nad tym, co oglądasz.

## Co możesz z tym zrobić

- **Napisy spotkań na żywo** — dodawaj napisy do rozmowy Zoom /
  Meet / Teams w innym języku bez dołączania jako bot tłumacza.
- **Nauka języka w czasie rzeczywistym** — dodawaj napisy do treści
  w języku obcym (filmy, podcasty, wykłady) w swoim języku ojczystym
  jako ścieżce tłumaczenia.
- **Napisy systemowe** — przechwyć dźwięk systemowy, aby móc
  dodawać napisy do YouTube / Netflix / wszystkiego, co odtwarza się
  na twoich głośnikach.

## Czego potrzebujesz

- **FFmpeg** w `PATH` — zobacz
  [konfigurację FFmpeg](../setup/ffmpeg.md).
- Backend STT, jeden z:
    - **faster-whisper** — lokalny, offline, darmowy, domyślny
    - **Soniox** — chmurowy, płatny, diaryzacja mówcy w czasie
      rzeczywistym. Zobacz [konfigurację Soniox](../setup/soniox.md).

- Dla **przechwytywania dźwięku systemowego** odpowiedni backend
  per-OS jest auto-wybierany: Linux używa `parec` (PulseAudio /
  PipeWire), Windows używa natywnego WASAPI loopback (w większości
  przypadków bez dodatkowego oprogramowania), macOS używa
  `ffmpeg -f avfoundation` przeciwko wirtualnemu urządzeniu loopback
  (BlackHole / Loopback / itp.). Pojawia się inline banner ostrzeżenia
  z klikalnymi linkami instalacyjnymi, jeśli czegoś brakuje. Zobacz
  [Setup → System audio](../setup/system-audio.md) po pełne
  instrukcje instalacji per-OS.

## Krok po kroku

1. Kliknij **Tłumaczenie na żywo** w pasku bocznym.
2. Skonfiguruj raz w **Settings → Live**:

    - **Język źródłowy** (mówiony język)
    - **Język docelowy** (lub pozostaw pusty dla samej transkrypcji)
    - **Źródło dźwięku**: Mikrofon / Dźwięk systemowy / Oba
    - **Metoda STT**: Whisper / Soniox

3. Z powrotem na stronie Live kliknij **Start** (`Ctrl+Enter`).
4. Transkrypt wypełnia główny panel karta po karcie. Pływające okno
   **Overlay** również pokazuje napisy (przeciągnij je gdziekolwiek
   chcesz).
5. Kliknij **Stop**, aby zakończyć sesję.

## Widok transkryptu

Wybierz układ w pasku narzędzi:

- **Oba ułożone** — oryginał + tłumaczenie, jeden nad drugim
- **Oba obok siebie** — oryginał po lewej, tłumaczenie po prawej
- **Tylko oryginał** / **Tylko tłumaczenie**

Przyciski paska narzędzi używają sufiksów **`ON`** / **`OFF`** dla
stanu na pierwszy rzut oka — np. `TTS ON`, `TTS OFF`,
`Timestamps ON`, `Overlay OFF`.

Przełącz **timestampy** ikoną zegara. Przełącz **odtwarzanie TTS**
przetłumaczonych linii ikoną głośnika. Honoruje twój wybór
**Settings → Voice → TTS method** — Edge TTS (domyślnie),
ElevenLabs, Google Cloud TTS, Gemini TTS lub **Piper TTS**
(całkowicie offline). Z wybranym Piperem brakujące głosy per-język
**cicho fallbackują na Edge TTS** w środku strumienia — na tej
stronie nie ma modalnego pre-flightu, ponieważ blokowanie strumienia
na żywo dialogiem pobierania byłoby gorsze niż fallback.

## Okno overlay

Przeciągalne, zmienialne, zawsze na wierzchu okno narzędzia. Skróty:

| Skrót | Akcja |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Zmniejsz / zwiększ przezroczystość |
| `Ctrl+Arrow` | Przesuń overlay |
| `Ctrl+0` / `Ctrl+9` | Powiększ / zmniejsz |

Pozycja, rozmiar, przezroczystość i rozmiar czcionki utrzymują się
między sesjami.

### Synchronizacja na żywo z ustawieniami

Kontrolki rozmiaru czcionki i przezroczystości działają w obu
kierunkach: przeciągnięcie suwaka **Rozmiar czcionki** lub
**Przezroczystość** w **Ustawienia → Tłumaczenie na żywo →
Konfiguracja nakładki** aktualizuje otwartą nakładkę w czasie
rzeczywistym, a naciśnięcie `+` / `-` / `Ctrl+[` / `Ctrl+]`
wewnątrz nakładki aktualizuje suwaki w Ustawieniach. Nie ma
potrzeby ponownego otwierania nakładki.

### Symbol zastępczy stanu pustego

Przed przechwyceniem dźwięku nakładka wyświetla symbol zastępczy
("Naciśnij Start..." bezczynny / "Słucham..." po kliknięciu
Start), który odzwierciedla stan pusty głównego okna —
przełącznik pozostaje zsynchronizowany ze wskaźnikiem stanu.
Symbol zastępczy dostosowuje się do bieżącej szerokości ×
wysokości nakładki, aby pozostać czytelny przy dowolnym
rozmiarze okna.

### Tryb minimalnych napisów

Pole wyboru **Pokaż minimalne napisy** w Ustawienia →
Tłumaczenie na żywo → Konfiguracja nakładki ukrywa znaczniki
czasu i mówcy na nakładce, jednocześnie pozostawiając je
widoczne w głównym oknie. Przydatne, gdy nakładka jest
udostępniana publiczności (tryb prezentera / udostępnianie
ekranu), ale chcesz zachować pełne metadane w widoku
roboczym. Przełącznik dotyczy tylko nakładki — nie zmienia
preferencji "Etykiety mówcy" dla głównego okna.

## Zapisz transkrypt

Kliknij **Save Transcript**, aby wyeksportować sesję do pliku `.txt`
z timestampami, mówcami, oryginalnymi liniami i przetłumaczonymi
liniami.

## Wybór backendu STT

| Backend | Najlepszy do | Koszt | Latencja |
|---|---|---|---|
| **Whisper** (lokalny) | Offline, wrażliwy na prywatność | Darmowy | Średnia (~1 s po końcu zdania) |
| **Soniox** | Spotkania wielomówcowe | Płatny (~$0.005 / min) | Niska (czas rzeczywisty) |

## Zastrzeżenia

!!! warning "Wybór mikrofonu"
    Wejście mikrofonu zawsze używa **domyślnego urządzenia OS** —
    brak selektora w aplikacji (sounddevice eksponuje zbyt wiele
    wirtualnych pluginów ALSA, aby był użyteczny, a OS już posiada
    interfejs domyślnego mikrofonu). Ustaw preferowany mikrofon w
    ustawieniach dźwięku OS przed startem.

!!! warning "Ograniczenie kolejki TTS (Backpressure)"
    Kolejka TTS jest ograniczona do 3 najnowszych zdań — starsze
    audio w kolejce jest porzucane, jeśli synteza pozostaje w tyle.
    To utrzymuje mówione odtwarzanie blisko napisów na ekranie.

!!! tip "ElevenLabs bez klucza"
    Jeśli ustawiłeś metodę TTS na ElevenLabs, ale żaden klucz API
    nie jest skonfigurowany, strona Live automatycznie fallbackuje
    na Edge TTS i ogłasza fallback w etykiecie statusu.

## Skróty

| Skrót | Akcja |
|---|---|
| `Ctrl+Enter` | Start / Stop |
| `Ctrl+K` | Wyczyść log (z potwierdzeniem) |
| `Ctrl+[` / `Ctrl+]` | Dostosuj przezroczystość overlay |
