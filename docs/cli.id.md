---
description: Gunakan antarmuka command-line ait untuk menerjemahkan file secara headless — mendukung PDF, dokumen Office, subtitle, dan 45+ bahasa dari script atau job CI.
---

# Command Line (`ait`)

Terjemahan headless — pipeline yang sama dengan aplikasi desktop, tanpa
perlu display. Berguna untuk CI, batch job, server, dan workflow yang
di-script.

## Mulai cepat

```bash
ait report.docx --target French
```

Output muncul di sebelah sumber sebagai
`report_translated_<src>_<tgt>.docx`.

## Resep umum

### File berganda

```bash
ait *.pdf --target Japanese
```

Ekspansi glob adalah tugas shell (Unix). Di Windows / `cmd.exe`,
daftar file secara eksplisit atau gunakan PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Direktori output kustom

```bash
ait report.docx --target French --output ./translated/
```

Direktori dibuat jika tidak ada. Jika tidak dapat dibuat (izin ditolak,
dll.) Anda mendapat error jelas dan exit code 2 — tidak ada eksekusi
parsial.

### Tentukan bahasa sumber

```bash
ait letter.txt --target German --source "English (US)"
```

Pencocokan sumber tidak case-sensitive. "Chinese" sendiri mencetak
petunjuk:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Pilih model spesifik

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Atau Provider:model_name lain yang terdaftar di tab LLM aplikasi desktop.
```

Format ketat `Provider:model_name`. Tanpa titik dua → keluar 2 dengan
pesan jelas, bukan jatuh diam-diam ke model Gemini default.

### Opsi Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` membutuhkan OCR yang dikonfigurasi (lihat
[Mesin OCR](setup/ocr-engines.md)).

### Auto-konversi format legacy

```bash
ait old-doc.doc --target French --convert-legacy
```

Pipeline mengonversi `.doc` → `.docx` dulu (kesetiaan lebih baik),
menerjemahkan salinan modern, mengonversi balik. Sama untuk
`--convert-odf` dan `.odt` / `.ods` / `.odp`.

### Diam / verbose

```bash
ait report.docx --target French --quiet      # hanya error
ait report.docx --target French --verbose    # firehose DEBUG penuh
```

Mode default mencetak banner dan progres per task ke stderr; detail
penuh (dump body HTTP, log retry) masuk ke direktori log aplikasi
platform terlepas dari verbositas konsol (lihat
[Pemecahan masalah → Di mana log?](troubleshooting.md#where-are-the-logs)
untuk path di OS Anda).

### Daftar bahasa yang didukung

```bash
ait --list-languages
```

Mencetak semua 45 bahasa yang didukung. Berguna untuk pipe ke loop shell.

### Versi

```bash
ait --version
# ait 0.1.0
```

## Exit code

| Code | Arti |
|---|---|
| `0` | Semua task berhasil |
| `2` | Error argumen (bahasa tidak dikenal, target hilang, model salah format, output tidak dapat ditulis, ekstensi file tidak didukung) |
| `3` | LLM tidak dikonfigurasi |
| `4` | Kegagalan parsial (sebagian berhasil, sebagian tidak) |
| `5` | Semua gagal |
| `130` | Diinterupsi (`Ctrl+C`) |

## Pembatalan

`Ctrl+C` sekali — pembatalan kooperatif. Checkpoint task saat ini
disimpan, pipeline keluar bersih di batas polling berikutnya.

`Ctrl+C` lagi — interupsi keras. Gunakan dengan hemat; file parsial
mungkin tertinggal dalam keadaan setengah ditulis.

## Referensi flag lengkap

```bash
ait --help
```

Menampilkan setiap flag dengan defaultnya. Konten yang sama diringkas di sini:

| Flag | Default | Catatan |
|---|---|---|
| `--target / -t LANG` | _wajib_ | Tidak case-sensitive |
| `--source / -s LANG` | auto-deteksi | Tidak case-sensitive |
| `--output / -o DIR` | parent sumber | Dibuat jika hilang |
| `--model / -m PROVIDER:MODEL` | default desktop | Format ketat |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | Membutuhkan OCR yang dikonfigurasi |
| `--translate-comments` | off | Komentar Office |
| `--translate-shapes` | off | Bentuk / kotak teks |
| `--translate-notes` | off | Catatan pembicara PowerPoint |
| `--translate-sheet-names` | off | Tab sheet Excel |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → format modern |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | Pertahankan entri riwayat setelah selesai |
| `--quiet / -q` | off | Hanya error di konsol |
| `--verbose / -v` | off | Firehose DEBUG |
| `--list-languages` | — | Mencetak 45 bahasa dan keluar |
| `--version` | — | Mencetak versi dan keluar |

## Tips

!!! tip "Setup sekali, gunakan di mana saja"
    CLI berbagi API key dan pengaturan dengan aplikasi desktop —
    setup semua sekali di GUI, lalu otomatisasi dengan `ait` dari sana.

!!! tip "Cache endpoint cold-start"
    Untuk setiap pasangan `(endpoint, model)`, pilihan
    chat-vs-responses-API dan varian payload yang berhasil dipersist
    ke `llm_endpoint_cache.json` di direktori cache OS
    (`~/.cache/ai-translate/` di Linux,
    `~/Library/Caches/ai-translate/` di macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` di Windows). Invokasi CLI
    cold-start melompati probe auto-deteksi sepenuhnya setelah
    panggilan sukses pertama — berguna saat scripting terhadap
    deployment Azure / vLLM / OpenRouter / Anthropic / DeepSeek yang
    membutuhkan tuning payload spesifik provider. Cache aman
    multi-process dan multi-thread (read-merge-write di bawah RLock
    dengan rename atomik).

!!! tip "Stream output"
    Mode default mencetak banner, daftar task antrian, dan progres
    per task ke **stdout** (line-buffered agar terjalin benar dengan
    error); pesan error dan record log pergi ke **stderr**. Kombinasikan
    dengan `--quiet` untuk menekan stdout sepenuhnya untuk piping bersih:

    ```bash
    ait --list-languages | grep -i japanese    # data di stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
