---
description: "Konfigurasi penyedia LLM untuk terjemahan: Google Gemini (direkomendasikan), endpoint kompatibel OpenAI, atau penyedia kustom apa pun dengan kunci API."
---

# Penyedia LLM

Pipeline terjemahan memanggil Large Language Model untuk terjemahan
sebenarnya. Kamu dapat mengkonfigurasi satu atau banyak; pemilih
model per fitur memungkinkan setiap halaman menggunakan yang berbeda.

## Google Gemini (direkomendasikan untuk pengaturan pertama kali) {: #google-gemini-recommended-for-first-time-setup }

Tier gratis murah hati dan cukup baik untuk sebagian besar
penggunaan pribadi.

1. Pergi ke <https://aistudio.google.com/apikey>
2. Klik **Create API key** (masuk dengan akun Google kamu)
3. Salin kunci (terlihat seperti `AIza...`)
4. Di aplikasi desktop: **Pengaturan → LLM → Kunci API Gemini** →
   tempel → **Simpan**
5. Pilih model default di dropdown **Model Gemini default**. Lineup
   Google cenderung terlihat seperti:

    - Varian **Flash** (misalnya `gemini-2.5-flash`) — cepat, tier
      gratis murah hati, kualitas baik. Titik awal yang
      direkomendasikan.
    - Varian **Pro** — lebih lambat, kualitas lebih tinggi, lebih
      mahal.
    - **Flash-lite** — tercepat, termurah, kualitas lebih rendah.

    Nama model yang tepat tersedia tergantung apa yang Google rilis
    ke akun kamu; pilih satu yang namanya berisi `flash` untuk
    default seimbang.

Selesai. Kunci disimpan di keychain OS kamu, bukan dalam teks biasa.

### Mode Vertex AI (enterprise)

Di dalam blok konfigurasi Gemini, sepasang radio memungkinkan kamu
beralih dari **Developer API** ke **Vertex AI** — model Gemini yang
sama, ditagih melalui akun GCP kamu, dengan kontrol tingkat-org
(VPC-SC, log audit, residensi data regional).

1. Di **Pengaturan → LLM**, alihkan radio Gemini dari **Developer
   API** ke **Vertex AI**
2. Isi:
    - **Project** — ID proyek GCP kamu
    - **Location** — region Vertex (default `us-central1`)
    - **Credentials path** *(opsional)* — jalur ke file kunci JSON
      service account. Biarkan kosong untuk menggunakan Application
      Default Credentials
      (`gcloud auth application-default login`)
3. **Simpan**. Dropdown model akan dipopulasi ulang dari Vertex
   setelah proyek diatur.

Penyegaran OAuth ditangani oleh `google-genai` secara otomatis.
Jalur JSON service account disimpan dalam teks biasa secara sengaja
(*jalur* bukan rahasia — konten file ya, dan tetap di disk di mana
praktik terbaik yang didokumentasikan Google menyimpannya).

## OpenAI / Kompatibel dengan OpenAI

Apa pun yang mengekspos REST API kompatibel OpenAI bekerja — OpenAI
sendiri, Anthropic via [proxy LiteLLM](https://docs.litellm.ai),
Ollama lokal, LM Studio, vLLM, Together.ai, Groq, dan sebagainya.

Di **Pengaturan → LLM**:

1. Klik **Add Custom Provider**
2. Isi:
    - **Name** — label seperti "OpenAI" / "Local Ollama" /
      "Anthropic"
    - **API endpoint** — URL dasar (misalnya
      `https://api.openai.com/v1` atau `http://localhost:11434/v1`
      untuk Ollama)
    - **API key** — biarkan kosong untuk endpoint lokal yang tidak
      diautentikasi
    - **Models** — daftar dipisahkan koma (misalnya `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. Klik **Save**.

Penyedia kustom disimpan sebagai blob JSON di keychain OS (kunci
API termasuk).

## Mengganti model default

Dropdown **Model Gemini default** di **Pengaturan → LLM** mengatur
fallback yang digunakan oleh setiap halaman fitur yang tidak
memiliki pemilihnya sendiri.

Halaman dengan pemilih model mereka sendiri:

- **Terjemahkan Teks** — `tab pengaturan Terjemahkan Teks → Model default`
- **Terjemahkan Dokumen** — memilih per tugas; jatuh ke default
- **Subtitle / Suara / Dubbing / Live / Ekstrak Teks** — masing-
  masing memiliki default per-fitur sendiri di tab Pengaturannya

Ini memungkinkan kamu mencampur dan mencocokkan: Flash gratis untuk
live, Pro untuk dokumen besar, Ollama lokal untuk data sensitif.

## Di mana kunci disimpan

| OS | Penyimpanan |
|---|---|
| **macOS** | Keychain (login keychain) |
| **Windows** | Credential Manager |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (tanpa daemon)** | Jatuh ke INI plaintext di `~/.config/ai-translate/settings.ini` |

Nilai INI fallback dimigrasikan ke keychain pada bacaan pertama
setiap kali keychain tersedia — tanpa langkah manual.

## Instalasi headless / server

Tanpa sesi desktop, kamu masih bisa mengatur kunci via CLI `keyring`
Python (setelah `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Penyedia kustom (tempel blob JSON — lihat UI Pengaturan untuk skema)
uv run keyring set ai-translate llm/custom_providers
```

Atau atur kunci INI yang sama langsung di `settings.ini` — aplikasi
memigrasikannya ke keychain pada bacaan pertama. File terletak di:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Menguji pengaturan kamu

Sanity check tercepat:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Indonesian --quiet
cat /tmp/x_translated__id.txt
```

Jika kamu melihat "Halo dunia." — kamu selesai.

## Error umum

| Error | Kemungkinan penyebab |
|---|---|
| `AUTH_ERROR` | Kunci API salah / kedaluwarsa. Tempel ulang di Pengaturan. |
| `QUOTA_ERROR` | Permintaan-per-hari tier gratis terlampaui. Tunggu, atau bayar. |
| `MODEL_NOT_FOUND` | Daftar `models` penyedia kustom tidak menyertakan model yang diminta. |
| `VISION_NOT_SUPPORTED` | Model yang kamu pilih tidak dapat melakukan input gambar. Gunakan varian `flash` / `pro` / `vision`. |

Lihat [Pemecahan Masalah](../troubleshooting.md) untuk lebih lanjut.
