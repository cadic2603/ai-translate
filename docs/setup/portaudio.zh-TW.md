---
description: 用於即時翻譯的跨平台麥克風音訊擷取。
---

# PortAudio 設定 (麥克風)

[即時翻譯](../features/live-translation.md) 功能使用 Python 套件 `sounddevice`，該套件依賴於 PortAudio C 函式庫來存取所有作業系統上的麥克風裝置。大多數使用者需要安裝此系統級相依項目。

## Windows
`sounddevice` 和 `PyAudio` 的預先編譯 wheel 通常在 Windows 上捆綁了 PortAudio 二進位檔案。通常不需要手動進行系統範圍的安裝。如果遇到錯誤，請確保您的音訊驅動程式是最新的。

## macOS
使用 Homebrew 安裝 PortAudio：

```bash
brew install portaudio
```

## Linux
套件名稱取決於您的發行版。如果沒有可用的預先編譯 wheel，則必須安裝開發套件（通常以 `-dev` 或 `-devel` 結尾），以便 Python 可以建置 C 綁定。

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

## 疑難排解

如果安裝後應用程式繼續報告無法存取麥克風：

1. 確保您的終端機應用程式（或桌面環境）具有存取麥克風的權限（尤其是在 macOS 上）。
2. 重新啟動應用程式（或終端機/MCP 伺服器），以便它取得新的函式庫路徑。
