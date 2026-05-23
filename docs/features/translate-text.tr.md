---
description: AI Translate ile metin parçalarını 45+ dilde anında çevirin — yapıştırın, yazın veya konuşun; düzenleme modu, TTS oynatma ve dil değişimi destekler.
---

# Metin Çevir

Otomatik algılama, dil değişimi, streaming çıktı ve TTS oynatma ile
anlık LLM çevirisi. Kısa parçalar, sohbet tarzı kullanım ve LLM
yapılandırmanızı test etmek için en iyisi.

## Adım adım

1. Kenar çubuğunda **Metin Çevir**'e tıklayın.
2. Sol panele kaynak metninizi yazın veya yapıştırın.
3. Yazarken **Kaynak** dili otomatik algılanır (`langdetect` ile).
4. Sağ taraftaki dropdown'dan bir **Hedef** dil seçin.
5. **Çevir**'e tıklayın (veya `Ctrl+Enter` basın).
6. Çeviri sağ panele token token akar.

## Aldıklarınız

- **Streaming çıktı** — çeviri LLM oluştururken görünür, tüm yanıtı
  beklemek yok.
- **Otomatik kaynak algılama** — kaynak seçici gerçek zamanlı
  güncellenir. Geçersiz kılmak için tıklayın.
- **Düzenleme modu** — çeviriyi manuel düzenlemek için sağ panele
  tıklayın. Devam eden çeviriyi iptal etmek için `Esc`'e basın;
  düzenleme modundan çıkmak için tekrar basın.
- **Geçmiş yeniden kullanımı** — her çeviri kaydedilir. Aşağıdaki
  Metin Çeviri Geçmişi panelindeki bir girişe tıklayarak her iki
  paneli yeniden yükleyin; düzenlemeler kopya oluşturmak yerine
  orijinal girişi günceller.
- **TTS oynatma** — herhangi bir panelin yanındaki **Dinle**'ye
  tıklayarak yüksek sesle okunmasını duyun.
  **Ayarlar → Ses → TTS yöntemi** seçiminize uyar — Edge TTS
  (varsayılan), ElevenLabs, Google Cloud TTS, Gemini TTS veya
  **Piper TTS** (tamamen çevrimdışı). Piper seçildiğinde, Dinle
  düğmesi Ses sayfası ile aynı pre-flight'ı çalıştırır: dile özgü
  eksik bir ses, indirmek için **Ayarları Aç** düğmesi olan bir
  modal iletişim kutusu yüzeye çıkarır. Cache isabetleri pre-flight'ı
  tamamen atlar.
- **Özellik başına model seçici** — birden fazla LLM yapılandırıldığında,
  bir dropdown hız için hızlı Flash modeli veya kalite için daha
  ağır Pro modeli seçmenize izin verir, sadece bu sayfa için.

## Kısayollar

| Kısayol | Eylem |
|---|---|
| `Ctrl+Enter` | Çevir |
| `Ctrl+L` | Kaynak ↔ hedef değiştir |
| `Esc` | Devam eden çeviriyi iptal et veya düzenleme modundan çık |
| `Ctrl+F` | Geçmiş aramasına odaklan |

## İpuçları

!!! tip "RTL diller"
    **Arapça**, **İbranice** veya **Farsça**'ya çeviriler çıktı
    panelinde otomatik olarak sağdan sola render edilir. Aynı RTL
    işleme, [Belge Çevir](translate-document.md) sayfasındaki her
    formatta dosya çıktısına geçer (PDF, DOCX, PPTX, XLSX, ODF, RTF,
    HTML, EPUB, ASS/SSA) ve Farsça, Edge TTS oynatma için yerel bir
    `fa-IR` sesi alır.

!!! tip "Dinle düğmesi cache'i"
    Belirli bir (metin, dil) çifti için Dinle'ye ilk kez bastığınızda
    ses sentezlenir ve diske önbelleğe alınır. Sonraki çalmalar
    anlıktır. Cache uygulama başlangıcında silinir, böylece her
    oturum taze başlar.

!!! tip "Anahtarlar nereye gider"
    Metin Çevir sayfası uygulamanın geri kalanıyla aynı keychain
    girişlerini okur — bkz. [LLM Sağlayıcıları](../setup/llm-providers.md).
