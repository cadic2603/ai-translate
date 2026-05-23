---
description: 安裝 LibreOffice 以便 AI Translate 可以在 macOS 和 Linux 上翻譯舊版 Office 格式（.doc、.xls、.ppt）和 ODF 檔案（.odt、.ods、.odp）。
---

# LibreOffice（Office 格式）

Office 翻譯管道按以下顺序選擇最佳可用后端：

1. **win32com**（Windows + MS Office 已安裝）— 最高保真度
2. **LibreOffice UNO**（跨平台）— win32com 不在時的后備
3. **python-docx / openpyxl / python-pptx**（僅現代格式）— 上述都
   不可用時的純 Python 后備

LibreOffice 是 Linux 和 macOS 上舊版 `.doc` / `.xls` / `.ppt` 的
**唯一路徑**，也是這些平台上現代 Office 格式的推薦路徑（比純 Python
后端的保真度更好，特別是對於表格和嵌入物件）。

## 安裝

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    或從 <https://www.libreoffice.org/download/download/> 下載。

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Windows 上的桌面應用程式通常使用 **win32com** 與已安裝的 MS Office
    — LibreOffice 是 MS Office 缺失時的*后備*。從
    <https://www.libreoffice.org/download/download/> 安裝。

## 驗證

```bash
soffice --version
```

如果你在 macOS 上得到 "command not found"，二進制位於
`/Applications/LibreOffice.app/Contents/MacOS/soffice`。應用透過
常見安裝路徑自動發現它，但你可以在**設定 → 通用 → LibreOffice 路徑**
中根據需要覆蓋。

## 它支援什麼

当 LibreOffice 是活動后端時：

| 功能 | 注意 |
|---|---|
| **現代 Office**（`.docx`、`.xlsx`、`.pptx`） | 在 win32com 不可用時用作后備 |
| **舊版 Office**（`.doc`、`.xls`、`.ppt`） | 必需 — 純 Python 無法讀取它們 |
| **ODF**（`.odt`、`.ods`、`.odp`） | 在**自動轉換 ODF**開啟時用於來回轉換 |
| **自動轉換舊版 / ODF → OOXML** | 必需 |

## 后台處理程序

第一次需要 LibreOffice 時，應用會在 headless 模式下生成一個
`soffice` 處理程序，並在翻譯之間保持活動（`office_lifecycle.py`）。它
在應用結束時自動關閉。

## 注意事项

!!! warning "首次執行啟動時間"
    第一次到 LibreOffice 的翻譯要等待 ~5-10 秒讓 `soffice` 啟動。
    后續翻譯重用相同的處理程序並很快。

!!! info "JVM 崩潰記錄檔"
    LibreOffice 的 Java 組件偶爾在 segfault 時產生 `hs_err_pid*.log`
    檔案。應用將它們路由到臨時目錄，以便它們不污染你的專案檔案夾。

!!! tip "自動轉換舊版 / ODF"
    如果你經常翻譯 `.doc` / `.xls` / `.ppt`，請啟用**設定 → 翻譯
    → 自動轉換舊版**。管道首先將它們轉換為 `.docx` / `.xlsx` /
    `.pptx`（透過 `convert_to_modern_format`），翻譯現代副本，然後
    轉換回來。保真度比直接翻譯舊版格式高得多。
