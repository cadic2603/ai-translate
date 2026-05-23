---
description: "Pertanyaan umum tentang AI Translate: format file yang didukung, fitur gratis vs berbayar, penggunaan offline, pilihan provider LLM, dan pemilihan mesin OCR."
---

# Pertanyaan yang sering diajukan

## Umum

### Apakah berfungsi offline?

Sebagian besar ya. Khususnya:

- **Terjemahan** membutuhkan LLM. API Gemini gratis adalah online;
  **Ollama / LM Studio lokal** melalui pengaturan Custom Provider
  sepenuhnya offline.
- **OCR** dengan **Tesseract** atau **EasyOCR** offline.
- **STT** dengan **Whisper** (default) offline.
- **TTS** dengan **Edge TTS** (default) online; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** online (gratis atau berbayar);
  **Piper TTS** adalah TTS neural sepenuhnya offline — tanpa key,
  tanpa panggilan jaringan setelah Anda mengunduh suara per bahasa
  (file ONNX ~25–60 MB) via **Pengaturan → Suara → Piper TTS →
  Unduh suara sekarang**.

Untuk setup sepenuhnya air-gapped: Custom Provider → LLM lokal,
Tesseract atau EasyOCR untuk OCR, Whisper untuk STT, dan Piper TTS
untuk output suara.

### Di mana file terjemahan saya disimpan?

Di sebelah aslinya secara default, dengan suffix
`_translated_<src>_<tgt>` (mis. `report_translated_en_fr.docx`).
Override per fitur di **Pengaturan → Umum → Path penyimpanan terjemahan**.

### Di mana pengaturan saya disimpan?

File INI di:

| OS | Path |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

API key tinggal di keychain OS (bukan di INI). Riwayat terjemahan
tinggal di DB SQLite di direktori data.

### Bagaimana data saya ditangani?

- **Local-first** — teks tidak pernah meninggalkan mesin Anda kecuali
  Anda memanggil layanan LLM / OCR / STT / TTS cloud.
- **Tanpa telemetri** — aplikasi tidak phone-home. Satu-satunya
  permintaan keluar yang dilakukan aplikasi sendiri adalah
  pemeriksaan update GitHub Releases opsional (toggle di
  **Pengaturan → Umum**); backend cloud hanya memanggil vendor
  masing-masing.
- **API key** — disimpan di keychain OS Anda. Fallback keychain
  aplikasi desktop adalah INI plain text ketika tidak ada daemon
  keychain.

### Bisakah saya menerjemahkan Google Doc / halaman Notion?

Tidak langsung. Ekspor ke `.docx` dulu, terjemahkan, lalu impor file
terjemahan kembali. Sama untuk Notion (ekspor sebagai Markdown / HTML),
Confluence (ekspor sebagai `.docx`), dll.

## Memilih model / mesin

### Model LLM mana yang harus saya gunakan?

Untuk kebanyakan pengguna:

- **Varian Gemini Flash apa pun** — tier gratis, cepat, mengejutkan
  bagus. Gunakan untuk terjemahan harian. Nama mirip `gemini-2.5-flash`,
  `gemini-3-flash-preview`, dll., tergantung yang tersedia.
- **Varian Gemini Pro apa pun** — bayar per token, kualitas lebih
  tinggi. Gunakan untuk dokumen penting (legal, teknis, customer-facing).
- **Ollama lokal** dengan model 7B-13B — saat Anda butuh offline /
  privasi.

Pemilih model per fitur berarti Anda dapat menggunakan model cepat
untuk terjemahan gaya chat dan menyimpan yang mahal untuk dokumen.

### Mesin OCR mana yang harus saya gunakan?

- **Tesseract** untuk teks cetak bersih dalam script utama. Gratis,
  offline, cepat.
- **EasyOCR** untuk script non-Latin (terutama CJK) dan gambar lebih
  noisy.
- **Google Cloud Vision** untuk tulisan tangan, script campuran, dan
  akurasi tertinggi saat Anda dapat membayar.

### Metode STT mana yang harus saya gunakan?

- **Whisper local** untuk offline / privasi.
- **Soniox** untuk rekaman multi-pembicara — label pembicara melakukan
  round-trip ke SRT Anda.
- **Google Cloud STT** untuk audio telepon / medis (model domain
  mereka bagus).
- **Gemini Live** untuk terjemahan speech-to-speech real-time.

### Backend TTS mana?

- **Edge TTS** untuk suara berkualitas tinggi gratis.
- **ElevenLabs** untuk suara premium / branded / clone.
- **Google Cloud TTS** untuk suara WaveNet di bahasa long-tail di
  mana Edge cakupannya tipis.
- **Gemini TTS** untuk suara prebuilt natural gratis menggunakan
  ulang API key Gemini Anda.
- **Piper TTS** saat Anda butuh output suara **offline / air-gapped**.
  Trade-off: setiap bahasa membutuhkan unduhan suara satu kali
  ~25–60 MB via **Pengaturan → Suara → Piper TTS → Unduh suara
  sekarang**, dan 13 dari 45 bahasa aplikasi tidak punya suara Piper
  (yang itu jatuh diam-diam ke Edge TTS).

## Workflow

### Bagaimana saya menerjemahkan seluruh folder?

Jatuhkan folder ke drop zone **Terjemahkan Dokumen**. File yang
didukung di dalamnya (rekursif) diantrikan; semua lainnya diam-diam
dilewati. Ada cap 100 file per drop; batch lebih besar → bagi
menjadi beberapa drop.

### Bisakah saya pause dan resume terjemahan?

Ya. Keluar aplikasi kapan saja — task Pending / Translating resume
di launch berikutnya. Per-task checkpointing berarti halaman 47 dari
100 PDF tidak diulang saat Anda resume.

### Bisakah saya mengedit terjemahan secara manual?

Untuk **Terjemahkan Teks** — ya, klik panel kanan dan ketik. Edit
auto-save ke record riwayat entri.

Untuk **Terjemahkan Dokumen** — buka file terjemahan di editor biasa
Anda (Word, LibreOffice, dll.) dan edit di sana. Aplikasi tidak
melakukan round-trip edit kembali ke riwayat.

### Bisakah saya menerjemahkan secara massal daftar string?

Gunakan CLI:

```bash
ait *.txt --target French
```

Atau untuk string in-process (mis. string UI yang diekstrak dari kode),
panggil tool MCP `translate_text` dengan list, atau gunakan API Python
langsung:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glosarium

### Mengapa LLM tidak menggunakan glosarium saya?

Tiga hal untuk diperiksa:

1. Set **aktif** (checkbox dicentang).
2. Istilah sumber dalam glosarium Anda benar-benar muncul di teks
   sumber (kompresi per panggilan hanya mengirim entri yang cocok
   dengan teks batch ke LLM — menghemat token, tapi berarti istilah
   sumber dengan typo tidak terlihat).
3. Model cukup kuat — `flash-lite` kadang mengabaikan petunjuk yang
   `flash` dan `pro` honor.

### Apakah istilah glosarium dicocokkan tanpa memperhatikan aksen?

Ya. Baik pencarian glosarium maupun bilah pencarian di halaman
Glosarium menggunakan fungsi normalisasi yang menghapus aksen dan
case. Jadi `cafe`, `Café`, dan `CAFE` semua cocok dengan entri yang
sumbernya adalah `Café`.

## Privasi

### Apakah Anda mengumpulkan data penggunaan?

Tidak. Aplikasi tidak punya SDK analytics. Pemeriksaan update
opsional polling satu endpoint GitHub Releases saat startup;
togglable di **Pengaturan → Umum**.

### Apakah API key saya aman?

Disimpan di keychain OS Anda (Keychain di macOS, Credential Manager
di Windows, Secret Service di Linux). Proses lain tidak dapat
membacanya tanpa izin eksplisit Anda. Fallback (saat tidak ada
daemon keychain — biasanya server Linux headless) adalah INI plain
text di bawah direktori konfigurasi user Anda; di mode itu key
dilindungi izin file tapi tidak dienkripsi kriptografi.
