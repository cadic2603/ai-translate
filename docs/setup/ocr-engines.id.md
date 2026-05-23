---
description: Siapkan mesin OCR untuk ekstraksi teks gambar dan PDF — pilih antara Tesseract atau EasyOCR offline, atau Google Vision OCR berbasis cloud.
---

# Mesin OCR

OCR digunakan untuk membaca teks dari gambar — baik di halaman
[Ekstrak Teks](../features/extract-text.md) maupun sebagai fallback
di dalam terjemahan Dokumen ketika halaman dipindai (tanpa lapisan
teks) atau ketika kamu mengaktifkan **Terjemahkan gambar tertanam**.

Kamu bisa memilih dari tiga mesin OCR.

## Tesseract (default yang direkomendasikan)

Gratis, cepat, offline. Membutuhkan instalasi sistem.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` membawa setiap bahasa yang didukung. Untuk
    menghemat disk, pasang hanya apa yang kamu butuhkan (misalnya
    `tesseract-ocr-fra` untuk Prancis).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Unduh installer dari
    [release Tesseract UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
    Jalankan, terima default — paket bahasa dibundel.

Verifikasi:

```bash
tesseract --version
tesseract --list-langs
```

Di aplikasi desktop: **Pengaturan → OCR → Metode OCR = Tesseract**.
Selesai.

## EasyOCR

Gratis, offline. Bagus untuk script non-Latin (Cina, Korea, Jepang,
Thai). Model diunduh pada penggunaan pertama (~1 GB total).

```bash
uv sync --extra easyocr
```

Di aplikasi desktop: **Pengaturan → OCR → Metode OCR = EasyOCR**.

Pertama kali kamu menggunakannya untuk suatu bahasa, model yang
relevan diunduh ke `~/.EasyOCR/`. Run berikutnya instan.

## Google Cloud Vision

Cloud, berbayar (1.000 request gratis / bulan). Akurasi tertinggi,
terutama pada konten yang bising / tulisan tangan / multi-script.

1. [Buat proyek Google Cloud](https://console.cloud.google.com/projectcreate)
2. Aktifkan [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Buat kunci API](https://console.cloud.google.com/apis/credentials)
4. Di aplikasi desktop: **Pengaturan → Layanan → Kunci API Google Cloud** → tempel
5. **Pengaturan → OCR → Metode OCR = Google Cloud OCR**

Kunci API Google Cloud yang sama mendukung Vision OCR, Speech-to-Text,
dan Text-to-Speech jika kamu juga mengaktifkan API tersebut.

## Membandingkan akurasi

Tab **Pengaturan → OCR** memiliki tabel perbandingan kecil yang
terintegrasi — cakupan bahasa, online/offline, biaya, akurasi.
Baca ulang setiap kali kamu tergoda untuk berganti.

## Kapan OCR digunakan

| Tempat | Perilaku |
|---|---|
| **Halaman Ekstrak Teks** (saat metode = OCR) | OCR langsung pada gambar yang dijatuhkan |
| **Terjemahkan Dokumen → PDF** | Fallback OCR pada halaman hanya-pindai (tanpa lapisan teks) |
| **Terjemahkan Dokumen → Office** dengan **Terjemahkan gambar tertanam** aktif | OCR + LLM vision pada setiap gambar tertanam |

## Tips

!!! tip "Pilih bahasa sumber"
    Sebagian besar mesin OCR jauh lebih akurat ketika kamu memberi
    tahu mereka bahasa apa yang diharapkan. Halaman Subtitle /
    Dokumen / Ekstrak Teks semuanya meneruskan pemilih **Bahasa
    sumber** kamu ke mesin OCR.

!!! tip "Tesseract cukup untuk teks cetak yang bersih"
    Jangan langsung beralih ke OCR cloud sampai Tesseract / EasyOCR
    benar-benar gagal pada konten kamu. Mereka gratis, cepat, dan
    mengejutkan baiknya.
