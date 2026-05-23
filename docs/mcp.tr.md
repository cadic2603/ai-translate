---
description: AI Translate'i Model Context Protocol araçları olarak gösterin, böylece Claude Desktop, Claude Code ve diğer MCP istemcileri metin, dosya ve sesi çevirebilir.
---

# MCP Sunucusu (`ait-mcp`)

Çeviri pipeline'ını **Model Context Protocol** araçları olarak
gösterir, böylece Claude Desktop ve Claude Code gibi AI ajanları onu
doğrudan yönetebilir — "Bu PDF'i Fransızcaya çevir" bir tool çağrısına
dönüşür, copy-paste değil.

## Neyin gösterildiği

Dokuz araç:

| Araç | Amaç |
|---|---|
| `translate_text` | Bir string listesini çevir |
| `translate_document` | Dosya çeviri görevlerini sıraya al (görev ID'leri döndürür) |
| `get_task_status` | Görev durumunu sorgula |
| `cancel_task` | Devam eden görevleri kooperatif olarak iptal et |
| `extract_image_text` | OCR veya LLM vision |
| `transcribe_audio` | Ses → SRT |
| `synthesize_speech` | Metin → MP3 / WAV |
| `query_glossary` | Sözlük setlerini / girdilerini listele |
| `list_languages` | Desteklenen tüm 45 dil |

## Sunucuyu çalıştır

```bash
ait-mcp                       # stdio transport (masaüstü ajanları için varsayılan)
ait-mcp --transport sse       # web istemcileri için Server-Sent Events
ait-mcp --transport sse --port 9000
```

`stdio` SSE'yi açıkça bağlamadıysanız her MCP istemcisinin beklediğidir.

## Claude Desktop'a ekle

1. Claude Desktop'ı açın → **Settings → Developer → Edit Config**
2. Bu girişi `mcpServers` altına ekleyin:

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

    `/absolute/path/to/ai-translate`'i klonlanmış repo yoluyla değiştirin.

3. Claude Desktop'ı kapatıp yeniden açın. Çekiç simgesi şimdi
   "ai-translate"i tüm 9 araçla göstermeli. Deneyin:

    > "Bu PDF'i (`/home/me/report.pdf`) Fransızcaya çevir — çıktıyı
    > kaynağın yanına kaydet."

## Claude Code'a ekle

`~/.config/claude-code/mcp_servers.json` (veya Claude Code içinden
`claude mcp add`):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Claude Code'u yeniden başlatın. Aynı 9 araç çağrılabilir hale gelir.

## Diğer MCP istemcilerine ekle

Herhangi bir MCP uyumlu istemci benzer bir şekil alır:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (varsayılan)

HTTP / SSE tabanlı istemciler için `ait-mcp --transport sse --port 9000`
çalıştırın ve istemciyi `http://localhost:9000`'a yönlendirin.

## Doğrulama garantileri

Her araç hatalarda aynı şekli döndürür, böylece ajanlar başarısızlıkları
tutarlı şekilde işleyebilir:

| Kötü giriş | Araç yanıtı |
|---|---|
| Bilinmeyen dil | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM yapılandırılmamış | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Desteklenmeyen dosya türü | İzin verilen uzantıları listeleyen `ValueError` |
| Hatalı biçimlendirilmiş `model="…"` (`:` olmadan) | Varsayılanı sessizce kullanmak yerine `ValueError` |
| `cancel_task` içinde bilinmeyen görev ID'leri | `unknown` dizisinde döndürülür — hata yok |
| `transcribe_audio`'da eksik FFmpeg | `RuntimeError: FFmpeg is required…` (motorun çıplak `FFMPEG_NOT_FOUND` etiketinden yeniden sarmalanmış) |

Bu araçları çağıran ajanlar bu sözleşmelere güvenebilir.

## Eşzamanlılık

`translate_document` pipeline'ı bir daemon thread'inde çalıştırır.
Her batch kendi cancel event'ini alır, bu yüzden bir batch'i iptal
etmek diğerini rahatsız etmez. MCP sunucusu aktif pipeline'ları
süreç-yerel bir haritada izler (pipeline bittiğinde otomatik temizlenir).

## Kullanım durumları

- **"Bu codebase'in dokümanlarını Vietnamcaya çevir"** — ajanı docs
  klasörüne yönlendirin, `translate_document` çağrılarını batch'ler
  ve her biri bitene kadar `get_task_status` sorgular.
- **"Hangi dilleri destekliyorsunuz?"** — ajan `list_languages`'ı
  çağırır, yanıtı okur.
- **"Bu Japonca makbuzu çevir"** — ajan fotoğraf üzerinde
  `extract_image_text`'i çağırır, sonra sonuç üzerinde `translate_text`'i.
- **"Bu Zoom kaydı için Vietnamca altyazı oluştur"** — ajan kaynak
  dilde SRT almak için `transcribe_audio`'yu çağırır, sonra
  yerelleştirmek için her cue üzerinde `translate_text`, ve SRT'yi
  yeniden birleştirir.

!!! note "Video dublajı bir MCP aracı değil"
    Tam STT → çeviri → TTS → mux pipeline'ı (masaüstü uygulamasının
    **Dublaj** sayfası) şu anda yalnızca GUI üzerinden kullanılabilir.
    MCP'den eşdeğeri kendiniz `transcribe_audio` + `translate_text` +
    `synthesize_speech` ile oluşturabilirsiniz, ancak timing-bilinçli
    mux adımını (FFmpeg) dışarıdan halletmeniz gerekir.

## İpuçları

!!! tip "Bir kez kurun, ajanlar her yerde çalışır"
    MCP sunucusu API anahtarlarını ve ayarları masaüstü uygulamasıyla
    ve CLI ile paylaşır. LLM / OCR / TTS'inizi GUI'de bir kez
    yapılandırın, sonra `ait-mcp` ile konuşan herhangi bir ajan aynı
    kurulumu devralır.

!!! tip "Cold-start endpoint cache'i"
    Her `(endpoint, model)` çifti için, chat-vs-responses-API seçimi
    ve çalışan payload varyantı OS cache dizinindeki
    `llm_endpoint_cache.json`'a kalıcılaştırılır
    (Linux'ta `~/.cache/ai-translate/`,
    macOS'ta `~/Library/Caches/ai-translate/`,
    Windows'ta `%LOCALAPPDATA%\ai-translate\cache\`). Taze `ait-mcp`
    süreçleri ilk başarılı çağrıdan sonra otomatik algılama probe'unu
    tamamen atlar — sunucuyu talep üzerine spawn eden ajanlar her
    invokasyonda varyant algılama round-trip'leri ödemez. Cache çoklu
    süreç ve çoklu thread güvenlidir (atomik rename ile RLock altında
    read-merge-write).

!!! tip "Araç başına model seçici"
    `translate_text` ve `translate_document` araçları isteğe bağlı bir
    `model` parametresi kabul eder — ajanlar hızlı turlar için hızlı
    bir model ve üretim çıktısı için daha ağır birini, kullanıcının
    masaüstü uygulamasını yeniden yapılandırmasını gerektirmeden
    seçebilir.

!!! warning "Uzun süreli pipeline'lar"
    `translate_document` görev ID'leriyle hemen döner. Ajanın her
    görev `Done` veya `Failed`'a ulaşana kadar `get_task_status`
    sorgulayacağı beklenir. Araç çağrısı içinde senkron olarak
    beklemeyin; bu MCP istemcisinin timeout'unun tetiklenmesini
    riskine atar.
