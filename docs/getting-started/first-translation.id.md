---
description: Terjemahkan dokumen pertama Anda dengan AI Translate dalam 5 menit — seret-dan-lepas PDF, pilih bahasa target, dan unduh salinan terjemahannya.
---

# Terjemahan pertama Anda

Run end-to-end yang cepat — kurang dari 5 menit setelah setup selesai.

!!! abstract "Sebelum Anda mulai"
    Anda perlu menyelesaikan [instalasi](installation.md) dan
    mengonfigurasi API key LLM. Tier gratis Google Gemini cukup untuk
    percobaan pertama.

## Terjemahkan dokumen Word

1. Jalankan aplikasi desktop:

    ```bash
    uv run python -m src.main
    ```

2. Klik **Terjemahkan Dokumen** di sidebar kiri.

3. Seret file `.docx` mana pun ke drop zone — atau klik **Browse**
   untuk memilih satu.

4. File muncul di antrian. Pilih bahasa target di atas:

    - Sumber: `Auto-deteksi` (default — biasanya benar)
    - Target: mis. `Prancis`, `Vietnam`, `Jepang`, `Mandarin (Sederhana)`

5. Klik **Terjemahkan** (atau tekan `Ctrl+Enter`).

6. Perhatikan progress bar di tabel riwayat di bagian bawah halaman.
   Ketika mencapai 100%, klik **Buka** di baris untuk membuka file
   terjemahan — disimpan di sebelah aslinya dengan suffix
   `_translated_<src>_<tgt>`.

## Apa yang baru saja terjadi

- File `.docx` Anda dikloning ke folder penyimpanan per-task agar
  aslinya tidak tersentuh.
- Teks diekstrak, dikelompokkan menjadi chunk yang ramah-LLM,
  diterjemahkan, lalu di-inject kembali ke dokumen dengan semua
  format dipertahankan (bold, italic, font, warna, header, catatan
  kaki, hyperlink…).
- Entri riwayat ditulis ke database SQLite agar Anda dapat membuka
  kembali, menjalankan ulang, atau menerjemahkan ulang file nanti.

## Coba kemenangan cepat selanjutnya

=== "Terjemahkan teks biasa"

    Mampir ke **Terjemahkan Teks** di sidebar. Tempel apa pun, pilih
    target, tekan Enter. Output streaming, tukar bahasa (`Ctrl+L`),
    mode edit, pemutaran TTS.

=== "Buat subtitle"

    **Buat Subtitle** — jatuhkan `.mp4`. Anda akan mendapat `.srt`
    dalam bahasa sumber. (Untuk menerjemahkan _dan_ men-dub video,
    gunakan halaman Dubbing sebagai gantinya.)

=== "Terjemahan mikrofon langsung"

    **Terjemahan Langsung** — pilih mikrofon atau audio sistem,
    pilih target, Mulai. Jendela overlay mengambang menampilkan
    subtitle real-time.

## Ke mana selanjutnya

- Lihat [indeks fitur](../index.md#headline-features) untuk apa yang dilakukan setiap halaman.
- Hubungkan [provider lain](../setup/llm-providers.md) (endpoint kustom, ElevenLabs, Soniox, Google Cloud).
- Coba [CLI](../cli.md) untuk run batch / scripted.
