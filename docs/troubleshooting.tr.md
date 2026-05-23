---
description: AI Translate sorunlarını teşhis edin — eksik fontlar, FFmpeg hataları, LibreOffice converter sorunları, OCR kurulum hataları ve LLM API kimlik doğrulaması.
---

# Sorun giderme

Yaygın hatalar, ne anlama geldikleri ve nasıl düzeltileceği.

## Kurulum hataları

### "LLM is not configured"

Henüz bir API anahtarı eklemediniz. Masaüstü uygulamasını açın →
**Ayarlar → LLM** → bir anahtar yapıştırın. Tam rehber için bkz.
[LLM Sağlayıcıları](setup/llm-providers.md).

### `AUTH_ERROR`

LLM API anahtarı yanlış veya süresi dolmuş.

- **Gemini** — <https://aistudio.google.com/apikey> adresinden yeni
  bir anahtar oluşturun, **Ayarlar → LLM** içinde yeniden yapıştırın.
- **Custom sağlayıcı** — anahtarın geçerli olduğunu doğrulayın
  (endpoint'i aynı `Authorization: Bearer …` başlığıyla manuel olarak
  curl edin). Endpoint taşındıysa, **API Endpoint** alanını da güncelleyin.

### `QUOTA_ERROR`

Ücretsiz katman veya ücretli plan limitine ulaştınız.

- **Gemini ücretsiz katman** — günlük istek kotası modele göre
  değişir (bkz. <https://ai.google.dev/gemini-api/docs/rate-limits>).
  Bir gün bekleyin veya ücretliye yükseltin.
- **OpenAI / diğerleri** — fatura panelinizi kontrol edin. Birçok
  sağlayıcının ulaştığınızda istekleri duraklatan "spend cap"i vardır.

### `MODEL_NOT_FOUND`

Seçtiğiniz model adı mevcut değil.

- Custom sağlayıcılar — modelin **Ayarlar → LLM** içindeki virgülle
  ayrılmış **Models** listesinde olduğundan emin olun.
- Yerleşik Gemini listesi — **Ayarlar → LLM → Varsayılan Gemini
  modeli**'nde belgelenmiş bir modele geçin.

### `VISION_NOT_SUPPORTED`

Vision olmayan bir model seçtiniz ve bir görüntü / taranmış PDF
çevirmeye çalıştınız. Adı `flash`, `pro` veya `vision` içeren bir
modele geçin (örn. OpenAI için `gpt-4o`, Gemini için herhangi bir
güncel Gemini Flash veya Pro varyantı).

## Ses / video hataları

### `FFMPEG_NOT_FOUND`

FFmpeg PATH'te değil. İşletim sisteminizin kurulum komutu için bkz.
[FFmpeg kurulumu](setup/ffmpeg.md).

MCP sunucusu bunu şu şekilde yeniden sarar: *"FFmpeg is required to
decode this audio/video file but is not installed or not on PATH."*

### Live sayfası altyazı göstermiyor

- **Yanlış ses kaynağı** — **Ayarlar → Live → Ses kaynağı**'nı açın
  ve gerçekten istediğiniz şeyle eşleştiğinden emin olun (Mikrofon /
  Sistem / Her ikisi).
- **Mikrofon mute** — OS ses ayarlarını kontrol edin; uygulama
  varsayılan giriş cihazınızı kullanır.
- **Sistem sesi ayarlanmamış** — macOS / Windows loopback adımları
  için bkz. [Sistem ses yakalama](setup/system-audio.md).

### Ses çıktısı sessiz / boş

- **Anahtarsız ElevenLabs** — Voice sayfası dostça bir pre-flight
  diyaloğu gösterir; eğer geçtiyse, dosya boş bayt olabilir.
  **Ayarlar → Service → ElevenLabs API key**'i kontrol edin.
- **Edge TTS ağ hatası** — Edge TTS internet gerektirir; firewall'ünüz
  `speech.platform.bing.com`'u engelliyorsa, ElevenLabs, Google Cloud
  TTS veya **Piper TTS** (tamamen çevrimdışı)'ye geçin.

### "Piper voice not installed" diyaloğu

Voice / Dubbing / Translate Text sayfaları, herhangi bir worker
başlamadan önce hedef dilinizin Piper sesinin diskte olduğunu
pre-flight kontrol eder. Yoksa, **Ayarları Aç** düğmeli bir modal görürsünüz.

Sesi indirmek için:

1. Diyalogda **Ayarları Aç**'a tıklayın (veya **Ayarlar → Ses**'i
   manuel açın).
2. **TTS yöntemi**'nin **Piper TTS** olarak ayarlandığından emin olun.
3. Ses kütüphanesi diyaloğunu açmak için **Sesleri şimdi indir**'e
   tıklayın.
4. Hedef dilinizin satırını bulun, sonra yanındaki **Female voice**
   veya **Male voice**'a tıklayın. Sesler HuggingFace'den indirilen
   ~25–60 MB ONNX dosyalarıdır; dil başına bir kez.
5. Diyaloğu kapatın ve çeviri / voice / dub işinizi yeniden çalıştırın.

Hedef diliniz listede yoksa, Piper kapsamı yoktur — motor sentez
sırasında sessizce Edge TTS'e geri düşer, bu yüzden aslında hiçbir
şey indirmenize gerek yok. Bugün Piper sesi olmayan 13 dil:
Belarusça, Bengalce, Çince (Geleneksel), Hırvatça, Estonca, İbranice,
Japonca, Khmer, Korece, Litvanca, Malayca, Moğolca, Tayca.

**Canlı Çeviri** sayfası bu diyaloğu *göstermeyecek* tek yerdir —
canlı bir akışı bir modal ile kesintiye uğratmak fallback'ten daha
kötü olurdu, bu yüzden orada eksik ses durumları sessizce Edge TTS'e
gider.

## Belge çeviri hataları

### PDF çevirisi belirli bir sayfada başarısız

PDF'ler sayfa başına checkpointing kullanır — başarılı sayfalar
yeniden yapılmaz. Başarısız sayfa `app.log`'a stack loglar; yaygın
suçlular:

- Sayfa **metin katmanı olmayan bir tarama** ve OCR yapılandırılmamış.
  **Ayarlar → OCR**'ı kurun (bkz. [OCR Motorları](setup/ocr-engines.md)).
- Sayfa LLM'in bozduğu **karmaşık matematik düzeni** içeriyor. Daha
  güçlü bir model deneyin (Flash yerine Pro varyantı).

### Office çevirisi formatı bozuyor

- **Modern formatlar** (`.docx`, `.xlsx`, `.pptx`) — biçimlendirme
  HTML round-trip ile run başına korunur. Çıktıda kayıp `<b>`
  etiketleri görüyorsanız, LLM onları kapatmamış — daha güçlü bir
  modelle yeniden çalıştırın.
- **Legacy formatlar** (`.doc`, `.xls`, `.ppt`) — çok daha iyi
  doğruluk için **Ayarlar → Çeviri → Auto-convert legacy**'yi açın.
  Pipeline önce `.docx`'e dönüştürür, çevirir, geri dönüştürür.

### Çeviri kuyruğu batch ortasında duruyor

Uygulamadan çıkın ve veritabanını kontrol edin:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

Dakikalardır dokunulmamış `Translating` satırları, bir worker'ın
sessizce çöktüğü anlamına gelir. Masaüstü uygulamasını yeniden
başlatın — başlangıçta Pending / Translating görevlerini otomatik
olarak devam ettirir.

## Çapraz kesişen sorunlar

### Aynı anda birden fazla dosya sessizce tek olarak çevriliyor

Tek seferde bir dosya bırakın VEYA kuyruk başlığındaki **Files**
sütununu kontrol edin — bıraktığınız sayıyı göstermeli. 100 dosya
cap'i aşıldığında bir bildirim gösterir.

### Sidebar sürekli spinner gösteriyor

Bir worker'ın hâlâ çalışıyor olarak işaretlendiğini gösterir.
Uygulamadan temiz çıkın (SIGKILL yok) — autouse cleanup hook'lar
flag'leri sıfırlar. Bir SIGKILL durumu sıkışık bıraktıysa, DB
worker'larını manuel temizleyin:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Loglar nerede? {: #where-are-the-logs }

| OS | Yol |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Loglar konsol ayrıntı seviyesinden bağımsız olarak her zaman DEBUG+
yakalar. Konsol çıktısı varsayılan olarak INFO+'dır; tam dosya
log'unu stdout'ta yansıtmak için CLI'ya `--verbose` geçirin.

## Hâlâ tıkalı?

- Tasarım düzeyindeki sorular için bkz. [SSS](faq.md).
- <https://github.com/cadic2603/ai-translate/issues> adresinde şunlarla
  bir issue açın: OS, Python sürümü, başarısız komut, `app.log`'un
  ilgili bölümü ve beklediğinizin açıklaması.
