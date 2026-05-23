---
description: 使用 ait 命令行界面无界面地翻译文件——支持 PDF、Office 文档、字幕和 45 多种语言,可从脚本或 CI 任务运行。
---

# 命令行 (`ait`)

无界面翻译——与桌面应用相同的管道,无需显示器。适用于 CI、批处理任务、
服务器和脚本化的工作流。

## 快速开始

```bash
ait report.docx --target French
```

输出落在源文件旁边,命名为 `report_translated_<src>_<tgt>.docx`。

## 常见用法

### 多个文件

```bash
ait *.pdf --target Japanese
```

Glob 展开是 shell 的工作(Unix)。在 Windows / `cmd.exe` 上,
显式列出文件或使用 PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### 自定义输出目录

```bash
ait report.docx --target French --output ./translated/
```

如果目录不存在则创建。如果无法创建(权限被拒绝等),
您会收到清晰的错误和退出码 2——不会有半运行状态。

### 指定源语言

```bash
ait letter.txt --target German --source "English (US)"
```

源匹配不区分大小写。"Chinese" 单独使用会打印提示:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### 选择特定模型

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# 或桌面应用 LLM 标签页中注册的任何其他 Provider:model_name。
```

格式严格为 `Provider:model_name`。缺少冒号 → 退出 2 并显示清晰消息,
而不是悄悄回退到默认 Gemini 模型。

### Office 选项

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` 需要配置 OCR(参见
[OCR 引擎](setup/ocr-engines.md))。

### 旧格式自动转换

```bash
ait old-doc.doc --target French --convert-legacy
```

管道首先将 `.doc` → `.docx` 转换(更好的保真度),翻译现代副本,
再转换回来。`--convert-odf` 和 `.odt` / `.ods` / `.odp` 同理。

### 静默 / 详细

```bash
ait report.docx --target French --quiet      # 仅错误
ait report.docx --target French --verbose    # 完整 DEBUG 流
```

默认模式将横幅和每任务进度打印到 stderr;完整详情(HTTP body 转储、
重试日志)无论控制台详细程度如何都会进入平台的应用日志目录(参见
[故障排除 → 日志在哪里?](troubleshooting.md#where-are-the-logs)
查看您的 OS 上的路径)。

### 列出支持的语言

```bash
ait --list-languages
```

打印所有 45 种支持的语言。便于通过管道传递到 shell 循环。

### 版本

```bash
ait --version
# ait 0.1.0
```

## 退出码

| 码 | 含义 |
|---|---|
| `0` | 所有任务成功 |
| `2` | 参数错误(未知语言、缺失目标、格式错误的模型、不可写的输出、不支持的文件扩展名) |
| `3` | LLM 未配置 |
| `4` | 部分失败(部分成功,部分失败) |
| `5` | 全部失败 |
| `130` | 中断 (`Ctrl+C`) |

## 取消

`Ctrl+C` 一次——协作式取消。当前任务的检查点被保存,
管道在下一个轮询边界干净退出。

`Ctrl+C` 再次——硬中断。谨慎使用;部分文件可能保留半写状态。

## 完整标志参考

```bash
ait --help
```

显示每个标志及其默认值。同样的内容在这里总结:

| 标志 | 默认 | 说明 |
|---|---|---|
| `--target / -t LANG` | _必需_ | 不区分大小写 |
| `--source / -s LANG` | 自动检测 | 不区分大小写 |
| `--output / -o DIR` | 源的父目录 | 缺失时创建 |
| `--model / -m PROVIDER:MODEL` | 桌面默认 | 严格格式 |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`、`EasyOCR`、`Google Cloud OCR` |
| `--translate-images` | 关 | 需要配置 OCR |
| `--translate-comments` | 关 | Office 注释 |
| `--translate-shapes` | 关 | 形状 / 文本框 |
| `--translate-notes` | 关 | PowerPoint 演讲者备注 |
| `--translate-sheet-names` | 关 | Excel 工作表标签 |
| `--convert-legacy` | 关 | `.doc`/`.xls`/`.ppt` → 现代格式 |
| `--convert-odf` | 关 | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | 关 | 完成后保留历史条目 |
| `--quiet / -q` | 关 | 控制台仅显示错误 |
| `--verbose / -v` | 关 | DEBUG 流 |
| `--list-languages` | — | 打印 45 种语言并退出 |
| `--version` | — | 打印版本并退出 |

## 提示

!!! tip "一次设置,处处使用"
    CLI 与桌面应用共享 API 密钥和设置——在 GUI 中一次性设置好,
    然后从那里用 `ait` 自动化。

!!! tip "冷启动 endpoint 缓存"
    对于每个 `(endpoint, 模型)` 对,chat-vs-responses-API 选择
    和有效的 payload 变体被持久化到 OS 缓存目录中的
    `llm_endpoint_cache.json`(Linux 上 `~/.cache/ai-translate/`,
    macOS 上 `~/Library/Caches/ai-translate/`,
    Windows 上 `%LOCALAPPDATA%\ai-translate\cache\`)。冷启动 CLI
    调用在第一次成功调用后完全跳过自动检测探测——
    在脚本化对接需要供应商特定 payload 调优的 Azure / vLLM /
    OpenRouter / Anthropic / DeepSeek 部署时很有用。
    缓存是多进程和多线程安全的(在 RLock 下进行 read-merge-write,
    带原子 rename)。

!!! tip "输出流"
    默认模式将横幅、排队任务列表和每任务进度打印到 **stdout**
    (按行缓冲,以便与错误正确交错);错误消息和日志记录进入
    **stderr**。结合 `--quiet` 完全抑制 stdout 以进行干净的管道:

    ```bash
    ait --list-languages | grep -i japanese    # 数据在 stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
