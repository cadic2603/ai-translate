---
description: AI Translate ile ilk belgenizi 5 dakikada çevirin — bir PDF'i sürükleyip bırakın, hedef bir dil seçin ve çevrilmiş kopyayı indirin.
---

# İlk çeviriniz

Hızlı uçtan uca bir çalıştırma — kurulum bittikten sonra 5 dakikadan
az.

!!! abstract "Başlamadan önce"
    [Kurulumu](installation.md) bitirmiş ve bir LLM API anahtarı
    yapılandırmış olmanız gerekir. Ücretsiz Google Gemini katmanı
    ilk deneme için yeterli.

## Bir Word belgesini çevir

1. Masaüstü uygulamasını başlatın:

    ```bash
    uv run python -m src.main
    ```

2. Sol kenar çubuğunda **Belge Çevir**'e tıklayın.

3. Herhangi bir `.docx` dosyasını drop zone'a sürükleyin — veya
   birini seçmek için **Gözat**'a tıklayın.

4. Dosya kuyrukta görünür. Yukarıdan bir hedef dil seçin:

    - Kaynak: `Otomatik algıla` (varsayılan — genellikle doğru)
    - Hedef: örn. `Fransızca`, `Vietnamca`, `Japonca`, `Çince (Basitleştirilmiş)`

5. **Çevir**'e tıklayın (veya `Ctrl+Enter` basın).

6. Sayfanın altındaki geçmiş tablosundaki ilerleme çubuğunu izleyin.
   %100'e ulaştığında, satırdaki **Aç**'a tıklayarak çevrilmiş dosyayı
   açın — orijinalin yanında `_translated_<src>_<tgt>` ekiyle kaydedildi.

## Az önce ne oldu

- `.docx` dosyanız, orijinaline dokunulmaması için görev başına
  depolama klasörüne klonlandı.
- Metin çıkarıldı, LLM-dostu parçalara bölündü, çevrildi, ardından
  tüm biçimlendirme korunarak belgeye yeniden enjekte edildi (kalın,
  italik, yazı tipleri, renkler, başlıklar, dipnotlar, köprüler…).
- Bir SQLite veritabanına bir geçmiş girdisi yazıldı, böylece
  dosyayı daha sonra yeniden açabilir, yeniden çalıştırabilir veya
  yeniden çevirebilirsiniz.

## Bir sonraki hızlı kazanımları deneyin

=== "Düz metin çevir"

    Kenar çubuğundaki **Metin Çevir**'e atlayın. Herhangi bir şeyi
    yapıştırın, bir hedef seçin, Enter'a basın. Streaming çıktı,
    dil değiştirme (`Ctrl+L`), düzenleme modu, TTS oynatma.

=== "Altyazı oluştur"

    **Altyazı Oluştur** — bir `.mp4` bırakın. Kaynak dilde bir `.srt`
    geri alacaksınız. (Videoyu çevirmek _ve_ dublajlamak için onun
    yerine Dublaj sayfasını kullanın.)

=== "Canlı mikrofon çevirisi"

    **Canlı Çeviri** — mikrofon veya sistem sesi seçin, bir hedef
    seçin, Başlat. Yüzen bir overlay penceresi gerçek zamanlı
    altyazıları gösterir.

## Sonra nereye

- Her sayfanın ne yaptığı için [özellik dizini](../index.md#headline-features)'ne bakın.
- [Daha fazla sağlayıcı](../setup/llm-providers.md) bağlayın (özel endpoint'ler, ElevenLabs, Soniox, Google Cloud).
- Batch / scripte edilmiş çalıştırmalar için [CLI](../cli.md)'yi deneyin.
