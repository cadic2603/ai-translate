---
description: Ekspos AI Translate sebagai tools Model Context Protocol agar Claude Desktop, Claude Code, dan klien MCP lain dapat menerjemahkan teks, file, dan audio.
---

# Server MCP (`ait-mcp`)

Mengekspos pipeline terjemahan sebagai tools **Model Context Protocol**
agar agen AI seperti Claude Desktop dan Claude Code dapat
mengendalikannya langsung — "Terjemahkan PDF ini ke bahasa Prancis"
menjadi panggilan tool, bukan copy-paste.

## Yang diekspos

Sembilan tools:

| Tool | Tujuan |
|---|---|
| `translate_text` | Menerjemahkan list string |
| `translate_document` | Mengantrikan task terjemahan file (mengembalikan ID task) |
| `get_task_status` | Polling status task |
| `cancel_task` | Pembatalan kooperatif task yang sedang berjalan |
| `extract_image_text` | OCR atau LLM vision |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Teks → MP3 / WAV |
| `query_glossary` | Daftar set / entri glosarium |
| `list_languages` | Semua 45 bahasa yang didukung |

## Menjalankan server

```bash
ait-mcp                       # transport stdio (default untuk agen desktop)
ait-mcp --transport sse       # Server-Sent Events untuk klien web
ait-mcp --transport sse --port 9000
```

`stdio` adalah yang diharapkan setiap klien MCP kecuali Anda telah
mengonfigurasi SSE secara eksplisit.

## Menambahkan ke Claude Desktop

1. Buka Claude Desktop → **Settings → Developer → Edit Config**
2. Tambahkan entri ini di bawah `mcpServers`:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    Ganti `/absolute/path/to/ai-translate` dengan path repo yang dikloning.

3. Tutup dan buka kembali Claude Desktop. Ikon palu sekarang harus
   menampilkan "ai-translate" dengan semua 9 tools. Coba:

    > "Terjemahkan PDF ini (`/home/me/report.pdf`) ke bahasa Prancis —
    > simpan output di sebelah sumbernya."

## Menambahkan ke Claude Code

`~/.config/claude-code/mcp_servers.json` (atau `claude mcp add` dari
dalam Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Restart Claude Code. 9 tools yang sama menjadi dapat dipanggil.

## Menambahkan ke klien MCP lain

Klien yang kompatibel dengan MCP mengambil bentuk serupa:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (default)

Untuk klien berbasis HTTP / SSE, jalankan
`ait-mcp --transport sse --port 9000` dan arahkan klien ke
`http://localhost:9000`.

## Jaminan validasi

Setiap tool mengembalikan bentuk yang sama pada error agar agen dapat
menangani kegagalan secara konsisten:

| Input buruk | Respons tool |
|---|---|
| Bahasa tidak diketahui | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM tidak dikonfigurasi | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Tipe file tidak didukung | `ValueError` mendaftar ekstensi yang diizinkan |
| `model="…"` tidak terformat (tanpa `:`) | `ValueError` daripada secara diam-diam menggunakan default |
| ID task tidak diketahui di `cancel_task` | Dikembalikan dalam array `unknown` — tanpa error |
| FFmpeg hilang di `transcribe_audio` | `RuntimeError: FFmpeg is required…` (dibungkus ulang dari tag `FFMPEG_NOT_FOUND` mentah engine) |

Agen yang memanggil tools ini dapat mengandalkan kontrak ini.

## Konkurensi

`translate_document` menjalankan pipeline dalam daemon thread. Setiap
batch mendapat event pembatalan sendiri, jadi membatalkan satu batch
tidak mengganggu yang lain. Server MCP melacak pipeline aktif dalam
peta lokal-proses (dibersihkan otomatis ketika pipeline selesai).

## Kasus penggunaan

- **"Terjemahkan dokumentasi codebase ini ke bahasa Vietnam"** —
  arahkan agen ke folder docs, ia mem-batch panggilan
  `translate_document` dan polling `get_task_status` sampai
  masing-masing selesai.
- **"Bahasa apa yang Anda dukung?"** — agen memanggil
  `list_languages`, membaca respons.
- **"Terjemahkan struk Jepang ini"** — agen memanggil
  `extract_image_text` pada foto, lalu `translate_text` pada hasil.
- **"Buat subtitle Vietnam untuk rekaman Zoom ini"** — agen memanggil
  `transcribe_audio` untuk mendapatkan SRT dalam bahasa sumber, lalu
  `translate_text` pada setiap cue untuk melokalisasi, dan menyusun
  ulang SRT.

!!! note "Dubbing video bukan MCP tool"
    Pipeline lengkap STT → terjemahkan → TTS → mux (halaman
    **Dubbing** aplikasi desktop) hanya tersedia melalui GUI saat ini.
    Dari MCP Anda dapat menyusun yang setara sendiri dengan
    `transcribe_audio` + `translate_text` + `synthesize_speech`,
    tetapi Anda perlu menangani langkah mux yang sadar timing
    (FFmpeg) di luar.

## Tips

!!! tip "Setup sekali, agen bekerja di mana saja"
    Server MCP berbagi API key dan pengaturan dengan aplikasi desktop
    dan CLI. Konfigurasikan LLM / OCR / TTS Anda sekali di GUI, lalu
    setiap agen yang berbicara ke `ait-mcp` mewarisi setup yang sama.

!!! tip "Cache endpoint cold-start"
    Untuk setiap pasangan `(endpoint, model)`, pilihan
    chat-vs-responses-API dan varian payload yang berhasil dipersist
    ke `llm_endpoint_cache.json` di direktori cache OS
    (`~/.cache/ai-translate/` di Linux,
    `~/Library/Caches/ai-translate/` di macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` di Windows). Proses
    `ait-mcp` segar melompati probe auto-deteksi sepenuhnya setelah
    panggilan sukses pertama — agen yang memunculkan server sesuai
    permintaan tidak membayar round-trip deteksi varian pada setiap
    invokasi. Cache aman multi-proses dan multi-thread
    (read-merge-write di bawah RLock dengan rename atomik).

!!! tip "Pemilih model per-tool"
    Tool `translate_text` dan `translate_document` menerima parameter
    `model` opsional — agen dapat memilih model cepat untuk giliran
    cepat dan yang lebih berat untuk output produksi tanpa memerlukan
    pengguna mengonfigurasi ulang aplikasi desktop.

!!! warning "Pipeline berjalan lama"
    `translate_document` segera kembali dengan ID task. Agen
    diharapkan polling `get_task_status` sampai setiap task mencapai
    `Done` atau `Failed`. Jangan menunggu secara sinkron di dalam
    panggilan tool; itu berisiko memicu timeout klien MCP.
