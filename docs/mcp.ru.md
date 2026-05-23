---
description: Раскройте AI Translate как инструменты Model Context Protocol, чтобы Claude Desktop, Claude Code и другие MCP-клиенты могли переводить текст, файлы и аудио.
---

# Сервер MCP (`ait-mcp`)

Раскрывает pipeline перевода как инструменты **Model Context
Protocol**, чтобы AI-агенты вроде Claude Desktop и Claude Code могли
управлять им напрямую — «Переведи этот PDF на французский» становится
вызовом инструмента, а не копированием-вставкой.

## Что раскрывается

Девять инструментов:

| Инструмент | Назначение |
|---|---|
| `translate_text` | Перевести список строк |
| `translate_document` | Поставить в очередь задачи перевода файлов (возвращает ID задач) |
| `get_task_status` | Опросить статус задачи |
| `cancel_task` | Кооперативная отмена выполняющихся задач |
| `extract_image_text` | OCR или vision LLM |
| `transcribe_audio` | Аудио → SRT |
| `synthesize_speech` | Текст → MP3 / WAV |
| `query_glossary` | Перечислить наборы / записи глоссария |
| `list_languages` | Все 45 поддерживаемых языков |

## Запуск сервера

```bash
ait-mcp                       # транспорт stdio (по умолчанию для desktop-агентов)
ait-mcp --transport sse       # Server-Sent Events для веб-клиентов
ait-mcp --transport sse --port 9000
```

`stdio` — это то, что ожидает каждый MCP-клиент, если вы явно не
настроили SSE.

## Добавить в Claude Desktop

1. Откройте Claude Desktop → **Settings → Developer → Edit Config**
2. Добавьте эту запись под `mcpServers`:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    Замените `/absolute/path/to/ai-translate` на путь к клонированному репо.

3. Закройте и снова откройте Claude Desktop. Иконка молотка теперь
   должна показать «ai-translate» со всеми 9 инструментами. Попробуйте:

    > «Переведи этот PDF (`/home/me/report.pdf`) на французский —
    > сохрани вывод рядом с источником.»

## Добавить в Claude Code

`~/.config/claude-code/mcp_servers.json` (или `claude mcp add` изнутри
Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Перезапустите Claude Code. Те же 9 инструментов становятся вызываемыми.

## Добавить в другие MCP-клиенты

Любой MCP-совместимый клиент имеет похожую форму:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (по умолчанию)

Для клиентов на основе HTTP / SSE запустите
`ait-mcp --transport sse --port 9000` и направьте клиент на
`http://localhost:9000`.

## Гарантии валидации

Каждый инструмент возвращает одинаковую форму при ошибках, чтобы
агенты могли обрабатывать сбои единообразно:

| Плохой ввод | Ответ инструмента |
|---|---|
| Неизвестный язык | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM не настроен | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Неподдерживаемый тип файла | `ValueError` со списком разрешённых расширений |
| Неправильно сформированный `model="…"` (без `:`) | `ValueError` вместо тихого использования значения по умолчанию |
| Неизвестные ID задач в `cancel_task` | Возвращены в массиве `unknown` — без ошибки |
| Отсутствует FFmpeg в `transcribe_audio` | `RuntimeError: FFmpeg is required…` (переупакован из сырого тега `FFMPEG_NOT_FOUND` движка) |

Агенты, вызывающие эти инструменты, могут полагаться на эти контракты.

## Параллелизм

`translate_document` выполняет pipeline в daemon-потоке. Каждый batch
получает собственное событие отмены, поэтому отмена одного batch не
мешает другому. MCP-сервер отслеживает активные pipeline'ы в карте,
локальной для процесса (автоматически очищается, когда pipeline
завершается).

## Сценарии использования

- **«Переведи docs этой codebase на вьетнамский»** — направьте агента
  на папку docs, он batch'ит вызовы `translate_document` и опрашивает
  `get_task_status`, пока каждый не завершится.
- **«Какие языки вы поддерживаете?»** — агент вызывает
  `list_languages`, читает ответ.
- **«Переведи этот японский чек»** — агент вызывает
  `extract_image_text` на фото, затем `translate_text` на результате.
- **«Создай вьетнамские субтитры для этой записи Zoom»** — агент
  вызывает `transcribe_audio`, чтобы получить SRT на исходном языке,
  затем `translate_text` на каждом cue для локализации, и собирает
  SRT обратно.

!!! note "Видеодубляж — не MCP-инструмент"
    Полный pipeline STT → перевод → TTS → mux (страница **Дубляж**
    desktop-приложения) сейчас доступен только через GUI. Из MCP вы
    можете собрать эквивалент сами с `transcribe_audio` +
    `translate_text` + `synthesize_speech`, но шаг mux с учётом
    тайминга (FFmpeg) придётся обработать снаружи.

## Советы

!!! tip "Настройте один раз, агенты работают везде"
    MCP-сервер делит API-ключи и настройки с desktop-приложением и
    CLI. Настройте свой LLM / OCR / TTS один раз в GUI, и любой агент,
    говорящий с `ait-mcp`, унаследует ту же настройку.

!!! tip "Cold-start кэш endpoint"
    Для каждой пары `(endpoint, модель)` выбор
    chat-vs-responses-API и работающий вариант payload персистятся в
    `llm_endpoint_cache.json` в директории кэша ОС
    (`~/.cache/ai-translate/` на Linux,
    `~/Library/Caches/ai-translate/` на macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` на Windows). Свежие
    `ait-mcp` процессы полностью пропускают auto-detection probe
    после первого успешного вызова — агенты, спавнящие сервер по
    запросу, не платят round-trip'ы определения варианта на каждом
    вызове. Кэш безопасен для multi-process и multi-thread
    (read-merge-write под RLock с атомарным rename).

!!! tip "Селектор модели по инструменту"
    Инструменты `translate_text` и `translate_document` принимают
    опциональный параметр `model` — агенты могут выбрать быструю
    модель для быстрых ходов и более тяжёлую для production-вывода,
    не требуя от пользователя реконфигурировать desktop-приложение.

!!! warning "Долго работающие pipeline'ы"
    `translate_document` возвращается немедленно с ID задач.
    Ожидается, что агент опрашивает `get_task_status`, пока каждая
    задача не достигнет `Done` или `Failed`. Не ждите синхронно
    внутри вызова инструмента; это рискует сработавшим timeout
    MCP-клиента.
