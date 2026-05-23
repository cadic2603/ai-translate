---
description: OCR motorlarını (Tesseract, EasyOCR, Google Vision) veya LLM vision'ı kullanarak resim ve ekran görüntülerinden metin çıkarın — TXT veya DOCX olarak çıktı.
---

# Metin Çıkar

Resimlerden metni çıkarın — fişler, ekran görüntüleri, fotoğraflanmış
belgeler, taranmış sayfalar, ne olursa. Çıktı `.txt` (düz) veya
`.docx` (biçimlendirilmiş paragraflar).

Bu sayfa **çevirmez** — sadece çıkarır. Çeviri de istiyorsanız çıktıyı
Belge Çevir'e aktarın.

## İki çıkarma yöntemi

| Yöntem | En uygun |
|---|---|
| **OCR** | Yüksek hacim / batch / maliyete duyarlı (resim başına ücretsiz veya çok düşük maliyetli) |
| **LLM vision** | Düzen koruma, karışık scriptler, düşük kaliteli resimler, el yazısı |

Varsayılanı **Ayarlar → Metin Çıkar → Çıkarma yöntemi** içinde seçin.

## OCR motorları (OCR yöntemi)

| Motor | Maliyet | Çevrimdışı | Diller | Notlar |
|---|---|---|---|---|
| **Tesseract** | Ücretsiz | Evet | 100+ | Varsayılan. Sistem kurulumu gerekir. |
| **EasyOCR** | Ücretsiz | Evet (model indirildikten sonra) | 80+ | Latin olmayan scriptler için en iyisi. ~1 GB model. |
| **Google Cloud Vision** | Ücretli (ayda 1.000 ücretsiz) | Hayır | 60+ | En yüksek doğruluk. |

**Ayarlar → OCR**'da yapılandırın.

## Adım adım

1. Kenar çubuğunda **Metin Çıkar**'a tıklayın.
2. Bir veya daha fazla resim dosyası bırakın (`.png`, `.jpg`, `.jpeg`,
   `.bmp`, `.webp`, `.tiff`, `.tif`).
3. **Kaynak dili** seçin (OCR'ın doğru modeli seçmesine yardımcı olur).
4. **Çıktı formatını** seçin — `.txt` veya `.docx`.
5. **Çıkar**'a tıklayın (veya `Ctrl+Enter`).
6. Bittiğinde satırda **Aç**'a tıklayın.

## Hangisini ne zaman

- **Metin yoğun fiş / fatura** → Tesseract hızlı ve doğru.
- **Fotoğraflanmış el yazısı notlar** → LLM vision büyük farkla kazanır.
- **Manga / çizgi roman panelleri** → EasyOCR (dikey CJK metni iyi işler).
- **Çok küçük alanı olan form** → Google Cloud Vision diğerlerinden
  alan sınırlarını daha iyi korur.

## İpuçları

!!! tip "OCR veya LLM, ikisi birden değil"
    Sayfa bir yöntem seçer ve çalıştırır. Çıktıları karşılaştırmak için
    aynı resmi farklı yöntemlerle iki kez çalıştırın.

!!! tip "Kurulum gerekli iletişim kutusu"
    OCR seçtiyseniz ancak hiçbir OCR motoru yapılandırılmamışsa
    (veya LLM ama hiçbir LLM anahtarı yapılandırılmamışsa), sayfa
    ilgili Ayarlar sekmesine doğrudan bağlantı veren tek bir
    "Kurulum gerekli" iletişim kutusu gösterir.

## Kısayollar

| Kısayol | Eylem |
|---|---|
| `Ctrl+Enter` | Çıkar |
| `Ctrl+O` | Gözat |
| `Ctrl+F` | Geçmiş aramasına odaklan |
