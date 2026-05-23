---
description: Kelola set glosarium kustom untuk menerapkan terminologi konsisten di seluruh terjemahan — impor/ekspor CSV, lingkup per pasangan bahasa, prioritas per proyek.
---

# Glosarium

Kunci istilah-istilah tertentu ke terjemahan tertentu di setiap job
terjemahan. Berguna untuk nama merek, terminologi produk, jargon
teknis, atau nama karakter yang ingin Anda jaga konsisten.

## Cara kerja

Glosarium adalah daftar pasangan (istilah sumber, istilah target)
yang dikelompokkan dalam **set**. Ketika Anda mengaktifkan set,
setiap panggilan LLM di app menerima entri yang relevan disuntikkan
ke prompt — jadi LLM melihat "gunakan 'OpenAI' untuk 'OpenAI', bukan
'开放AI'" sebelum menerjemahkan.

Beberapa set dapat aktif sekaligus. Hanya entri yang sumber atau
targetnya muncul di teks batch yang ditambahkan ke prompt (kompresi
per panggilan), jadi glosarium 5.000 entri tetap murah token.

## Langkah

1. Klik **Glosarium** di sidebar.
2. Klik **Set baru** (`Ctrl+N`) dan beri nama (mis. "Proyek Acme").
3. Dengan set terpilih di kiri, panel kanan menunjukkan entri-nya.
4. Klik **Tambah** untuk membuat entri baru. Isi:
    - **Sumber** — istilah asli
    - **Target** — terjemahan yang harus diterapkan
    - Opsional komentar / catatan
5. Ulangi untuk setiap istilah.
6. Centang kotak **Aktif** pada nama set untuk mengaktifkan.

## Aktifkan / nonaktifkan set

Kotak **Aktif** di samping setiap nama set mengontrol apakah
entrinya disuntikkan ke prompt LLM. Anda dapat membiarkan 50 set
tidak aktif dalam penyimpanan dan hanya mengaktifkan 2 yang Anda
butuhkan untuk proyek saat ini.

## Impor / Ekspor (CSV)

- **Ekspor** — pilih set, klik **Ekspor** → simpan sebagai `.csv`.
  Dua kolom: `source`, `target` (UTF-8, dipisah koma, quoting RFC 4180).
- **Impor** — klik **Impor** → pilih `.csv` → pilih set tujuan
  (yang sudah ada atau baru). Pada sumber duplikat Anda akan
  mendapat prompt ganti-atau-lewati.

Format CSV round-trip, jadi Ekspor → edit di Excel → Impor aman.

## Pencarian dan filter

`Ctrl+F` memfokuskan kotak pencarian. Ketik substring apa pun dan
entri (dan daftar set) tersaring ke kecocokan; substring yang cocok
disorot. Membersihkan pencarian memulihkan daftar penuh.

Pencarian **tidak peka aksen dan tidak peka huruf besar/kecil** —
`cafe` menemukan `café` dan sebaliknya.

## Edit di tempat

Klik sel mana pun untuk mengedit. Tekan `Tab` untuk pindah ke sel
berikutnya. Tekan `Esc` untuk membatalkan. Auto-save dipicu ketika
Anda mengklik keluar dari baris. Sumber atau target kosong
membatalkan baris alih-alih menyimpan entri yang tidak valid.

## Hapus

- **Hapus satu entri** — pilih, tekan `Del`. Anda akan melihat
  dialog konfirmasi.
- **Hapus seluruh set** — pilih set, tekan `Del`. Dialog menunjukkan
  jumlah entri kaskade jadi Anda tahu apa yang dihapus.

## Pintasan

| Pintasan | Tindakan |
|---|---|
| `Ctrl+N` | Set baru |
| `Ctrl+F` | Fokus pencarian |
| `Del` | Hapus entri / set yang dipilih |

## Tips

!!! tip "Lingkup per set"
    Set adalah pengelompokan *logis*. Kelompokkan per proyek, per
    klien, per domain (medis / hukum / gaming) — apa pun yang masuk
    akal. Hanya aktifkan set yang relevan dengan pekerjaan saat ini.

!!! tip "Glosarium tidak mengesampingkan terjemahan"
    LLM diinstruksikan untuk menggunakan entri glosarium, tetapi
    tetap merupakan petunjuk — terjemahan paksa yang sangat canggung
    masih bisa muncul. Gunakan pasangan sederhana
    `istilah → terjemahan` daripada kalimat utuh.
