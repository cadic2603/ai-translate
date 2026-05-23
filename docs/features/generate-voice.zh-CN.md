---
description: 使用 Edge TTS、ElevenLabs、Google Cloud TTS、Gemini TTS 或离线 Piper TTS 将字幕转换为口语音频 — 保留 SRT 时间以生成配音质量的语音。
---

# 生成语音 (TTS)

将字幕文件（带时间）或任意文本合成为 MP3 / WAV 音频。五种 TTS 后端：
Edge TTS（免费）、ElevenLabs（高质量）、Google Cloud TTS、Gemini TTS
（免费层）和 Piper TTS（离线）。

## 你需要什么

- `PATH` 中的 **FFmpeg** — 见 [FFmpeg 设置](../setup/ffmpeg.md)。
- 一个 TTS 后端，以下之一：
    - **Edge TTS** — 免费，无密钥，默认。使用 Microsoft Edge 的云端
      语音。
    - **ElevenLabs** — 付费，最高质量。见 [ElevenLabs 设置](../setup/elevenlabs.md)。
    - **Google Cloud TTS** — 付费，非常好。见 [Google Cloud 设置](../setup/google-cloud.md)。
    - **Gemini TTS** — 免费层，自然预设语音。复用你 LLM 选项卡中
      现有的 Gemini API 密钥 — 无需额外设置。
    - **Piper TTS** — 完全离线的神经网络 TTS。无 API 密钥，无网络
      调用 — 语音是约 25–60 MB 的 ONNX 文件，通过**设置 → 语音 →
      Piper TTS → 立即下载语音**一次性下载。应用 45 种语言中的 32
      种今天有 Piper 语音；没有 Piper 覆盖的语言在合成时会静默回退到
      Edge TTS。

## 操作步骤

1. 在侧边栏点击**生成语音**。
2. 拖放一个或多个 `.srt` / `.vtt` / `.ass` / `.ssa` 字幕文件。
3. 选择**语言**（尽可能从字幕文件名自动检测 — 例如
   `_translated_en_zh.srt` 被检测为中文）。
4. 选择**语音性别** — `女` 或 `男`。
5. 选择**输出格式** — `.mp3`（默认）或 `.wav`。
6. 点击**生成**（或 `Ctrl+Enter`）。
7. 完成后**打开**该行 — 在你的默认音频应用中播放。

## 输出

你会得到一个单一的音频文件，其中语音轨道放置在每个字幕的时间戳上。
静音间隙填充提示之间的时间，以便音频与原始时间保持同步。

## 选择 TTS 后端

| 后端 | 成本 | 语音 | 备注 |
|---|---|---|---|
| **Edge TTS** | 免费 | 数百，所有主要语言 | 默认。无设置。 |
| **ElevenLabs** | 付费（约 $5/月入门级） | 高级神经语音，语音克隆 | 最高质量。语音 ID 在设置 → 服务中设置。 |
| **Google Cloud TTS** | 付费（约 $4/M 字符；每月免费 1 M） | 50+ 种语言的 WaveNet / Studio 语音 | 强大的欧洲语言 WaveNet 语音。默认情况下，服务器根据语言 + 性别选择语音。 |
| **Gemini TTS** | 免费层（适用 Developer API 配额） | 24+ 种语言的自然预设语音 — `Kore`（女默认）/ `Puck`（男默认） | 复用你 LLM 选项卡中的 Gemini API 密钥。每次调用输出限制约 30 秒；长文本自动在句子边界分块。 |
| **Piper TTS** | 免费，**离线** | 应用 45 种语言中 32 种的神经语音 | 无密钥，无网络。每语言语音从**设置 → 语音 → Piper TTS → 立即下载语音**按需下载（每个约 25–60 MB）。预检查在工作开始前捕获缺失的语音。 |

在**设置 → 语音 → TTS 方法**中切换。

## Piper TTS 细节

Piper 是应用中唯一完全离线的 TTS 后端。需要了解的几件事：

- **语音库对话框** — 通过**设置 → 语音 → Piper TTS → 立即下载语音**
  打开。每个语言行显示一个`女声`和/或`男声`下载按钮（某些语言是
  单一性别）。语音来自
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
  HuggingFace 目录。
- **覆盖范围** — 应用 45 种语言中的 32 种有 Piper 语音。没有覆盖的
  13 种（白俄罗斯语、孟加拉语、中文（繁体）、克罗地亚语、爱沙尼亚语、
  希伯来语、日语、高棉语、韩语、立陶宛语、马来语、蒙古语、泰语）在
  合成时静默回退到 Edge TTS，所以合成永远不会因为缺失语音而硬失败。
- **性别解析** — 当你选择`女`时，引擎首先尝试该语言的女声；如果只有
  男声，它会改用那个（反之亦然）。在 INFO 级别记录。
- **预检查门** — 在语音运行开始之前，页面会检查每语言的 Piper 语音
  是否在磁盘上。如果缺失，你会得到一个带有**打开设置**按钮的模态
  对话框，它直接带你到语音库，这样你可以在不丢失队列的情况下下载它。

## Gemini TTS 细节

Gemini TTS 通过 Developer API 使用 `gemini-2.5-flash-preview-tts`。
需要了解的几件事：

- **语音选择**今天按性别 — 女映射到 `Kore`，男映射到 `Puck`。两者
  都是清晰、中性的语音，跨语言工作而不会听起来太具特征性。
- **输出长度上限** — 每次 Gemini API 调用最多返回约 30 秒的语音。
  应用在句子边界处将输入文本分块到 `_GEMINI_TTS_MAX_BYTES`
  （约 2000 字节 ≈ 30 秒）以下，然后通过 FFmpeg 连接块。在正常字幕
  文本上你不会遇到截断。
- **音频格式** — Gemini 输出 24 kHz 单声道 s16le 的原始 PCM；应用
  按块转码为 MP3（或如果你选择则为 WAV），以便最终文件与你选择的
  输出格式匹配。
- **Vertex AI 尚未支持 TTS** — 即使你的 LLM 选项卡配置为 Vertex，
  Gemini TTS 仍然需要 Developer API 密钥。如果缺失，应用会预先抛出
  `AUTH_ERROR`。

## ElevenLabs 模型

公开了三个模型：

| 模型 | 延迟 | 质量 | 用于 |
|---|---|---|---|
| `eleven_multilingual_v2`（默认） | 中等 | 高 | 通用 TTS |
| `eleven_v3` | 中等 | 最高 | 录音室 / 制作 |
| `eleven_flash_v2_5` | 低 | 良好 | 实时 / Live 模式 |

在**设置 → 语音 → ElevenLabs 模型**中配置。

## 提示

!!! tip "重新生成"
    右键点击行 → **重新生成**以交换语音性别 / TTS 方法 / 格式，无需
    重新运行翻译。

!!! tip "预检查"
    页面在开始前验证 ElevenLabs API 密钥（选择时）和 FFmpeg 可用性。
    如果缺少什么，你会看到一个友好的对话框。

!!! warning "Stop 是原子的"
    在合成期间按**Stop**，你不会在输出目录中得到一个写到一半的 MP3
    — 文件首先被写入临时位置，然后只在成功时移到位置。

## 快捷键

| 快捷键 | 操作 |
|---|---|
| `Ctrl+Enter` | 生成 |
| `Ctrl+O` | 浏览 |
| `Ctrl+F` | 聚焦历史搜索 |
