---
description: 安装 FFmpeg 以便 AI Translate 可以解码音频和视频，用于字幕生成、语音合成和视频配音 — 媒体功能必需。
---

# FFmpeg

任何音频 / 视频工作流程都需要 FFmpeg：

- **生成字幕** — 为 STT 解码源音频
- **生成语音** — 将定时 TTS 片段合并为一个文件
- **配音** — STT → TTS → 复用回视频
- **实时翻译** — 当系统音频捕获通过 `parec` 时

它不被打包 — 在你的系统上安装一次。

## 安装

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    或者，对于更完整的构建，先启用
    [RPM Fusion](https://rpmfusion.org/Configuration)。

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    从 <https://www.gyan.dev/ffmpeg/builds/> 下载静态构建（"release
    essentials" 构建即可），解压，然后将 `bin/` 文件夹添加到你的 PATH：

    1. 按 **Win + R**，输入 `sysdm.cpl`，按 **回车**
    2. **高级 → 环境变量 → 系统变量 → Path → 编辑**
    3. **新建** → 粘贴 FFmpeg 的 `bin` 文件夹的绝对路径
    4. 全部 **确定**，重启所有打开的终端

## 验证

```bash
ffmpeg -version
```

你应该看到带有 `--enable-libx264 --enable-libvpx` 的版本横幅在配置
行中。如果看到 "command not found"，安装没有进入 PATH。

## 应用内预检查

语音 / 配音页面在开始工作前调用 `shutil.which("ffmpeg")`。如果未
找到 FFmpeg，你会看到带有返回此处链接的友好错误对话框，而不是半执行
的任务。

## 常见错误

| 错误 | 含义 |
|---|---|
| `FFMPEG_NOT_FOUND` | 页面尝试运行时 `ffmpeg` 不在 PATH 中。安装它（上面）并重启应用。 |

在 MCP 服务器（`ait-mcp`）中，相同的错误被重新包装成人类可读的消息：

> *"需要 FFmpeg 来解码此音频/视频文件，但未安装或不在 PATH 中。安装
> FFmpeg 后重试。"*
