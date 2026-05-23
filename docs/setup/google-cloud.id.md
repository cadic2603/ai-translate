---
description: Hubungkan Google Cloud ke AI Translate untuk Vision OCR, Speech-to-Text, dan Text-to-Speech — siapkan kunci API dan aktifkan layanan yang relevan.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Satu kunci API Google Cloud mendukung tiga backend opsional:

- **Vision OCR** — mesin OCR berbayar (1.000 gratis / bulan)
- **Speech-to-Text v1** — STT berbayar (60 menit / bulan gratis)
- **Text-to-Speech v1** — TTS berbayar (1 M karakter / bulan gratis
  untuk WaveNet)

Kamu hanya perlu mengaktifkan API yang benar-benar kamu gunakan.

## Dapatkan kunci API

1. [Buat proyek Google Cloud](https://console.cloud.google.com/projectcreate)
2. Buka pustaka API: <https://console.cloud.google.com/apis/library>
3. Aktifkan salah satu dari:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Buat kunci API](https://console.cloud.google.com/apis/credentials):
   klik **+ Create Credentials → API key**
5. Salin kunci (terlihat seperti `AIza...`).

!!! tip "Batasi kunci"
    Di halaman detail kunci API, di bawah **API restrictions**,
    batasi kunci hanya untuk API yang telah kamu aktifkan. Dengan
    begitu kunci yang bocor tidak bisa menumpuk tagihan pada layanan
    yang tidak ingin kamu gunakan.

## Konfigurasi di aplikasi

Di **Pengaturan → Layanan**:

1. Tempel ke **Kunci API Google Cloud** → **Simpan**

Satu kunci ini sekarang tersedia untuk ketiga layanan Google.

## Aktifkan setiap layanan

### Vision OCR

Di **Pengaturan → OCR → Metode OCR = Google Cloud OCR**.

Begitu saja — ia akan menggunakan kunci yang sama dari Layanan.

### Speech-to-Text

Di **Pengaturan → Subtitle → Metode STT = Google Cloud** (untuk
halaman Subtitle / Suara) atau **Pengaturan → Live → Metode STT =
Google Cloud** (untuk halaman Live).

Di **Pengaturan → Subtitle → Model STT Google**, pilih model
pengenalan:

| Model | Terbaik untuk |
|---|---|
| `latest_long` (default) | Audio format panjang (wawancara, kuliah) |
| `latest_short` | Perintah suara, frasa pendek |
| `phone_call` | Audio telepon (8 kHz) |
| `medical_dictation` / `medical_conversation` | Audio domain medis |

### Text-to-Speech

Di **Pengaturan → Suara → Metode TTS = Google Cloud TTS**.

Secara default server memilih suara berdasarkan bahasa dan gender —
itu yang dibutuhkan kebanyakan pengguna. Mengunci suara Google
spesifik (misalnya `en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`)
didukung oleh mesin tetapi belum diekspos sebagai bidang Pengaturan;
itu bisa diatur dengan mengedit `voice/google_tts_voice_name` di
`settings.ini` secara langsung. ID suara tercantum di
<https://cloud.google.com/text-to-speech/docs/voices>.

## Error umum

| Error | Kemungkinan penyebab |
|---|---|
| `AUTH_ERROR` | Kunci salah / kedaluwarsa. Tempel ulang di Pengaturan → Layanan. |
| `API not enabled` | Kamu belum mengaktifkan API spesifik (Vision / Speech / TTS) di proyek Cloud ini. |
| `QUOTA_ERROR` | Batas tier gratis tercapai untuk API ini. Tunggu, atau upgrade billing. |
| `INVALID_ARGUMENT_ERROR` | Nama suara tidak ada dalam bahasa yang kamu pilih. |

## Penjaga biaya

!!! warning
    Ketiga API Google adalah post-paid — setelah kamu melebihi tier
    gratis kamu mulai ditagih tanpa henti. Atur [peringatan anggaran](https://console.cloud.google.com/billing/budgets)
    pada proyek Cloud sebelum melakukan pekerjaan volume tinggi.
