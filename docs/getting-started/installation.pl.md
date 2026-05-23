---
description: Zainstaluj AI Translate na Windows, macOS lub Linuxie z gotowych binariów lub źródeł — obejmuje Python, FFmpeg i opcjonalną konfigurację LibreOffice.
---

# Instalacja

## Czego potrzebujesz

- **Python 3.12 lub nowszy** ([download](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — szybki menedżer pakietów Python. Zainstaluj za pomocą:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **Klucz LLM API** — dowolny z:
    - [Google Gemini](https://aistudio.google.com/apikey) (dostępny darmowy poziom — zalecany na początek)
    - Dowolny endpoint kompatybilny z OpenAI (OpenAI, Anthropic przez proxy, lokalny Ollama / LM Studio itd.)

## Opcjonalne, ale odblokowuje więcej funkcji

| Narzędzie | Używane przez | Kiedy go potrzebujesz |
|---|---|---|
| **FFmpeg** ([download](https://ffmpeg.org/download.html)) | Napisy, Głos, Dubbing, Live | Każdy przepływ audio/wideo |
| **LibreOffice** ([download](https://www.libreoffice.org/download/)) | Formaty Office na Linux/macOS | Tłumaczenie starych `.doc` / `.xls` / `.ppt`, lub dowolny plik Office, gdy MS Office nie jest zainstalowany |
| **Tesseract** ([install guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | Silnik OCR (domyślny) | Strona Wyodrębnij tekst, tłumaczenie zeskanowanego PDF, tłumaczenie obrazów osadzonych |
| **MS Office** + **pywin32** | Office na Windows | Najwyższa wierność tłumaczenia Office na Windows |

Możesz zainstalować AI Translate bez żadnego z nich — funkcje, które
ich potrzebują, powiedzą ci o tym, zanim zawiodą.

## Skonfiguruj

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

To instaluje wszystko, czego potrzeba do uruchomienia aplikacji
desktopowej, CLI i serwera MCP.

## Uruchom

=== "Aplikacja desktopowa"
    ```bash
    uv run python -m src.main
    ```

=== "Wiersz poleceń"
    ```bash
    uv run ait --version
    ```

=== "Serwer MCP"
    ```bash
    uv run ait-mcp           # transport stdio (dla Claude Desktop / Code)
    ```

## Dodaj swój klucz API

Przy pierwszym otwarciu aplikacji desktopowej:

1. Kliknij **Ustawienia** w pasku bocznym
2. Otwórz zakładkę **LLM**
3. Wklej swój **klucz Google Gemini API** (lub skonfiguruj
   niestandardowego dostawcę kompatybilnego z OpenAI). Użytkownicy
   korporacyjni mogą zamiast tego przełączyć Gemini w **tryb
   Vertex AI** — skieruj go na projekt GCP i region, opcjonalnie
   podaj ścieżkę JSON konta usługi; szczegóły w
   [Dostawcy LLM](../setup/llm-providers.md).
4. Wybierz domyślny model — dowolny aktualny wariant Flash (np.
   `gemini-2.5-flash`) to solidny darmowy punkt startowy. Warianty
   Pro dają lepszą jakość przy wyższym koszcie.
5. Zamknij Ustawienia — gotowe

Klucze są przechowywane w **keychain twojego OS** (macOS Keychain,
Windows Credential Manager, GNOME / KDE Secret Service na Linuxie),
a nie w postaci zwykłego tekstu na dysku.

!!! tip "Instalacja bezgłowa / serwerowa"
    Jeśli nie możesz uruchomić aplikacji desktopowej do skonfigurowania
    kluczy, zobacz [Dostawcy LLM](../setup/llm-providers.md) dla poleceń
    CLI keychain.

## Następnie: wypróbuj

[5-minutowe pierwsze tłumaczenie →](first-translation.md){ .md-button .md-button--primary }
