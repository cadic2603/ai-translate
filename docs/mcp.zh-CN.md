---
description: 将 AI Translate 公开为 Model Context Protocol 工具,以便 Claude Desktop、Claude Code 和其他 MCP 客户端可以翻译文本、文件和音频。
---

# MCP 服务器 (`ait-mcp`)

将翻译管道公开为 **Model Context Protocol** 工具,以便 Claude Desktop
和 Claude Code 等 AI 智能体可以直接驱动它——"将这个 PDF 翻译成法语"
变成一次工具调用,而不是复制粘贴。

## 公开内容

九个工具:

| 工具 | 用途 |
|---|---|
| `translate_text` | 翻译字符串列表 |
| `translate_document` | 排队文件翻译任务(返回任务 ID) |
| `get_task_status` | 轮询任务状态 |
| `cancel_task` | 协作式取消正在运行的任务 |
| `extract_image_text` | OCR 或 LLM 视觉 |
| `transcribe_audio` | 音频 → SRT |
| `synthesize_speech` | 文本 → MP3 / WAV |
| `query_glossary` | 列出术语集 / 条目 |
| `list_languages` | 全部 45 种支持的语言 |

## 运行服务器

```bash
ait-mcp                       # stdio 传输(桌面智能体的默认)
ait-mcp --transport sse       # 用于 Web 客户端的 Server-Sent Events
ait-mcp --transport sse --port 9000
```

`stdio` 是任何 MCP 客户端的预期,除非您已显式配置 SSE。

## 添加到 Claude Desktop

1. 打开 Claude Desktop → **Settings → Developer → Edit Config**
2. 在 `mcpServers` 下添加此条目:

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

    将 `/absolute/path/to/ai-translate` 替换为克隆的 repo 路径。

3. 退出并重新打开 Claude Desktop。锤子图标现在应显示带有所有 9 个工具的
   "ai-translate"。试试:

    > "将这个 PDF (`/home/me/report.pdf`) 翻译成法语——把输出保存在源文件旁边。"

## 添加到 Claude Code

`~/.config/claude-code/mcp_servers.json`(或从 Claude Code 内部
`claude mcp add`):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

重启 Claude Code。同样的 9 个工具变得可调用。

## 添加到其他 MCP 客户端

任何 MCP 兼容的客户端采用类似的形式:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio(默认)

对于基于 HTTP / SSE 的客户端,运行
`ait-mcp --transport sse --port 9000` 并将客户端指向
`http://localhost:9000`。

## 验证保证

每个工具在错误时返回相同的形状,以便智能体可以一致地处理失败:

| 错误输入 | 工具响应 |
|---|---|
| 未知语言 | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM 未配置 | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| 不支持的文件类型 | 列出允许扩展名的 `ValueError` |
| 格式错误的 `model="…"` (无 `:`) | `ValueError`,而不是悄悄使用默认值 |
| `cancel_task` 中未知的任务 ID | 在 `unknown` 数组中返回——无错误 |
| `transcribe_audio` 中缺少 FFmpeg | `RuntimeError: FFmpeg is required…`(从引擎的原始 `FFMPEG_NOT_FOUND` 标签重新包装) |

调用这些工具的智能体可以依赖这些契约。

## 并发

`translate_document` 在守护线程中运行管道。每个批次获得自己的取消事件,
因此取消一个批次不会干扰另一个。MCP 服务器在进程本地映射中跟踪活动管道
(管道结束时自动清理)。

## 用例

- **"将这个代码库的文档翻译成越南语"** ——将智能体指向 docs 文件夹,
  它会批处理 `translate_document` 调用,并轮询 `get_task_status`
  直到每一个完成。
- **"你支持哪些语言?"** ——智能体调用 `list_languages`,读取响应。
- **"翻译这张日语收据"** ——智能体在照片上调用 `extract_image_text`,
  然后在结果上调用 `translate_text`。
- **"为这个 Zoom 录像生成越南语字幕"** ——智能体调用 `transcribe_audio`
  以获取源语言的 SRT,然后在每个 cue 上调用 `translate_text` 进行本地化,
  再重新组装 SRT。

!!! note "视频配音不是 MCP 工具"
    完整的 STT → 翻译 → TTS → mux 管道(桌面应用的**配音**页面)
    目前仅通过 GUI 可用。从 MCP 您可以自己组合等效的:
    `transcribe_audio` + `translate_text` + `synthesize_speech`,
    但您需要在外部处理时序敏感的 mux 步骤(FFmpeg)。

## 技巧

!!! tip "设置一次,智能体在任何地方工作"
    MCP 服务器与桌面应用和 CLI 共享 API 密钥和设置。在 GUI 中一次性
    配置 LLM / OCR / TTS,然后任何与 `ait-mcp` 通信的智能体都继承
    相同的设置。

!!! tip "冷启动 endpoint 缓存"
    对于每个 `(endpoint, 模型)` 对,chat-vs-responses-API 选择和
    有效的 payload 变体被持久化到 OS 缓存目录中的
    `llm_endpoint_cache.json`(Linux 上 `~/.cache/ai-translate/`,
    macOS 上 `~/Library/Caches/ai-translate/`,
    Windows 上 `%LOCALAPPDATA%\ai-translate\cache\`)。新的 `ait-mcp`
    进程在第一次成功调用后完全跳过自动检测探测——按需启动服务器的
    智能体不会在每次调用时支付变体检测往返。缓存是多进程和多线程
    安全的(在 RLock 下进行 read-merge-write,带原子 rename)。

!!! tip "每个工具的模型选择器"
    `translate_text` 和 `translate_document` 工具接受可选的 `model`
    参数——智能体可以为快速回合选择快速模型,为生产输出选择更重的
    模型,而不需要用户重新配置桌面应用。

!!! warning "长时间运行的管道"
    `translate_document` 立即返回任务 ID。期望智能体轮询
    `get_task_status` 直到每个任务达到 `Done` 或 `Failed`。不要在
    工具调用内部同步等待;那会冒 MCP 客户端超时触发的风险。
