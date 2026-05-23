---
description: Instal AI Translate di Windows, macOS, atau Linux dari binari prebuilt atau source — mencakup Python, FFmpeg, dan setup LibreOffice opsional.
---

# Instalasi

## Yang Anda butuhkan

- **Python 3.12 atau lebih baru** ([download](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — manajer paket Python yang cepat. Instal dengan:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **API key LLM** — salah satu dari:
    - [Google Gemini](https://aistudio.google.com/apikey) (tier gratis tersedia — direkomendasikan untuk memulai)
    - Endpoint kompatibel OpenAI mana pun (OpenAI, Anthropic via proxy, Ollama / LM Studio lokal, dll.)

## Opsional, tapi membuka lebih banyak fitur

| Tool | Digunakan oleh | Kapan Anda membutuhkannya |
|---|---|---|
| **FFmpeg** ([download](https://ffmpeg.org/download.html)) | Subtitle, Suara, Dubbing, Live | Workflow audio/video apa pun |
| **LibreOffice** ([download](https://www.libreoffice.org/download/)) | Format Office di Linux/macOS | Menerjemahkan legacy `.doc` / `.xls` / `.ppt`, atau file Office apa pun ketika MS Office tidak terinstal |
| **Tesseract** ([panduan instalasi](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | Mesin OCR (default) | Halaman Ekstrak Teks, terjemahan PDF di-scan, terjemahan gambar tersemat |
| **MS Office** + **pywin32** | Office di Windows | Kesetiaan terjemahan Office tertinggi di Windows |

Anda dapat menginstal AI Translate tanpa salah satu dari ini — fitur
yang membutuhkannya akan memberi tahu Anda sebelum gagal.

## Setup

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Itu menginstal segala yang dibutuhkan untuk menjalankan aplikasi
desktop, CLI, dan server MCP.

## Menjalankan

=== "Aplikasi desktop"
    ```bash
    uv run python -m src.main
    ```

=== "Command line"
    ```bash
    uv run ait --version
    ```

=== "Server MCP"
    ```bash
    uv run ait-mcp           # transport stdio (untuk Claude Desktop / Code)
    ```

## Tambahkan API key Anda

Pertama kali Anda membuka aplikasi desktop:

1. Klik **Pengaturan** di sidebar
2. Buka tab **LLM**
3. Tempelkan **Google Gemini API key** Anda (atau konfigurasikan
   provider kustom kompatibel OpenAI). Pengguna enterprise dapat
   mengubah Gemini ke **mode Vertex AI** — arahkan ke project dan
   region GCP, opsional sediakan path JSON service account; lihat
   [Provider LLM](../setup/llm-providers.md) untuk detailnya.
4. Pilih model default — varian Flash mana pun yang ada (mis.
   `gemini-2.5-flash`) adalah titik awal gratis yang solid. Varian
   Pro memberikan kualitas lebih baik dengan biaya lebih tinggi.
5. Tutup Pengaturan — selesai

Key disimpan di **keychain OS** Anda (Keychain macOS, Credential
Manager Windows, GNOME / KDE Secret Service di Linux), bukan dalam
plain text di disk.

!!! tip "Instalasi headless / server"
    Jika Anda tidak dapat menjalankan aplikasi desktop untuk setup
    key, lihat [Provider LLM](../setup/llm-providers.md) untuk perintah
    CLI keychain.

## Selanjutnya: cobalah

[Terjemahan pertama 5 menit →](first-translation.md){ .md-button .md-button--primary }
