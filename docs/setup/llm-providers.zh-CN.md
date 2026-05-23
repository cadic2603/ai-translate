---
description: "为翻译配置 LLM 提供商：Google Gemini（推荐）、与 OpenAI 兼容的端点，或任何带有 API 密钥的自定义提供商。"
---

# LLM 提供商

翻译管道调用大型语言模型进行实际翻译。你可以配置一个或多个；每个功能
的模型选择器允许每个页面使用不同的。

## Google Gemini（建议首次设置使用） {: #google-gemini-recommended-for-first-time-setup }

免费层很慷慨，对大多数个人使用足够好。

1. 前往 <https://aistudio.google.com/apikey>
2. 点击 **Create API key**（用你的 Google 账户登录）
3. 复制密钥（看起来像 `AIza...`）
4. 在桌面应用中：**设置 → LLM → Gemini API 密钥** → 粘贴 → **保存**
5. 在**默认 Gemini 模型**下拉菜单中选择默认模型。Google 的阵容往往
   看起来像：

    - **Flash** 变体（例如 `gemini-2.5-flash`）— 快速、慷慨的免费层、
      质量好。推荐起点。
    - **Pro** 变体 — 较慢、质量更高、更贵。
    - **Flash-lite** — 最快、最便宜、质量较低。

    可用的具体模型名取决于 Google 推送给你账户的内容；选择名称包含
    `flash` 的以获得平衡的默认值。

完成。密钥存储在你的 OS 钥匙串中，而不是明文。

### Vertex AI 模式（企业）

在 Gemini 配置块内，一对单选按钮让你从 **Developer API** 切换到
**Vertex AI** — 相同的 Gemini 模型，通过你的 GCP 账户计费，具有组织
级别控制（VPC-SC、审计日志、区域数据驻留）。

1. 在**设置 → LLM** 中将 Gemini 单选按钮从 **Developer API** 切换到
   **Vertex AI**
2. 填写：
    - **Project** — 你的 GCP 项目 ID
    - **Location** — Vertex 区域（默认 `us-central1`）
    - **Credentials path** *(可选)* — 服务账户 JSON 密钥文件的路径。
      留空使用 Application Default Credentials
      （`gcloud auth application-default login`）
3. **保存**。模型下拉菜单在项目设置好后从 Vertex 重新填充。

OAuth 刷新由 `google-genai` 自动处理。服务账户 JSON 路径故意以明文
存储（*路径*不是秘密 — 文件的内容才是，并且它们留在磁盘上，这是
Google 文档化的最佳实践所保留它们的位置）。

## OpenAI / OpenAI 兼容

任何暴露 OpenAI 兼容 REST API 的东西都有效 — OpenAI 自己、通过
[LiteLLM 代理](https://docs.litellm.ai)的 Anthropic、本地 Ollama、
LM Studio、vLLM、Together.ai、Groq 等等。

在**设置 → LLM**中：

1. 点击 **Add Custom Provider**
2. 填写：
    - **Name** — 像 "OpenAI" / "Local Ollama" / "Anthropic" 的标签
    - **API endpoint** — 基础 URL（例如 `https://api.openai.com/v1`
      或 `http://localhost:11434/v1` 用于 Ollama）
    - **API key** — 对未认证的本地端点留空
    - **Models** — 逗号分隔的列表（例如 `gpt-4o-mini, gpt-4o,
      gpt-3.5-turbo`）
3. 点击 **Save**。

自定义提供商作为 JSON blob 存储在 OS 钥匙串中（包括 API 密钥）。

## 切换默认模型

**设置 → LLM** 中的**默认 Gemini 模型**下拉菜单设置一个后备，由没有
自己选择器的每个功能页面使用。

具有自己模型选择器的页面：

- **翻译文本** — `翻译文本设置选项卡 → 默认模型`
- **翻译文档** — 按任务选择；回退到默认
- **字幕 / 语音 / 配音 / Live / 提取文本** — 每个在其设置选项卡中
  都有自己的每功能默认值

这让你混合搭配：免费 Flash 用于 live、Pro 用于大文档、本地 Ollama
用于敏感数据。

## 密钥存储位置

| OS | 存储 |
|---|---|
| **macOS** | 钥匙串（登录钥匙串） |
| **Windows** | 凭据管理器 |
| **Linux (GNOME)** | Secret Service（gnome-keyring / KWallet） |
| **Linux（无守护进程）** | 回退到 `~/.config/ai-translate/settings.ini` 中的明文 INI |

回退 INI 值在钥匙串可用时的首次读取时迁移到钥匙串 — 无手动步骤。

## 无头 / 服务器安装

没有桌面会话，你仍然可以通过 Python 的 `keyring` CLI 设置密钥
（在 `uv sync` 之后）：

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# 自定义提供商（粘贴 JSON blob — 见设置 UI 了解 schema）
uv run keyring set ai-translate llm/custom_providers
```

或直接在 `settings.ini` 中设置相同的 INI 密钥 — 应用在首次读取时
将它们迁移到钥匙串。文件位于：

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## 测试你的设置

最快的健全性检查：

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Chinese --quiet
cat /tmp/x_translated__zh.txt
```

如果你看到 "你好世界。" — 你完成了。

## 常见错误

| 错误 | 可能原因 |
|---|---|
| `AUTH_ERROR` | API 密钥错误 / 过期。在设置中重新粘贴。 |
| `QUOTA_ERROR` | 免费层每日请求超出。等待或付费。 |
| `MODEL_NOT_FOUND` | 自定义提供商的 `models` 列表不包含请求的模型。 |
| `VISION_NOT_SUPPORTED` | 你选择的模型不能进行图像输入。使用 `flash` / `pro` / `vision` 变体。 |

更多见[故障排除](../troubleshooting.md)。
