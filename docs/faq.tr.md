---
description: "AI Translate hakkında yaygın sorular: desteklenen dosya formatları, ücretsiz vs ücretli özellikler, çevrimdışı kullanım, LLM sağlayıcı seçimleri ve OCR motoru seçimi."
---

# Sıkça sorulan sorular

## Genel

### Çevrimdışı çalışıyor mu?

Çoğunlukla evet. Özellikle:

- **Çeviri** bir LLM gerektirir. Ücretsiz Gemini API çevrimiçidir;
  Custom Provider ayarları aracılığıyla **yerel Ollama / LM Studio**
  tamamen çevrimdışıdır.
- **Tesseract** veya **EasyOCR** ile **OCR** çevrimdışıdır.
- **Whisper** (varsayılan) ile **STT** çevrimdışıdır.
- **Edge TTS** (varsayılan) ile **TTS** çevrimiçidir; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** çevrimiçidir (ücretsiz veya
  ücretli); **Piper TTS**, dile göre sesi (~25–60 MB ONNX dosyası)
  **Ayarlar → Ses → Piper TTS → Sesleri şimdi indir** ile bir kez
  indirdikten sonra anahtarsız, ağ çağrısız tamamen çevrimdışı neural
  TTS'dir.

Tamamen air-gapped kurulum için: Custom Provider → yerel LLM, OCR için
Tesseract veya EasyOCR, STT için Whisper ve ses çıktısı için Piper TTS.

### Çevrilmiş dosyalarım nereye kaydediliyor?

Varsayılan olarak orijinalin yanına `_translated_<src>_<tgt>` ekiyle
(örn. `report_translated_en_fr.docx`). **Ayarlar → Genel → Çeviri
depolama yolu** içinde özelliğe göre geçersiz kılın.

### Ayarlarım nerede saklanıyor?

INI dosyası:

| OS | Yol |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

API anahtarları OS keychain'inde yaşar (INI'de değil). Çeviri geçmişi
veri dizininde bir SQLite DB'sinde yaşar.

### Verilerim nasıl ele alınıyor?

- **Local-first** — bulut LLM / OCR / STT / TTS hizmeti çağırmıyorsanız
  metin makinanızdan asla ayrılmaz.
- **Telemetri yok** — uygulama eve telefon etmez. Uygulamanın kendi
  başına yaptığı tek dış istek, isteğe bağlı GitHub Releases güncelleme
  kontrolüdür (**Ayarlar → Genel** içinde toggle); bulut backendleri
  yalnızca kendi sağlayıcılarını çağırır.
- **API anahtarları** — OS keychain'inde saklanır. Hiçbir keychain
  daemon'u yokken masaüstü uygulamasının keychain fallback'i düz metin
  INI'dir.

### Bir Google Doc / Notion sayfasını çevirebilir miyim?

Doğrudan değil. Önce `.docx`'e dışa aktarın, çevirin, sonra çevrilen
dosyayı geri içe aktarın. Notion (Markdown / HTML olarak dışa aktar),
Confluence (`.docx` olarak dışa aktar) vb. için aynı.

## Model / motor seçimi

### Hangi LLM modelini kullanmalıyım?

Çoğu kullanıcı için:

- **Herhangi bir Gemini Flash varyantı** — ücretsiz katman, hızlı,
  şaşırtıcı derecede iyi. Günlük çeviriler için kullanın. İsimler şuna
  benzer: `gemini-2.5-flash`, `gemini-3-flash-preview`, vs., şu anda
  mevcut olana göre.
- **Herhangi bir Gemini Pro varyantı** — token başına ödeme, daha
  yüksek kalite. Önemli belgeler için kullanın (yasal, teknik,
  müşteriye dönük).
- **Yerel Ollama** 7B-13B modeliyle — çevrimdışı / gizlilik gerektiğinde.

Özellik başına model seçici, chat-tarzı çeviri için hızlı bir model
kullanmanıza ve pahalısını belgeler için saklamanıza olanak tanır.

### Hangi OCR motorunu kullanmalıyım?

- Ana scriptlerde temiz basılı metin için **Tesseract**. Ücretsiz,
  çevrimdışı, hızlı.
- Latin olmayan scriptler (özellikle CJK) ve daha gürültülü görüntüler
  için **EasyOCR**.
- El yazısı, karışık scriptler ve ödeyebildiğinizde en yüksek
  doğruluk için **Google Cloud Vision**.

### Hangi STT yöntemini kullanmalıyım?

- Çevrimdışı / gizlilik için **Whisper local**.
- Çoklu konuşmacı kayıtları için **Soniox** — konuşmacı etiketleri
  SRT'nize round-trip yapar.
- Telefon / tıbbi ses için **Google Cloud STT** (alan modelleri iyidir).
- Gerçek zamanlı speech-to-speech çeviri için **Gemini Live**.

### Hangi TTS backend?

- Ücretsiz, yüksek kaliteli sesler için **Edge TTS**.
- Premium / markalanmış / klonlanmış sesler için **ElevenLabs**.
- Edge'in ince kapsama sahip olduğu uzun-kuyruk dillerde WaveNet
  sesleri için **Google Cloud TTS**.
- Mevcut Gemini API anahtarınızı yeniden kullanan ücretsiz doğal
  prebuilt sesler için **Gemini TTS**.
- **Çevrimdışı / air-gapped** ses çıktısına ihtiyaç duyduğunuzda
  **Piper TTS**. Trade-off: her dil **Ayarlar → Ses → Piper TTS →
  Sesleri şimdi indir** ile ~25–60 MB tek seferlik ses indirme
  gerektirir ve uygulamanın 45 dilinden 13'ünde Piper sesi yoktur
  (bunlar sessizce Edge TTS'e geri düşer).

## Workflow

### Tüm bir klasörü nasıl çeviririm?

Klasörü **Belge Çevir**'in drop zone'una bırakın. İçindeki desteklenen
dosyalar (özyinelemeli) kuyruğa alınır; geri kalan her şey sessizce
atlanır. Drop başına 100 dosya cap'i vardır; daha büyük batchler →
birden fazla drop'a bölün.

### Çevirileri duraklatabilir ve devam ettirebilir miyim?

Evet. İstediğiniz zaman uygulamadan çıkın — Pending / Translating
görevleri bir sonraki başlatmada devam eder. Görev başına checkpointing,
devam ettiğinizde 100 PDF'in 47. sayfasının yeniden yapılmadığı
anlamına gelir.

### Çeviriyi elle düzenleyebilir miyim?

**Metin Çevir** için — evet, sağ panele tıklayın ve yazın. Düzenleme,
girdinin geçmiş kaydına otomatik kaydedilir.

**Belge Çevir** için — çevrilmiş dosyayı normal editörünüzde (Word,
LibreOffice, vb.) açın ve orada düzenleyin. Uygulama düzenlemeleri
geçmişe geri round-trip yapmaz.

### Bir string listesini toplu çevirebilir miyim?

CLI'yi kullanın:

```bash
ait *.txt --target French
```

Veya in-process stringler için (örn. koddan çıkarılmış UI stringleri),
`translate_text` MCP aracını bir listeyle çağırın veya Python API'sini
doğrudan kullanın:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Sözlük

### LLM neden sözlüğümü kullanmıyor?

Kontrol edilecek üç şey:

1. Set **aktif** (checkbox işaretli).
2. Sözlüğünüzdeki kaynak terim aslında kaynak metinde görünüyor
   (per-call sıkıştırma yalnızca batch metinle eşleşen girişleri LLM'e
   gönderir — token tasarrufu sağlar, ancak hatalı yazılmış bir
   kaynak terimin görünmez olduğu anlamına gelir).
3. Model yeterince güçlü — `flash-lite` bazen `flash` ve `pro`'nun
   onurlandırdığı ipuçlarını yok sayar.

### Sözlük terimleri aksandan bağımsız eşleşiyor mu?

Evet. Hem sözlük araması hem de Sözlük sayfasındaki arama çubuğu,
aksanları ve büyük/küçük harfi kaldıran bir normalizasyon işlevi
kullanır. Yani `cafe`, `Café` ve `CAFE`, kaynağı `Café` olan bir
girişe eşleşir.

## Gizlilik

### Herhangi bir kullanım verisi topluyor musunuz?

Hayır. Uygulamanın analytics SDK'sı yok. İsteğe bağlı güncelleme
kontrolü, başlangıçta tek bir GitHub Releases endpoint'ini sorgular;
**Ayarlar → Genel** içinde toggle edilebilir.

### API anahtarlarım güvende mi?

OS keychain'inizde saklanır (macOS'ta Keychain, Windows'ta Credential
Manager, Linux'ta Secret Service). Diğer süreçler açık izniniz
olmadan onları okuyamaz. Fallback (hiçbir keychain daemon'u
yokken — tipik olarak headless Linux sunucuları) kullanıcınızın
yapılandırma dizini altındaki düz metin INI'dir; bu modda anahtarlar
dosya izinleriyle korunur ancak kriptografik olarak şifrelenmez.
