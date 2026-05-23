---
description: AI Translate'i Windows, macOS veya Linux'a önceden derlenmiş ikili dosyalardan veya kaynak koddan kurun — Python, FFmpeg ve isteğe bağlı LibreOffice kurulumunu kapsar.
---

# Kurulum

## Gerekenler

- **Python 3.12 veya daha yeni** ([indir](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — hızlı Python paket yöneticisi. Şununla yükleyin:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **Bir LLM API anahtarı** — şunlardan herhangi biri:
    - [Google Gemini](https://aistudio.google.com/apikey) (ücretsiz katman mevcut — başlamak için önerilen)
    - Herhangi bir OpenAI uyumlu endpoint (OpenAI, proxy üzerinden Anthropic, yerel Ollama / LM Studio, vb.)

## İsteğe bağlı, ancak daha fazla özelliği açar

| Araç | Şununla kullanılır | Ne zaman ihtiyacınız olur |
|---|---|---|
| **FFmpeg** ([indir](https://ffmpeg.org/download.html)) | Altyazı, Ses, Dublaj, Live | Her ses/video iş akışı |
| **LibreOffice** ([indir](https://www.libreoffice.org/download/)) | Linux/macOS'ta Office formatları | Legacy `.doc` / `.xls` / `.ppt` çevirisi, veya MS Office yüklü değilken herhangi bir Office dosyası |
| **Tesseract** ([kurulum kılavuzu](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR motoru (varsayılan) | Metin Çıkar sayfası, taranmış PDF çevirisi, gömülü resim çevirisi |
| **MS Office** + **pywin32** | Windows'ta Office | Windows'ta en yüksek doğrulukta Office çevirisi |

AI Translate'i bunların hiçbiri olmadan kurabilirsiniz — bunlara
ihtiyaç duyan özellikler başarısız olmadan önce size söyler.

## Kurulum

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Bu, masaüstü uygulamasını, CLI'yi ve MCP sunucusunu çalıştırmak için
gereken her şeyi kurar.

## Çalıştırın

=== "Masaüstü uygulama"
    ```bash
    uv run python -m src.main
    ```

=== "Komut satırı"
    ```bash
    uv run ait --version
    ```

=== "MCP sunucusu"
    ```bash
    uv run ait-mcp           # stdio transport (Claude Desktop / Code için)
    ```

## API anahtarınızı ekleyin

Masaüstü uygulamasını ilk açtığınızda:

1. Kenar çubuğundan **Ayarlar**'a tıklayın
2. **LLM** sekmesini açın
3. **Google Gemini API anahtarınızı** yapıştırın (veya OpenAI uyumlu
   özel bir sağlayıcı yapılandırın). Kurumsal kullanıcılar Gemini'yi
   **Vertex AI moduna** geçirebilir — bir GCP projesi ve bölgesine
   yönlendirin, isteğe bağlı olarak bir service-account JSON yolu
   sağlayın; ayrıntılar için
   [LLM Sağlayıcıları](../setup/llm-providers.md)'na bakın.
4. Varsayılan model seçin — herhangi bir mevcut Flash varyantı (örn.
   `gemini-2.5-flash`) sağlam bir ücretsiz başlangıç noktasıdır. Pro
   varyantları daha yüksek maliyetle daha iyi kalite verir.
5. Ayarları kapatın — bitti

Anahtarlar diskte düz metin olarak değil, **OS keychain'inizde**
saklanır (macOS Keychain, Windows Credential Manager, Linux'ta
GNOME / KDE Secret Service).

!!! tip "Headless / sunucu kurulumu"
    Anahtarları ayarlamak için masaüstü uygulamasını çalıştıramıyorsanız,
    keychain CLI komutları için
    [LLM Sağlayıcıları](../setup/llm-providers.md)'na bakın.

## Sıradaki: deneyin

[5 dakikalık ilk çeviri →](first-translation.md){ .md-button .md-button--primary }
