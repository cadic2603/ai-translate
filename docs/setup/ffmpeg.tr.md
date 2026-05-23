---
description: AI Translate'in altyazı oluşturma, ses sentezi ve video dublajı için ses ve videoyu çözebilmesi için FFmpeg'i kur — medya özellikleri için gereklidir.
---

# FFmpeg

FFmpeg, herhangi bir ses / video iş akışı için gereklidir:

- **Altyazı Üret** — STT için kaynak sesi çözümleme
- **Ses Üret** — zamanlanmış TTS kliplerini tek bir dosyada birleştirme
- **Dublaj** — STT → TTS → videoya geri mux
- **Canlı Çeviri** — sistem ses yakalaması `parec` üzerinden gittiğinde

Paket dahilinde gelmez — sisteminize bir kere kurun.

## Kurulum

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    Veya daha eksiksiz bir build için önce
    [RPM Fusion](https://rpmfusion.org/Configuration)'ı etkinleştirin.

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    <https://www.gyan.dev/ffmpeg/builds/> adresinden statik bir build
    indirin ("release essentials" build'i uygun), açın, sonra `bin/`
    klasörünü PATH'inize ekleyin:

    1. **Win + R** basın, `sysdm.cpl` yazın, **Enter** basın
    2. **Gelişmiş → Ortam Değişkenleri → Sistem değişkenleri → Path → Düzenle**
    3. **Yeni** → FFmpeg'in `bin` klasörünün mutlak yolunu yapıştırın
    4. Her şeyde **Tamam**, açık olan tüm terminalleri yeniden başlatın

## Doğrulama

```bash
ffmpeg -version
```

Yapılandırma satırında `--enable-libx264 --enable-libvpx` ile bir
sürüm bandını görmelisiniz. "command not found" görüyorsanız, kurulum
PATH'e ulaşmadı.

## Uygulama içi pre-flight kontrolü

Ses / Dublaj sayfaları, çalışmaya başlamadan önce
`shutil.which("ffmpeg")` çağırır. FFmpeg bulunamazsa, yarı çalıştırılan
bir görev yerine buraya geri dönüş bağlantısı olan dostça bir hata
diyaloğu görürsünüz.

## Yaygın hata

| Hata | Anlamı |
|---|---|
| `FFMPEG_NOT_FOUND` | Sayfa onu çalıştırmaya çalıştığında `ffmpeg` PATH'te değil. Kurun (yukarıda) ve uygulamayı yeniden başlatın. |

MCP sunucusunda (`ait-mcp`), aynı hata insan tarafından okunabilir
bir mesaja yeniden sarılır:

> *"Bu ses/video dosyasını çözmek için FFmpeg gereklidir, ancak
> kurulu değildir veya PATH'te değildir. FFmpeg'i kurun ve tekrar
> deneyin."*
