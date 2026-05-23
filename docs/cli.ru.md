---
description: Используйте CLI ait для headless-перевода файлов — поддерживает PDF, документы Office, субтитры и 45+ языков из скрипта или CI-задачи.
---

# Командная строка (`ait`)

Headless-перевод — тот же pipeline, что и в десктопном приложении,
без необходимости в дисплее. Полезно для CI, batch-задач, серверов и
скриптуемых workflow'ов.

## Быстрый старт

```bash
ait report.docx --target French
```

Вывод появляется рядом с источником как
`report_translated_<src>_<tgt>.docx`.

## Распространённые рецепты

### Несколько файлов

```bash
ait *.pdf --target Japanese
```

Glob-расширение — задача shell (Unix). На Windows / `cmd.exe`,
перечислите файлы явно или используйте PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Пользовательская выходная директория

```bash
ait report.docx --target French --output ./translated/
```

Директория создаётся, если её нет. Если её нельзя создать (отказано в
доступе и т. п.) — вы получите чёткую ошибку и код выхода 2 — без
частичного выполнения.

### Указание исходного языка

```bash
ait letter.txt --target German --source "English (US)"
```

Сопоставление источника без учёта регистра. Голое "Chinese" печатает
подсказку:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Выбор конкретной модели

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Или любой другой Provider:model_name, зарегистрированный во вкладке LLM десктопного приложения.
```

Формат строго `Provider:model_name`. Отсутствие двоеточия → выход 2 с
чётким сообщением вместо тихого fallback на дефолтную Gemini-модель.

### Опции Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` требует настроенный OCR (см.
[OCR-движки](setup/ocr-engines.md)).

### Авто-конверсия legacy-форматов

```bash
ait old-doc.doc --target French --convert-legacy
```

Pipeline сначала конвертирует `.doc` → `.docx` (лучшая точность),
переводит современную копию, конвертирует обратно. То же для
`--convert-odf` и `.odt` / `.ods` / `.odp`.

### Тихий / подробный

```bash
ait report.docx --target French --quiet      # только ошибки
ait report.docx --target French --verbose    # полный DEBUG-поток
```

Режим по умолчанию печатает баннер и прогресс по задаче в stderr;
полные детали (HTTP body-дампы, retry-логи) попадают в директорию
логов приложения платформы независимо от уровня логирования консоли
(см.
[Решение проблем → Где логи?](troubleshooting.md#where-are-the-logs)
для пути на вашей ОС).

### Список поддерживаемых языков

```bash
ait --list-languages
```

Печатает все 45 поддерживаемых языков. Удобно для shell-циклов.

### Версия

```bash
ait --version
# ait 0.1.0
```

## Коды выхода

| Код | Значение |
|---|---|
| `0` | Все задачи успешны |
| `2` | Ошибка аргумента (неизвестный язык, отсутствует целевой, неправильный формат модели, выход недоступен для записи, неподдерживаемое расширение) |
| `3` | LLM не настроен |
| `4` | Частичный сбой (некоторые успешны, некоторые нет) |
| `5` | Все провалились |
| `130` | Прервано (`Ctrl+C`) |

## Отмена

`Ctrl+C` один раз — кооперативная отмена. Чекпоинт текущей задачи
сохраняется, pipeline чисто завершается на следующей границе polling.

`Ctrl+C` снова — жёсткое прерывание. Используйте экономно; частичные
файлы могут остаться в недописанном состоянии.

## Полный справочник флагов

```bash
ait --help
```

Показывает каждый флаг с дефолтом. Тот же контент в сводке здесь:

| Флаг | По умолчанию | Заметки |
|---|---|---|
| `--target / -t LANG` | _обязательный_ | Без учёта регистра |
| `--source / -s LANG` | автоопределение | Без учёта регистра |
| `--output / -o DIR` | родитель источника | Создаётся, если нет |
| `--model / -m PROVIDER:MODEL` | дефолт desktop | Строгий формат |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | Требует настроенный OCR |
| `--translate-comments` | off | Office-комментарии |
| `--translate-shapes` | off | Фигуры / текстовые блоки |
| `--translate-notes` | off | Заметки докладчика PowerPoint |
| `--translate-sheet-names` | off | Вкладки листов Excel |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → современный формат |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | Сохранять записи истории после завершения |
| `--quiet / -q` | off | Только ошибки в консоли |
| `--verbose / -v` | off | DEBUG-поток |
| `--list-languages` | — | Печатает 45 языков и выходит |
| `--version` | — | Печатает версию и выходит |

## Советы

!!! tip "Настройте один раз, используйте везде"
    CLI разделяет API-ключи и настройки с десктопным приложением —
    настройте всё один раз в GUI, затем автоматизируйте `ait`.

!!! tip "Кэш endpoint cold-start"
    Для каждой пары `(endpoint, модель)` выбор chat-vs-responses-API
    и работающий вариант payload персистятся в `llm_endpoint_cache.json`
    в директории кэша ОС (`~/.cache/ai-translate/` на Linux,
    `~/Library/Caches/ai-translate/` на macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` на Windows). Cold-start
    CLI-вызовы полностью пропускают auto-detection probe после
    первого успешного вызова — полезно при скриптинге против
    Azure / vLLM / OpenRouter / Anthropic / DeepSeek-развёртываний,
    которым нужна тонкая настройка payload под провайдера. Кэш
    безопасен для multi-process и multi-thread (read-merge-write
    под RLock с атомарным rename).

!!! tip "Потоки вывода"
    Режим по умолчанию печатает баннер, список задач в очереди и
    прогресс по задаче в **stdout** (line-buffered, чтобы корректно
    переплетаться с ошибками); сообщения об ошибках и записи логов
    идут в **stderr**. Комбинируйте с `--quiet`, чтобы полностью
    подавить stdout для чистого pipe:

    ```bash
    ait --list-languages | grep -i japanese    # данные в stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
