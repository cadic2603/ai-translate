---
description: Görüntü ve PDF metin çıkarımı için OCR motorlarını kur — çevrimdışı Tesseract veya EasyOCR ya da bulut tabanlı Google Vision OCR arasında seçim yap.
---

# OCR Motorları

OCR, görüntülerden metni okumak için kullanılır — hem
[Metin Çıkar](../features/extract-text.md) sayfasında hem de bir
sayfa taranmış olduğunda (metin katmanı yok) veya **Gömülü
görüntüleri çevir** açıldığında Belge çevirisi içinde geri dönüş
olarak.

Üç OCR motoru arasından seçim yapabilirsin.

## Tesseract (önerilen varsayılan)

Ücretsiz, hızlı, çevrimdışı. Bir sistem kurulumu gerektirir.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` desteklenen her dili getirir. Diskten
    tasarruf etmek için yalnızca ihtiyacın olanı kur (örn. Fransızca
    için `tesseract-ocr-fra`).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Yükleyiciyi
    [UB Mannheim'ın Tesseract sürümleri](https://github.com/UB-Mannheim/tesseract/wiki)
    adresinden indir. Çalıştır, varsayılanları kabul et — dil
    paketleri paket halinde gelir.

Doğrula:

```bash
tesseract --version
tesseract --list-langs
```

Masaüstü uygulamada: **Ayarlar → OCR → OCR yöntemi = Tesseract**.
Bitti.

## EasyOCR

Ücretsiz, çevrimdışı. Latin olmayan yazılar için harika (Çince,
Korece, Japonca, Tayca). Modeller ilk kullanımda indirilir
(toplamda ~1 GB).

```bash
uv sync --extra easyocr
```

Masaüstü uygulamada: **Ayarlar → OCR → OCR yöntemi = EasyOCR**.

Bir dil için ilk kullanımda, ilgili model `~/.EasyOCR/`'a indirilir.
Sonraki çalıştırmalar anında.

## Google Cloud Vision

Bulut, ücretli (ayda 1.000 ücretsiz istek). En yüksek doğruluk,
özellikle gürültülü / el yazısı / çok yazılı içerikte.

1. [Bir Google Cloud projesi oluştur](https://console.cloud.google.com/projectcreate)
2. [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)'yi etkinleştir
3. [Bir API anahtarı oluştur](https://console.cloud.google.com/apis/credentials)
4. Masaüstü uygulamada: **Ayarlar → Servis → Google Cloud API anahtarı** → yapıştır
5. **Ayarlar → OCR → OCR yöntemi = Google Cloud OCR**

Aynı Google Cloud API anahtarı, bu API'leri de etkinleştirirsen
Vision OCR, Speech-to-Text ve Text-to-Speech'i güçlendirir.

## Doğruluk karşılaştırması

**Ayarlar → OCR** sekmesinde küçük bir karşılaştırma tablosu
yerleşiktir — dil kapsamı, çevrimiçi/çevrimdışı, maliyet, doğruluk.
Her geçiş yapma cazibesi geldiğinde tekrar oku.

## OCR ne zaman kullanılır

| Yer | Davranış |
|---|---|
| **Metin Çıkar sayfası** (yöntem = OCR olduğunda) | Bırakılan görüntülerde doğrudan OCR |
| **Belge Çevir → PDF** | Yalnızca-tarama sayfalarında OCR geri dönüşü (metin katmanı yok) |
| **Belge Çevir → Office** ile **Gömülü görüntüleri çevir** açık | Her gömülü görüntüde OCR + LLM görüntüsü |

## İpuçları

!!! tip "Kaynak dili seç"
    Çoğu OCR motoru, hangi dili beklediğini söylediğinde çok daha
    doğrudur. Altyazı / Belge / Metin Çıkar sayfalarının tümü
    **Kaynak dil** seçicini OCR motoruna iletir.

!!! tip "Tesseract temiz basılı metin için yeterli"
    Tesseract / EasyOCR içeriğinde gerçekten başarısız olana kadar
    bulut OCR'a uzanma. Bunlar ücretsiz, hızlı ve şaşırtıcı derecede
    iyi.
