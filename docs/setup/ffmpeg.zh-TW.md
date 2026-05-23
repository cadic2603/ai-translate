---
description: 安裝 FFmpeg 以便 AI Translate 可以解碼音訊和影片，用於字幕生成、語音合成和影片配音 — 媒體功能必需。
---

# FFmpeg

任何音訊 / 影片工作流程都需要 FFmpeg：

- **生成字幕** — 為 STT 解碼源音訊
- **生成語音** — 將定時 TTS 片段合並為一個檔案
- **配音** — STT → TTS → 復用回影片
- **即時翻譯** — 当系統音訊捕獲透過 `parec` 時

它不被打套件 — 在你的系統上安裝一次。

## 安裝

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

    或者，對於更完整的構建，先啟用
    [RPM Fusion](https://rpmfusion.org/Configuration)。

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    從 <https://www.gyan.dev/ffmpeg/builds/> 下載靜態構建（"release
    essentials" 構建即可），解壓，然後將 `bin/` 檔案夾添加到你的 PATH：

    1. 按 **Win + R**，輸入 `sysdm.cpl`，按 **Enter**
    2. **進階 → 環境變數 → 系統變數 → Path → 編輯**
    3. **新建** → 貼上 FFmpeg 的 `bin` 檔案夾的絕對路徑
    4. 全部 **確定**，重新啟動所有開啟的終端機

## 驗證

```bash
ffmpeg -version
```

你應該看到帶有 `--enable-libx264 --enable-libvpx` 的版本橫幅在設定
行中。如果看到 "command not found"，安裝沒有進入 PATH。

## 應用內預檢查

語音 / 配音頁面在開始工作前調用 `shutil.which("ffmpeg")`。如果未
找到 FFmpeg，你會看到帶有返回此處鏈接的友好錯誤對話方塊，而不是半執行
的任務。

## 常見錯誤

| 錯誤 | 含義 |
|---|---|
| `FFMPEG_NOT_FOUND` | 頁面嘗試執行時 `ffmpeg` 不在 PATH 中。安裝它（上面）並重新啟動應用。 |

在 MCP 伺服器（`ait-mcp`）中，相同的錯誤被重新套件裝成人類別可讀的消息：

> *"需要 FFmpeg 來解碼此音訊/影片檔案，但未安裝或不在 PATH 中。安裝
> FFmpeg 后重試。"*
