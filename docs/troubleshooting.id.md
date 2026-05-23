---
description: Diagnosis masalah AI Translate — font hilang, error FFmpeg, masalah converter LibreOffice, kegagalan setup OCR, dan autentikasi API LLM.
---

# Pemecahan masalah

Error umum, artinya, dan cara memperbaikinya.

## Error setup

### "LLM is not configured"

Anda belum menambahkan API key. Buka aplikasi desktop →
**Pengaturan → LLM** → tempel key. Lihat
[Provider LLM](setup/llm-providers.md) untuk panduan lengkap.

### `AUTH_ERROR`

API key LLM salah atau kedaluwarsa.

- **Gemini** — generate key baru di
  <https://aistudio.google.com/apikey>, tempel ulang di
  **Pengaturan → LLM**.
- **Provider kustom** — verifikasi key valid (curl endpoint manual
  dengan header `Authorization: Bearer …` yang sama). Jika endpoint
  pindah, update juga field **Endpoint API**.

### `QUOTA_ERROR`

Anda mencapai batas tier gratis atau plan berbayar.

- **Tier gratis Gemini** — kuota request harian bervariasi per model
  (lihat <https://ai.google.dev/gemini-api/docs/rate-limits>). Tunggu
  sehari, atau upgrade ke berbayar.
- **OpenAI / lainnya** — periksa dashboard billing. Banyak provider
  punya "spend cap" yang mempause request saat Anda mencapainya.

### `MODEL_NOT_FOUND`

Nama model yang Anda pilih tidak tersedia.

- Provider kustom — pastikan model ada di list **Models**
  comma-separated di **Pengaturan → LLM**.
- List Gemini bawaan — beralih ke model terdokumentasi di
  **Pengaturan → LLM → Model Gemini default**.

### `VISION_NOT_SUPPORTED`

Anda memilih model non-vision dan mencoba menerjemahkan gambar / PDF
scan. Beralih ke model yang namanya berisi `flash`, `pro`, atau
`vision` (mis. `gpt-4o` untuk OpenAI, varian Gemini Flash atau Pro
saat ini untuk Gemini).

## Error audio / video

### `FFMPEG_NOT_FOUND`

FFmpeg tidak di PATH. Lihat [Setup FFmpeg](setup/ffmpeg.md) untuk
perintah instalasi OS Anda.

Server MCP membungkus ulang ini sebagai: *"FFmpeg is required to
decode this audio/video file but is not installed or not on PATH."*

### Halaman Live tidak menampilkan subtitle

- **Sumber audio salah** — buka **Pengaturan → Live → Sumber audio**
  dan pastikan cocok dengan yang Anda inginkan (Mikrofon / Sistem /
  Keduanya).
- **Mic dimute** — periksa pengaturan suara OS; aplikasi menggunakan
  perangkat input default Anda.
- **Audio sistem tidak diatur** — lihat
  [Penangkapan audio sistem](setup/system-audio.md) untuk langkah
  loopback macOS / Windows.

### Output suara senyap / kosong

- **ElevenLabs tanpa key** — halaman Voice menampilkan dialog
  pre-flight yang ramah; jika lolos, file mungkin byte kosong.
  Periksa **Pengaturan → Service → ElevenLabs API key**.
- **Error jaringan Edge TTS** — Edge TTS membutuhkan internet; jika
  firewall Anda memblokir `speech.platform.bing.com`, beralih ke
  ElevenLabs, Google Cloud TTS, atau **Piper TTS** (sepenuhnya offline).

### Dialog "Piper voice not installed"

Halaman Voice / Dubbing / Translate Text memeriksa pre-flight bahwa
suara Piper untuk bahasa target Anda ada di disk sebelum worker mana
pun mulai. Jika tidak, Anda akan melihat modal dengan tombol
**Buka Pengaturan**.

Untuk mengunduh suara:

1. Klik **Buka Pengaturan** di dialog (atau buka
   **Pengaturan → Suara** manual).
2. Pastikan **Metode TTS** diset ke **Piper TTS**.
3. Klik **Unduh suara sekarang** untuk membuka dialog perpustakaan suara.
4. Temukan baris bahasa target Anda, lalu klik **Female voice** atau
   **Male voice** di sebelahnya. Suara adalah file ONNX ~25–60 MB
   yang diunduh dari HuggingFace; sekali per bahasa.
5. Tutup dialog dan jalankan ulang job translasi / voice / dub Anda.

Jika bahasa target Anda tidak ada di list, ia tidak punya cakupan
Piper — mesin jatuh diam-diam ke Edge TTS pada saat sintesis, jadi
Anda sebenarnya tidak perlu mengunduh apa pun. 13 bahasa tanpa suara
Piper hari ini: Belarus, Bengali, Mandarin (Tradisional), Kroasia,
Estonia, Ibrani, Jepang, Khmer, Korea, Lituania, Melayu, Mongolia, Thai.

Halaman **Terjemahan Langsung** adalah satu-satunya tempat yang
*tidak* akan menampilkan dialog ini — mengganggu stream live dengan
modal akan lebih buruk daripada fallback, jadi kasus suara hilang
di sana diam-diam menuju Edge TTS.

## Error terjemahan dokumen

### Terjemahan PDF gagal di halaman tertentu

PDF menggunakan checkpointing per halaman — halaman sukses tidak
diulang. Halaman yang gagal log stack ke `app.log`; tersangka umum:

- Halaman adalah **scan tanpa layer teks** dan OCR tidak dikonfigurasi.
  Atur **Pengaturan → OCR** (lihat [Mesin OCR](setup/ocr-engines.md)).
- Halaman berisi **layout matematika kompleks** yang LLM hancurkan.
  Coba model lebih kuat (varian Pro, bukan Flash).

### Terjemahan Office merusak format

- **Format modern** (`.docx`, `.xlsx`, `.pptx`) — format dipreservasi
  per run via round-trip HTML. Jika Anda melihat tag `<b>` nyasar di
  output, LLM tidak menutupnya — jalankan ulang dengan model lebih kuat.
- **Format legacy** (`.doc`, `.xls`, `.ppt`) — aktifkan
  **Pengaturan → Terjemahan → Auto-convert legacy** untuk kesetiaan
  jauh lebih baik. Pipeline mengonversi ke `.docx` dulu, terjemahkan,
  konversi balik.

### Antrian terjemahan berhenti di tengah batch

Keluar aplikasi dan periksa database:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

Baris `Translating` yang tidak disentuh dalam menit berarti worker
crash diam-diam. Jalankan ulang aplikasi desktop — auto-resume task
Pending / Translating saat startup.

## Masalah lintas-fungsi

### Beberapa file sekaligus diam-diam diterjemahkan sebagai satu

Jatuhkan satu file pada satu waktu, ATAU periksa kolom **Files** di
header antrian — harus menampilkan jumlah yang Anda jatuhkan. Cap
100 file menampilkan notifikasi saat dilampaui.

### Sidebar menampilkan spinner selamanya

Menunjukkan worker masih ditandai sebagai berjalan. Keluar aplikasi
bersih (tanpa SIGKILL) — autouse cleanup hooks reset flag. Jika
SIGKILL meninggalkan state stuck, bersihkan worker DB manual:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Di mana log? {: #where-are-the-logs }

| OS | Path |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Log selalu menangkap DEBUG+ terlepas dari verbositas konsol. Output
konsol default INFO+; lewatkan `--verbose` ke CLI untuk mencerminkan
log file lengkap di stdout.

## Masih stuck?

- Lihat [FAQ](faq.md) untuk pertanyaan tingkat desain.
- Buat issue di <https://github.com/cadic2603/ai-translate/issues>
  dengan: OS, versi Python, perintah yang gagal, slice relevan
  `app.log`, dan deskripsi yang Anda harapkan.
