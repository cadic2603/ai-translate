---
description: Konversi subtitle menjadi audio terucap dengan Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS, atau Piper TTS offline — mempertahankan timing SRT untuk pembuatan suara berkualitas dubbing.
---

# Buat Suara (TTS)

Sintesis file subtitle (dengan timing) atau teks sembarang menjadi
audio MP3 / WAV. Lima backend TTS: Edge TTS (gratis), ElevenLabs
(kualitas tinggi), Google Cloud TTS, Gemini TTS (tier gratis), dan
Piper TTS (offline).

## Yang kamu butuhkan

- **FFmpeg** di `PATH` — lihat [Setup FFmpeg](../setup/ffmpeg.md).
- Backend TTS, salah satu dari:
    - **Edge TTS** — gratis, tanpa kunci, default. Menggunakan suara
      cloud Microsoft Edge.
    - **ElevenLabs** — berbayar, kualitas tertinggi. Lihat [Setup ElevenLabs](../setup/elevenlabs.md).
    - **Google Cloud TTS** — berbayar, sangat baik. Lihat [Setup Google Cloud](../setup/google-cloud.md).
    - **Gemini TTS** — tier gratis, suara prebuilt natural. Menggunakan
      ulang kunci API Gemini kamu yang ada dari tab LLM — tanpa setup
      tambahan.
    - **Piper TTS** — TTS neural sepenuhnya offline. Tanpa kunci API,
      tanpa panggilan jaringan — suara adalah file ONNX ~25–60 MB
      yang diunduh sekali via **Pengaturan → Suara → Piper TTS →
      Unduh suara sekarang**. 32 dari 45 bahasa aplikasi memiliki
      suara Piper hari ini; bahasa tanpa cakupan Piper diam-diam jatuh
      kembali ke Edge TTS pada saat sintesis.

## Langkah demi langkah

1. Klik **Buat Suara** di sidebar.
2. Drop satu atau lebih file subtitle `.srt` / `.vtt` / `.ass` /
   `.ssa`.
3. Pilih **Bahasa** (auto-detected dari nama file subtitle bila
   memungkinkan — misalnya `_translated_en_id.srt` terdeteksi sebagai
   Indonesia).
4. Pilih **Gender suara** — `Perempuan` atau `Laki-laki`.
5. Pilih **Format output** — `.mp3` (default) atau `.wav`.
6. Klik **Buat** (atau `Ctrl+Enter`).
7. **Buka** baris ketika selesai — ia diputar di aplikasi audio
   default kamu.

## Output

Kamu mendapat satu file audio dengan jalur suara ditempatkan pada
timestamp setiap subtitle. Celah hening mengisi waktu antar cue
sehingga audio tetap sinkron dengan timing asli.

## Memilih backend TTS

| Backend | Biaya | Suara | Catatan |
|---|---|---|---|
| **Edge TTS** | Gratis | Ratusan, semua bahasa utama | Default. Tanpa setup. |
| **ElevenLabs** | Berbayar (~$5/bln tier entry) | Suara neural premium, kloning suara | Kualitas tertinggi. ID suara diatur di Pengaturan → Layanan. |
| **Google Cloud TTS** | Berbayar (~$4/M karakter; 1 M gratis / bulan) | Suara WaveNet / Studio dalam 50+ bahasa | Suara WaveNet kuat untuk bahasa Eropa. Secara default server memilih suara berdasarkan bahasa + gender. |
| **Gemini TTS** | Tier gratis (kuota Developer API berlaku) | Suara prebuilt natural dalam 24+ bahasa — `Kore` (perempuan default) / `Puck` (laki-laki default) | Menggunakan ulang kunci API Gemini kamu dari tab LLM. Output per panggilan dibatasi ~30 dtk; teks panjang otomatis dipotong di batas kalimat. |
| **Piper TTS** | Gratis, **offline** | Suara neural dalam 32 dari 45 bahasa aplikasi | Tanpa kunci, tanpa jaringan. Suara per-bahasa diunduh on-demand dari **Pengaturan → Suara → Piper TTS → Unduh suara sekarang** (~25–60 MB masing-masing). Pre-flight menangkap suara yang hilang sebelum pekerjaan dimulai. |

Ganti di **Pengaturan → Suara → Metode TTS**.

## Spesifik Piper TTS

Piper adalah satu-satunya backend TTS yang sepenuhnya offline di
aplikasi. Beberapa hal yang perlu diketahui:

- **Dialog perpustakaan suara** — buka via **Pengaturan → Suara →
  Piper TTS → Unduh suara sekarang**. Setiap baris bahasa
  menampilkan tombol unduh `Suara perempuan` dan / atau `Suara
  laki-laki` (beberapa bahasa hanya satu gender). Suara berasal dari
  katalog HuggingFace
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- **Cakupan** — 32 dari 45 bahasa aplikasi memiliki suara Piper. 13
  yang tanpa cakupan (Belarusia, Bengali, Cina (Tradisional),
  Kroasia, Estonia, Ibrani, Jepang, Khmer, Korea, Lituania, Melayu,
  Mongolia, Thai) diam-diam jatuh kembali ke Edge TTS pada saat
  sintesis sehingga sintesis tidak pernah gagal keras pada suara
  yang hilang.
- **Resolusi gender** — saat kamu memilih `Perempuan`, mesin terlebih
  dahulu mencoba suara perempuan untuk bahasa tersebut; jika hanya
  ada suara laki-laki, ia menggunakan itu sebagai gantinya (dan
  sebaliknya). Dicatat pada level INFO.
- **Gerbang pre-flight** — sebelum eksekusi Suara dimulai, halaman
  memeriksa bahwa suara Piper per-bahasa ada di disk. Jika hilang,
  kamu mendapatkan dialog modal dengan tombol **Buka Pengaturan**
  yang membawa kamu langsung ke perpustakaan suara sehingga kamu
  bisa mengunduhnya tanpa kehilangan antrian kamu.

## Spesifik Gemini TTS

Gemini TTS menggunakan `gemini-2.5-flash-preview-tts` via Developer
API. Beberapa hal yang perlu diketahui:

- **Pemilihan suara** saat ini berdasarkan gender — Perempuan
  memetakan ke `Kore`, Laki-laki ke `Puck`. Keduanya adalah suara
  jelas, netral yang bekerja di seluruh bahasa tanpa terdengar
  terlalu berkarakter.
- **Batas panjang output** — setiap panggilan API Gemini
  mengembalikan paling banyak ~30 dtk ucapan. Aplikasi memotong
  teks input di bawah `_GEMINI_TTS_MAX_BYTES` (~2000 byte ≈ 30 dtk)
  pada batas kalimat, kemudian menggabungkan potongan via FFmpeg.
  Kamu tidak akan mengalami pemotongan pada teks subtitle normal.
- **Format audio** — Gemini menghasilkan PCM mentah pada 24 kHz mono
  s16le; aplikasi mentranscoding per potongan ke MP3 (atau WAV jika
  kamu memilihnya) sehingga file akhir sesuai dengan format output
  yang kamu pilih.
- **Vertex AI belum didukung untuk TTS** — bahkan jika tab LLM kamu
  dikonfigurasi untuk Vertex, Gemini TTS masih membutuhkan kunci API
  Developer. Aplikasi menaikkan `AUTH_ERROR` di muka jika hilang.

## Model ElevenLabs

Tiga model terbuka:

| Model | Latensi | Kualitas | Digunakan untuk |
|---|---|---|---|
| `eleven_multilingual_v2` (default) | Sedang | Tinggi | TTS umum |
| `eleven_v3` | Sedang | Tertinggi | Studio / produksi |
| `eleven_flash_v2_5` | Rendah | Baik | Real-time / mode Live |

Konfigurasi di **Pengaturan → Suara → Model ElevenLabs**.

## Tips

!!! tip "Buat ulang"
    Klik kanan baris → **Buat ulang** untuk menukar gender suara /
    metode TTS / format tanpa menjalankan ulang terjemahan.

!!! tip "Pemeriksaan pre-flight"
    Halaman memvalidasi kunci API ElevenLabs (saat dipilih) dan
    ketersediaan FFmpeg sebelum mulai. Kamu akan melihat dialog yang
    ramah jika ada yang hilang.

!!! warning "Stop atomik"
    Tekan **Stop** selama sintesis dan kamu tidak akan mendapatkan
    MP3 setengah-tertulis di direktori output — file ditulis ke
    lokasi temp dulu, kemudian dipindahkan ke tempat hanya pada
    keberhasilan.

## Pintasan

| Pintasan | Tindakan |
|---|---|
| `Ctrl+Enter` | Buat |
| `Ctrl+O` | Telusuri |
| `Ctrl+F` | Fokus pencarian riwayat |
