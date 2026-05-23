---
description: Konfigurasi Soniox untuk speech-to-text real-time di halaman Live AI Translate — mendukung diarisasi pembicara, istilah glosarium, dan terjemahan langsung.
---

# Soniox (STT)

Speech-to-text real-time melalui API WebSocket Soniox. Digunakan oleh
halaman **[Subtitle](../features/generate-subtitle.md)** dan
**[Terjemahan Live](../features/live-translation.md)** ketika kamu
memilih Soniox sebagai metode STT.

## Kenapa Soniox

- **Real-time** — token tiba saat pembicara masih berbicara.
- **Diarisasi pembicara** — label pembicara per token (misalnya
  _Pembicara 1: Halo…_).
- **Terjemahan dalam stream** — Soniox dapat menerjemahkan saat
  mentranskripsi, menghemat satu round trip LLM tambahan.
- **Multi-bahasa** — auto-detect bahasa sumber bahkan di tengah stream.

## Dapatkan kunci API

1. Daftar di <https://console.soniox.com>
2. Buka **API keys** → **Create new API key**
3. Salin (terlihat seperti `Bearer ...`; salin hanya tokennya tanpa
   prefiks `Bearer `).

Harga dihitung per menit audio (~$0,005 / menit pada saat penulisan)
— lihat <https://soniox.com/pricing>.

## Konfigurasi di aplikasi

Di **Pengaturan → Layanan**:

1. Tempel kunci ke **Kunci API Soniox** → **Simpan**

Di **Pengaturan → Live** *(untuk terjemahan langsung)* atau
**Pengaturan → Subtitle** *(untuk pembuatan subtitle)*:

1. Atur **Metode STT** ke **Soniox**

## Apa yang didukungnya

| Halaman | Gunakan Soniox saat |
|---|---|
| **Subtitle** | Rekaman multi-pembicara (wawancara, panel, rapat) di mana kamu ingin label pembicara di SRT |
| **Terjemahan Live** | Subtitling rapat real-time, terutama dengan beberapa pembicara |

## Istilah glosarium

WebSocket Soniox menerima glosarium istilah untuk mempengaruhi
pengenalan. Aplikasi meneruskan entri glosarium aktif kamu secara
otomatis — nama merek / nama proper / jargon dikenali lebih andal.

## Peringatan

!!! warning "Hanya online"
    Soniox hanya cloud; jika audio kamu sensitif (medis, hukum),
    gunakan Whisper (lokal) sebagai gantinya.

!!! info "Reconnect"
    WebSocket auto-reconnect pada kegagalan transien dengan backoff
    eksponensial. Sesi panjang tetap terhubung melalui blip jaringan
    singkat.

## Error umum

| Error | Kemungkinan penyebab |
|---|---|
| `AUTH_ERROR` | Kunci API salah / kedaluwarsa. Tempel ulang di Pengaturan → Layanan. |
| `QUOTA_ERROR` | Batas plan terlampaui. |
| `CONNECTION_ERROR` | Jaringan diblokir / firewall. Coba lagi dari jaringan berbeda. |
