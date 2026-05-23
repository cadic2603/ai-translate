---
description: Подключи Google Cloud к AI Translate для Vision OCR, Speech-to-Text и Text-to-Speech — настрой API-ключ и включи соответствующие сервисы.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Один API-ключ Google Cloud обеспечивает три необязательных бэкенда:

- **Vision OCR** — платный движок OCR (1 000 бесплатно / месяц)
- **Speech-to-Text v1** — платный STT (60 минут / месяц бесплатно)
- **Text-to-Speech v1** — платный TTS (1 М символов / месяц
  бесплатно для WaveNet)

Тебе нужно включить только те API, которые ты действительно
используешь.

## Получить API-ключ

1. [Создай проект Google Cloud](https://console.cloud.google.com/projectcreate)
2. Открой библиотеку API: <https://console.cloud.google.com/apis/library>
3. Включи любой из:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Создай API-ключ](https://console.cloud.google.com/apis/credentials):
   кликни **+ Create Credentials → API key**
5. Скопируй ключ (выглядит как `AIza...`).

!!! tip "Ограничь ключ"
    На странице деталей API-ключа, в **API restrictions**, ограничь
    ключ только API, которые ты включил. Таким образом утёкший ключ
    не сможет накопить счета на сервисах, которые ты не собирался
    использовать.

## Настройка в приложении

В **Настройки → Сервис**:

1. Вставь в **API-ключ Google Cloud** → **Сохранить**

Этот один ключ теперь доступен для всех трёх сервисов Google.

## Включи каждый сервис

### Vision OCR

В **Настройки → OCR → Метод OCR = Google Cloud OCR**.

Вот и всё — он будет использовать тот же ключ из Сервиса.

### Speech-to-Text

В **Настройки → Субтитры → Метод STT = Google Cloud** (для страниц
Субтитры / Голос) или **Настройки → Live → Метод STT = Google
Cloud** (для страницы Live).

В **Настройки → Субтитры → Модель Google STT**, выбери модель
распознавания:

| Модель | Лучше всего для |
|---|---|
| `latest_long` (по умолч.) | Длинноформатное аудио (интервью, лекции) |
| `latest_short` | Голосовые команды, короткие фразы |
| `phone_call` | Телефонное аудио (8 кГц) |
| `medical_dictation` / `medical_conversation` | Медицинская аудио-область |

### Text-to-Speech

В **Настройки → Голос → Метод TTS = Google Cloud TTS**.

По умолчанию сервер выбирает голос на основе языка и пола — это всё,
что нужно большинству пользователей. Закрепление конкретного голоса
Google (например, `en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`)
поддерживается движком, но пока не выставлено как поле Настроек; его
можно установить, отредактировав `voice/google_tts_voice_name`
напрямую в `settings.ini`. ID голосов перечислены по адресу
<https://cloud.google.com/text-to-speech/docs/voices>.

## Распространённые ошибки

| Ошибка | Вероятная причина |
|---|---|
| `AUTH_ERROR` | Неверный / истёкший ключ. Вставь заново в Настройки → Сервис. |
| `API not enabled` | Ты не включил конкретный API (Vision / Speech / TTS) на этом Cloud-проекте. |
| `QUOTA_ERROR` | Достигнут лимит бесплатного уровня для этого API. Подожди или обнови биллинг. |
| `INVALID_ARGUMENT_ERROR` | Имя голоса не существует в выбранном тобой языке. |

## Защита расходов

!!! warning
    Все три API Google пост-оплачиваемые — как только превысишь
    бесплатный уровень, начнёт начисляться плата без остановки. Установи
    [уведомление о бюджете](https://console.cloud.google.com/billing/budgets)
    на Cloud-проекте перед выполнением работы большого объёма.
