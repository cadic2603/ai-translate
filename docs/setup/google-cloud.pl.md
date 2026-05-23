---
description: Połącz Google Cloud z AI Translate dla Vision OCR, Speech-to-Text i Text-to-Speech — skonfiguruj klucz API i włącz odpowiednie usługi.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Pojedynczy klucz Google Cloud API zasila trzy opcjonalne backendy:

- **Vision OCR** — płatny silnik OCR (1000 darmowych / miesiąc)
- **Speech-to-Text v1** — płatny STT (60 minut / miesiąc darmowych)
- **Text-to-Speech v1** — płatny TTS (1 M znaków / miesiąc darmowych
  dla WaveNet)

Musisz włączyć tylko APIs, których faktycznie używasz.

## Pobierz klucz API

1. [Utwórz projekt Google Cloud](https://console.cloud.google.com/projectcreate)
2. Otwórz bibliotekę API: <https://console.cloud.google.com/apis/library>
3. Włącz dowolne z:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Utwórz klucz API](https://console.cloud.google.com/apis/credentials):
   kliknij **+ Create Credentials → API key**
5. Skopiuj klucz (wygląda jak `AIza...`).

!!! tip "Ogranicz klucz"
    Na stronie szczegółów klucza API, w sekcji **API restrictions**,
    ogranicz klucz tylko do APIs, które włączyłeś. W ten sposób
    wyciekły klucz nie może gromadzić rachunków za usługi, których
    nie zamierzałeś używać.

## Konfiguruj w aplikacji

W **Settings → Service**:

1. Wklej w **Google Cloud API key** → **Save**

Ten pojedynczy klucz jest teraz dostępny dla wszystkich trzech
usług Google.

## Włącz każdą usługę

### Vision OCR

W **Settings → OCR → OCR method = Google Cloud OCR**.

To wszystko — będzie używał tego samego klucza z Service.

### Speech-to-Text

W **Settings → Subtitle → STT method = Google Cloud** (dla stron
Subtitle / Voice) lub **Settings → Live → STT method = Google
Cloud** (dla strony Live).

W **Settings → Subtitle → Google STT model**, wybierz model
rozpoznawania:

| Model | Najlepszy dla |
|---|---|
| `latest_long` (domyślny) | Długie audio (wywiady, wykłady) |
| `latest_short` | Komendy głosowe, krótkie frazy |
| `phone_call` | Audio telefoniczne (8 kHz) |
| `medical_dictation` / `medical_conversation` | Audio medyczne |

### Text-to-Speech

W **Settings → Voice → TTS method = Google Cloud TTS**.

Domyślnie serwer wybiera głos na podstawie języka i płci — to,
czego potrzebuje większość użytkowników. Przypinanie konkretnego
głosu Google (np. `en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`) jest
obsługiwane przez silnik, ale nie jest jeszcze eksponowane jako
pole Settings; można je ustawić, edytując `voice/google_tts_voice_name`
bezpośrednio w `settings.ini`. ID głosów są wymienione na
<https://cloud.google.com/text-to-speech/docs/voices>.

## Częste błędy

| Error | Prawdopodobna przyczyna |
|---|---|
| `AUTH_ERROR` | Zły / wygasły klucz. Wklej ponownie w Settings → Service. |
| `API not enabled` | Nie włączyłeś konkretnego API (Vision / Speech / TTS) na tym projekcie Cloud. |
| `QUOTA_ERROR` | Osiągnięto limit poziomu darmowego dla tego API. Poczekaj lub zaktualizuj rozliczenia. |
| `INVALID_ARGUMENT_ERROR` | Nazwa głosu nie istnieje w wybranym języku. |

## Ochrona kosztów

!!! warning
    Wszystkie trzy APIs Google są post-paid — gdy przekroczysz
    poziom darmowy, zaczynasz być rozliczany bez przerwy. Ustaw
    [alert budżetu](https://console.cloud.google.com/billing/budgets)
    na projekcie Cloud przed wykonaniem pracy o dużej objętości.
