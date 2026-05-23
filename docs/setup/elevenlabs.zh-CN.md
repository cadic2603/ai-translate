---
description: 将 ElevenLabs 连接到 AI Translate 以获得高质量神经 TTS — 用逼真、富有表现力的语音生成 30+ 种语言的配音。
---

# ElevenLabs (TTS)

高级神经文本转语音。当你选择 ElevenLabs 作为 TTS 方法时，由
**[生成语音](../features/generate-voice.md)**、
**[配音](../features/dubbing.md)**和
**[实时翻译](../features/live-translation.md)**页面使用。

## 获取 API 密钥

1. 在 <https://elevenlabs.io> 注册
2. 打开 <https://elevenlabs.io/app/settings/api-keys>
3. 点击 **+ Create New Key**，命名（例如 "ai-translate"），复制密钥
   （看起来像 `sk_...`）

免费层每月给你约 10,000 个字符，足够测试。生产使用从约 $5/月开始。

## 在应用中配置

在**设置 → 服务**中：

1. 将密钥粘贴到 **ElevenLabs API 密钥** → **保存**
2. 在**语音 ID** 中输入你偏好的**语音 ID**（在
   <https://elevenlabs.io/app/voice-lab> 找到 ID；从语音的 URL 中
   复制 ID）。留空让 ElevenLabs 选择默认。

在**设置 → 语音**中：

1. 将 **TTS 方法**设为 **ElevenLabs**
2. 选择 **ElevenLabs 模型**：

    | 模型 | 最适合 |
    |---|---|
    | `eleven_multilingual_v2`（默认） | 通用使用，延迟/质量平衡 |
    | `eleven_v3` | 最高质量（用于生产配音） |
    | `eleven_flash_v2_5` | 最低延迟（用于实时翻译） |

## 它支持什么

| 页面 | 何时使用 ElevenLabs |
|---|---|
| **生成语音** | 你想从字幕文件获得高级质量配音 |
| **配音** | 你想在翻译视频上获得高质量的配音轨 |
| **实时翻译** | 你想实时播放翻译字幕的语音 |

## 语音克隆

ElevenLabs 支持自定义语音克隆（付费计划）。在 ElevenLabs 网站上克隆
语音后，将其语音 ID 粘贴到**设置 → 服务 → 语音 ID** 中，配音 / 语音
生成管道将使用它。

## 注意事项

!!! warning "预检查"
    语音 / 配音页面在开始工作*之前*检查你的 ElevenLabs API 密钥已
    设置。如果缺失，你会得到一个友好的对话框指向设置，而不是半执行
    的任务。

!!! tip "Live 模式自动回退"
    在**实时翻译**页面，如果你选择了 ElevenLabs 但没有配置密钥，
    应用会自动回退到 **Edge TTS**（免费）并在状态标签中宣布回退，
    以便你方便时修复。

!!! info "仍需要 FFmpeg"
    ElevenLabs 返回音频字节；应用仍使用 FFmpeg 在格式之间转换并将
    定时片段组合成一个文件。见 [FFmpeg 设置](ffmpeg.md)。

## 常见错误

| 错误 | 可能原因 |
|---|---|
| `AUTH_ERROR` | API 密钥错误 / 过期。在设置 → 服务中重新粘贴。 |
| `QUOTA_ERROR` | 免费层字符限制达到，或付费计划耗尽。 |
| `MODEL_NOT_FOUND` | 所选 ElevenLabs 模型不再可用；在设置 → 语音中选择另一个。 |
