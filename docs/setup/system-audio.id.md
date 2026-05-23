---
description: Tangkap audio sistem di Linux, macOS, dan Windows untuk halaman Live AI Translate — terjemahkan suara apa pun yang diputar di komputer kamu secara real-time.
---

# Penangkapan Audio Sistem (Live)

Halaman **[Terjemahan Live](../features/live-translation.md)** dapat
menangkap **audio sistem** (semua yang diputar di speaker kamu)
sehingga kamu bisa subtitle / menerjemahkan media apa pun — panggilan
Zoom, YouTube, Netflix, game, suara sistem.

Di **Pengaturan → Live → Sumber audio** (atau combo di atas halaman
Live), pilih:

- **Mikrofon** — hanya mikrofon kamu
- **Audio sistem** — hanya apa pun yang diputar di speaker kamu
- **Keduanya** — keduanya dicampur (bagus untuk menarasikan media
  atau menangkap rapat hibrida)

Saat kamu memilih **Audio sistem** atau **Keduanya**, aplikasi
mengirim ke backend penangkapan yang tepat untuk OS kamu. Banner
peringatan inline dengan link instalasi yang dapat diklik muncul
jika prasyarat OS tidak terpenuhi, sehingga kamu tidak harus memulai
sesi untuk mengetahui sesuatu hilang.

## Linux (PulseAudio / PipeWire)

Bekerja out-of-the-box di setiap distro modern.

Aplikasi menggunakan `parec` (PulseAudio Recorder) untuk menyadap
**sumber monitor** dari sink default kamu. Shim kompatibilitas
PulseAudio dari PipeWire membuat ini transparan — kamu tidak butuh
PulseAudio mentah.

```bash
parec --version    # harus mencetak sesuatu
```

Jika `parec` hilang, banner peringatan mendeteksi pengelola paket
distro kamu dan memasukkan perintah instalasi yang tepat — misalnya:

> Penangkapan audio sistem membutuhkan PulseAudio atau PipeWire — jalankan `sudo apt-get install pulseaudio`.

Terdeteksi di apt-get / dnf / pacman / zypper / apk; kamu bisa
copy-paste perintah langsung ke terminal.

## macOS

CoreAudio tidak mengekspos audio sistem secara native, jadi kamu
butuh **perangkat loopback virtual** — pasang salah satu dari:

- **[BlackHole](https://existential.audio/blackhole/)** — gratis, open source
- **[Loopback](https://rogueamoeba.com/loopback/)** — berbayar, GUI dipoles
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — opsi gratis legacy
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — berbayar

Aplikasi auto-detect mereka via
`ffmpeg -f avfoundation -list_devices` dan menggunakan match
pertama. Tidak perlu mengatur loopback sebagai output / input
default kamu — penangkapan terjadi langsung melalui backend
avfoundation `ffmpeg`.

Setelah memasang, pilih saja **Audio sistem** di combo halaman Live
dan banner peringatan menghilang.

## Windows

Native — **tidak ada software ekstra yang dibutuhkan** dalam
sebagian besar kasus.

Aplikasi berbicara langsung dengan **WASAPI loopback** via paket
Python [`soundcard`](https://github.com/bastibe/SoundCard) (dipasang
otomatis dengan aplikasi di Windows). Ini adalah API loopback native
yang sama yang digunakan aplikasi desktop Tauri / Rust; ia
menangkap output speaker default tanpa kabel virtual.

Jika karena suatu alasan WASAPI loopback tidak tersedia (versi
Windows lebih lama, driver audio tidak biasa), aplikasi jatuh
kembali ke `ffmpeg -f dshow` terhadap perangkat DirectShow loopback
virtual. Pilih salah satu dari:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — gratis, menyediakan `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — gratis, datang sebagai `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — opsi on-board legacy, sering dinonaktifkan secara default

Aplikasi memeriksa ini secara berurutan dan menggunakan yang pertama
hadir.

## Mengapa "Keduanya" menangkap suara kamu DAN audio sistem

Dalam mode **Keduanya**, aplikasi membuka DUA stream penangkapan
secara paralel — mikrofon kamu via `sounddevice`, audio sistem via
backend spesifik OS di atas — dan mencampurnya pada granularitas
blok sampel. Ini adalah mode yang tepat untuk menarasikan video,
atau untuk menangkap kedua sisi rapat hibrida (suara kamu plus
peserta di speaker).

> **Tip:** jika kamu mendengar gema atau mendapat caption duplikat,
> kamu memiliki audio sistem yang masuk melalui mikrofon kamu
> (speaker keras → mikrofon menangkapnya). Beralih ke **Audio
> sistem** saja, atau gunakan headphone.

## Pemecahan masalah

| Gejala | Kemungkinan penyebab |
|---|---|
| Halaman Live mulai tetapi tanpa caption | Sumber audio salah dipilih, atau mikrofon default kamu di-mute |
| Caption untuk suara kamu tetapi tidak untuk video YouTube | Prasyarat audio sistem tidak terpasang (banner harus menampilkan instruksi instalasi) |
| Caption dua kali (gema) | Mode "Keduanya" menangkap audio sistem dua kali — sekali dari speaker via mikrofon, sekali via loopback. Beralih ke Audio sistem saja atau gunakan headphone |
| Banner tetap terlihat setelah memasang software yang hilang | Beralih tab dan kembali — banner mengecek ulang saat tampilan halaman |
| macOS: BlackHole terpasang tetapi banner masih ada | Konfirmasi bahwa BlackHole ada di daftar perangkat audio `ffmpeg -f avfoundation -list_devices true -i ""`; aplikasi perlu melihatnya di sana |
| Windows: WASAPI loopback gagal meskipun tanpa error | Coba pasang VB-Audio Virtual Cable sebagai fallback; versi Windows lebih lama atau beberapa driver audio tidak mengekspos loopback via `soundcard` |
