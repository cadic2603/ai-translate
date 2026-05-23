---
description: Dosyaları headless olarak çevirmek için ait komut satırı arayüzünü kullanın — bir script veya CI işinden PDF'leri, Office belgelerini, altyazıları ve 45+ dili destekler.
---

# Komut Satırı (`ait`)

Headless çeviri — masaüstü uygulamasıyla aynı pipeline, ekran
gerektirmez. CI, batch işler, sunucular ve scripte edilmiş workflow'lar
için yararlı.

## Hızlı başlangıç

```bash
ait report.docx --target French
```

Çıktı kaynağın yanına `report_translated_<src>_<tgt>.docx` olarak iner.

## Yaygın tarifler

### Birden fazla dosya

```bash
ait *.pdf --target Japanese
```

Glob genişletme shell'in işidir (Unix). Windows / `cmd.exe`'de
dosyaları açıkça listeleyin veya PowerShell kullanın:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Özel çıktı dizini

```bash
ait report.docx --target French --output ./translated/
```

Dizin yoksa oluşturulur. Oluşturulamazsa (izin reddedildi vb.) açık
bir hata ve çıkış kodu 2 alırsınız — yarım çalışma yok.

### Kaynak dili belirtin

```bash
ait letter.txt --target German --source "English (US)"
```

Kaynak eşleşmesi büyük/küçük harf duyarsız. Çıplak "Chinese" bir
ipucu yazdırır:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Belirli bir model seçin

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Veya masaüstü uygulamasının LLM sekmesinde kayıtlı herhangi bir Provider:model_name.
```

Format kesin olarak `Provider:model_name`. İki nokta yoksa → varsayılan
Gemini modeline sessizce dönmek yerine net bir mesajla 2 ile çıkış.

### Office seçenekleri

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` yapılandırılmış OCR gerektirir (bkz.
[OCR Motorları](setup/ocr-engines.md)).

### Legacy formatların otomatik dönüştürülmesi

```bash
ait old-doc.doc --target French --convert-legacy
```

Pipeline önce `.doc` → `.docx` dönüştürür (daha iyi doğruluk), modern
kopyayı çevirir, geri dönüştürür. `--convert-odf` ve `.odt` / `.ods` /
`.odp` için aynı.

### Sessiz / ayrıntılı

```bash
ait report.docx --target French --quiet      # yalnızca hatalar
ait report.docx --target French --verbose    # tam DEBUG firehose
```

Varsayılan mod stderr'e bir banner ve görev başına ilerleme yazdırır;
tam ayrıntı (HTTP body dump'ları, retry logları) konsol ayrıntı
seviyesinden bağımsız olarak platformun uygulama-log dizinine iner
(işletim sisteminizdeki yol için
[Sorun giderme → Loglar nerede?](troubleshooting.md#where-are-the-logs)
bölümüne bakın).

### Desteklenen dilleri listele

```bash
ait --list-languages
```

Desteklenen 45 dilin tümünü yazdırır. Shell döngülerine pipe etmek
için yararlı.

### Sürüm

```bash
ait --version
# ait 0.1.0
```

## Çıkış kodları

| Kod | Anlam |
|---|---|
| `0` | Tüm görevler başarılı |
| `2` | Argüman hatası (bilinmeyen dil, eksik hedef, hatalı biçimlendirilmiş model, yazılamayan çıktı, desteklenmeyen dosya uzantısı) |
| `3` | LLM yapılandırılmadı |
| `4` | Kısmi başarısızlık (bazıları başarılı, bazıları değil) |
| `5` | Tümü başarısız |
| `130` | Kesintiye uğradı (`Ctrl+C`) |

## İptal

`Ctrl+C` bir kez — kooperatif iptal. Mevcut görevin checkpoint'i
kaydedilir, pipeline bir sonraki polling sınırında temiz çıkar.

`Ctrl+C` tekrar — sert kesinti. Az kullanın; kısmi dosyalar yarı
yazılmış durumda kalabilir.

## Tam flag referansı

```bash
ait --help
```

Her flag'i varsayılanıyla gösterir. Aynı içerik burada özetlendi:

| Flag | Varsayılan | Notlar |
|---|---|---|
| `--target / -t LANG` | _gerekli_ | Büyük/küçük harf duyarsız |
| `--source / -s LANG` | otomatik algıla | Büyük/küçük harf duyarsız |
| `--output / -o DIR` | kaynağın üst dizini | Yoksa oluşturulur |
| `--model / -m PROVIDER:MODEL` | masaüstü varsayılanı | Kesin format |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | kapalı | Yapılandırılmış OCR gerektirir |
| `--translate-comments` | kapalı | Office yorumları |
| `--translate-shapes` | kapalı | Şekiller / metin kutuları |
| `--translate-notes` | kapalı | PowerPoint konuşmacı notları |
| `--translate-sheet-names` | kapalı | Excel sayfa sekmeleri |
| `--convert-legacy` | kapalı | `.doc`/`.xls`/`.ppt` → modern format |
| `--convert-odf` | kapalı | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | kapalı | Tamamlandıktan sonra geçmiş girdilerini koru |
| `--quiet / -q` | kapalı | Konsolda yalnızca hatalar |
| `--verbose / -v` | kapalı | DEBUG firehose |
| `--list-languages` | — | 45 dili yazdırır ve çıkar |
| `--version` | — | Sürümü yazdırır ve çıkar |

## İpuçları

!!! tip "Bir kez yapılandırın, her yerde kullanın"
    CLI, API anahtarlarını ve ayarlarını masaüstü uygulamasıyla
    paylaşır — her şeyi GUI'de bir kez ayarlayın, sonra oradan `ait`
    ile otomatikleştirin.

!!! tip "Cold-start endpoint cache'i"
    Her `(endpoint, model)` çifti için, chat-vs-responses-API seçimi
    ve çalışan payload varyantı OS cache dizinindeki
    `llm_endpoint_cache.json`'a kalıcılaştırılır
    (Linux'ta `~/.cache/ai-translate/`,
    macOS'ta `~/Library/Caches/ai-translate/`,
    Windows'ta `%LOCALAPPDATA%\ai-translate\cache\`). Cold-start CLI
    çağrıları, ilk başarılı çağrıdan sonra otomatik algılama probe'unu
    tamamen atlar — sağlayıcıya özgü payload ayarı gerektiren
    Azure / vLLM / OpenRouter / Anthropic / DeepSeek dağıtımlarına
    karşı script yazarken yararlıdır. Cache çoklu süreç ve çoklu
    thread güvenli (atomik rename ile RLock altında read-merge-write).

!!! tip "Çıktı akışları"
    Varsayılan mod banner'ı, kuyruğa alınmış görev listesini ve görev
    başına ilerlemeyi **stdout**'a yazdırır (hatalarla doğru şekilde
    iç içe geçmesi için satır tampolu); hata mesajları ve log kayıtları
    **stderr**'e gider. Temiz piping için stdout'u tamamen bastırmak
    için `--quiet` ile birleştirin:

    ```bash
    ait --list-languages | grep -i japanese    # stdout'ta veri
    ait file.txt --target French --quiet 2> errors.log
    ```
