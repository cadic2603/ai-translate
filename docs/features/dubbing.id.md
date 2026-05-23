---
description: "Dub video end-to-end: transkripsi audio, terjemahkan subtitle, sintesis ucapan dalam bahasa target, dan mix kembali ke video asli."
---

# Dubbing Video

Pipeline lengkap **STT → Terjemahkan → TTS → Mix** yang menghasilkan
file video dalam bahasa lain dengan track suara diganti. Audio asli
dibuang; track dubbing baru diatur waktu ke subtitle.

## Yang Anda butuhkan

- **FFmpeg** di `PATH` — lihat [Setup FFmpeg](../setup/ffmpeg.md).
- Backend STT (default Whisper lokal, tanpa setup)
- Backend TTS — Edge TTS (default), ElevenLabs, Google Cloud TTS,
  Gemini TTS, atau **Piper TTS** (sepenuhnya offline; suara per-bahasa
  diunduh sekali via **Pengaturan → Suara → Piper TTS → Unduh suara
  sekarang**)
- **LLM** terkonfigurasi untuk langkah terjemahan

## Langkah

1. Klik **Dubbing** di sidebar.
2. Jatuhkan satu atau lebih file video (`.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`).
3. Pilih **Bahasa sumber** (bahasa yang *diucapkan* di video) dan
   **Bahasa target** untuk di-dub.
4. Klik **Mulai Dubbing** (`Ctrl+Enter`).
5. Perhatikan progres per-task di tabel riwayat. Ia melalui empat fase:

| Fase | Rentang | Yang terjadi |
|---|---|---|
| **STT** | 5–25% | Mentranskripsi audio sumber |
| **Terjemahkan** | 25–50% | LLM menerjemahkan setiap baris subtitle |
| **TTS** | 50–90% | Mensintesis suara bahasa-target untuk setiap baris |
| **Mix** | 90–100% | FFmpeg mengganti track audio |

6. Ketika selesai, **Buka** baris untuk memutar video yang di-dub.

## Output

Untuk setiap video input Anda mendapat empat file di direktori output:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← video di-dub
movie_subtitle_en.srt               ← subtitle bahasa asli
movie_subtitle_fr.srt               ← subtitle terjemahan
movie_voice_fr.mp3                  ← track suara tersintesis
```

## Melanjutkan run yang di-pause / crash

Pipeline membuat checkpoint setelah setiap fase. Jika Anda menekan
**Stop**, keluar app, atau crash, menekan **Lanjutkan** pada baris
melanjutkan dari fase terakhir yang selesai — Anda tidak membayar
lagi untuk STT atau terjemahan jika sudah selesai.

Klik kanan pada entri Done / Failed untuk opsi-opsi ini:

- **Lanjutkan** — melanjutkan dari checkpoint terakhir tanpa re-prompt.
- **Re-dub** — membuka kembali pemilih bahasa; jika Anda memilih
  target baru, checkpoint terjemahkan dan TTS dibuang (Anda tidak
  membayar lagi untuk STT). Memilih target yang sama efektif
  menjalankan ulang dari checkpoint terakhir, seperti Lanjutkan.
- **Buka** — memutar video yang di-dub.

## Peringatan

!!! warning "Sinkronisasi bibir"
    Dubbing cocok dengan *timestamp* audio sumber, bukan gerakan
    bibir. Baris terjemahan yang jauh lebih panjang dari aslinya akan
    terdengar terburu-buru; jauh lebih pendek akan meninggalkan
    keheningan. Untuk dubbing profesional biasanya re-time secara
    manual setelah pass ini — itu fitur masa depan.

!!! tip "Cek pre-flight"
    Halaman memvalidasi FFmpeg + key backend TTS Anda sebelum mulai.
    Key hilang → dialog ramah, bukan dub yang dijalankan setengah.
    Dengan **Piper TTS** terpilih, juga memeriksa bahwa suara Piper
    per-bahasa ada di disk; suara hilang → dialog modal dengan tombol
    **Buka Pengaturan** yang membawa Anda ke perpustakaan suara, jadi
    Anda tidak membakar waktu STT + terjemahan untuk gagal di langkah TTS.

!!! tip "Mengubah bahasa target"
    Pada re-target pipeline membuang checkpoint terjemahkan + TTS
    (kontennya tidak lagi valid untuk bahasa baru) tetapi menyimpan
    checkpoint STT — Anda menghemat biaya transkripsi.

## Pintasan

| Pintasan | Tindakan |
|---|---|
| `Ctrl+Enter` | Mulai Dubbing |
| `Ctrl+O` | Browse |
| `Ctrl+F` | Fokus pencarian riwayat |
| `Ctrl+P` | Pause antrean aktif |
| `Ctrl+G` | Lanjutkan antrean aktif |

`Ctrl+P` / `Ctrl+G` ditekan ketika input teks memiliki fokus, agar
tidak bertabrakan dengan mengetik.
