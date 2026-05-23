---
description: AI Translate'in Python API'si için geliştirici referansı — docstring'lerden otomatik üretilir; core, utils, constants, CLI ve MCP sunucu modüllerini kapsar.
---

# Geliştirici Referansı

Son kullanıcılar muhtemelen bu bölümü değil,
[özellik sayfalarını](../index.md#headline-features) veya
[kurulum kılavuzlarını](../setup/llm-providers.md) ister.

Bu, **otomatik üretilen API referansıdır** — `src/` içindeki her
Python modülü için bir sayfa, projenin docstring'lerinden render
edilir. Altta yatan fonksiyonları kendi Python kodlarından çağırmak
isteyen katkıda bulunanlar ve entegratörler için tasarlanmıştır.

## Build hedefi

`uv run mkdocs build` her build'de bu sayfaları `src/`'den yeniden
oluşturur, böylece daima koddaki mevcut hâli yansıtırlar.

## Nereden başlamalı

Headless çeviri giriş noktası
[`run_translation_pipeline`](api/core/translator.md) — masaüstü
uygulamasındaki her özellik, CLI ve MCP sunucusu sonunda buradan
geçer. Bu fonksiyonu ve komşusu `TranslationConfig`'i okumak,
pipeline'ı anlamanın en hızlı yoludur.

## Düzen

- **[Constants](api/constants/index.md)** — ayar anahtarları, hata kodları, dil tabloları, i18n / tema motorları.
- **[Core](api/core/index.md)** — çeviri pipeline'ı, LLM dispatch, formata özgü işlemciler, OCR / STT / TTS motorları, checkpoint'ler, veritabanı.
- **[Utils](api/utils/index.md)** — çapraz kesişen yardımcılar.
- **[CLI](api/cli.md)** — `ait` giriş noktası.
- **[MCP Server](api/mcp_server.md)** — `ait-mcp` giriş noktası.
