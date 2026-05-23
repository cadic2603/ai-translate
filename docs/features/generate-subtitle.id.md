---
description: Buat subtitle SRT, VTT, ASS, atau SSA dari audio atau video apa pun — menggunakan Whisper atau Google Cloud Speech-to-Text untuk transkripsi berkualitas tinggi.
---

# Buat Subtitle (STT)

Transkripsi audio atau video menjadi subtitle dengan timing. Mengambil
ucapan dan memancarkan SRT / VTT / ASS / SSA — dengan terjemahan
opsional dalam pass yang sama.

## Yang Anda butuhkan

- **FFmpeg** di `PATH` untuk decoding audio/video — lihat
  [Setup FFmpeg](../setup/ffmpeg.md).
- Backend transkripsi, salah satu dari:
    - **faster-whisper** — lokal, offline, gratis (default; tidak perlu setup)
    - **Google Cloud Speech-to-Text** — cloud, berbayar, lebih akurat pada audio bising. Lihat [Setup Google Cloud](../setup/google-cloud.md).
    - **Soniox** — cloud, berbayar, real-time dan diarisasi pembicara. Lihat [Setup Soniox](../setup/soniox.md).

## Langkah

1. Klik **Buat Subtitle** di sidebar.
2. Jatuhkan satu atau lebih file audio / video (`.mp3`, `.wav`, `.m4a`,
   `.flac`, `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`, `.avi`,
   `.mov`, `.wmv`).
3. Pilih **Bahasa sumber** (bahasa yang *diucapkan* di audio) — biarkan
   `Auto-deteksi` agar Whisper menemukannya.
4. Pilih **Bahasa target** — pilih `Tanpa terjemahan` untuk transkrip
   sederhana, atau salah satu dari 45 bahasa yang didukung untuk
   menerjemahkan transkrip dalam pass yang sama.
5. Pilih **Format output** (SRT / VTT / ASS / SSA).
6. Klik **Buat** (atau `Ctrl+Enter`).
7. Perhatikan antrean. **Buka** baris ketika selesai.

## Pilihan format

| Format | Terbaik untuk |
|---|---|
| **SRT** | Universal — hampir semua pemutar mendukung |
| **VTT** | Elemen `<track>` HTML5 `<video>` |
| **ASS / SSA** | Karaoke, subtitle bergaya, alur fansub |

Keempat format round-trip melalui parser yang sama, jadi Anda dapat
mengganti format output saat re-translate tanpa kehilangan timing.

## Ukuran model Whisper

Ganti di **Pengaturan → Subtitle**:

| Model | Ukuran | Kecepatan | Akurasi |
|---|---|---|---|
| `tiny` | ~75 MB | sangat cepat | rendah |
| `base` (default) | ~150 MB | cepat | layak |
| `small` | ~500 MB | menengah | baik |
| `medium` | ~1.5 GB | lambat | tinggi |
| `large` | ~3 GB | sangat lambat | terbaik |

Model diunduh pada pemakaian pertama dan di-cache secara lokal. Pada
koneksi lambat, run pertama terasa lama; berikutnya cepat.

## Perbandingan metode STT

| Backend | Biaya | Online? | Diarisasi pembicara | Bahasa |
|---|---|---|---|---|
| **Whisper** (lokal) | Gratis | Tidak | Tidak | 99 |
| **Google Cloud STT** | Berbayar | Ya | Ya (model `latest_long`) | 125+ |
| **Soniox** | Berbayar | Ya | Ya (label per-token) | 60+ |

Ganti di **Pengaturan → Subtitle → Metode STT**.

## Tips

- **Tombol Stop** — menginterupsi batch yang sedang berjalan. File
  yang antri di belakang yang aktif tetap antri; Anda dapat melanjutkan
  nanti.
- **Buat ulang** — klik kanan pada entri Done untuk menjalankan ulang
  dengan format / bahasa / metode STT yang berbeda.
- **Audio panjang** — Whisper menangani audio berjam-jam dengan baik;
  anggarkan ~1 menit pemrosesan per menit audio pada CPU dengan model `base`.

## Pintasan

| Pintasan | Tindakan |
|---|---|
| `Ctrl+Enter` | Buat |
| `Ctrl+O` | Browse |
| `Ctrl+F` | Fokus pencarian riwayat |
