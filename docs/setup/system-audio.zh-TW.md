---
description: 在 Linux、macOS 和 Windows 上為 AI Translate 的 Live 頁面捕獲系統音訊 — 即時翻譯計算機上播放的任何聲音。
---

# 系統音訊捕獲 (Live)

**[即時翻譯](../features/live-translation.md)**頁面可以捕獲**系統
音訊**（在你喇叭上播放的所有內容），以便你可以為任何媒體添加字幕 /
翻譯 — Zoom 通話、YouTube、Netflix、游戲、系統聲音。

在**設定 → Live → 音訊源**（或 Live 頁面頂部的組合框）中，選擇：

- **麥克風** — 僅你的麥克風
- **系統音訊** — 僅在你喇叭上播放的內容
- **兩者** — 兩者混合（用於在媒體上敘述或捕獲混合會議很好）

当你選擇**系統音訊**或**兩者**時，應用會調度到你的 OS 的正確捕獲
后端。如果不滿足 OS 先決條件，將出現一個帶有可點擊安裝鏈接的內聯
警告橫幅，這樣你不必啟動會話即可發現缺少某些東西。

## Linux (PulseAudio / PipeWire)

在每個現代發行版上開箱即用。

應用使用 `parec`（PulseAudio 錄音機）來獲取你預設 sink 的**監視器
源**。PipeWire 的 PulseAudio 兼容性 shim 使這一切變得透明 — 你不
需要原始 PulseAudio。

```bash
parec --version    # 應該打印一些東西
```

如果 `parec` 缺失，警告橫幅會檢測你發行版的套件管理員，並內聯確切的
安裝命令 — 例如：

> 系統音訊捕獲需要 PulseAudio 或 PipeWire — 執行 `sudo apt-get install pulseaudio`。

在 apt-get / dnf / pacman / zypper / apk 上檢測到；你可以將命令直接
複製貼上到終端機中。

## macOS

CoreAudio 不會原生暴露系統音訊，因此你需要一個**虛擬環回設備** —
安裝其中一個：

- **[BlackHole](https://existential.audio/blackhole/)** — 免費、開源
- **[Loopback](https://rogueamoeba.com/loopback/)** — 付費、精致的 GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — 舊版免費選項
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — 付費

應用透過 `ffmpeg -f avfoundation -list_devices` 自動檢測它們中的
任何一個並使用第一個匹配项。無需將環回設定為你的預設輸出 / 輸入 —
捕獲透過 `ffmpeg` 的 avfoundation 后端直接進行。

安裝后，只需在 Live 頁面組合框中選擇**系統音訊**，警告橫幅就會消失。

## Windows

原生 — 大多數情況下**不需要額外軟體**。

應用透過 [`soundcard`](https://github.com/bastibe/SoundCard) Python
套件（在 Windows 上隨應用自動安裝）直接與 **WASAPI 環回**通話。這是
Tauri / Rust 桌面應用程式使用的相同原生環回 API；它捕獲預設喇叭輸出而
無需虛擬電纜。

如果由於某種原因 WASAPI 環回不可用（較舊的 Windows 版本、不尋常的
音訊驅動程式），應用會回到 `ffmpeg -f dshow` 對虛擬環回 DirectShow
設備。選擇其中一個：

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — 免費，提供 `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — 免費，作為 `CABLE Output (VB-Audio Virtual Cable)` 提供
- **立體聲混音 (Realtek Audio)** — 舊版板載選項，通常預設禁用

應用按顺序探測這些並使用存在的第一個。

## 為什麼"兩者"既能拾取你的聲音又能拾取系統音訊

在**兩者**模式下，應用並行開啟兩個捕獲流 — 你的麥克風透過
`sounddevice`，系統音訊透過上面的 OS 特定后端 — 並在采樣塊粒度上混合
它們。這是敘述影片或捕獲混合會議兩側（你的聲音加喇叭上的參與者）的
正確模式。

> **提示：** 如果你聽到回聲或得到重復字幕，你的麥克風正在接收系統
> 音訊（喇叭響 → 麥克風拾取它們）。僅切換到**系統音訊**，或使用
> 耳機。

## 故障排除

| 症狀 | 可能原因 |
|---|---|
| Live 頁面啟動但沒有字幕 | 選擇了錯誤的音訊源，或你的預設麥克風被靜音 |
| 你聲音的字幕但沒有 YouTube 影片的字幕 | 系統音訊先決條件未安裝（橫幅應顯示安裝說明） |
| 字幕兩次（回聲） | "兩者"模式拾取系統音訊兩次 — 一次從喇叭透過麥克風，一次透過環回。僅切換到系統音訊或使用耳機 |
| 安裝缺失軟體后橫幅仍可見 | 切換標籤並返回 — 橫幅在頁面顯示時重新檢查 |
| macOS：BlackHole 已安裝但橫幅仍在 | 確認 BlackHole 在 `ffmpeg -f avfoundation -list_devices true -i ""` 音訊設備清單中；應用需要在那裡看到它 |
| Windows：儘管沒有錯誤但 WASAPI 環回失敗 | 嘗試安裝 VB-Audio Virtual Cable 作為后備；較舊的 Windows 版本或某些音訊驅動程式不透過 `soundcard` 暴露環回 |
