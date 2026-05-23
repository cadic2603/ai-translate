---
description: Canlı Çeviri için çapraz platform mikrofon ses yakalama.
---

# PortAudio Kurulumu (Mikrofon)

[Canlı Çeviri](../features/live-translation.md) özelliği, tüm işletim sistemlerinde mikrofon aygıtlarına erişmek için PortAudio C kitaplığına dayanan `sounddevice` Python paketini kullanır. Çoğu kullanıcının bu sistem düzeyindeki bağımlılığı yüklemesi gerekir.

## Windows
`sounddevice` ve `PyAudio` için önceden derlenmiş wheeller (tekerlekler) genellikle Windows'ta PortAudio ikili dosyasını bir araya getirir. Manuel sistem çapında kurulum normalde gerekli değildir. Hatalarla karşılaşırsanız, ses sürücülerinizin güncel olduğundan emin olun.

## macOS
PortAudio'yu yüklemek için Homebrew'u kullanın:

```bash
brew install portaudio
```

## Linux
Paket adı dağıtımınıza bağlıdır. Önceden derlenmiş bir wheel mevcut değilse Python'un C bağlamalarını oluşturabilmesi için geliştirme paketi (genellikle `-dev` veya `-devel` ile biter) yüklenmelidir.

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## Sorun Giderme

Uygulama kurulumdan sonra mikrofona erişemediğini bildirmeye devam ederse:

1. Terminal uygulamanızın (veya masaüstü ortamınızın) mikrofona erişme iznine sahip olduğundan emin olun (özellikle macOS'te).
2. Yeni kitaplık yolunu alması için uygulamayı (veya terminal/MCP sunucusunu) yeniden başlatın.
