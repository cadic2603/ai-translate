---
description: AI Translate adalah penerjemah desktop gratis dan lintas-platform untuk dokumen, PDF, subtitle, audio, dan ucapan langsung dalam 45+ bahasa.
---

# AI Translate

Penerjemah desktop gratis, lintas-platform yang menangani **45 bahasa**
dan jauh melampaui teks biasa — ia menerjemahkan dokumen, audio, video,
ucapan langsung, tangkapan layar, dan lebih banyak lagi, semua melalui
satu pipeline berbasis LLM.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Aplikasi desktop**

    ---

    Seret file masuk, pilih bahasa target, dapatkan salinan terjemahan.
    Drag-and-drop, riwayat, glosarium, semuanya.

    [:octicons-arrow-right-24: Walkthrough 5 menit](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Command line**

    ---

    `ait report.docx --target French` — pipeline yang sama, dapat
    di-script dan headless. Berguna untuk CI, batch job, server.

    [:octicons-arrow-right-24: Panduan CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **Agen AI (MCP)**

    ---

    Ekspos terjemahan sebagai tools Model Context Protocol agar Claude
    Desktop, Claude Code, dan klien MCP lain dapat memanggilnya langsung.

    [:octicons-arrow-right-24: Setup MCP](mcp.md)

</div>

## Apa yang dapat Anda terjemahkan

| Jenis | Format |
|---|---|
| **Dokumen Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, plus legacy `.doc` / `.xls` / `.ppt` |
| **PDF** | terjemahan extract-overlay dengan preservasi tata letak, terjemahan bookmark / form / link, fallback OCR untuk hasil scan |
| **Teks & web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Subtitle** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Lokalisasi** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Gambar** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR atau LLM vision) |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Video** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (pipeline dubbing lengkap) |

## Fitur utama {: #headline-features }

- **[Terjemahkan Teks](features/translate-text.md)** — terjemahan LLM instan dengan auto-deteksi, edit di tempat, pemutaran TTS. Bahasa kanan-ke-kiri (Arab, Ibrani, Persia) dirender secara native.
- **[Terjemahkan Dokumen](features/translate-document.md)** — jatuhkan file, lihat spinner progres per task, dapatkan salinan terjemahan berdampingan. Target RTL mendapatkan markup bidi yang tepat; `Ctrl+P` / `Ctrl+G` mempause dan melanjutkan antrian.
- **[Buat Subtitle (STT)](features/generate-subtitle.md)** — transkripsi audio / video ke SRT / VTT / ASS / SSA.
- **[Buat Suara (TTS)](features/generate-voice.md)** — sintesis subtitle ke MP3 / WAV dengan timing.
- **[Dubbing Video](features/dubbing.md)** — STT → terjemah → TTS → mix lengkap kembali ke video sumber.
- **[Terjemahan Langsung](features/live-translation.md)** — overlay subtitle real-time dari mikrofon atau audio sistem.
- **[Ekstrak Teks](features/extract-text.md)** — OCR atau LLM vision → `.txt` / `.docx`.
- **[Glosarium](features/glossary.md)** — menerapkan terminologi konsisten di semua terjemahan.

!!! tip "Mode Vertex AI untuk Gemini"
    Pengguna enterprise dapat mengubah pemanggilan Gemini dari Developer
    API ke **Vertex AI** di **Pengaturan → LLM** — arahkan ke project
    dan region GCP, opsional sediakan path JSON service account. Lihat
    [Provider LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Pertama kali di sini?"
    Mulai dengan [Instalasi](getting-started/installation.md), lalu
    [walkthrough terjemahan pertama 5 menit](getting-started/first-translation.md).
    Anda akan memiliki dokumen terjemahan dalam waktu kurang dari 10
    menit dari clone segar.
