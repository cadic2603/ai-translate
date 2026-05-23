---
description: AI Translate'in Live sayfası için Linux, macOS ve Windows'ta sistem sesini yakala — bilgisayarında çalan herhangi bir sesi gerçek zamanlı çevir.
---

# Sistem Ses Yakalama (Live)

**[Canlı Çeviri](../features/live-translation.md)** sayfası, herhangi
bir medyaya altyazı / çeviri verebilmen için **sistem sesini**
(hoparlörlerinde çalan her şeyi) yakalayabilir — Zoom çağrıları,
YouTube, Netflix, oyunlar, sistem sesleri.

**Ayarlar → Live → Ses kaynağı** (veya Live sayfasının üstündeki
combo) içinde şunlardan birini seç:

- **Mikrofon** — sadece mikrofonun
- **Sistem ses** — sadece hoparlörlerinde çalan şey
- **Her ikisi** — ikisi karıştırılmış (medya üzerinde anlatım
  yapmak veya hibrit toplantıları yakalamak için iyi)

**Sistem ses** veya **Her ikisi**'ni seçtiğinde, uygulama OS'in
için doğru yakalama arka ucuna gönderir. OS önkoşulları
karşılanmamışsa tıklanabilir kurulum bağlantılarıyla satır içi bir
uyarı pankartı görünür, böylece bir şeyin eksik olduğunu bulmak için
oturum başlatmana gerek kalmaz.

## Linux (PulseAudio / PipeWire)

Her modern dağıtımda kutudan çıkar çıkmaz çalışır.

Uygulama, varsayılan sink'inin **monitör kaynağı**na bağlanmak için
`parec` (PulseAudio Recorder) kullanır. PipeWire'ın PulseAudio
uyumluluk shimi bunu şeffaf yapar — ham PulseAudio'ya ihtiyacın
yoktur.

```bash
parec --version    # bir şey yazdırmalı
```

`parec` eksikse, uyarı pankartı dağıtımının paket yöneticisini
algılar ve tam kurulum komutunu satır içine alır — örneğin:

> Sistem ses yakalaması PulseAudio veya PipeWire gerektiriyor — `sudo apt-get install pulseaudio` çalıştır.

apt-get / dnf / pacman / zypper / apk üzerinde algılanır; komutu
doğrudan bir terminale kopyala-yapıştır yapabilirsin.

## macOS

CoreAudio sistem sesini yerel olarak göstermez, bu nedenle bir
**sanal loopback cihazı** gerekir — şunlardan birini kur:

- **[BlackHole](https://existential.audio/blackhole/)** — ücretsiz, açık kaynak
- **[Loopback](https://rogueamoeba.com/loopback/)** — ücretli, cilalı GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — eski ücretsiz seçenek
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — ücretli

Uygulama bunlardan herhangi birini
`ffmpeg -f avfoundation -list_devices` üzerinden otomatik algılar
ve ilk eşleşmeyi kullanır. Loopback'i varsayılan çıkış / giriş
olarak ayarlamana gerek yok — yakalama doğrudan `ffmpeg`'in
avfoundation arka ucu üzerinden gerçekleşir.

Kurduktan sonra, Live sayfası combosunda sadece **Sistem ses**'i
seç ve uyarı pankartı kaybolur.

## Windows

Yerel — çoğu durumda **ekstra yazılım gerekmez**.

Uygulama, [`soundcard`](https://github.com/bastibe/SoundCard) Python
paketi (Windows'ta uygulamayla otomatik kurulur) aracılığıyla
doğrudan **WASAPI loopback** ile konuşur. Bu, Tauri / Rust masaüstü
uygulamalarının kullandığı aynı yerel loopback API'sidir; sanal
kablo olmadan varsayılan hoparlör çıkışını yakalar.

Eğer bir nedenle WASAPI loopback kullanılamazsa (eski Windows
sürümleri, alışılmadık ses sürücüsü), uygulama sanal-loopback
DirectShow cihazına karşı `ffmpeg -f dshow`'a geri düşer.
Şunlardan birini seç:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — ücretsiz, `virtual-audio-capturer` sağlar
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — ücretsiz, `CABLE Output (VB-Audio Virtual Cable)` olarak gelir
- **Stereo Mix (Realtek Audio)** — eski yerleşik seçenek, genellikle varsayılan olarak devre dışı

Uygulama bunları sırayla araştırır ve mevcut olan ilkini kullanır.

## Neden "Her ikisi" hem sesini hem de sistem sesini alır

**Her ikisi** modunda, uygulama paralel olarak İKİ yakalama akışı
açar — `sounddevice` üzerinden mikrofonun, yukarıdaki OS'e özgü
arka uç üzerinden sistem sesi — ve örnek-blok ayrıntı düzeyinde
karıştırır. Bu, bir videoyu anlatmak veya hibrit bir toplantının
her iki tarafını da yakalamak için doğru moddur (sesin artı
hoparlörlerdeki katılımcılar).

> **İpucu:** bir yankı duyarsan veya yinelenen altyazılar alırsan,
> mikrofonundan giren sistem sesin var (yüksek hoparlörler →
> mikrofon onları yakalıyor). Sadece **Sistem ses**'e geç veya
> kulaklık kullan.

## Sorun giderme

| Belirti | Olası neden |
|---|---|
| Live sayfası başlar ama altyazı yok | Yanlış ses kaynağı seçili veya varsayılan mikrofonun sessize alınmış |
| Sesin için altyazı var ama YouTube videosu için değil | Sistem ses önkoşulu kurulu değil (pankart kurulum talimatlarını göstermeli) |
| Altyazılar iki kez (yankı) | "Her ikisi" modu sistem sesini iki kez alır — bir kez hoparlörlerden mikrofon yoluyla, bir kez loopback yoluyla. Sadece Sistem sese geç veya kulaklık kullan |
| Eksik yazılımı kurduktan sonra pankart görünür kalıyor | Sekmeleri değiştir ve geri dön — pankart sayfa gösterimi sırasında yeniden kontrol eder |
| macOS: BlackHole kurulu ama pankart hala yukarıda | BlackHole'un `ffmpeg -f avfoundation -list_devices true -i ""` ses cihazları listesinde olduğunu doğrula; uygulamanın onu orada görmesi gerekiyor |
| Windows: WASAPI loopback hata olmamasına rağmen başarısız | Geri dönüş olarak VB-Audio Virtual Cable kurmayı dene; eski Windows sürümleri veya bazı ses sürücüleri loopback'i `soundcard` üzerinden açığa çıkarmaz |
