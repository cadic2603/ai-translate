---
description: 将 Google Cloud 连接到 AI Translate 用于 Vision OCR、Speech-to-Text 和 Text-to-Speech — 设置 API 密钥并启用相关服务。
---

# Google Cloud（Vision OCR / Speech-to-Text / Text-to-Speech）

一个 Google Cloud API 密钥支持三个可选的后端：

- **Vision OCR** — 付费 OCR 引擎（每月 1,000 次免费）
- **Speech-to-Text v1** — 付费 STT（每月 60 分钟免费）
- **Text-to-Speech v1** — 付费 TTS（WaveNet 每月 1 M 字符免费）

你只需要启用你实际使用的 API。

## 获取 API 密钥

1. [创建 Google Cloud 项目](https://console.cloud.google.com/projectcreate)
2. 打开 API 库：<https://console.cloud.google.com/apis/library>
3. 启用以下任一：
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [创建 API 密钥](https://console.cloud.google.com/apis/credentials)：
   点击 **+ Create Credentials → API key**
5. 复制密钥（看起来像 `AIza...`）。

!!! tip "限制密钥"
    在 API 密钥详细信息页面，在 **API restrictions** 下，将密钥限制
    为仅你已启用的 API。这样泄漏的密钥不能在你不想使用的服务上累积
    账单。

## 在应用中配置

在**设置 → 服务**中：

1. 粘贴到 **Google Cloud API 密钥** → **保存**

这个单一密钥现在对所有三个 Google 服务可用。

## 启用每个服务

### Vision OCR

在**设置 → OCR → OCR 方法 = Google Cloud OCR**。

就是这样 — 它将使用服务中的相同密钥。

### Speech-to-Text

在**设置 → 字幕 → STT 方法 = Google Cloud**（用于字幕 / 语音页面）或
**设置 → Live → STT 方法 = Google Cloud**（用于 Live 页面）。

在**设置 → 字幕 → Google STT 模型**中，选择识别模型：

| 模型 | 最适合 |
|---|---|
| `latest_long`（默认） | 长格式音频（采访、讲座） |
| `latest_short` | 语音命令、短句 |
| `phone_call` | 电话音频（8 kHz） |
| `medical_dictation` / `medical_conversation` | 医疗领域音频 |

### Text-to-Speech

在**设置 → 语音 → TTS 方法 = Google Cloud TTS**。

默认情况下，服务器根据语言和性别选择语音 — 这是大多数用户所需的全部。
固定特定 Google 语音（例如 `en-US-Chirp3-HD-Charon`、
`vi-VN-Wavenet-A`）由引擎支持，但尚未作为设置字段公开；可以通过直接
在 `settings.ini` 中编辑 `voice/google_tts_voice_name` 来设置。语音
ID 在 <https://cloud.google.com/text-to-speech/docs/voices> 列出。

## 常见错误

| 错误 | 可能原因 |
|---|---|
| `AUTH_ERROR` | 密钥错误 / 过期。在设置 → 服务中重新粘贴。 |
| `API not enabled` | 你尚未在此 Cloud 项目上启用特定 API（Vision / Speech / TTS）。 |
| `QUOTA_ERROR` | 此 API 的免费层限额达到。等待，或升级账单。 |
| `INVALID_ARGUMENT_ERROR` | 你选择的语言中不存在该语音名称。 |

## 成本守卫

!!! warning
    所有三个 Google API 都是后付费的 — 一旦你超过免费层，就会开始
    被无限制地计费。在做大量工作之前，在 Cloud 项目上设置
    [预算警报](https://console.cloud.google.com/billing/budgets)。
