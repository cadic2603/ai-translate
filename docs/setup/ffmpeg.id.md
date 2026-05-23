---
description: Instal FFmpeg sehingga AI Translate dapat mendekode audio dan video untuk pembuatan subtitle, sintesis suara, dan dubbing video — diperlukan untuk fitur media.
---

# FFmpeg

FFmpeg diperlukan untuk alur kerja audio / video apa pun:

- **Buat Subtitle** — mendekode audio sumber untuk STT
- **Buat Suara** — menggabungkan klip TTS bertiming menjadi satu
  file
- **Dubbing** — STT → TTS → mux kembali ke video
- **Terjemahan Live** — saat penangkapan audio sistem melalui `parec`

Tidak disertakan — pasang sekali di sistem kamu.

## Instal

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    Atau, untuk build yang lebih lengkap, aktifkan
    [RPM Fusion](https://rpmfusion.org/Configuration) dulu.

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Unduh build statis dari <https://www.gyan.dev/ffmpeg/builds/>
    (build "release essentials" cukup), unzip, lalu tambahkan folder
    `bin/` ke PATH kamu:

    1. Tekan **Win + R**, ketik `sysdm.cpl`, tekan **Enter**
    2. **Advanced → Environment Variables → System variables → Path → Edit**
    3. **New** → tempel jalur absolut folder `bin` FFmpeg
    4. **OK** di semua langkah, restart terminal yang terbuka

## Verifikasi

```bash
ffmpeg -version
```

Kamu harus melihat banner versi dengan `--enable-libx264 --enable-libvpx`
di baris konfigurasi. Jika kamu melihat "command not found",
instalasi tidak berakhir di PATH.

## Pemeriksaan pre-flight di-app

Halaman Suara / Dubbing memanggil `shutil.which("ffmpeg")` sebelum
mulai bekerja. Jika FFmpeg tidak ditemukan, kamu akan melihat dialog
kesalahan yang ramah dengan tautan kembali ke sini, bukan tugas
setengah jalan.

## Kesalahan umum

| Kesalahan | Arti |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` tidak ada di PATH saat halaman mencoba menjalankannya. Instal (di atas) dan restart aplikasi. |

Di server MCP (`ait-mcp`), kesalahan yang sama dibungkus ulang
menjadi pesan yang dapat dibaca:

> *"FFmpeg diperlukan untuk mendekode file audio/video ini tetapi
> tidak terinstal atau tidak ada di PATH. Instal FFmpeg dan coba
> lagi."*
