---
description: "Videoları uçtan uca dublajlayın: sesi transkribe edin, altyazıyı çevirin, hedef dilde konuşma sentezleyin ve orijinal videoya geri mixleyin."
---

# Video Dublajı

Tam **STT → Çevir → TTS → Mix** pipeline'ı, ses parçası değiştirilmiş
başka bir dilde video dosyası üretir. Orijinal ses atılır; yeni
dublaj parçası altyazılara zamanlanır.

## Gerekenler

- `PATH`'ta **FFmpeg** — bkz. [FFmpeg kurulumu](../setup/ffmpeg.md).
- Bir STT backend'i (varsayılan yerel Whisper, kurulum gerekmez)
- Bir TTS backend'i — Edge TTS (varsayılan), ElevenLabs, Google
  Cloud TTS, Gemini TTS veya **Piper TTS** (tamamen çevrimdışı; dile
  özgü sesler **Ayarlar → Ses → Piper TTS → Sesleri şimdi indir**
  ile bir kez indirilir)
- Çeviri adımı için yapılandırılmış bir **LLM**

## Adım adım

1. Kenar çubuğunda **Dublaj**'a tıklayın.
2. Bir veya daha fazla video dosyası bırakın (`.mp4`, `.webm`,
   `.mkv`, `.avi`, `.mov`, `.wmv`).
3. **Kaynak dili** (videoda *konuşulan* dil) ve dublajlanacak
   **Hedef dili** seçin.
4. **Dublaja Başla**'ya tıklayın (`Ctrl+Enter`).
5. Geçmiş tablosundaki görev başına ilerlemeyi izleyin. Dört fazdan
   geçer:

| Faz | Aralık | Ne oluyor |
|---|---|---|
| **STT** | 5–25% | Kaynak ses transkribe ediliyor |
| **Çevir** | 25–50% | LLM her altyazı satırını çeviriyor |
| **TTS** | 50–90% | Her satır için hedef-dil sesi sentezleniyor |
| **Mix** | 90–100% | FFmpeg ses parçasını değiştiriyor |

6. Tamamlandığında, dublajlanmış videoyu oynatmak için satırda
   **Aç**'a tıklayın.

## Çıktılar

Her giriş videosu için çıktı dizininde dört dosya alırsınız:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← dublajlanmış video
movie_subtitle_en.srt               ← orijinal dil altyazısı
movie_subtitle_fr.srt               ← çevrilmiş altyazı
movie_voice_fr.mp3                  ← sentezlenmiş ses parçası
```

## Duraklatılmış / çökmüş çalıştırmayı sürdürme

Pipeline her fazdan sonra checkpoint yapar. **Durdur**'a basarsanız,
uygulamadan çıkarsanız veya çökerseniz, satırda **Devam**'a basmak
son tamamlanan fazdan sürdürür — STT veya çeviri zaten yapılmışsa
yeniden ödemezsiniz.

Bu seçenekler için Done / Failed girişine sağ tıklayın:

- **Devam** — son checkpoint'ten yeniden sormadan sürdürür.
- **Yeniden dublaj** — dil seçicisini yeniden açar; yeni bir hedef
  seçerseniz, çevir ve TTS checkpoint'leri atılır (STT için yeniden
  ödemezsiniz). Aynı hedefi seçmek son checkpoint'ten yeniden
  çalıştırmaya eşdeğer, Devam gibi.
- **Aç** — dublajlanmış videoyu oynatır.

## Uyarılar

!!! warning "Dudak senkronizasyonu"
    Dublaj kaynak sesin *zaman damgalarına* uyar, dudak hareketlerine
    değil. Orijinalden çok daha uzun çevrilmiş satırlar acele
    geliyor; çok daha kısalar sessizlik bırakıyor. Profesyonel
    dublaj için genellikle bu geçişten sonra manuel olarak yeniden
    zamanlama yapılır — bu gelecekteki bir özellik.

!!! tip "Pre-flight kontrolleri"
    Sayfa başlamadan önce FFmpeg + TTS backend'inizin anahtarlarını
    doğrular. Eksik anahtar → dostça iletişim kutusu, yarı
    çalıştırılmış dublaj yok. **Piper TTS** seçildiğinde, dile özgü
    Piper sesinin diskte olduğunu da kontrol eder; eksik ses → ses
    kütüphanesine götüren **Ayarları Aç** düğmesi olan modal iletişim
    kutusu, böylece STT + çeviri zamanını TTS adımında başarısız
    olmak için yakmazsınız.

!!! tip "Hedef dili değiştirme"
    Re-target'te pipeline çevir + TTS checkpoint'lerini atar
    (içerikleri yeni dil için artık geçerli değil) ancak STT
    checkpoint'ini saklar — transkripsiyon maliyetinden tasarruf edersiniz.

## Kısayollar

| Kısayol | Eylem |
|---|---|
| `Ctrl+Enter` | Dublaja Başla |
| `Ctrl+O` | Gözat |
| `Ctrl+F` | Geçmiş aramasına odaklan |
| `Ctrl+P` | Aktif kuyruğu duraklat |
| `Ctrl+G` | Aktif kuyruğu sürdür |

Metin girişi odaklandığında `Ctrl+P` / `Ctrl+G` bastırılır, böylece
yazımla çakışmazlar.
