---
description: 安装 LibreOffice 以便 AI Translate 可以在 macOS 和 Linux 上翻译旧版 Office 格式（.doc、.xls、.ppt）和 ODF 文件（.odt、.ods、.odp）。
---

# LibreOffice（Office 格式）

Office 翻译管道按以下顺序选择最佳可用后端：

1. **win32com**（Windows + MS Office 已安装）— 最高保真度
2. **LibreOffice UNO**（跨平台）— win32com 不在时的后备
3. **python-docx / openpyxl / python-pptx**（仅现代格式）— 上述都
   不可用时的纯 Python 后备

LibreOffice 是 Linux 和 macOS 上旧版 `.doc` / `.xls` / `.ppt` 的
**唯一路径**，也是这些平台上现代 Office 格式的推荐路径（比纯 Python
后端的保真度更好，特别是对于表格和嵌入对象）。

## 安装

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    或从 <https://www.libreoffice.org/download/download/> 下载。

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Windows 上的桌面应用通常使用 **win32com** 与已安装的 MS Office
    — LibreOffice 是 MS Office 缺失时的*后备*。从
    <https://www.libreoffice.org/download/download/> 安装。

## 验证

```bash
soffice --version
```

如果你在 macOS 上得到 "command not found"，二进制位于
`/Applications/LibreOffice.app/Contents/MacOS/soffice`。应用通过
常见安装路径自动发现它，但你可以在**设置 → 通用 → LibreOffice 路径**
中根据需要覆盖。

## 它支持什么

当 LibreOffice 是活动后端时：

| 功能 | 注意 |
|---|---|
| **现代 Office**（`.docx`、`.xlsx`、`.pptx`） | 在 win32com 不可用时用作后备 |
| **旧版 Office**（`.doc`、`.xls`、`.ppt`） | 必需 — 纯 Python 无法读取它们 |
| **ODF**（`.odt`、`.ods`、`.odp`） | 在**自动转换 ODF**开启时用于来回转换 |
| **自动转换旧版 / ODF → OOXML** | 必需 |

## 后台进程

第一次需要 LibreOffice 时，应用会在 headless 模式下生成一个
`soffice` 进程，并在翻译之间保持活动（`office_lifecycle.py`）。它
在应用退出时自动关闭。

## 注意事项

!!! warning "首次运行启动时间"
    第一次到 LibreOffice 的翻译要等待 ~5-10 秒让 `soffice` 启动。
    后续翻译重用相同的进程并很快。

!!! info "JVM 崩溃日志"
    LibreOffice 的 Java 组件偶尔在 segfault 时产生 `hs_err_pid*.log`
    文件。应用将它们路由到临时目录，以便它们不污染你的项目文件夹。

!!! tip "自动转换旧版 / ODF"
    如果你经常翻译 `.doc` / `.xls` / `.ppt`，请启用**设置 → 翻译
    → 自动转换旧版**。管道首先将它们转换为 `.docx` / `.xlsx` /
    `.pptx`（通过 `convert_to_modern_format`），翻译现代副本，然后
    转换回来。保真度比直接翻译旧版格式高得多。
