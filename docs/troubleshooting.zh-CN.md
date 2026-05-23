---
description: 诊断 AI Translate 问题——缺失字体、FFmpeg 错误、LibreOffice 转换器问题、OCR 设置失败和 LLM API 身份验证。
---

# 故障排除

常见错误、它们的含义,以及如何修复。

## 设置错误

### "LLM is not configured"

您还没有添加 API 密钥。打开桌面应用 → **设置 → LLM** → 粘贴一个密钥。
完整指南见 [LLM 提供商](setup/llm-providers.md)。

### `AUTH_ERROR`

LLM API 密钥错误或已过期。

- **Gemini**——在 <https://aistudio.google.com/apikey> 生成新密钥,
  在**设置 → LLM** 中重新粘贴。
- **自定义提供商**——验证密钥有效(用相同的
  `Authorization: Bearer …` 头手动 curl endpoint)。
  如果 endpoint 移动了,也更新 **API endpoint** 字段。

### `QUOTA_ERROR`

您达到了免费层或付费方案的限制。

- **Gemini 免费层**——每个模型的每日请求配额不同
  (见 <https://ai.google.dev/gemini-api/docs/rate-limits>)。
  等一天,或升级到付费。
- **OpenAI / 其他**——查看您的账单仪表板。许多提供商有"消费上限",
  达到时会暂停请求。

### `MODEL_NOT_FOUND`

您选择的模型名称不可用。

- 自定义提供商——确保模型在**设置 → LLM** 中以逗号分隔的 **Models** 列表中。
- 内置 Gemini 列表——切换到**设置 → LLM → 默认 Gemini 模型**中
  记录的模型。

### `VISION_NOT_SUPPORTED`

您选择了非视觉模型并尝试翻译图像 / 扫描 PDF。切换到名称包含
`flash`、`pro` 或 `vision` 的模型(例如 OpenAI 的 `gpt-4o`、
Gemini 的任何当前 Gemini Flash 或 Pro 变体)。

## 音频 / 视频错误

### `FFMPEG_NOT_FOUND`

FFmpeg 不在 PATH 中。您的 OS 的安装命令见
[FFmpeg 设置](setup/ffmpeg.md)。

MCP 服务器将其重新包装为:*"FFmpeg is required to decode this
audio/video file but is not installed or not on PATH."*

### Live 页面不显示字幕

- **错误的音频源**——打开**设置 → Live → 音频源**并确保它与
  您实际想要的匹配(麦克风 / 系统 / 两者)。
- **麦克风静音**——检查 OS 声音设置;应用使用您的默认输入设备。
- **系统音频未设置**——见
  [系统音频捕获](setup/system-audio.md) 了解 macOS / Windows
  loopback 步骤。

### 语音输出静音 / 空

- **没有密钥的 ElevenLabs**——Voice 页面在飞行前显示友好对话框;
  如果它溜过了,文件可能是空字节。检查
  **设置 → Service → ElevenLabs API key**。
- **Edge TTS 网络错误**——Edge TTS 需要互联网;如果您的防火墙
  阻止 `speech.platform.bing.com`,切换到 ElevenLabs、
  Google Cloud TTS 或 **Piper TTS**(完全离线)。

### "Piper voice not installed" 对话框

Voice / Dubbing / Translate Text 页面在任何 worker 启动前
飞行前检查您的目标语言的 Piper 语音是否在磁盘上。如果不在,
您将看到一个带**打开设置**按钮的模态。

下载语音:

1. 在对话框中点击**打开设置**(或手动打开**设置 → 语音**)。
2. 确保 **TTS 方法**设置为 **Piper TTS**。
3. 点击**立即下载语音**打开语音库对话框。
4. 找到您目标语言的行,然后点击旁边的 **Female voice** 或
   **Male voice**。语音是从 HuggingFace 下载的 ~25–60 MB ONNX 文件;
   每种语言一次。
5. 关闭对话框并重新运行您的翻译 / voice / dub 任务。

如果您的目标语言不在列表中,它没有 Piper 覆盖——引擎在合成时
悄悄回退到 Edge TTS,所以您实际上不需要下载任何东西。
今天没有 Piper 语音的 13 种语言:白俄罗斯语、孟加拉语、
中文(繁体)、克罗地亚语、爱沙尼亚语、希伯来语、日语、
高棉语、韩语、立陶宛语、马来语、蒙古语、泰语。

**实时翻译**页面是*不会*显示此对话框的唯一地方——
用模态打断实时流会比回退更糟,所以那里语音缺失的情况
悄悄走向 Edge TTS。

## 文档翻译错误

### PDF 翻译在特定页面失败

PDF 使用每页检查点——成功的页面不会重做。失败的页面将堆栈日志记录
到 `app.log`;常见罪魁祸首:

- 页面是**没有文本层的扫描**且 OCR 未配置。设置**设置 → OCR**
  (见 [OCR 引擎](setup/ocr-engines.md))。
- 页面包含 LLM 弄乱的**复杂数学布局**。尝试更强的模型
  (Pro 变体而不是 Flash)。

### Office 翻译破坏格式

- **现代格式**(`.docx`、`.xlsx`、`.pptx`)——通过 HTML 往返
  逐 run 保留格式。如果您在输出中看到流浪的 `<b>` 标签,LLM 没有
  关闭它们——用更强的模型重新运行。
- **旧格式**(`.doc`、`.xls`、`.ppt`)——开启**设置 → 翻译 →
  Auto-convert legacy** 以获得更好的保真度。管道首先转换为 `.docx`,
  翻译,再转换回来。

### 翻译队列在批次中间停止

退出应用并检查数据库:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

数分钟未触及的 `Translating` 行意味着 worker 静默崩溃。
重新启动桌面应用——它在启动时自动恢复 Pending / Translating 任务。

## 跨界问题

### 一次多个文件被静默地翻译为一个

一次拖放一个文件,或检查队列标题中的 **Files** 列——
它应显示您拖放的数量。100 文件上限在超过时显示通知。

### 侧边栏永远显示旋转器

表示 worker 仍被标记为运行中。干净退出应用(无 SIGKILL)——
autouse 清理钩子重置标志。如果 SIGKILL 留下了卡住的状态,
手动清除 DB worker:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### 日志在哪里? {: #where-are-the-logs }

| OS | 路径 |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

无论控制台详细程度如何,日志总是捕获 DEBUG+。控制台输出
默认是 INFO+;向 CLI 传递 `--verbose` 以在 stdout 上镜像
完整的文件日志。

## 仍然卡住?

- 设计层面的问题见 [FAQ](faq.md)。
- 在 <https://github.com/cadic2603/ai-translate/issues>
  提交 issue,包含:OS、Python 版本、失败的命令、`app.log` 的
  相关切片以及您期望的内容描述。
