---
description: Yüksek kaliteli sinirsel TTS için ElevenLabs'i AI Translate'e bağla — gerçekçi, anlamlı konuşmayla 30'dan fazla dilde seslendirme oluştur.
---

# ElevenLabs (TTS)

Premium sinirsel metinden konuşmaya. **[Ses Üret](../features/generate-voice.md)**,
**[Dublaj](../features/dubbing.md)** ve
**[Canlı Çeviri](../features/live-translation.md)** sayfaları
tarafından, TTS yöntemi olarak ElevenLabs'i seçtiğinde kullanılır.

## Bir API anahtarı al

1. <https://elevenlabs.io> adresinde kaydol
2. <https://elevenlabs.io/app/settings/api-keys> aç
3. **+ Create New Key** tıkla, ad ver (örn. "ai-translate"), anahtarı
   kopyala (`sk_...` gibi görünür)

Ücretsiz katman sana ayda ~10.000 karakter verir, test etmek için
yeterli. Üretim kullanımı yaklaşık ayda 5 $'dan başlar.

## Uygulamada yapılandır

**Ayarlar → Servis**:

1. Anahtarı **ElevenLabs API anahtarı** içine yapıştır → **Kaydet**
2. Tercih ettiğin **Ses ID**'sini **Ses ID** içine gir (ID'leri
   <https://elevenlabs.io/app/voice-lab> adresinde bul; ID'yi bir
   sesin URL'sinden kopyala). ElevenLabs'in varsayılan seçmesi için
   boş bırak.

**Ayarlar → Ses**:

1. **TTS yöntemi**'ni **ElevenLabs** olarak ayarla
2. **ElevenLabs modeli**'ni seç:

    | Model | En iyisi |
    |---|---|
    | `eleven_multilingual_v2` (varsayılan) | Genel kullanım, dengeli gecikme/kalite |
    | `eleven_v3` | En yüksek kalite (üretim dublajları için kullan) |
    | `eleven_flash_v2_5` | En düşük gecikme (Canlı Çeviri için kullan) |

## Neyi güçlendirir

| Sayfa | ElevenLabs'i şu durumda kullan |
|---|---|
| **Ses Üret** | Altyazı dosyalarından premium kaliteli seslendirmeler istiyorsun |
| **Dublaj** | Çevrilmiş bir videoda yüksek kaliteli bir dublaj parçası istiyorsun |
| **Canlı Çeviri** | Çevrilmiş altyazıların gerçek zamanlı sözlü oynatımını istiyorsun |

## Ses klonlama

ElevenLabs özel ses klonlamayı destekler (ücretli plan). ElevenLabs
sitesinde bir sesi klonladıktan sonra, Ses ID'sini **Ayarlar → Servis
→ Ses ID** içine yapıştır ve dublaj / ses üretimi pipeline'ı onu
kullanacaktır.

## Uyarılar

!!! warning "Pre-flight kontrolü"
    Ses / Dublaj sayfaları, çalışmaya başlamadan *önce* ElevenLabs API
    anahtarının ayarlandığını kontrol eder. Eksikse, yarı çalıştırılan
    bir görev yerine seni Ayarlar'a yönlendiren dostça bir diyalog
    alacaksın.

!!! tip "Canlı modu otomatik olarak geri düşer"
    **Canlı Çeviri** sayfasında, ElevenLabs'i seçtiysen ancak bir
    anahtar yapılandırmadıysan, uygulama otomatik olarak **Edge TTS**'e
    (ücretsiz) geri düşer ve durum etiketinde geri düşmeyi duyurur, bu
    sayede uygunken düzeltebilirsin.

!!! info "FFmpeg hala gerekli"
    ElevenLabs ses baytları döndürür; uygulama hala formatlar arasında
    dönüştürmek ve zamanlanmış klipleri tek bir dosyada birleştirmek
    için FFmpeg kullanır. Bkz. [FFmpeg kurulumu](ffmpeg.md).

## Yaygın hatalar

| Hata | Olası neden |
|---|---|
| `AUTH_ERROR` | Yanlış / süresi dolmuş API anahtarı. Ayarlar → Servis'te tekrar yapıştır. |
| `QUOTA_ERROR` | Ücretsiz katman karakter sınırına ulaşıldı veya ücretli plan tükendi. |
| `MODEL_NOT_FOUND` | Seçilen ElevenLabs modeli artık mevcut değil; Ayarlar → Ses'te başka birini seç. |
