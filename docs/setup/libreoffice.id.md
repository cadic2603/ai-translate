---
description: Instal LibreOffice sehingga AI Translate dapat menerjemahkan format Office lama (.doc, .xls, .ppt) dan file ODF (.odt, .ods, .odp) di macOS dan Linux.
---

# LibreOffice (format Office)

Pipeline terjemahan Office memilih backend terbaik yang tersedia
dalam urutan ini:

1. **win32com** (Windows + MS Office terinstal) — kesetiaan tertinggi
2. **LibreOffice UNO** (lintas platform) — fallback ketika win32com
   tidak ada
3. **python-docx / openpyxl / python-pptx** (hanya format modern) —
   fallback pure-Python ketika tidak ada dari yang di atas yang
   tersedia

LibreOffice adalah **satu-satunya jalur** untuk `.doc` / `.xls` /
`.ppt` lama di Linux dan macOS, dan jalur yang direkomendasikan di
platform tersebut juga untuk format Office modern (kesetiaan lebih
baik dari backend pure-Python, terutama untuk tabel dan objek
tertanam).

## Instal

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    Atau unduh dari <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Aplikasi desktop di Windows biasanya menggunakan **win32com**
    dengan MS Office terinstal — LibreOffice adalah *fallback* jika
    MS Office tidak ada. Instal dari
    <https://www.libreoffice.org/download/download/>.

## Verifikasi

```bash
soffice --version
```

Jika kamu mendapat "command not found" di macOS, biner ada di
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. Aplikasi
auto-mendeteksinya melalui jalur instalasi umum, tetapi kamu dapat
menimpa di **Pengaturan → Umum → Jalur LibreOffice** jika
diperlukan.

## Apa yang didukungnya

Ketika LibreOffice adalah backend aktif:

| Fitur | Catatan |
|---|---|
| **Office modern** (`.docx`, `.xlsx`, `.pptx`) | Digunakan sebagai fallback ketika win32com tidak tersedia |
| **Office lama** (`.doc`, `.xls`, `.ppt`) | Diperlukan — Python murni tidak bisa membacanya |
| **ODF** (`.odt`, `.ods`, `.odp`) | Digunakan untuk konversi round-trip ketika **Auto-konversi ODF** aktif |
| **Auto-konversi legacy / ODF → OOXML** | Diperlukan |

## Proses latar belakang

Pertama kali LibreOffice dibutuhkan, aplikasi memunculkan proses
`soffice` dalam mode headless dan mempertahankannya tetap hidup di
seluruh terjemahan (`office_lifecycle.py`). Ia mati otomatis saat
keluar aplikasi.

## Peringatan

!!! warning "Waktu mulai pertama kali"
    Terjemahan pertama yang menyentuh LibreOffice menunggu ~5-10
    detik agar `soffice` berputar. Terjemahan berikutnya menggunakan
    kembali proses yang sama dan cepat.

!!! info "Log crash JVM"
    Komponen Java LibreOffice sesekali menghasilkan file
    `hs_err_pid*.log` saat segfault. Aplikasi merutekannya ke
    direktori temp sehingga tidak mengotori folder proyek kamu.

!!! tip "Auto-konversi legacy / ODF"
    Aktifkan **Pengaturan → Terjemahan → Auto-konversi legacy** jika
    kamu rutin menerjemahkan `.doc` / `.xls` / `.ppt`. Pipeline
    mengonversinya ke `.docx` / `.xlsx` / `.pptx` dulu (via
    `convert_to_modern_format`), menerjemahkan salinan modern,
    kemudian mengonversi kembali. Kesetiaan jauh lebih tinggi dari
    menerjemahkan format lama langsung.
