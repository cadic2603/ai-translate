---
description: Install LibreOffice so AI Translate can translate legacy Office formats (.doc, .xls, .ppt) and ODF files (.odt, .ods, .odp) on macOS and Linux.
---

# LibreOffice (Office formats)

The Office translation pipeline picks the best available backend in
this order:

1. **win32com** (Windows + MS Office installed) — highest fidelity
2. **LibreOffice UNO** (cross-platform) — fallback when win32com isn't there
3. **python-docx / openpyxl / python-pptx** (modern formats only) —
   pure-Python fallback when neither of the above is available

LibreOffice is **the only path** for legacy `.doc` / `.xls` / `.ppt`
on Linux and macOS, and the recommended path on those platforms for
modern Office formats too (better fidelity than the pure-Python
backend, especially for tables and embedded objects).

## Install

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    Or download from <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    The desktop app on Windows usually uses **win32com** with MS Office
    installed — LibreOffice is the *fallback* if MS Office is missing.
    Install from <https://www.libreoffice.org/download/download/>.

## Verify

```bash
soffice --version
```

If you get "command not found" on macOS, the binary is at
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. The app
auto-discovers it across common install paths, but you can override
in **Settings → General → LibreOffice path** if needed.

## What it powers

When LibreOffice is the active backend:

| Feature | Note |
|---|---|
| **Modern Office** (`.docx`, `.xlsx`, `.pptx`) | Used as fallback when win32com isn't available |
| **Legacy Office** (`.doc`, `.xls`, `.ppt`) | Required — pure Python can't read these |
| **ODF** (`.odt`, `.ods`, `.odp`) | Used for round-trip conversion when **Auto-convert ODF** is on |
| **Auto-convert legacy / ODF → OOXML** | Required |

## Background process

The first time LibreOffice is needed, the app spawns a `soffice`
process in headless mode and keeps it alive across translations
(`office_lifecycle.py`). It auto-shuts down on app quit.

## Caveats

!!! warning "First-run startup time"
    The first translation that hits LibreOffice waits ~5-10 seconds for
    `soffice` to spin up. Subsequent translations reuse the same
    process and are fast.

!!! info "JVM crash logs"
    LibreOffice's Java component occasionally produces `hs_err_pid*.log`
    files when it segfaults. The app routes those to a temp directory
    so they don't pollute your project folder.

!!! tip "Auto-convert legacy / ODF"
    Enable **Settings → Translation → Auto-convert legacy** if you
    routinely translate `.doc` / `.xls` / `.ppt`. The pipeline converts
    them to `.docx` / `.xlsx` / `.pptx` first (via `convert_to_modern_format`),
    translates the modern copy, then converts back. Fidelity is much
    higher than translating the legacy format directly.
