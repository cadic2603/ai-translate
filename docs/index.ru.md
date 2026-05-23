---
description: AI Translate — бесплатный кроссплатформенный десктопный переводчик для документов, PDF, субтитров, аудио и живой речи на более чем 45 языков.
---

# AI Translate

Бесплатный кроссплатформенный десктопный переводчик, поддерживающий
**45 языков** и идущий далеко дальше простого текста — он переводит
документы, аудио, видео, живую речь, скриншоты и многое другое, всё через
единый pipeline на базе LLM.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Десктопное приложение**

    ---

    Перетащите файл, выберите целевой язык, получите переведённую копию.
    Drag-and-drop, история, глоссарии, всё включено.

    [:octicons-arrow-right-24: 5-минутное руководство](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Командная строка**

    ---

    `ait report.docx --target French` — тот же pipeline, скриптуемый
    и без интерфейса. Полезно для CI, batch-задач, серверов.

    [:octicons-arrow-right-24: Руководство CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI-агенты (MCP)**

    ---

    Раскрывает перевод как инструменты Model Context Protocol, чтобы
    Claude Desktop, Claude Code и другие MCP-клиенты могли вызывать
    их напрямую.

    [:octicons-arrow-right-24: Настройка MCP](mcp.md)

</div>

## Что вы можете перевести

| Тип | Форматы |
|---|---|
| **Документы Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, плюс legacy `.doc` / `.xls` / `.ppt` |
| **PDF** | extract-overlay перевод с сохранением вёрстки, перевод закладок / форм / ссылок, OCR-fallback для сканов |
| **Текст и веб** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Субтитры** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Локализация** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Изображения** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR или vision LLM) |
| **Аудио** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Видео** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (полный pipeline дубляжа) |

## Ключевые возможности {: #headline-features }

- **[Перевод текста](features/translate-text.md)** — мгновенный LLM-перевод с авто-определением, редактированием на месте, воспроизведением TTS. Языки справа налево (арабский, иврит, персидский) рендерятся нативно.
- **[Перевод документа](features/translate-document.md)** — бросайте файлы, наблюдайте спиннер прогресса по задаче, получайте переведённые копии бок о бок. Цели RTL получают правильную bidi-разметку; `Ctrl+P` / `Ctrl+G` приостанавливают и возобновляют очередь.
- **[Создание субтитров (STT)](features/generate-subtitle.md)** — транскрибирует аудио / видео в SRT / VTT / ASS / SSA.
- **[Создание голоса (TTS)](features/generate-voice.md)** — синтезирует субтитры в MP3 / WAV с тайм-кодами.
- **[Дубляж видео](features/dubbing.md)** — STT → перевод → TTS → полный микс обратно в исходное видео.
- **[Живой перевод](features/live-translation.md)** — overlay субтитров в реальном времени с микрофона или системного аудио.
- **[Извлечение текста](features/extract-text.md)** — OCR или vision LLM → `.txt` / `.docx`.
- **[Глоссарий](features/glossary.md)** — обеспечивает единообразную терминологию во всех переводах.

!!! tip "Режим Vertex AI для Gemini"
    Корпоративные пользователи могут переключить вызовы Gemini с
    Developer API на **Vertex AI** в **Настройки → LLM** — укажите ваш
    GCP-проект и регион, опционально путь к JSON service-account. См.
    [LLM-провайдеры](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Впервые здесь?"
    Начните с [Установки](getting-started/installation.md), затем
    [5-минутный туториал первого перевода](getting-started/first-translation.md).
    Вы получите переведённый документ менее чем за 10 минут от свежего
    клона.
