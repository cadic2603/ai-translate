---
description: Referensi pengembang untuk Python API AI Translate — dibuat otomatis dari docstring; mencakup modul core, utils, constants, CLI, dan server MCP.
---

# Referensi Pengembang

Pengguna akhir kemungkinan menginginkan
[halaman fitur](../index.md#headline-features) atau
[panduan setup](../setup/llm-providers.md), bukan bagian ini.

Ini adalah **referensi API yang dibuat otomatis** — satu halaman per
modul Python di `src/`, dirender dari docstring proyek. Ditujukan
untuk kontributor dan integrator yang ingin memanggil fungsi-fungsi
yang mendasarinya dari kode Python mereka sendiri.

## Target build

`uv run mkdocs build` membuat ulang halaman-halaman ini dari `src/`
pada setiap build, jadi selalu mencerminkan kode saat ini.

## Mulai dari mana

Titik masuk terjemahan headless adalah
[`run_translation_pipeline`](api/core/translator.md) — setiap fitur
di aplikasi desktop, CLI, dan server MCP pada akhirnya melewatinya.
Membaca fungsi ini dan tetangganya `TranslationConfig` adalah cara
tercepat untuk memahami pipeline.

## Tata letak

- **[Constants](api/constants/index.md)** — kunci pengaturan, kode error, tabel bahasa, mesin i18n / tema.
- **[Core](api/core/index.md)** — pipeline terjemahan, dispatch LLM, prosesor per format, mesin OCR / STT / TTS, checkpoint, database.
- **[Utils](api/utils/index.md)** — helper lintas-fungsi.
- **[CLI](api/cli.md)** — titik masuk `ait`.
- **[MCP Server](api/mcp_server.md)** — titik masuk `ait-mcp`.
