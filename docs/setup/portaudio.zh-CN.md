---
description: 用于实时翻译的跨平台麦克风音频捕获。
---

# PortAudio 设置 (麦克风)

[实时翻译](../features/live-translation.md) 功能使用 Python 包 `sounddevice`，该包依赖于 PortAudio C 库来访问所有操作系统上的麦克风设备。大多数用户需要安装此系统级依赖项。

## Windows
`sounddevice` 和 `PyAudio` 的预编译 wheel 通常在 Windows 上捆绑了 PortAudio 二进制文件。通常不需要手动进行系统范围的安装。如果遇到错误，请确保您的音频驱动程序是最新的。

## macOS
使用 Homebrew 安装 PortAudio：

```bash
brew install portaudio
```

## Linux
包名称取决于您的发行版。如果没有可用的预编译 wheel，则必须安装开发包（通常以 `-dev` 或 `-devel` 结尾），以便 Python 可以构建 C 绑定。

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## 故障排除

如果安装后应用程序继续报告无法访问麦克风：

1. 确保您的终端应用程序（或桌面环境）具有访问麦克风的权限（尤其是在 macOS 上）。
2. 重新启动应用程序（或终端/MCP 服务器），以便它获取新的库路径。
