---
description: Połącz ElevenLabs z AI Translate dla wysokiej jakości neuronowego TTS — generuj voiceovery w 30+ językach z realistyczną, ekspresyjną mową.
---

# ElevenLabs (TTS)

Premium neuronowy text-to-speech. Używany przez strony
**[Generate Voice](../features/generate-voice.md)**,
**[Dubbing](../features/dubbing.md)** i
**[Live Translation](../features/live-translation.md)** gdy wybierasz
ElevenLabs jako metodę TTS.

## Pobierz klucz API

1. Zarejestruj się na <https://elevenlabs.io>
2. Otwórz <https://elevenlabs.io/app/settings/api-keys>
3. Kliknij **+ Create New Key**, nazwij go (np. "ai-translate"),
   skopiuj klucz (wygląda jak `sk_...`)

Darmowy poziom daje ci ~10 000 znaków / miesiąc, wystarczająco do
testów. Użycie produkcyjne zaczyna się od około $5/miesiąc.

## Konfiguruj w aplikacji

W **Settings → Service**:

1. Wklej klucz w **ElevenLabs API key** → **Save**
2. Wprowadź preferowane **Voice ID** w **Voice ID** (znajdź ID na
   <https://elevenlabs.io/app/voice-lab>; skopiuj ID z URL głosu).
   Pozostaw puste, aby ElevenLabs wybrał domyślny.

W **Settings → Voice**:

1. Ustaw **TTS method** na **ElevenLabs**
2. Wybierz **ElevenLabs model**:

    | Model | Najlepszy dla |
    |---|---|
    | `eleven_multilingual_v2` (domyślny) | Ogólne użycie, zbalansowana latencja/jakość |
    | `eleven_v3` | Najwyższa jakość (użyj dla dubbingów produkcyjnych) |
    | `eleven_flash_v2_5` | Najniższa latencja (użyj dla Live Translation) |

## Co zasila

| Page | Używaj ElevenLabs, gdy |
|---|---|
| **Generate Voice** | Chcesz voiceoverów premium z plików napisów |
| **Dubbing** | Chcesz wysokiej jakości toru dubbingu na przetłumaczonym wideo |
| **Live Translation** | Chcesz mówionego odtwarzania przetłumaczonych napisów w czasie rzeczywistym |

## Klonowanie głosu

ElevenLabs obsługuje niestandardowe klonowanie głosu (płatny plan).
Gdy sklonujesz głos na stronie ElevenLabs, wklej jego Voice ID w
**Settings → Service → Voice ID** i potok dubbingu / generowania
głosu go użyje.

## Zastrzeżenia

!!! warning "Sprawdzenie pre-flight"
    Strony Voice / Dubbing sprawdzają, że twój klucz ElevenLabs API
    jest ustawiony *przed* rozpoczęciem pracy. Jeśli brakuje, otrzymasz
    przyjazny dialog wskazujący na Settings, a nie pół-uruchomione
    zadanie.

!!! tip "Live mode fallbackuje automatycznie"
    Na stronie **Live Translation**, jeśli wybrałeś ElevenLabs, ale
    nie skonfigurowałeś klucza, aplikacja fallbackuje na **Edge TTS**
    (darmowe) i ogłasza fallback w etykiecie statusu, abyś mógł
    naprawić to, gdy będzie wygodnie.

!!! info "FFmpeg nadal wymagany"
    ElevenLabs zwraca bajty audio; aplikacja nadal używa FFmpeg do
    konwersji między formatami i łączenia taktowanych klipów w
    jeden plik. Zobacz [konfigurację FFmpeg](ffmpeg.md).

## Częste błędy

| Error | Prawdopodobna przyczyna |
|---|---|
| `AUTH_ERROR` | Zły / wygasły klucz API. Wklej ponownie w Settings → Service. |
| `QUOTA_ERROR` | Osiągnięto limit znaków poziomu darmowego lub wyczerpano płatny plan. |
| `MODEL_NOT_FOUND` | Wybrany model ElevenLabs nie jest już dostępny; wybierz inny w Settings → Voice. |
