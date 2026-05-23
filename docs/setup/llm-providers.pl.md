---
description: "Skonfiguruj dostawców LLM dla tłumaczenia: Google Gemini (zalecane), endpointy kompatybilne z OpenAI lub dowolny niestandardowy dostawca z kluczem API."
---

# Dostawcy LLM

Potok tłumaczenia wywołuje Large Language Model dla rzeczywistego
tłumaczenia. Możesz skonfigurować jednego lub wielu; selektor modelu
per-funkcję pozwala każdej stronie używać innego.

## Google Gemini (zalecany dla pierwszej konfiguracji)

Darmowy poziom jest hojny i wystarczający dla większości użytku
osobistego.

1. Idź do <https://aistudio.google.com/apikey>
2. Kliknij **Create API key** (zaloguj się swoim kontem Google)
3. Skopiuj klucz (wygląda jak `AIza...`)
4. W aplikacji desktopowej: **Settings → LLM → Gemini API key** →
   wklej → **Save**
5. Wybierz domyślny model w rozwijanym menu **Default Gemini model**.
   Linia Google ma tendencję wyglądać jak:

    - Warianty **Flash** (np. `gemini-2.5-flash`) — szybkie, hojny
      darmowy poziom, dobra jakość. Zalecany punkt startowy.
    - Warianty **Pro** — wolniejsze, wyższa jakość, droższe.
    - **Flash-lite** — najszybszy, najtańszy, niższa jakość.

    Dokładne dostępne nazwy modeli zależą od tego, co Google
    udostępniło na twoim koncie; wybierz taki, którego nazwa
    zawiera `flash`, dla zbalansowanego domyślnego.

Gotowe. Klucz jest przechowywany w keychainie OS, nie w postaci
zwykłego tekstu.

### Tryb Vertex AI (korporacyjny)

W bloku konfiguracji Gemini para radio pozwala ci przełączyć z
**Developer API** na **Vertex AI** — te same modele Gemini,
rozliczane przez twoje konto GCP, z kontrolami na poziomie
organizacji (VPC-SC, logi audytu, regionalna rezydencja danych).

1. W **Settings → LLM** przełącz radio Gemini z **Developer API**
   na **Vertex AI**
2. Wypełnij:
    - **Project** — twój ID projektu GCP
    - **Location** — region Vertex (domyślnie `us-central1`)
    - **Credentials path** *(opcjonalne)* — ścieżka do pliku JSON
      klucza konta usługi. Pozostaw puste, aby użyć Application
      Default Credentials
      (`gcloud auth application-default login`)
3. **Save**. Rozwijane menu modeli ponownie zapełnia się z Vertex,
   gdy projekt jest ustawiony.

Odświeżanie OAuth jest obsługiwane automatycznie przez `google-genai`.
Ścieżka JSON konta usługi jest przechowywana w plaintext celowo
(*ścieżka* nie jest tajemnicą — zawartość pliku jest, i pozostają
na dysku, gdzie udokumentowana najlepsza praktyka Google je
przechowuje).

## OpenAI / Kompatybilny z OpenAI

Wszystko, co eksponuje REST API kompatybilne z OpenAI, działa —
sam OpenAI, Anthropic przez [LiteLLM proxy](https://docs.litellm.ai),
lokalny Ollama, LM Studio, vLLM, Together.ai, Groq itd.

W **Settings → LLM**:

1. Kliknij **Add Custom Provider**
2. Wypełnij:
    - **Name** — etykieta jak "OpenAI" / "Local Ollama" /
      "Anthropic"
    - **API endpoint** — URL bazowy (np.
      `https://api.openai.com/v1` lub `http://localhost:11434/v1`
      dla Ollama)
    - **API key** — pozostaw puste dla nieuwierzytelnionych
      lokalnych endpointów
    - **Models** — lista oddzielona przecinkami (np. `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. Kliknij **Save**.

Niestandardowi dostawcy są przechowywani jako JSON blob w keychainie
OS (włącznie z kluczami API).

## Przełączanie domyślnego modelu

Rozwijane menu **Default Gemini model** w **Settings → LLM**
ustawia fallback używany przez każdą stronę funkcji, która nie ma
własnego selektora.

Strony z własnym selektorem modelu:

- **Translate Text** — `Translate Text settings tab → Default model`
- **Translate Document** — wybiera per-zadanie; fallbackuje na
  domyślny
- **Subtitle / Voice / Dubbing / Live / Extract Text** — każda ma
  własny domyślny per-funkcja w swojej zakładce Settings

To pozwala mieszać i dopasowywać: darmowy Flash dla live, Pro dla
dużych dokumentów, lokalny Ollama dla wrażliwych danych.

## Gdzie przechowywane są klucze

| OS | Przechowywanie |
|---|---|
| **macOS** | Keychain (login keychain) |
| **Windows** | Credential Manager |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (bez daemona)** | Fallbackuje na plaintext INI w `~/.config/ai-translate/settings.ini` |

Wartość INI fallbacku jest migrowana do keychain przy pierwszym
odczycie, gdy keychain staje się dostępny — bez ręcznego kroku.

## Instalacja bezgłowa / serwerowa

Bez sesji desktopowej nadal możesz ustawiać klucze przez `keyring`
CLI Pythona (po `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Niestandardowi dostawcy (wklej JSON blob — zobacz Settings UI dla schematu)
uv run keyring set ai-translate llm/custom_providers
```

Lub ustaw te same klucze INI bezpośrednio w `settings.ini` —
aplikacja migruje je do keychain przy pierwszym odczycie. Plik
znajduje się w:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Testowanie konfiguracji

Najszybsze sprawdzenie poprawności:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Polish --quiet
cat /tmp/x_translated__pl.txt
```

Jeśli widzisz "Witaj świecie." — gotowe.

## Częste błędy

| Error | Prawdopodobna przyczyna |
|---|---|
| `AUTH_ERROR` | Zły / wygasły klucz API. Wklej ponownie w Settings. |
| `QUOTA_ERROR` | Przekroczono żądania-na-dzień poziomu darmowego. Poczekaj lub zapłać. |
| `MODEL_NOT_FOUND` | Lista `models` niestandardowego dostawcy nie zawiera żądanego modelu. |
| `VISION_NOT_SUPPORTED` | Wybrany model nie potrafi obsłużyć wejścia obrazów. Użyj wariantu `flash` / `pro` / `vision`. |

Zobacz [Troubleshooting](../troubleshooting.md) po więcej.
