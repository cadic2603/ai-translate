---
description: "关于 AI Translate 的常见问题:支持的文件格式、免费 vs 付费功能、离线使用、LLM 提供商选择和 OCR 引擎选择。"
---

# 常见问题

## 一般

### 它能离线工作吗?

大部分可以。具体而言:

- **翻译**需要 LLM。免费 Gemini API 在线;通过 Custom Provider 设置的
  **本地 Ollama / LM Studio** 完全离线。
- **OCR** 使用 **Tesseract** 或 **EasyOCR** 离线。
- **STT** 使用 **Whisper**(默认)离线。
- **TTS** 使用 **Edge TTS**(默认)在线;**ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** 在线(免费或付费);
  **Piper TTS** 是完全离线的神经 TTS——通过**设置 → 语音 → Piper TTS
  → 立即下载语音**下载每语言语音(~25–60 MB ONNX 文件)后,
  无密钥、无网络调用。

完全 air-gapped 设置:Custom Provider → 本地 LLM,Tesseract 或 EasyOCR
用于 OCR,Whisper 用于 STT,Piper TTS 用于语音输出。

### 我翻译的文件保存在哪里?

默认在原文件旁边,带有 `_translated_<src>_<tgt>` 后缀
(例如 `report_translated_en_fr.docx`)。在
**设置 → 通用 → 翻译存储路径**中按功能覆盖。

### 我的设置存储在哪里?

INI 文件位于:

| OS | 路径 |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

API 密钥存放在 OS 钥匙串中(不在 INI 中)。
翻译历史存放在数据目录中的 SQLite DB 中。

### 我的数据如何处理?

- **本地优先**——除非您在调用云 LLM / OCR / STT / TTS 服务,
  否则文本永远不会离开您的机器。
- **无遥测**——应用不会"打电话回家"。应用本身唯一发出的出站请求是
  可选的 GitHub Releases 更新检查(在**设置 → 通用**中切换);
  云后端仅调用各自的供应商。
- **API 密钥**——存储在您的 OS 钥匙串中。当没有钥匙串守护进程可用时,
  桌面应用的钥匙串回退是明文 INI。

### 我可以翻译 Google Doc / Notion 页面吗?

不能直接。先导出为 `.docx`,翻译,然后将翻译后的文件导入回来。
Notion 同理(导出为 Markdown / HTML)、Confluence(导出为 `.docx`)等。

## 选择模型 / 引擎

### 我应该使用哪个 LLM 模型?

对于大多数用户:

- **任何 Gemini Flash 变体**——免费层、快速、出乎意料地好。
  用于日常翻译。名称看起来像 `gemini-2.5-flash`、
  `gemini-3-flash-preview` 等,取决于当前可用情况。
- **任何 Gemini Pro 变体**——按 token 付费,更高质量。
  用于重要文档(法律、技术、面向客户)。
- **本地 Ollama** 配 7B-13B 模型——当您需要离线 / 隐私时。

每功能模型选择器意味着您可以为聊天式翻译使用快速模型,
将昂贵的留给文档。

### 我应该使用哪个 OCR 引擎?

- **Tesseract** 用于主要脚本中的清晰打印文本。免费、离线、快速。
- **EasyOCR** 用于非拉丁脚本(尤其是 CJK)和较嘈杂的图像。
- **Google Cloud Vision** 用于手写、混合脚本和您可以付费时的最高准确性。

### 我应该使用哪个 STT 方法?

- **Whisper local** 用于离线 / 隐私。
- **Soniox** 用于多说话者录音——说话者标签往返进入您的 SRT。
- **Google Cloud STT** 用于电话 / 医疗音频(他们的领域模型很好)。
- **Gemini Live** 用于实时语音到语音翻译。

### 哪个 TTS 后端?

- **Edge TTS** 用于免费的高质量语音。
- **ElevenLabs** 用于高级 / 品牌 / 克隆语音。
- **Google Cloud TTS** 用于 Edge 覆盖薄弱的长尾语言中的 WaveNet 语音。
- **Gemini TTS** 用于复用现有 Gemini API 密钥的免费自然 prebuilt 语音。
- **Piper TTS** 当您需要**离线 / air-gapped** 语音输出时。
  权衡:每种语言通过**设置 → 语音 → Piper TTS → 立即下载语音**
  需要一次性 ~25–60 MB 语音下载,且应用 45 种语言中的 13 种没有
  Piper 语音(那些会悄悄回退到 Edge TTS)。

## 工作流

### 我如何翻译整个文件夹?

将文件夹拖到**翻译文档**的拖放区。其中(递归地)支持的文件被排队;
其他一切都被静默跳过。每次拖放有 100 个文件的上限;更大的批次 →
分成多次拖放。

### 我可以暂停和恢复翻译吗?

可以。随时退出应用——Pending / Translating 任务在下次启动时恢复。
每任务检查点意味着 PDF 100 页中的第 47 页在恢复时不会重做。

### 我可以手动编辑翻译吗?

对于**翻译文本**——可以,点击右侧面板并输入。编辑会自动保存到
条目的历史记录。

对于**翻译文档**——在您常用的编辑器中打开翻译后的文件
(Word、LibreOffice 等)并在那里编辑。应用不会将编辑往返回历史记录。

### 我可以批量翻译字符串列表吗?

使用 CLI:

```bash
ait *.txt --target French
```

或对于进程内字符串(例如从代码中提取的 UI 字符串),用列表调用
MCP `translate_text` 工具,或直接使用 Python API:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## 术语表

### 为什么 LLM 不使用我的术语表?

要检查的三件事:

1. 集合**激活**(复选框已勾选)。
2. 您术语表中的源术语实际上出现在源文本中(每次调用压缩仅向 LLM
   发送与批次文本匹配的条目——节省 token,但意味着源术语中的拼写
   错误是不可见的)。
3. 模型足够强——`flash-lite` 有时忽略 `flash` 和 `pro` 尊重的提示。

### 术语表条目是否独立于重音匹配?

是的。术语表查找和术语表页面中的搜索栏都使用一个去除重音和
大小写的归一化函数。所以 `cafe`、`Café` 和 `CAFE` 都匹配源为
`Café` 的条目。

## 隐私

### 您是否收集任何使用数据?

不。应用没有 analytics SDK。可选的更新检查在启动时轮询单个
GitHub Releases endpoint;在**设置 → 通用**中可切换。

### 我的 API 密钥安全吗?

它们存储在您的 OS 钥匙串中(macOS 上的 Keychain、Windows 上的
Credential Manager、Linux 上的 Secret Service)。其他进程没有
您的明确许可无法读取它们。回退(当没有钥匙串守护进程可用时——
通常是无界面 Linux 服务器)是您用户配置目录下的明文 INI;
在该模式下密钥受文件权限保护但未经过加密。
