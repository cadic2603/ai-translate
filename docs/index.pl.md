---
description: AI Translate to darmowy, wieloplatformowy desktopowy translator dokumentów, plików PDF, napisów, audio i mowy na żywo w ponad 45 językach.
---

# AI Translate

Darmowy, wieloplatformowy desktopowy translator obsługujący **45
języków** i wykraczający daleko poza zwykły tekst — tłumaczy
dokumenty, audio, wideo, mowę na żywo, zrzuty ekranu i więcej, wszystko
za pomocą jednego potoku zasilanego LLM.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Aplikacja desktopowa**

    ---

    Przeciągnij plik, wybierz język docelowy, otrzymaj przetłumaczoną
    kopię. Drag-and-drop, historia, glosariusze, wszystko.

    [:octicons-arrow-right-24: 5-minutowy przewodnik](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Wiersz poleceń**

    ---

    `ait report.docx --target French` — ten sam potok, skryptowalny
    i bezgłowy. Przydatne dla CI, zadań wsadowych, serwerów.

    [:octicons-arrow-right-24: Przewodnik CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **Agenci AI (MCP)**

    ---

    Udostępnij tłumaczenie jako narzędzia Model Context Protocol, aby
    Claude Desktop, Claude Code i inni klienci MCP mogli je wywoływać
    bezpośrednio.

    [:octicons-arrow-right-24: Konfiguracja MCP](mcp.md)

</div>

## Co możesz tłumaczyć

| Rodzaj | Formaty |
|---|---|
| **Dokumenty Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, plus stare `.doc` / `.xls` / `.ppt` |
| **PDF-y** | tłumaczenie metodą extract-overlay z zachowaniem układu, tłumaczenie zakładek / formularzy / linków, fallback OCR dla skanów |
| **Tekst i web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Napisy** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Lokalizacja** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Obrazy** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR lub LLM vision) |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Wideo** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (pełny potok dubbingu) |

## Główne funkcje

- **[Tłumacz tekst](features/translate-text.md)** — natychmiastowe tłumaczenie LLM z auto-wykrywaniem, edycją w miejscu, odtwarzaniem TTS. Języki right-to-left (arabski, hebrajski, perski) renderują się natywnie.
- **[Tłumacz dokument](features/translate-document.md)** — upuszczaj pliki, obserwuj spinner postępu dla każdego zadania, otrzymuj przetłumaczone kopie obok siebie. Cele RTL otrzymują odpowiednie znaczniki bidi; `Ctrl+P` / `Ctrl+G` wstrzymują i kontynuują kolejkę.
- **[Generuj napisy (STT)](features/generate-subtitle.md)** — transkrybuj audio / wideo do SRT / VTT / ASS / SSA.
- **[Generuj głos (TTS)](features/generate-voice.md)** — syntetyzuj napisy do MP3 / WAV z taktowaniem.
- **[Dubbing wideo](features/dubbing.md)** — pełny STT → tłumaczenie → TTS → miks z powrotem do źródłowego wideo.
- **[Tłumaczenie na żywo](features/live-translation.md)** — overlay napisów z mikrofonu lub dźwięku systemowego w czasie rzeczywistym.
- **[Wyodrębnij tekst](features/extract-text.md)** — OCR lub LLM vision → `.txt` / `.docx`.
- **[Glosariusz](features/glossary.md)** — egzekwuj spójną terminologię w tłumaczeniach.

!!! tip "Tryb Vertex AI dla Gemini"
    Użytkownicy korporacyjni mogą przełączyć wywołania Gemini z
    Developer API na **Vertex AI** w **Ustawienia → LLM** —
    skieruj go na swój projekt GCP i region, opcjonalnie podaj
    ścieżkę JSON konta usługi. Zobacz
    [Dostawcy LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Pierwszy raz tutaj?"
    Zacznij od [Instalacji](getting-started/installation.md), następnie
    [5-minutowy przewodnik pierwszego tłumaczenia](getting-started/first-translation.md).
    Otrzymasz przetłumaczony dokument w mniej niż 10 minut od świeżego
    klona.
