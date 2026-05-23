---
description: Vision OCR, Speech-to-Text ve Text-to-Speech için Google Cloud'u AI Translate'e bağla — bir API anahtarı kur ve ilgili hizmetleri etkinleştir.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Tek bir Google Cloud API anahtarı üç isteğe bağlı arka ucu güçlendirir:

- **Vision OCR** — ücretli OCR motoru (ayda 1.000 ücretsiz)
- **Speech-to-Text v1** — ücretli STT (ayda 60 dakika ücretsiz)
- **Text-to-Speech v1** — ücretli TTS (WaveNet için ayda 1 M karakter
  ücretsiz)

Yalnızca gerçekten kullandığın API'leri etkinleştirmen gerekir.

## Bir API anahtarı al

1. [Google Cloud projesi oluştur](https://console.cloud.google.com/projectcreate)
2. API kütüphanesini aç: <https://console.cloud.google.com/apis/library>
3. Şunlardan herhangi birini etkinleştir:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [API anahtarı oluştur](https://console.cloud.google.com/apis/credentials):
   **+ Create Credentials → API key** tıkla
5. Anahtarı kopyala (`AIza...` gibi görünür).

!!! tip "Anahtarı kısıtla"
    API anahtarı detay sayfasında, **API restrictions** altında,
    anahtarı yalnızca etkinleştirdiğin API'lere kısıtla. Bu şekilde
    sızdırılan bir anahtar, kullanmak istemediğin hizmetlerde fatura
    biriktiremez.

## Uygulamada yapılandır

**Ayarlar → Servis**:

1. **Google Cloud API anahtarı** içine yapıştır → **Kaydet**

Bu tek anahtar şimdi her üç Google hizmeti için kullanılabilir.

## Her hizmeti etkinleştir

### Vision OCR

**Ayarlar → OCR → OCR yöntemi = Google Cloud OCR**.

Hepsi bu — Servis'ten aynı anahtarı kullanacak.

### Speech-to-Text

**Ayarlar → Altyazı → STT yöntemi = Google Cloud** (Altyazı / Ses
sayfaları için) veya **Ayarlar → Live → STT yöntemi = Google Cloud**
(Live sayfası için).

**Ayarlar → Altyazı → Google STT modeli**, tanıma modelini seç:

| Model | En iyisi |
|---|---|
| `latest_long` (varsayılan) | Uzun formatlı ses (röportajlar, dersler) |
| `latest_short` | Sesli komutlar, kısa ifadeler |
| `phone_call` | Telefon sesi (8 kHz) |
| `medical_dictation` / `medical_conversation` | Tıbbi alan sesi |

### Text-to-Speech

**Ayarlar → Ses → TTS yöntemi = Google Cloud TTS**.

Varsayılan olarak sunucu dil ve cinsiyete göre bir ses seçer — bu
çoğu kullanıcının ihtiyacı olan tek şey. Belirli bir Google sesini
sabitleme (örn. `en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`) motor
tarafından destekleniyor ancak henüz bir Ayarlar alanı olarak
açığa çıkarılmamış; `voice/google_tts_voice_name` doğrudan
`settings.ini` içinde düzenlenerek ayarlanabilir. Ses ID'leri
<https://cloud.google.com/text-to-speech/docs/voices> adresinde
listelenmiştir.

## Yaygın hatalar

| Hata | Olası neden |
|---|---|
| `AUTH_ERROR` | Yanlış / süresi dolmuş anahtar. Ayarlar → Servis'te tekrar yapıştır. |
| `API not enabled` | Bu Cloud projesinde belirli API'yi (Vision / Speech / TTS) etkinleştirmedin. |
| `QUOTA_ERROR` | Bu API için ücretsiz katman sınırı aşıldı. Bekle veya faturalandırmayı yükselt. |
| `INVALID_ARGUMENT_ERROR` | Ses adı seçtiğin dilde mevcut değil. |

## Maliyet koruması

!!! warning
    Üç Google API'si de geç ödenir — ücretsiz katmanı aşar aşmaz
    durdurmadan faturalandırılmaya başlarsın. Yüksek hacimli iş yapmadan
    önce Cloud projesinde bir [bütçe uyarısı](https://console.cloud.google.com/billing/budgets)
    ayarla.
