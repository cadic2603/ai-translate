---
description: LibreOffice install करें ताकि AI Translate macOS और Linux पर legacy Office formats (.doc, .xls, .ppt) और ODF files (.odt, .ods, .odp) translate कर सके।
---

# LibreOffice (Office formats)

Office translation pipeline इस order में सबसे अच्छा available
backend चुनती है:

1. **win32com** (Windows + MS Office installed) — highest fidelity
2. **LibreOffice UNO** (cross-platform) — fallback जब win32com न हो
3. **python-docx / openpyxl / python-pptx** (केवल modern formats)
   — pure-Python fallback जब उपरोक्त में से कोई भी available न हो

Linux और macOS पर legacy `.doc` / `.xls` / `.ppt` के लिए LibreOffice
**एकमात्र path** है, और इन platforms पर modern Office formats के
लिए भी recommended path है (pure-Python backend से better fidelity,
विशेष रूप से tables और embedded objects के लिए)।

## Install करें

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    या <https://www.libreoffice.org/download/download/> से download
    करें।

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Windows पर desktop ऐप आमतौर पर MS Office installed के साथ
    **win32com** का उपयोग करता है — LibreOffice *fallback* है यदि
    MS Office missing है। <https://www.libreoffice.org/download/download/>
    से install करें।

## Verify करें

```bash
soffice --version
```

यदि आपको macOS पर "command not found" मिलता है, binary
`/Applications/LibreOffice.app/Contents/MacOS/soffice` पर है।
ऐप इसे common install paths में auto-discover करता है, लेकिन यदि
ज़रूरत हो तो आप **Settings → General → LibreOffice path** में
override कर सकते हैं।

## यह क्या powers देता है

जब LibreOffice active backend है:

| Feature | Note |
|---|---|
| **Modern Office** (`.docx`, `.xlsx`, `.pptx`) | win32com unavailable होने पर fallback के रूप में उपयोग |
| **Legacy Office** (`.doc`, `.xls`, `.ppt`) | Required — pure Python इन्हें read नहीं कर सकता |
| **ODF** (`.odt`, `.ods`, `.odp`) | जब **Auto-convert ODF** on हो तो round-trip conversion के लिए उपयोग |
| **Auto-convert legacy / ODF → OOXML** | Required |

## Background process

जब LibreOffice को पहली बार ज़रूरत होती है, ऐप headless mode में एक
`soffice` process spawn करती है और translations के बीच इसे जीवित
रखती है (`office_lifecycle.py`)। यह ऐप quit पर auto-shutdown
होती है।

## Caveats

!!! warning "First-run startup time"
    पहली translation जो LibreOffice को hit करती है `soffice` को
    spin up होने के लिए ~5-10 seconds wait करती है। बाद की
    translations वही process reuse करती हैं और तेज़ होती हैं।

!!! info "JVM crash logs"
    LibreOffice का Java component कभी-कभी `hs_err_pid*.log` files
    produce करता है जब यह segfault होता है। ऐप उन्हें एक temp
    directory में route करती है ताकि वे आपके project folder को
    pollute न करें।

!!! tip "Auto-convert legacy / ODF"
    यदि आप routinely `.doc` / `.xls` / `.ppt` translate करते हैं
    तो **Settings → Translation → Auto-convert legacy** enable
    करें। Pipeline उन्हें पहले `.docx` / `.xlsx` / `.pptx` में
    convert करती है (`convert_to_modern_format` के माध्यम से),
    modern copy translate करती है, फिर वापस convert करती है।
    Fidelity legacy format को सीधे translate करने से बहुत अधिक है।
