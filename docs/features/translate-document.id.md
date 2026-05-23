---
description: Terjemahkan PDF, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT, dan 30+ format file lainnya sambil mempertahankan format dan tata letak.
---

# Terjemahkan Dokumen

Terjemahkan file lengkap — Office, PDF, EPUB, teks biasa, subtitle,
format lokalisasi, dan lainnya — dengan format dipertahankan.

## Format yang didukung

| Kategori | Ekstensi |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Teks & web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBook | `.epub` |
| Subtitle | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Lokalisasi | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Langkah demi langkah

1. Klik **Terjemahkan Dokumen** di sidebar.
2. Seret file ke dalam (atau klik **Telusuri**). Folder juga bekerja
   — file yang didukung di dalamnya diambil secara rekursif.
3. Pilih **Sumber** (atau biarkan di `Deteksi otomatis`) dan
   **Target**.
4. Klik **Terjemahkan** — atau tekan `Ctrl+Enter`.
5. Tabel riwayat di bawah menunjukkan progres per file (Tertunda →
   Menerjemahkan → Selesai / Gagal). Sidebar menunjukkan spinner
   sementara ada tugas yang aktif.
6. Klik **Buka** pada baris untuk membuka file yang diterjemahkan.
   Klik kanan untuk opsi: terjemahkan ulang, jeda, coba lagi, hapus.

## Di mana file berakhir

Secara default, file yang diterjemahkan disimpan di samping aslinya
dengan suffix `_translated_<src>_<tgt>`:

```
~/Documents/laporan.docx
~/Documents/laporan_translated_en_id.docx     ← di sini
```

Ubah ini di **Pengaturan → Umum → Jalur penyimpanan terjemahan** ke
direktori kustom.

## Batas dan penjaga

- **Batas drop 100 file** — drop lebih banyak dan kamu akan
  mendapatkan notifikasi. Terjemahkan dalam batch.
- **Deteksi duplikat** — drop file yang sudah ada di antrian dan
  kamu akan melihat notifikasi (duplikat dibuang, tidak ditambahkan
  dua kali).
- **Auto-resume** — keluar dari aplikasi sementara terjemahan
  sedang berjalan dan mereka akan dilanjutkan saat peluncuran
  berikutnya (tugas Tertunda / Menerjemahkan).

## Opsi khusus Office

Tab Terjemahan di **Pengaturan** mengekspos toggle ini untuk file
Office:

| Opsi | Apa yang dilakukan |
|---|---|
| **Terjemahkan gambar tertanam** | Menjalankan OCR + visi LLM pada gambar di dalam `.docx` / `.xlsx` / `.pptx` dan memasukkan kembali gambar yang diterjemahkan. Membutuhkan OCR yang dikonfigurasi. |
| **Terjemahkan komentar** | Komentar / catatan tinjauan diterjemahkan bersama dengan teks badan. |
| **Terjemahkan bentuk & kotak teks** | Menangkap teks yang ada di bentuk, callout, dan kotak teks mengambang. |
| **Terjemahkan catatan pembicara** | Catatan pembicara PowerPoint diterjemahkan. |
| **Terjemahkan nama lembar** | Label tab lembar Excel diterjemahkan. |
| **Auto-konversi legacy** | `.doc` / `.xls` / `.ppt` dikonversi ke OOXML modern sebelum terjemahan (kesetiaan lebih baik). |
| **Auto-konversi ODF** | `.odt` / `.ods` / `.odp` dikonversi ke OOXML sebelum terjemahan. |

Semua terjemahan Office mempertahankan format per-run: tebal, miring,
garis bawah, coret, ukuran font, warna, hyperlink, header, footer,
catatan kaki, catatan akhir, semuanya.

### Terjemahan gambar tersemat: lewati-dengan-peringatan + cache

Saat **Terjemahkan gambar tersemat** aktif, setiap gambar
tersemat melewati OCR → visi LLM → injeksi ulang yang
dirender. Dua perilaku yang perlu diketahui:

- **Lewati-dengan-peringatan**: jika satu gambar gagal
  diterjemahkan (terlalu besar, rusak, model visi menolak
  format, dll.) dokumen tetap selesai — gambar yang rusak
  tetap dalam bahasa asli, peringatan dicatat ke `app.log`,
  dan loop berlanjut dengan gambar berikutnya. Hanya
  kesalahan LLM fatal (`AUTH_ERROR`, `QUOTA_ERROR`,
  `VISION_NOT_SUPPORTED`) menghentikan pipeline segera
  karena mereka juga memblokir setiap gambar yang tersisa.
  Banner info di atas kotak centang **Terjemahkan gambar
  tersemat** mendokumentasikan kebijakan secara inline.
- **Cache per-gambar**: terjemahan gambar yang berhasil
  dipertahankan di direktori penyimpanan internal tugas
  dengan kunci SHA256 byte sumber. Pada percobaan ulang,
  gambar yang sudah diterjemahkan menghit cache alih-alih
  menjalankan ulang OCR + LLM — pekerjaan berbayar tidak
  diulang. Gambar duplikat (logo perusahaan di setiap slide)
  diterjemahkan sekali dan digunakan ulang N − 1 kali.

File output hanya muncul di folder output pilihan Anda saat
**berhasil** — terjemahan parsial dari proses yang
dibatalkan atau gagal tetap terbatas pada direktori
penyimpanan internal tugas, sehingga folder output Anda tidak
pernah mengumpulkan dokumen setengah-terjemah yatim.

## Spesifik PDF

PDF menggunakan mesin extract-overlay: teks asli diredaksi di
tempat dan teks yang diterjemahkan dilapisi ke kotak yang sama,
mempertahankan tata letak visual. Checkpoint per-halaman berarti
proses yang dijeda / crash dilanjutkan dari tempatnya berhenti, bukan
halaman 1.

Apa yang diterjemahkan:

- Teks badan (dengan deteksi penjajaran — kiri / tengah / kanan /
  rata kanan-kiri)
- Bookmark / outline (entri TOC)
- Bidang formulir (input teks, dropdown, kotak daftar)
- Hyperlink (rect link diperbarui untuk membungkus teks baru)
- Gambar tertanam (saat **Terjemahkan gambar tertanam** aktif)
- Komentar / anotasi PDF

Untuk PDF yang dipindai (tanpa lapisan teks tertanam), OCR berjalan
otomatis per halaman. Konfigurasi mesin OCR kamu di
**Pengaturan → OCR**.

## Output kanan-ke-kiri

Terjemahan ke **Arab**, **Ibrani**, atau **Persia** dirender sebagai
RTL secara native di setiap format output — `dir="rtl"` disuntikkan
ke overlay PDF, HTML, dan bab EPUB (dengan
`page-progression-direction="rtl"` di OPF EPUB sehingga Apple Books
dan Kindle membalik halaman ke arah yang benar); DOCX `<w:bidi/>` +
`<w:rtl/>`, PPTX `rtl="1"`, tampilan lembar XLSX kanan-ke-kiri,
ODT/ODS/ODP `style:writing-mode="rl-tb"`, RTF `\rtldoc`, dan
pencerminan kode penjajaran ASS/SSA (`\an1` ↔ `\an3`, `\an4` ↔
`\an6`, dll.). Penjajaran tengah tidak disentuh.

## Pintasan

| Pintasan | Tindakan |
|---|---|
| `Ctrl+Enter` | Mulai terjemahan |
| `Ctrl+O` | Telusuri file |
| `Ctrl+F` | Fokus pencarian riwayat |
| `Ctrl+P` | Jeda antrian aktif |
| `Ctrl+G` | Lanjutkan antrian aktif |
| `Delete` | Hapus entri riwayat yang dipilih |

`Ctrl+P` / `Ctrl+G` ditekan saat input teks memiliki fokus, supaya
tidak bertabrakan dengan pengetikan.

## Saat ada yang gagal

Tugas yang gagal menampilkan status merah dengan kode kesalahan dan
pesan terlokalisasi — lihat [panduan pemecahan masalah](../troubleshooting.md)
untuk yang umum (`AUTH_ERROR`, `QUOTA_ERROR`, `FFMPEG_NOT_FOUND`,
dll.).
