---
description: Hubungkan ElevenLabs ke AI Translate untuk TTS neural berkualitas tinggi — hasilkan voiceover dalam 30+ bahasa dengan ucapan realistis dan ekspresif.
---

# ElevenLabs (TTS)

Sintesis text-to-speech neural premium. Digunakan oleh halaman
**[Buat Suara](../features/generate-voice.md)**,
**[Dubbing](../features/dubbing.md)**, dan
**[Terjemahan Live](../features/live-translation.md)** ketika kamu
memilih ElevenLabs sebagai metode TTS.

## Dapatkan kunci API

1. Daftar di <https://elevenlabs.io>
2. Buka <https://elevenlabs.io/app/settings/api-keys>
3. Klik **+ Create New Key**, beri nama (misal "ai-translate"),
   salin kunci (terlihat seperti `sk_...`)

Tier gratis memberi kamu ~10.000 karakter / bulan, cukup untuk
mencoba. Penggunaan produksi mulai dari sekitar $5/bulan.

## Konfigurasi di aplikasi

Di **Pengaturan → Layanan**:

1. Tempel kunci ke **Kunci API ElevenLabs** → **Simpan**
2. Masukkan **ID Suara** pilihan kamu di **ID Suara** (temukan ID di
   <https://elevenlabs.io/app/voice-lab>; salin ID dari URL suara).
   Biarkan kosong agar ElevenLabs memilih default.

Di **Pengaturan → Suara**:

1. Atur **Metode TTS** ke **ElevenLabs**
2. Pilih **Model ElevenLabs**:

    | Model | Terbaik untuk |
    |---|---|
    | `eleven_multilingual_v2` (default) | Penggunaan umum, latensi/kualitas seimbang |
    | `eleven_v3` | Kualitas tertinggi (gunakan untuk dubbing produksi) |
    | `eleven_flash_v2_5` | Latensi terendah (gunakan untuk Terjemahan Live) |

## Apa yang didukungnya

| Halaman | Gunakan ElevenLabs saat |
|---|---|
| **Buat Suara** | Kamu ingin voiceover berkualitas premium dari file subtitle |
| **Dubbing** | Kamu ingin trek dubbing berkualitas tinggi pada video yang diterjemahkan |
| **Terjemahan Live** | Kamu ingin pemutaran ucapan dari teks terjemahan secara real-time |

## Kloning suara

ElevenLabs mendukung kloning suara kustom (paket berbayar). Setelah
kamu mengkloning suara di situs ElevenLabs, tempel ID Suaranya ke
**Pengaturan → Layanan → ID Suara** dan pipeline dubbing /
pembuatan suara akan menggunakannya.

## Peringatan

!!! warning "Pemeriksaan pre-flight"
    Halaman Suara / Dubbing memeriksa kunci API ElevenLabs kamu sudah
    diatur *sebelum* mulai bekerja. Jika hilang, kamu akan mendapat
    dialog ramah yang mengarahkan kamu ke Pengaturan, bukan tugas
    setengah jalan.

!!! tip "Mode Live jatuh kembali secara otomatis"
    Di halaman **Terjemahan Live**, jika kamu memilih ElevenLabs
    tetapi belum mengkonfigurasi kunci, aplikasi jatuh kembali ke
    **Edge TTS** (gratis) dan mengumumkan fallback di label status
    sehingga kamu bisa memperbaikinya saat nyaman.

!!! info "FFmpeg masih diperlukan"
    ElevenLabs mengembalikan byte audio; aplikasi masih menggunakan
    FFmpeg untuk mengkonversi antar format dan menggabungkan klip
    bertiming menjadi satu file. Lihat [Setup FFmpeg](ffmpeg.md).

## Error umum

| Error | Kemungkinan penyebab |
|---|---|
| `AUTH_ERROR` | Kunci API salah / kedaluwarsa. Tempel ulang di Pengaturan → Layanan. |
| `QUOTA_ERROR` | Batas karakter tier gratis terlampaui, atau paket berbayar habis. |
| `MODEL_NOT_FOUND` | Model ElevenLabs yang dipilih tidak lagi tersedia; pilih lainnya di Pengaturan → Suara. |
