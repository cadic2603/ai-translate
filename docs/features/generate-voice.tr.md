---
description: Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS veya çevrimdışı Piper TTS ile altyazıları konuşulan sese dönüştür — dublaj kalitesinde ses üretimi için SRT zamanlamasını korur.
---

# Ses Üret (TTS)

Altyazı dosyalarını (zamanlamayla birlikte) veya rastgele metni MP3 /
WAV sese sentezle. Beş TTS arka ucu: Edge TTS (ücretsiz), ElevenLabs
(yüksek kalite), Google Cloud TTS, Gemini TTS (ücretsiz katman) ve
Piper TTS (çevrimdışı).

## Neye ihtiyacın var

- `PATH`'te **FFmpeg** — bkz. [FFmpeg kurulumu](../setup/ffmpeg.md).
- Bir TTS arka ucu, şunlardan biri:
    - **Edge TTS** — ücretsiz, anahtar yok, varsayılan. Microsoft
      Edge'in bulut seslerini kullanır.
    - **ElevenLabs** — ücretli, en yüksek kalite. Bkz. [ElevenLabs kurulumu](../setup/elevenlabs.md).
    - **Google Cloud TTS** — ücretli, çok iyi. Bkz. [Google Cloud kurulumu](../setup/google-cloud.md).
    - **Gemini TTS** — ücretsiz katman, doğal önceden oluşturulmuş
      sesler. LLM sekmesindeki mevcut Gemini API anahtarını yeniden
      kullanır — ekstra kurulum yok.
    - **Piper TTS** — tamamen çevrimdışı sinirsel TTS. API anahtarı
      yok, ağ çağrısı yok — sesler **Ayarlar → Ses → Piper TTS →
      Sesleri şimdi indir** ile bir kez indirilen ~25–60 MB ONNX
      dosyalarıdır. Uygulamanın 45 dilinden 32'sinin bugün bir Piper
      sesi var; Piper kapsamına alınmamış diller sentez zamanında
      sessizce Edge TTS'e geri düşer.

## Adım adım

1. Kenar çubuğunda **Ses Üret**'e tıkla.
2. Bir veya daha fazla `.srt` / `.vtt` / `.ass` / `.ssa` altyazı
   dosyası bırak.
3. **Dil**'i seç (mümkün olduğunda altyazı dosya adından otomatik
   algılanır — örn. `_translated_en_tr.srt` Türkçe olarak algılanır).
4. **Ses cinsiyeti**ni seç — `Kadın` veya `Erkek`.
5. **Çıktı formatı**nı seç — `.mp3` (varsayılan) veya `.wav`.
6. **Üret**'e tıkla (veya `Ctrl+Enter`).
7. Bittiğinde satırı **Aç** — varsayılan ses uygulamanda çalar.

## Çıktı

Her altyazının zaman damgasına yerleştirilmiş ses parçalarıyla tek
bir ses dosyası elde edersin. Sessiz boşluklar, sesin orijinal
zamanlamayla senkronize kalmasını sağlamak için cue'lar arasındaki
zamanı doldurur.

## Bir TTS arka ucu seçme

| Arka uç | Maliyet | Sesler | Notlar |
|---|---|---|---|
| **Edge TTS** | Ücretsiz | Yüzlerce, tüm büyük diller | Varsayılan. Kurulum yok. |
| **ElevenLabs** | Ücretli (~aylık $5 giriş katmanı) | Premium sinir sesleri, ses klonlama | En yüksek kalite. Ses ID'si Ayarlar → Servis'te ayarlanır. |
| **Google Cloud TTS** | Ücretli (~$4/M karakter; ay başına 1 M ücretsiz) | 50+ dilde WaveNet / Studio sesleri | Avrupa dilleri için güçlü WaveNet sesleri. Varsayılan olarak sunucu dil + cinsiyete göre bir ses seçer. |
| **Gemini TTS** | Ücretsiz katman (Developer API kotaları geçerli) | 24+ dilde doğal önceden oluşturulmuş sesler — `Kore` (kadın varsayılan) / `Puck` (erkek varsayılan) | LLM sekmesindeki Gemini API anahtarını yeniden kullanır. Çağrı başına çıktı ~30 sn ile sınırlı; uzun metinler otomatik olarak cümle sınırlarında parçalanır. |
| **Piper TTS** | Ücretsiz, **çevrimdışı** | Uygulamanın 45 dilinden 32'sinde sinir sesleri | Anahtar yok, ağ yok. Dile özel ses **Ayarlar → Ses → Piper TTS → Sesleri şimdi indir** üzerinden talep üzerine indirilir (~25–60 MB her biri). Pre-flight, iş başlamadan önce eksik bir sesi yakalar. |

**Ayarlar → Ses → TTS yöntemi**'nde geçiş yap.

## Piper TTS özellikleri

Piper, uygulamadaki tek tamamen çevrimdışı TTS arka ucudur. Bilmen
gereken birkaç şey:

- **Ses kütüphanesi diyaloğu** — **Ayarlar → Ses → Piper TTS →
  Sesleri şimdi indir** üzerinden aç. Her dil satırı bir
  `Kadın sesi` ve / veya `Erkek sesi` indirme düğmesi gösterir
  (bazı diller tek cinsiyettir). Sesler
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
  HuggingFace kataloğundan gelir.
- **Kapsam** — uygulamanın 45 dilinden 32'sinin bir Piper sesi var.
  Kapsamı olmayan 13 dil (Belarusça, Bengalce, Çince (Geleneksel),
  Hırvatça, Estonca, İbranice, Japonca, Khmerce, Korece, Litvanca,
  Malayca, Moğolca, Tayca) sentez zamanında sessizce Edge TTS'e
  geri düşer, böylece sentez asla eksik bir seste sert başarısız
  olmaz.
- **Cinsiyet çözümleme** — `Kadın`'ı seçtiğinde, motor önce o dilin
  kadın sesini dener; sadece bir erkek sesi varsa, onu kullanır
  (ve tersi). INFO seviyesinde günlüğe kaydedilir.
- **Pre-flight kapısı** — bir Ses çalışması başlamadan önce, sayfa
  dile özel Piper sesinin diskte olduğunu kontrol eder. Eksikse,
  kuyruğunu kaybetmeden indirebilmen için seni doğrudan ses
  kütüphanesine götüren bir **Ayarları Aç** düğmesiyle modal bir
  diyalog alırsın.

## Gemini TTS özellikleri

Gemini TTS, Developer API üzerinden
`gemini-2.5-flash-preview-tts`'i kullanır. Bilmen gereken birkaç şey:

- **Ses seçimi** bugün cinsiyete göredir — Kadın `Kore`'ye eşler,
  Erkek `Puck`'a. Her ikisi de diller arasında çok karakteristik
  sesler vermeden çalışan açık, nötr seslerdir.
- **Çıktı uzunluğu sınırı** — her Gemini API çağrısı en fazla
  ~30 sn konuşma döndürür. Uygulama, girdi metnini cümle
  sınırlarında `_GEMINI_TTS_MAX_BYTES` (~2000 bayt ≈ 30 sn)
  altında parçalar, sonra parçaları FFmpeg üzerinden birleştirir.
  Normal altyazı metninde kesintiyle karşılaşmazsın.
- **Ses formatı** — Gemini, 24 kHz mono s16le'de ham PCM yayınlar;
  uygulama parça başına MP3'e (veya seçtiysen WAV'a) transkod
  eder, böylece son dosya seçtiğin çıktı formatıyla eşleşir.
- **Vertex AI henüz TTS için desteklenmiyor** — LLM sekmen Vertex
  için yapılandırılmış olsa bile, Gemini TTS hala bir Developer API
  anahtarına ihtiyaç duyar. Eksikse, uygulama önceden `AUTH_ERROR`
  yükseltir.

## ElevenLabs modelleri

Üç model açığa çıkarılır:

| Model | Gecikme | Kalite | Şunun için kullan |
|---|---|---|---|
| `eleven_multilingual_v2` (varsayılan) | Orta | Yüksek | Genel TTS |
| `eleven_v3` | Orta | En yüksek | Stüdyo / üretim |
| `eleven_flash_v2_5` | Düşük | İyi | Gerçek zamanlı / Live modu |

**Ayarlar → Ses → ElevenLabs modeli**'nde yapılandır.

## İpuçları

!!! tip "Yeniden üret"
    Bir satıra sağ tıkla → **Yeniden üret** ile çeviriyi yeniden
    çalıştırmadan ses cinsiyetini / TTS yöntemini / formatı değiştir.

!!! tip "Pre-flight kontrolleri"
    Sayfa, başlamadan önce ElevenLabs API anahtarını (seçildiğinde)
    ve FFmpeg kullanılabilirliğini doğrular. Eksik bir şey varsa
    arkadaşça bir diyalog görürsün.

!!! warning "Stop atomiktir"
    Sentez sırasında **Stop**'a bas ve çıktı dizininde yarı yazılmış
    bir MP3 olmaz — dosya önce bir geçici konuma yazılır, sonra
    sadece başarıda yerine taşınır.

## Kısayollar

| Kısayol | Eylem |
|---|---|
| `Ctrl+Enter` | Üret |
| `Ctrl+O` | Gözat |
| `Ctrl+F` | Geçmiş aramasına odaklan |
