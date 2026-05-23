---
description: 在 AI Translate 的 Live 页面配置 Soniox 用于实时语音转文字 — 支持说话人分离、术语表条目和实时翻译。
---

# Soniox (STT)

通过 Soniox WebSocket API 进行实时语音转文字。当你选择 Soniox 作为
STT 方法时，由**[字幕](../features/generate-subtitle.md)**和
**[实时翻译](../features/live-translation.md)**页面使用。

## 为什么选择 Soniox

- **实时** — 在说话人还在说话时令牌就已到达。
- **说话人分离** — 每个令牌的说话人标签（例如 _说话人 1：你好…_）。
- **流内翻译** — Soniox 可以在转录的同时翻译，节省额外的 LLM 往返。
- **多语言** — 即使在流中也能自动检测源语言。

## 获取 API 密钥

1. 在 <https://console.soniox.com> 注册
2. 打开 **API keys** → **Create new API key**
3. 复制（看起来像 `Bearer ...`；只复制 token，不带 `Bearer ` 前缀）。

定价按音频分钟计费（撰写时约 $0.005 / 分钟）— 见
<https://soniox.com/pricing>。

## 在应用中配置

在**设置 → 服务**中：

1. 将密钥粘贴到 **Soniox API 密钥** → **保存**

在**设置 → Live**（用于实时翻译）或**设置 → 字幕**（用于字幕生成）中：

1. 将 **STT 方法**设为 **Soniox**

## 它支持什么

| 页面 | 何时使用 Soniox |
|---|---|
| **字幕** | 多说话人录音（采访、小组讨论、会议），你希望在 SRT 中有说话人标签 |
| **实时翻译** | 实时会议字幕，特别是有多个说话人时 |

## 术语表条目

Soniox WebSocket 接受一个术语表来偏置识别。应用自动转发你的活动术语
表条目 — 品牌名 / 专有名词 / 行话能更可靠地被识别。

## 注意事项

!!! warning "仅在线"
    Soniox 仅云端；如果你的音频敏感（医疗、法律），请改用 Whisper
    （本地）。

!!! info "重连"
    WebSocket 在瞬时故障时会以指数退避自动重连。长会话能在短暂网络
    波动中保持连接。

## 常见错误

| 错误 | 可能原因 |
|---|---|
| `AUTH_ERROR` | API 密钥错误 / 过期。在设置 → 服务中重新粘贴。 |
| `QUOTA_ERROR` | 套餐限额超出。 |
| `CONNECTION_ERROR` | 网络被阻止 / 防火墙。从不同网络重试。 |
