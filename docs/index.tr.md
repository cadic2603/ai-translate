---
description: AI Translate, belgeler, PDF'ler, altyazılar, ses ve canlı konuşma için 45'ten fazla dilde ücretsiz, çapraz platform masaüstü çevirmenidir.
---

# AI Translate

**45 dili** işleyen ve düz metnin çok ötesine geçen ücretsiz, çapraz
platform masaüstü çevirmeni — belgeleri, sesi, videoyu, canlı konuşmayı,
ekran görüntülerini ve daha fazlasını, hepsini tek bir LLM-tabanlı
pipeline ile çevirir.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Masaüstü uygulama**

    ---

    Bir dosyayı sürükleyin, hedef dil seçin, çevrilmiş bir kopya alın.
    Sürükle-bırak, geçmiş, sözlükler, hepsi.

    [:octicons-arrow-right-24: 5 dakikalık adım adım](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Komut satırı**

    ---

    `ait report.docx --target French` — aynı pipeline, scripte
    edilebilir ve headless. CI, batch işler, sunucular için yararlı.

    [:octicons-arrow-right-24: CLI rehberi](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI ajanları (MCP)**

    ---

    Çeviriyi Model Context Protocol araçları olarak açığa çıkarır,
    böylece Claude Desktop, Claude Code ve diğer MCP istemcileri onları
    doğrudan çağırabilir.

    [:octicons-arrow-right-24: MCP kurulumu](mcp.md)

</div>

## Neyi çevirebilirsiniz

| Tür | Formatlar |
|---|---|
| **Office belgeleri** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, ayrıca legacy `.doc` / `.xls` / `.ppt` |
| **PDF** | düzen korumalı extract-overlay çevirisi, yer imi / form / link çevirisi, taramalar için OCR fallback |
| **Metin & web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Altyazılar** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Yerelleştirme** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Görüntüler** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR veya LLM vision) |
| **Ses** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Video** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (tam dublaj pipeline'ı) |

## Öne çıkan özellikler {: #headline-features }

- **[Metin Çevir](features/translate-text.md)** — otomatik algılama, yerinde düzenleme, TTS oynatma ile anlık LLM çevirisi. Sağdan sola diller (Arapça, İbranice, Farsça) yerel olarak render edilir.
- **[Belge Çevir](features/translate-document.md)** — dosyaları bırakın, görev başına ilerleme spinner'ını izleyin, çevrilmiş kopyaları yan yana alın. RTL hedefler uygun bidi markup alır; `Ctrl+P` / `Ctrl+G` kuyruğu duraklatır ve devam ettirir.
- **[Altyazı Oluştur (STT)](features/generate-subtitle.md)** — sesi / videoyu SRT / VTT / ASS / SSA'ya transkribe eder.
- **[Ses Oluştur (TTS)](features/generate-voice.md)** — altyazıları zamanlama ile MP3 / WAV'a sentezler.
- **[Video Dublajı](features/dubbing.md)** — tam STT → çevir → TTS → kaynak videoya geri mix.
- **[Canlı Çeviri](features/live-translation.md)** — mikrofondan veya sistem sesinden gerçek zamanlı altyazı overlay.
- **[Metin Çıkar](features/extract-text.md)** — OCR veya LLM vision → `.txt` / `.docx`.
- **[Sözlük](features/glossary.md)** — çeviriler arasında tutarlı terminolojiyi zorunlu kılar.

!!! tip "Gemini için Vertex AI modu"
    Kurumsal kullanıcılar Gemini çağrılarını Developer API'den
    **Ayarlar → LLM** içinde **Vertex AI**'ya çevirebilir — GCP
    proje ve bölgenizi gösterin, isteğe bağlı olarak service-account
    JSON yolu sağlayın. Bkz.
    [LLM Sağlayıcıları](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Buraya ilk kez mi geldiniz?"
    [Kurulum](getting-started/installation.md) ile başlayın, ardından
    [5 dakikalık ilk çeviri adım adımı](getting-started/first-translation.md).
    Yeni bir clone'dan 10 dakikadan kısa sürede çevrilmiş bir belgeniz olacak.
