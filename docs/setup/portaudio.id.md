---
description: Tangkapan audio mikrofon lintas platform untuk Terjemahan Langsung.
---

# Pengaturan PortAudio (Mikrofon)

Fitur [Terjemahan Langsung](../features/live-translation.md) menggunakan paket Python `sounddevice`, yang bergantung pada perpustakaan C PortAudio untuk mengakses perangkat mikrofon di semua sistem operasi. Sebagian besar pengguna perlu menginstal dependensi tingkat sistem ini.

## Windows
Wheel yang telah dikompilasi sebelumnya untuk `sounddevice` dan `PyAudio` biasanya menggabungkan biner PortAudio di Windows. Instalasi manual di seluruh sistem biasanya tidak diperlukan. Jika Anda mengalami kesalahan, pastikan driver audio Anda sudah yang terbaru.

## macOS
Gunakan Homebrew untuk menginstal PortAudio:

```bash
brew install portaudio
```

## Linux
Nama paket tergantung pada distribusi Anda. Paket pengembangan (biasanya diakhiri dengan `-dev` atau `-devel`) harus diinstal agar Python dapat membangun ikatan C jika wheel yang telah dikompilasi sebelumnya tidak tersedia.

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## Pemecahan Masalah

Jika aplikasi terus melaporkan tidak dapat mengakses mikrofon setelah instalasi:

1. Pastikan aplikasi terminal (atau lingkungan desktop) Anda diizinkan untuk mengakses mikrofon (terutama di macOS).
2. Mulai ulang aplikasi (atau terminal/server MCP) agar mendapatkan jalur perpustakaan yang baru.
