---
description: "Çeviri için LLM sağlayıcılarını yapılandır: Google Gemini (önerilen), OpenAI uyumlu uç noktalar veya API anahtarına sahip herhangi bir özel sağlayıcı."
---

# LLM Sağlayıcıları

Çeviri pipeline'ı gerçek çeviri için bir Large Language Model'i
çağırır. Bir veya birçok yapılandırabilirsin; özellik başına model
seçici, her sayfanın farklı bir tane kullanmasına izin verir.

## Google Gemini (ilk kez kurulum için önerilir) {: #google-gemini-recommended-for-first-time-setup }

Ücretsiz katman cömert ve çoğu kişisel kullanım için yeterince
iyidir.

1. <https://aistudio.google.com/apikey> adresine git
2. **Create API key** tıkla (Google hesabınla giriş yap)
3. Anahtarı kopyala (`AIza...` gibi görünür)
4. Masaüstü uygulamada: **Ayarlar → LLM → Gemini API anahtarı** →
   yapıştır → **Kaydet**
5. **Varsayılan Gemini modeli** açılır listesinde varsayılan bir
   model seç. Google'ın sıralaması şuna benzemeye eğilimlidir:

    - **Flash** varyantları (örn. `gemini-2.5-flash`) — hızlı,
      cömert ücretsiz katman, iyi kalite. Önerilen başlangıç noktası.
    - **Pro** varyantları — daha yavaş, daha yüksek kalite, daha
      pahalı.
    - **Flash-lite** — en hızlı, en ucuz, daha düşük kalite.

    Mevcut tam model adları, Google'ın hesabına dağıttıklarına bağlı
    olur; dengeli bir varsayılan için adında `flash` içeren birini
    seç.

Tamamlandı. Anahtar OS keychain'inde saklanır, düz metinde değil.

### Vertex AI modu (kurumsal)

Gemini yapılandırma bloğu içinde, bir radyo çifti **Developer API**'den
**Vertex AI**'ye geçmeni sağlar — aynı Gemini modelleri, GCP hesabın
üzerinden faturalandırılmış, organizasyon düzeyinde kontrollerle
(VPC-SC, denetim günlükleri, bölgesel veri ikametgahı).

1. **Ayarlar → LLM**'de Gemini radyosunu **Developer API**'den
   **Vertex AI**'ye geçir
2. Doldur:
    - **Project** — GCP proje ID'in
    - **Location** — bir Vertex bölgesi (varsayılan `us-central1`)
    - **Credentials path** *(isteğe bağlı)* — bir hizmet hesabı JSON
      anahtar dosyasının yolu. Application Default Credentials
      kullanmak için boş bırak
      (`gcloud auth application-default login`)
3. **Kaydet**. Proje ayarlandıktan sonra model açılır listesi
   Vertex'ten yeniden doldurulur.

OAuth yenileme `google-genai` tarafından otomatik olarak yönetilir.
Hizmet hesabı JSON yolu kasıtlı olarak düz metinde saklanır (*yol*
bir sır değildir — dosyanın içeriği öyle ve Google'ın belgelediği
en iyi uygulamanın onları sakladığı yer olan diskte kalır).

## OpenAI / OpenAI uyumlu

OpenAI uyumlu bir REST API'yi açığa çıkaran her şey çalışır — OpenAI'nin
kendisi, [LiteLLM proxy](https://docs.litellm.ai) üzerinden Anthropic,
yerel Ollama, LM Studio, vLLM, Together.ai, Groq vb.

**Ayarlar → LLM**:

1. **Add Custom Provider** tıkla
2. Doldur:
    - **Name** — "OpenAI" / "Local Ollama" / "Anthropic" gibi bir
      etiket
    - **API endpoint** — temel URL (örn. `https://api.openai.com/v1`
      veya Ollama için `http://localhost:11434/v1`)
    - **API key** — kimliği doğrulanmamış yerel uç noktalar için boş
      bırak
    - **Models** — virgülle ayrılmış liste (örn. `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. **Save** tıkla.

Özel sağlayıcılar OS keychain'inde JSON blob olarak saklanır (API
anahtarları dahil).

## Varsayılan modeli değiştirme

**Ayarlar → LLM**'deki **Varsayılan Gemini modeli** açılır listesi,
kendi seçicisi olmayan her özellik sayfası tarafından kullanılan bir
geri dönüş ayarlar.

Kendi model seçicisi olan sayfalar:

- **Metin Çevir** — `Metin Çevir ayarlar sekmesi → Varsayılan model`
- **Belge Çevir** — görev başına seçer; varsayılana geri düşer
- **Altyazı / Ses / Dublaj / Live / Metin Çıkar** — her birinin
  kendi Ayarlar sekmesinde özellik başına varsayılanı vardır

Bu, karıştırıp eşleştirmene olanak tanır: live için ücretsiz Flash,
büyük belgeler için Pro, hassas veriler için yerel Ollama.

## Anahtarların depolandığı yer

| OS | Depolama |
|---|---|
| **macOS** | Keychain (login keychain) |
| **Windows** | Credential Manager |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (daemon yok)** | `~/.config/ai-translate/settings.ini`'deki düz metin INI'ye geri düşer |

Geri dönüş INI değeri, bir keychain kullanılabilir hale geldiğinde
ilk okumada keychain'e taşınır — manuel adım yok.

## Headless / sunucu kurulumu

Bir masaüstü oturumu olmadan, anahtarları yine Python'un `keyring`
CLI'si üzerinden ayarlayabilirsin (`uv sync` sonrası):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Özel sağlayıcılar (JSON blob'unu yapıştır — şema için Ayarlar UI'sine bak)
uv run keyring set ai-translate llm/custom_providers
```

Veya aynı INI anahtarlarını doğrudan `settings.ini`'ye ayarla —
uygulama bunları ilk okumada keychain'e taşır. Dosya şu adreste:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Kurulumu test etme

En hızlı sanity check:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Turkish --quiet
cat /tmp/x_translated__tr.txt
```

"Merhaba dünya." görüyorsan — bittiğin anlamına gelir.

## Yaygın hatalar

| Hata | Olası neden |
|---|---|
| `AUTH_ERROR` | Yanlış / süresi dolmuş API anahtarı. Ayarlar'da tekrar yapıştır. |
| `QUOTA_ERROR` | Ücretsiz katman gün başına istek sayısı aşıldı. Bekle veya öde. |
| `MODEL_NOT_FOUND` | Özel sağlayıcının `models` listesi istenen modeli içermiyor. |
| `VISION_NOT_SUPPORTED` | Seçtiğin model görüntü girişi yapamıyor. Bir `flash` / `pro` / `vision` varyantı kullan. |

Daha fazlası için bkz. [Sorun giderme](../troubleshooting.md).
