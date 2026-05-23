---
description: "Gerçek zamanlı konuşma çevirisi: mikrofonu veya sistem sesini Whisper veya Soniox arka uçlarıyla canlı olarak yazıya dök ve çevir."
---

# Canlı Çeviri

Mikrofondan, sistem sesinden veya her ikisinden gerçek zamanlı altyazı
ve çeviriler — izlediğin her şeyin üzerinde durmaları için isteğe
bağlı her zaman üstte bir overlay penceresiyle.

## Bununla neler yapabilirsin

- **Canlı toplantı altyazıları** — bir Zoom / Meet / Teams aramasına
  çevirmen botu olarak katılmadan başka bir dilde altyazı ekle.
- **Gerçek zamanlı dil öğrenme** — yabancı dildeki içeriklere
  (filmler, podcast'ler, dersler) ana dilini çeviri parçası olarak
  altyazı ekle.
- **Sistem genelinde altyazılar** — YouTube / Netflix / hoparlörlerde
  çalan her şeye altyazı eklemek için sistem sesini yakala.

## Neye ihtiyacın var

- `PATH`'te **FFmpeg** — bkz. [FFmpeg kurulumu](../setup/ffmpeg.md).
- Bir STT arka ucu, şunlardan biri:
    - **faster-whisper** — yerel, çevrimdışı, ücretsiz, varsayılan
    - **Soniox** — bulut, ücretli, gerçek zamanlı konuşmacı diyarizasyonu. Bkz. [Soniox kurulumu](../setup/soniox.md).

- **Sistem ses yakalama** için, OS başına doğru arka uç otomatik
  olarak seçilir: Linux `parec` (PulseAudio / PipeWire) kullanır,
  Windows yerel WASAPI loopback kullanır (çoğu durumda ekstra
  yazılım gerekmez), macOS sanal bir loopback cihazına karşı
  `ffmpeg -f avfoundation` kullanır (BlackHole / Loopback / vb.).
  Bir şey eksikse, tıklanabilir kurulum bağlantılarıyla satır içi bir
  uyarı pankartı görünür. OS başına tam kurulum talimatları için bkz.
  [Kurulum → Sistem ses](../setup/system-audio.md).

## Adım adım

1. Kenar çubuğunda **Canlı Çeviri**'ye tıkla.
2. **Ayarlar → Live**'da bir kez yapılandır:

    - **Kaynak dil** (konuşulan dil)
    - **Hedef dil** (veya yalnızca yazıya döküm için boş bırak)
    - **Ses kaynağı**: Mikrofon / Sistem ses / Her ikisi
    - **STT yöntemi**: Whisper / Soniox

3. Live sayfasına dönüp **Başlat**'a tıkla (`Ctrl+Enter`).
4. Yazıya dökme ana paneli kart kart doldurur. Yüzen **Overlay**
   penceresi de altyazıları gösterir (istediğin yere sürükle).
5. Oturumu sonlandırmak için **Durdur**'a tıkla.

## Yazıya dökme görünümü

Araç çubuğunda bir düzen seç:

- **İkisi de üst üste** — orijinal + çeviri, biri diğerinin üstünde
- **İkisi de yan yana** — orijinal solda, çeviri sağda
- **Sadece orijinal** / **Sadece çeviri**

Araç çubuğu düğmeleri bir bakışta durum için **`ON`** / **`OFF`**
sonekleri kullanır — örn. `TTS ON`, `TTS OFF`, `Timestamps ON`,
`Overlay OFF`.

Saat simgesiyle **zaman damgalarını** aç/kapa. Hoparlör simgesiyle
çevrilmiş satırların **TTS oynatımını** aç/kapa. **Ayarlar → Ses →
TTS yöntemi** seçimini onurlandırır — Edge TTS (varsayılan),
ElevenLabs, Google Cloud TTS, Gemini TTS veya **Piper TTS**
(tamamen çevrimdışı). Piper seçiliyken, eksik dile özgü sesler stream
ortasında **sessizce Edge TTS'e geri düşer** — bu sayfada modal
pre-flight yoktur, çünkü canlı akışı bir indirme diyaloğuyla
engellemek geri dönüşten daha kötü olurdu.

## Overlay penceresi

Sürüklenebilir, yeniden boyutlandırılabilir, her zaman üstte bir
araç penceresi. Kısayollar:

| Kısayol | Eylem |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Opaklığı azalt / artır |
| `Ctrl+Ok` | Overlay'i taşı |
| `Ctrl+0` / `Ctrl+9` | Büyüt / küçült |

Konum, boyut, opaklık ve yazı tipi boyutu oturumlar arasında kalıcıdır.

### Ayarlarla canlı senkronizasyon

Yazı tipi boyutu ve saydamlık kontrolleri iki yönlü çalışır:
**Ayarlar → Canlı Çeviri → Yer Paylaşımı Yapılandırması**
içindeki **Yazı tipi boyutu** veya **Saydamlık** kaydırıcısını
sürüklemek açık yer paylaşımını gerçek zamanlı olarak günceller
ve tersine, yer paylaşımı içinde `+` / `-` / `Ctrl+[` /
`Ctrl+]` tuşlarına basmak Ayarlardaki kaydırıcıları günceller.
Yer paylaşımını yeniden başlatmaya gerek yoktur.

### Boş durum yer tutucusu

Herhangi bir ses yakalanmadan önce yer paylaşımı bir yer
tutucu gösterir ("Başlat'a basın..." boşta / "Dinleniyor..."
Başlat tıklandıktan sonra). Bu, ana pencerenin boş durumunu
yansıtır — geçiş, çalışan durum hapıyla senkronize kalır. Yer
tutucu, yer paylaşımının mevcut genişliği × yüksekliğiyle
ölçeklenir ve her pencere boyutunda okunabilir kalır.

### Sade altyazı modu

Ayarlar → Canlı Çeviri → Yer Paylaşımı Yapılandırması'ndaki
**Sade altyazıları göster** onay kutusu, yer paylaşımında zaman
damgası ve konuşmacı çiplerini gizlerken bunları ana pencerede
görünür tutar. Yer paylaşımı bir izleyici kitlesiyle
paylaşıldığında (sunum modu / ekran paylaşımı) ancak çalışma
görünümünüzde tam meta verileri korumak istediğinizde
yararlıdır. Bu geçiş yalnızca yer paylaşımı içindir — ana
pencere için "Konuşmacı etiketleri" tercihinizi değiştirmez.

## Yazıya dökmeyi kaydet

Oturumu zaman damgaları, konuşmacılar, orijinal satırlar ve çevrilmiş
satırlarla bir `.txt` dosyasına aktarmak için **Yazıya Dökmeyi
Kaydet**'e tıkla.

## STT arka ucu seçme

| Arka uç | En iyi | Maliyet | Gecikme |
|---|---|---|---|
| **Whisper** (yerel) | Çevrimdışı, gizliliğe duyarlı | Ücretsiz | Orta (~cümle sonundan 1 sn sonra) |
| **Soniox** | Çoklu konuşmacı toplantıları | Ücretli (~$0.005 / dk) | Düşük (gerçek zamanlı) |

## Uyarılar

!!! warning "Mikrofon seçimi"
    Mikrofon girişi her zaman **OS varsayılan cihazını** kullanır —
    uygulama içinde bir seçici yoktur (sounddevice yararlı olamayacak
    kadar çok sanal ALSA eklentisini açığa çıkarır ve OS varsayılan
    mikrofon UI'sine zaten sahiptir). Başlamadan önce tercih ettiğin
    mikrofonu OS ses ayarlarında ayarla.

!!! warning "TTS ters basıncı"
    TTS kuyruğu en son 3 cümleyle sınırlıdır — sentez geride kalırsa
    daha eski kuyruktaki ses bırakılır. Bu, sesli oynatmayı ekran
    üzerindeki altyazılara yakın tutar.

!!! tip "Anahtar olmadan ElevenLabs"
    TTS yöntemini ElevenLabs olarak ayarladıysan ama API anahtarı
    yapılandırılmamışsa, Live sayfası otomatik olarak Edge TTS'e geri
    döner ve durum etiketinde geri dönüşü duyurur.

## Kısayollar

| Kısayol | Eylem |
|---|---|
| `Ctrl+Enter` | Başlat / Durdur |
| `Ctrl+K` | Logu temizle (onayla) |
| `Ctrl+[` / `Ctrl+]` | Overlay opaklığını ayarla |
