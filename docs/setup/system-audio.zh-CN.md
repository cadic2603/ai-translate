---
description: 在 Linux、macOS 和 Windows 上为 AI Translate 的 Live 页面捕获系统音频 — 实时翻译计算机上播放的任何声音。
---

# 系统音频捕获 (Live)

**[实时翻译](../features/live-translation.md)**页面可以捕获**系统
音频**（在你扬声器上播放的所有内容），以便你可以为任何媒体添加字幕 /
翻译 — Zoom 通话、YouTube、Netflix、游戏、系统声音。

在**设置 → Live → 音频源**（或 Live 页面顶部的组合框）中，选择：

- **麦克风** — 仅你的麦克风
- **系统音频** — 仅在你扬声器上播放的内容
- **两者** — 两者混合（用于在媒体上叙述或捕获混合会议很好）

当你选择**系统音频**或**两者**时，应用会调度到你的 OS 的正确捕获
后端。如果不满足 OS 先决条件，将出现一个带有可点击安装链接的内联
警告横幅，这样你不必启动会话即可发现缺少某些东西。

## Linux (PulseAudio / PipeWire)

在每个现代发行版上开箱即用。

应用使用 `parec`（PulseAudio 录音机）来获取你默认 sink 的**监视器
源**。PipeWire 的 PulseAudio 兼容性 shim 使这一切变得透明 — 你不
需要原始 PulseAudio。

```bash
parec --version    # 应该打印一些东西
```

如果 `parec` 缺失，警告横幅会检测你发行版的包管理器，并内联确切的
安装命令 — 例如：

> 系统音频捕获需要 PulseAudio 或 PipeWire — 运行 `sudo apt-get install pulseaudio`。

在 apt-get / dnf / pacman / zypper / apk 上检测到；你可以将命令直接
复制粘贴到终端中。

## macOS

CoreAudio 不会原生暴露系统音频，因此你需要一个**虚拟环回设备** —
安装其中一个：

- **[BlackHole](https://existential.audio/blackhole/)** — 免费、开源
- **[Loopback](https://rogueamoeba.com/loopback/)** — 付费、精致的 GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — 旧版免费选项
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — 付费

应用通过 `ffmpeg -f avfoundation -list_devices` 自动检测它们中的
任何一个并使用第一个匹配项。无需将环回设置为你的默认输出 / 输入 —
捕获通过 `ffmpeg` 的 avfoundation 后端直接进行。

安装后，只需在 Live 页面组合框中选择**系统音频**，警告横幅就会消失。

## Windows

原生 — 大多数情况下**不需要额外软件**。

应用通过 [`soundcard`](https://github.com/bastibe/SoundCard) Python
包（在 Windows 上随应用自动安装）直接与 **WASAPI 环回**通话。这是
Tauri / Rust 桌面应用使用的相同原生环回 API；它捕获默认扬声器输出而
无需虚拟电缆。

如果由于某种原因 WASAPI 环回不可用（较旧的 Windows 版本、不寻常的
音频驱动程序），应用会回退到 `ffmpeg -f dshow` 对虚拟环回 DirectShow
设备。选择其中一个：

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — 免费，提供 `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — 免费，作为 `CABLE Output (VB-Audio Virtual Cable)` 提供
- **立体声混音 (Realtek Audio)** — 旧版板载选项，通常默认禁用

应用按顺序探测这些并使用存在的第一个。

## 为什么"两者"既能拾取你的声音又能拾取系统音频

在**两者**模式下，应用并行打开两个捕获流 — 你的麦克风通过
`sounddevice`，系统音频通过上面的 OS 特定后端 — 并在采样块粒度上混合
它们。这是叙述视频或捕获混合会议两侧（你的声音加扬声器上的参与者）的
正确模式。

> **提示：** 如果你听到回声或得到重复字幕，你的麦克风正在接收系统
> 音频（扬声器响 → 麦克风拾取它们）。仅切换到**系统音频**，或使用
> 耳机。

## 故障排除

| 症状 | 可能原因 |
|---|---|
| Live 页面启动但没有字幕 | 选择了错误的音频源，或你的默认麦克风被静音 |
| 你声音的字幕但没有 YouTube 视频的字幕 | 系统音频先决条件未安装（横幅应显示安装说明） |
| 字幕两次（回声） | "两者"模式拾取系统音频两次 — 一次从扬声器通过麦克风，一次通过环回。仅切换到系统音频或使用耳机 |
| 安装缺失软件后横幅仍可见 | 切换标签并返回 — 横幅在页面显示时重新检查 |
| macOS：BlackHole 已安装但横幅仍在 | 确认 BlackHole 在 `ffmpeg -f avfoundation -list_devices true -i ""` 音频设备列表中；应用需要在那里看到它 |
| Windows：尽管没有错误但 WASAPI 环回失败 | 尝试安装 VB-Audio Virtual Cable 作为后备；较旧的 Windows 版本或某些音频驱动程序不通过 `soundcard` 暴露环回 |
