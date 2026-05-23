---
description: "Terjemahan ucapan real-time: transkripsikan dan terjemahkan mikrofon atau audio sistem secara langsung dengan backend Whisper atau Soniox."
---

# Terjemahan Live

Caption dan terjemahan real-time dari mikrofon, audio sistem, atau
keduanya — dengan jendela overlay always-on-top opsional sehingga
caption berada di atas apa pun yang sedang kamu tonton.

## Apa yang bisa kamu lakukan

- **Caption rapat live** — caption panggilan Zoom / Meet / Teams dalam
  bahasa lain tanpa bergabung sebagai bot penerjemah.
- **Belajar bahasa real-time** — caption konten berbahasa asing
  (film, podcast, kuliah) dengan bahasa nativ kamu sebagai jalur
  terjemahan.
- **Subtitle level sistem** — tangkap audio sistem agar bisa membuat
  subtitle YouTube / Netflix / apa saja yang diputar di speaker kamu.

## Yang kamu butuhkan

- **FFmpeg** di `PATH` — lihat [Setup FFmpeg](../setup/ffmpeg.md).
- Backend STT, salah satu dari:
    - **faster-whisper** — lokal, offline, gratis, default
    - **Soniox** — cloud, berbayar, diarisasi pembicara real-time. Lihat [Setup Soniox](../setup/soniox.md).

- Untuk **penangkapan audio sistem**, backend yang tepat per OS
  dipilih otomatis: Linux menggunakan `parec` (PulseAudio / PipeWire),
  Windows menggunakan WASAPI loopback native (tanpa software tambahan
  di sebagian besar kasus), macOS menggunakan
  `ffmpeg -f avfoundation` terhadap perangkat loopback virtual
  (BlackHole / Loopback / dll.). Banner peringatan inline dengan link
  pemasangan yang dapat diklik muncul jika ada yang kurang. Lihat
  [Setup → Audio sistem](../setup/system-audio.md) untuk instruksi
  pemasangan lengkap per OS.

## Langkah demi langkah

1. Klik **Terjemahan Live** di sidebar.
2. Konfigurasikan sekali di **Pengaturan → Live**:

    - **Bahasa sumber** (bahasa yang diucapkan)
    - **Bahasa target** (atau biarkan kosong untuk hanya transkripsi)
    - **Sumber audio**: Mikrofon / Audio sistem / Keduanya
    - **Metode STT**: Whisper / Soniox

3. Kembali di halaman Live, klik **Mulai** (`Ctrl+Enter`).
4. Transkripsi mengisi panel utama kartu demi kartu. Jendela
   **Overlay** mengambang juga menampilkan caption (seret ke mana pun
   kamu mau).
5. Klik **Berhenti** untuk mengakhiri sesi.

## Tampilan transkripsi

Pilih layout di toolbar:

- **Keduanya bertumpuk** — asli + terjemahan, satu di atas yang lain
- **Keduanya berdampingan** — asli di kiri, terjemahan di kanan
- **Hanya asli** / **Hanya terjemahan**

Tombol toolbar menggunakan suffix **`ON`** / **`OFF`** untuk status
sekilas — misalnya `TTS ON`, `TTS OFF`, `Timestamps ON`, `Overlay OFF`.

Aktifkan/nonaktifkan **timestamps** dengan ikon jam. Aktifkan/
nonaktifkan **pemutaran TTS** dari baris terjemahan dengan ikon
speaker. Mengikuti pilihan kamu di **Pengaturan → Suara → Metode
TTS** — Edge TTS (default), ElevenLabs, Google Cloud TTS, Gemini
TTS, atau **Piper TTS** (sepenuhnya offline). Dengan Piper terpilih,
suara per-bahasa yang hilang **diam-diam jatuh kembali ke Edge TTS**
di tengah stream — tidak ada pre-flight modal di halaman ini, karena
memblokir aliran live dengan dialog unduhan akan lebih buruk daripada
fallback.

## Jendela overlay

Jendela alat yang dapat diseret, diubah ukurannya, dan selalu di
atas. Pintasan:

| Pintasan | Tindakan |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Kurangi / tingkatkan opasitas |
| `Ctrl+Panah` | Pindahkan overlay |
| `Ctrl+0` / `Ctrl+9` | Perbesar / kecilkan |

Posisi, ukuran, opasitas, dan ukuran font tetap antar sesi.

### Sinkronisasi langsung dengan Pengaturan

Kontrol ukuran font dan opasitas bekerja dua arah: menggeser
penggeser **Ukuran font** atau **Opasitas** di **Pengaturan →
Terjemahan Langsung → Konfigurasi Overlay** memperbarui overlay
yang terbuka secara real-time, dan sebaliknya, menekan `+` / `-`
/ `Ctrl+[` / `Ctrl+]` di dalam overlay memperbarui penggeser di
Pengaturan. Tidak perlu memulai ulang overlay.

### Placeholder status kosong

Sebelum audio ditangkap, overlay menampilkan placeholder
("Tekan Mulai..." idle / "Mendengarkan..." setelah Mulai diklik)
yang mencerminkan status kosong jendela utama — pertukarannya
tetap sinkron dengan pil status yang berjalan. Placeholder akan
diskalakan dengan lebar × tinggi overlay saat ini sehingga tetap
dapat dibaca pada ukuran jendela apa pun.

### Mode keterangan minimal

Kotak centang **Tampilkan keterangan minimal** di Pengaturan →
Terjemahan Langsung → Konfigurasi Overlay menyembunyikan label
waktu dan pembicara di overlay sambil tetap menampilkannya di
jendela utama. Berguna saat overlay dibagikan dengan audiens
(mode presenter / berbagi layar) tetapi Anda tetap ingin
metadata lengkap di tampilan kerja Anda. Sakelar ini hanya
untuk overlay — tidak mengubah preferensi "Label pembicara"
Anda untuk jendela utama.

## Simpan transkripsi

Klik **Simpan Transkripsi** untuk mengekspor sesi ke file `.txt`
dengan timestamps, pembicara, baris asli, dan baris terjemahan.

## Memilih backend STT

| Backend | Terbaik untuk | Biaya | Latensi |
|---|---|---|---|
| **Whisper** (lokal) | Offline, sensitif privasi | Gratis | Sedang (~1 d setelah akhir kalimat) |
| **Soniox** | Rapat multi-pembicara | Berbayar (~$0.005 / mnt) | Rendah (real-time) |

## Peringatan

!!! warning "Pemilihan mikrofon"
    Input mikrofon selalu menggunakan **perangkat default OS** —
    tidak ada pemilih dalam aplikasi (sounddevice menampilkan terlalu
    banyak plugin ALSA virtual untuk berguna, dan OS sudah memiliki
    UI mikrofon default). Atur mikrofon pilihanmu di pengaturan
    suara OS sebelum mulai.

!!! warning "Backpressure TTS"
    Antrian TTS dibatasi pada 3 kalimat terbaru — audio antrian yang
    lebih lama dibuang jika sintesis tertinggal. Ini menjaga
    pemutaran ucapan dekat dengan caption di layar.

!!! tip "ElevenLabs tanpa kunci"
    Jika kamu mengatur metode TTS ke ElevenLabs tetapi tidak ada
    kunci API yang dikonfigurasi, halaman Live otomatis jatuh kembali
    ke Edge TTS dan mengumumkan fallback di label status.

## Pintasan

| Pintasan | Tindakan |
|---|---|
| `Ctrl+Enter` | Mulai / Berhenti |
| `Ctrl+K` | Bersihkan log (dengan konfirmasi) |
| `Ctrl+[` / `Ctrl+]` | Atur opasitas overlay |
