---
description: Ekstrak teks dari gambar dan tangkapan layar menggunakan mesin OCR (Tesseract, EasyOCR, Google Vision) atau LLM vision — output ke TXT atau DOCX.
---

# Ekstrak teks

Keluarkan teks dari gambar — kuitansi, tangkapan layar, dokumen
yang difoto, halaman yang di-scan, apa pun. Output ke `.txt` (biasa)
atau `.docx` (paragraf berformat).

Halaman ini **tidak menerjemahkan** — hanya mengekstrak. Kirim output
ke Terjemahkan Dokumen jika Anda juga ingin menerjemahkan.

## Dua metode ekstraksi

| Metode | Terbaik untuk |
|---|---|
| **OCR** | Volume tinggi / batch / sensitif biaya (gratis atau hampir gratis per gambar) |
| **LLM vision** | Pelestarian layout, script campuran, gambar kualitas rendah, tulisan tangan |

Pilih default di **Pengaturan → Ekstrak Teks → Metode ekstraksi**.

## Mesin OCR (metode OCR)

| Mesin | Biaya | Offline | Bahasa | Catatan |
|---|---|---|---|---|
| **Tesseract** | Gratis | Ya | 100+ | Default. Membutuhkan instalasi sistem. |
| **EasyOCR** | Gratis | Ya (setelah unduh model) | 80+ | Terbaik untuk script non-Latin. ~1 GB model. |
| **Google Cloud Vision** | Berbayar (1.000 gratis / bulan) | Tidak | 60+ | Akurasi tertinggi. |

Konfigurasikan di **Pengaturan → OCR**.

## Langkah demi langkah

1. Klik **Ekstrak Teks** di sidebar.
2. Jatuhkan satu atau lebih file gambar (`.png`, `.jpg`, `.jpeg`,
   `.bmp`, `.webp`, `.tiff`, `.tif`).
3. Pilih **Bahasa sumber** (membantu OCR memilih model yang tepat).
4. Pilih **Format output** — `.txt` atau `.docx`.
5. Klik **Ekstrak** (atau `Ctrl+Enter`).
6. **Buka** baris ketika selesai.

## Kapan menggunakan apa

- **Kuitansi / faktur padat teks** → Tesseract cepat dan akurat.
- **Catatan tulisan tangan yang difoto** → LLM vision menang banyak.
- **Panel manga / komik** → EasyOCR (menangani teks CJK vertikal dengan baik).
- **Formulir dengan banyak field kecil** → Google Cloud Vision
  cenderung mempertahankan batas field lebih baik dari yang lain.

## Tips

!!! tip "OCR atau LLM, bukan keduanya"
    Halaman memilih satu metode dan menjalankannya. Untuk membandingkan
    output, jalankan gambar yang sama dua kali dengan metode berbeda.

!!! tip "Dialog Setup diperlukan"
    Jika Anda memilih OCR tetapi tidak ada mesin OCR yang dikonfigurasi
    (atau LLM tetapi tidak ada key LLM yang dikonfigurasi), halaman
    menampilkan satu dialog "Setup diperlukan" yang langsung
    menghubungkan ke tab Pengaturan yang relevan.

## Pintasan

| Pintasan | Tindakan |
|---|---|
| `Ctrl+Enter` | Ekstrak |
| `Ctrl+O` | Browse |
| `Ctrl+F` | Fokus pencarian riwayat |
