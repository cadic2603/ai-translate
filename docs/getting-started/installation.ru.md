---
description: Установите AI Translate на Windows, macOS или Linux из готовых бинарников или из исходников — охватывает Python, FFmpeg и опциональную настройку LibreOffice.
---

# Установка

## Что вам нужно

- **Python 3.12 или новее** ([скачать](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — быстрый менеджер пакетов Python. Установите:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **API-ключ LLM** — любой из:
    - [Google Gemini](https://aistudio.google.com/apikey) (бесплатный уровень — рекомендуется для старта)
    - Любой OpenAI-совместимый endpoint (OpenAI, Anthropic через прокси, локальный Ollama / LM Studio и т. д.)

## Опционально, но открывает больше возможностей

| Инструмент | Используется | Когда нужен |
|---|---|---|
| **FFmpeg** ([скачать](https://ffmpeg.org/download.html)) | Субтитры, Голос, Дубляж, Live | Любой аудио/видео workflow |
| **LibreOffice** ([скачать](https://www.libreoffice.org/download/)) | Office-форматы на Linux/macOS | Перевод legacy `.doc` / `.xls` / `.ppt`, или любого Office-файла, когда MS Office не установлен |
| **Tesseract** ([руководство по установке](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR-движок (по умолчанию) | Страница «Извлечение текста», перевод сканированных PDF, перевод встроенных изображений |
| **MS Office** + **pywin32** | Office на Windows | Высочайшая точность Office-перевода на Windows |

Можно установить AI Translate без всего этого — функции, которым нужны
эти инструменты, скажут вам об этом до сбоя.

## Настройка

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Это устанавливает всё необходимое для запуска десктопного приложения,
CLI и MCP-сервера.

## Запуск

=== "Десктопное приложение"
    ```bash
    uv run python -m src.main
    ```

=== "Командная строка"
    ```bash
    uv run ait --version
    ```

=== "MCP-сервер"
    ```bash
    uv run ait-mcp           # stdio-транспорт (для Claude Desktop / Code)
    ```

## Добавление API-ключа

При первом открытии десктопного приложения:

1. Нажмите **Настройки** в боковой панели
2. Откройте вкладку **LLM**
3. Вставьте **Google Gemini API-ключ** (или настройте кастомного
   OpenAI-совместимого провайдера). Корпоративные пользователи могут
   переключить Gemini в **режим Vertex AI** — укажите GCP-проект и
   регион, опционально путь к JSON service-account; см.
   [LLM-провайдеры](../setup/llm-providers.md) для деталей.
4. Выберите модель по умолчанию — любой текущий вариант Flash (например
   `gemini-2.5-flash`) — солидная бесплатная отправная точка. Pro-варианты
   дают лучшее качество за более высокую цену.
5. Закройте Настройки — готово

Ключи хранятся в **связке ключей вашей ОС** (Keychain на macOS,
Credential Manager на Windows, GNOME / KDE Secret Service на Linux),
не в открытом виде на диске.

!!! tip "Headless / серверная установка"
    Если вы не можете запустить десктопное приложение для настройки
    ключей, см. [LLM-провайдеры](../setup/llm-providers.md) для команд
    keychain CLI.

## Дальше: попробуйте

[Первый перевод за 5 минут →](first-translation.md){ .md-button .md-button--primary }
