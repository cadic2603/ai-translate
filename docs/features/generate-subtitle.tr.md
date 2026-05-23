---
description: Herhangi bir ses veya videodan SRT, VTT, ASS veya SSA altyazıları oluşturun — yüksek kaliteli transkripsiyon için Whisper veya Google Cloud Speech-to-Text kullanır.
---

# Altyazı Oluştur (STT)

Sesi veya videoyu zamanlanmış altyazılara transkribe eder. Konuşmayı
yakalar ve SRT / VTT / ASS / SSA çıkarır — aynı geçişte isteğe bağlı çeviri ile.

## Gerekenler

- Ses/video kod çözme için `PATH`'ta **FFmpeg** — bkz. [FFmpeg kurulumu](../setup/ffmpeg.md).
- Bir transkripsiyon backend'i, şunlardan biri:
    - **faster-whisper** — yerel, çevrimdışı, ücretsiz (varsayılan; kurulum gerekmez)
    - **Google Cloud Speech-to-Text** — bulut, ücretli, gürültülü seste daha doğru. Bkz. [Google Cloud kurulumu](../setup/google-cloud.md).
    - **Soniox** — bulut, ücretli, gerçek zamanlı ve konuşmacı diarizasyonu. Bkz. [Soniox kurulumu](../setup/soniox.md).

## Adım adım

1. Kenar çubuğunda **Altyazı Oluştur**'a tıklayın.
2. Bir veya daha fazla ses / video dosyası bırakın (`.mp3`, `.wav`,
   `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`).
3. **Kaynak dili** seçin (seste *konuşulan* dil) — Whisper'ın
   bulması için `Otomatik algıla`'da bırakın.
4. Bir **Hedef dil** seçin — düz transkript için `Çeviri yok`'u veya
   transkripti aynı geçişte çevirmek için desteklenen 45 dilden
   herhangi birini seçin.
5. **Çıktı formatını** seçin (SRT / VTT / ASS / SSA).
6. **Oluştur**'a tıklayın (veya `Ctrl+Enter`).
7. Kuyruğu izleyin. Bittiğinde satırda **Aç**'a tıklayın.

## Format seçimi

| Format | En uygun |
|---|---|
| **SRT** | Evrensel — neredeyse her oynatıcı destekler |
| **VTT** | HTML5 `<video>` `<track>` öğeleri |
| **ASS / SSA** | Karaoke, stilize altyazılar, fansub akışları |

Dört format aynı parser üzerinden round-trip yapar, böylece zamanlamayı
kaybetmeden yeniden çeviride çıktı formatını değiştirebilirsiniz.

## Whisper model boyutu

**Ayarlar → Altyazı**'da değiştirin:

| Model | Boyut | Hız | Doğruluk |
|---|---|---|---|
| `tiny` | ~75 MB | çok hızlı | düşük |
| `base` (varsayılan) | ~150 MB | hızlı | makul |
| `small` | ~500 MB | orta | iyi |
| `medium` | ~1.5 GB | yavaş | yüksek |
| `large` | ~3 GB | çok yavaş | en iyi |

Modeller ilk kullanımda indirilir ve yerel olarak önbelleğe alınır.
Yavaş bağlantıda ilk çalıştırma uzun gelir; sonrakiler hızlıdır.

## STT yöntem karşılaştırması

| Backend | Maliyet | Çevrimiçi? | Konuşmacı diarizasyonu | Diller |
|---|---|---|---|---|
| **Whisper** (yerel) | Ücretsiz | Hayır | Hayır | 99 |
| **Google Cloud STT** | Ücretli | Evet | Evet (`latest_long` modeli) | 125+ |
| **Soniox** | Ücretli | Evet | Evet (token başına etiket) | 60+ |

**Ayarlar → Altyazı → STT yöntemi**'nde değiştirin.

## İpuçları

- **Durdur düğmesi** — devam eden bir batch'i keser. Aktifin arkasında
  kuyrukta olan dosyalar kuyrukta kalır; daha sonra devam edebilirsiniz.
- **Yeniden oluştur** — farklı format / dil / STT yöntemiyle yeniden
  çalıştırmak için bitmiş bir girişe sağ tıklayın.
- **Uzun ses** — Whisper saatlerce sesi iyi işler; CPU'da `base` modeli
  ile her dakika sese ~1 dakika işleme bütçeleyin.

## Kısayollar

| Kısayol | Eylem |
|---|---|
| `Ctrl+Enter` | Oluştur |
| `Ctrl+O` | Gözat |
| `Ctrl+F` | Geçmiş aramasına odaklan |
