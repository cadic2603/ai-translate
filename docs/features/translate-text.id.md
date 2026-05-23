---
description: Terjemahkan cuplikan teks instan ke 45+ bahasa dengan AI Translate — tempel, ketik, atau bicara; mendukung mode edit, pemutaran TTS, dan pertukaran bahasa.
---

# Terjemahkan Teks

Terjemahan LLM instan dengan auto-deteksi, pertukaran bahasa, output
streaming, dan pemutaran TTS. Terbaik untuk cuplikan pendek, penggunaan
gaya chat, dan pengujian setup LLM Anda.

## Langkah

1. Klik **Terjemahkan Teks** di sidebar.
2. Ketik atau tempel teks sumber Anda di panel kiri.
3. Bahasa **Sumber** auto-deteksi saat Anda mengetik (didukung `langdetect`).
4. Pilih bahasa **Target** dari dropdown sisi kanan.
5. Klik **Terjemahkan** (atau tekan `Ctrl+Enter`).
6. Terjemahan mengalir ke panel kanan token-per-token.

## Apa yang Anda dapatkan

- **Output streaming** — terjemahan muncul saat LLM membuatnya, tanpa
  menunggu seluruh respons.
- **Auto-deteksi sumber** — pemilih sumber update secara real-time.
  Klik untuk override.
- **Mode edit** — klik panel kanan untuk mengedit terjemahan secara
  manual. Tekan `Esc` untuk membatalkan terjemahan yang sedang
  berlangsung; tekan lagi untuk keluar dari mode edit.
- **Penggunaan ulang riwayat** — setiap terjemahan disimpan. Klik
  entri di panel Riwayat Terjemahan Teks di bawah untuk memuat ulang
  kedua panel; edit memperbarui entri asli daripada membuat duplikat.
- **Pemutaran TTS** — klik **Dengar** di samping panel mana pun
  untuk mendengarnya dibacakan. Menghormati pilihan Anda di
  **Pengaturan → Suara → Metode TTS** — Edge TTS (default),
  ElevenLabs, Google Cloud TTS, Gemini TTS, atau **Piper TTS**
  (sepenuhnya offline). Dengan Piper terpilih, tombol Dengar
  menjalankan pre-flight yang sama dengan halaman Suara: suara
  per-bahasa yang hilang menampilkan dialog modal dengan tombol
  **Buka Pengaturan** untuk mengunduhnya. Cache hit melompati
  pre-flight sepenuhnya.
- **Pemilih model per-fitur** — ketika lebih dari satu LLM
  dikonfigurasi, dropdown memungkinkan Anda memilih model Flash
  cepat untuk kecepatan atau model Pro lebih berat untuk kualitas,
  hanya untuk halaman ini.

## Pintasan

| Pintasan | Tindakan |
|---|---|
| `Ctrl+Enter` | Terjemahkan |
| `Ctrl+L` | Tukar sumber ↔ target |
| `Esc` | Batalkan terjemahan berjalan, atau keluar mode edit |
| `Ctrl+F` | Fokus pencarian riwayat |

## Tips

!!! tip "Bahasa RTL"
    Terjemahan ke **Arab**, **Ibrani**, atau **Persia** otomatis
    di-render kanan-ke-kiri di panel output. Penanganan RTL yang sama
    diteruskan ke output file di setiap format pada halaman
    [Terjemahkan Dokumen](translate-document.md) (PDF, DOCX, PPTX,
    XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), dan Persia mendapat suara
    `fa-IR` native untuk pemutaran Edge TTS.

!!! tip "Cache tombol Dengar"
    Pertama kali Anda menekan Dengar untuk pasangan (teks, bahasa)
    tertentu, audio disintesis dan di-cache di disk. Pemutaran
    berikutnya instan. Cache dihapus saat startup aplikasi, jadi
    setiap sesi mulai segar.

!!! tip "Di mana key disimpan"
    Halaman Terjemahkan Teks membaca entri keychain yang sama dengan
    sisa aplikasi — lihat [Provider LLM](../setup/llm-providers.md).
