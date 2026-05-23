---
description: PDF, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT ve 30+ diğer dosya formatını biçimlendirme ve düzeni koruyarak çevir.
---

# Belge Çevir

Tam dosyaları çevir — Office, PDF, EPUB, düz metin, altyazılar,
yerelleştirme formatları ve daha fazlası — biçimlendirme korunur.

## Desteklenen formatlar

| Kategori | Uzantılar |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Metin & web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eKitaplar | `.epub` |
| Altyazılar | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Yerelleştirme | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Adım adım

1. Kenar çubuğunda **Belge Çevir**'e tıkla.
2. Dosyaları sürükle (veya **Gözat**'a tıkla). Klasörler de çalışır
   — içindeki desteklenen dosyalar özyinelemeli olarak alınır.
3. **Kaynak**'ı (veya `Otomatik algıla` olarak bırak) ve **Hedef**'i
   seç.
4. **Çevir**'e tıkla — veya `Ctrl+Enter`'a bas.
5. Aşağıdaki geçmiş tablosu dosya başına ilerlemeyi gösterir
   (Beklemede → Çeviriliyor → Bitti / Başarısız). Kenar çubuğu, bir
   görev aktifken bir spinner gösterir.
6. Çevrilmiş dosyayı açmak için bir satırdaki **Aç**'a tıkla. Sağ
   tıklayınca seçenekler: yeniden çevir, duraklat, yeniden dene, sil.

## Dosyalar nereye gider

Varsayılan olarak çevrilmiş dosyalar orijinalin yanına
`_translated_<src>_<tgt>` son ekiyle kaydedilir:

```
~/Documents/rapor.docx
~/Documents/rapor_translated_en_tr.docx     ← burada
```

Bunu **Ayarlar → Genel → Çeviri depolama yolu** içinde özel bir
dizine değiştir.

## Limitler ve korumalar

- **100 dosya bırakma sınırı** — daha fazla bırak ve bir bildirim
  alırsın. Toplu olarak çevir.
- **Yinelenen algılama** — kuyrukta zaten olan bir dosyayı bırak ve
  bir bildirim göreceksin (yinelenen iki kez eklenmek yerine
  bırakılır).
- **Otomatik devam** — çeviriler çalışırken uygulamadan çık, bir
  sonraki açılışta devam ederler (Beklemede / Çeviriliyor görevleri).

## Office'e özgü seçenekler

**Ayarlar**'daki Çeviri sekmesi Office dosyaları için bu
geçişleri açığa çıkarır:

| Seçenek | Ne yapar |
|---|---|
| **Gömülü görüntüleri çevir** | `.docx` / `.xlsx` / `.pptx` içindeki görüntülerde OCR + LLM görüntüsü çalıştırır ve çevrilmiş görüntüyü yeniden ekler. Yapılandırılmış OCR gerektirir. |
| **Yorumları çevir** | Yorumlar / inceleme notları gövde metniyle birlikte çevrilir. |
| **Şekilleri & metin kutularını çevir** | Şekillerde, baloncuklarda ve yüzen metin kutularında yaşayan metni yakalar. |
| **Konuşmacı notlarını çevir** | PowerPoint konuşmacı notları çevrilir. |
| **Sayfa adlarını çevir** | Excel sayfa sekme etiketleri çevrilir. |
| **Eski formatı otomatik dönüştür** | `.doc` / `.xls` / `.ppt`, çeviri öncesinde modern OOXML'e dönüştürülür (daha iyi sadakat). |
| **ODF'yi otomatik dönüştür** | `.odt` / `.ods` / `.odp`, çeviri öncesinde OOXML'e dönüştürülür. |

Tüm Office çevirisi run başına biçimlendirmeyi korur: kalın, italik,
altı çizili, üstü çizili, font boyutu, renk, köprüler, üstbilgiler,
altbilgiler, dipnotlar, son notlar, hepsi.

### Gömülü görsel çevirisi: uyarıyla-atla + önbellek

**Gömülü görselleri çevir** açık olduğunda, her gömülü görsel
OCR → LLM görüşü → görüntülenmiş yeniden enjeksiyondan geçer.
Bilinmesi gereken iki davranış:

- **Uyarıyla-atla**: bir görsel çevrilemezse (çok büyük,
  bozuk, görüntü modeli formatı reddediyor, vs.) belge yine
  de tamamlanır — bozuk görsel orijinal dilde kalır,
  `app.log` dosyasına bir uyarı kaydedilir ve döngü bir
  sonraki görselle devam eder. Yalnızca ölümcül LLM
  hataları (`AUTH_ERROR`, `QUOTA_ERROR`,
  `VISION_NOT_SUPPORTED`) işlem hattını derhal durdurur
  çünkü kalan tüm görselleri de engellerler. **Gömülü
  görselleri çevir** onay kutusunun üzerindeki bilgi
  şeridi politikayı satır içinde belgeler.
- **Görsel başına önbellek**: başarılı görsel çevirileri
  görevin iç depolama dizininde kaynak baytların SHA256
  anahtarıyla saklanır. Yeniden denemede, daha önce
  çevrilmiş görseller OCR + LLM'yi yeniden çalıştırmak
  yerine önbelleğe çarpar — ücretli iş yeniden
  yapılmaz. Tekrarlanan görseller (her slaytta bir şirket
  logosu) bir kez çevrilir ve N − 1 kez yeniden
  kullanılır.

Çıktı dosyası, seçtiğiniz çıktı klasörüne yalnızca
**başarı** durumunda görünür — iptal edilen veya
başarısız çalışmalardan kalan kısmi çeviriler görevin iç
depolama dizininde sınırlı kalır, böylece çıktı klasörünüz
asla yetim yarım çevrilmiş belgeler toplamaz.

## PDF'in özellikleri

PDF'ler bir extract-overlay motoru kullanır: orijinal metin yerinde
redakte edilir ve çevrilmiş metin aynı kutulara bindirilir, görsel
düzeni korur. Sayfa başı checkpoint, duraklatılmış / çökmüş bir
çalışmanın 1. sayfadan değil, kaldığı yerden devam ettiği anlamına
gelir.

Çevrilenler:

- Gövde metni (hizalama algılama ile — sol / orta / sağ / yasla)
- Yer imleri / ana hatlar (TOC girişleri)
- Form alanları (metin girişleri, açılır menüler, liste kutuları)
- Köprüler (link rect yeni metni saracak şekilde güncellenir)
- Gömülü görüntüler (**Gömülü görüntüleri çevir** açıkken)
- PDF yorumları / ek açıklamaları

Taranmış PDF'ler için (gömülü metin katmanı olmadan), OCR sayfa başına
otomatik olarak çalışır. OCR motorunu **Ayarlar → OCR**'da
yapılandır.

## Sağdan-sola çıktı

**Arapça**, **İbranice** veya **Farsça**'ya çeviriler her çıktı
formatında yerel olarak RTL render edilir — PDF overlay'lerine, HTML
ve EPUB bölümlerine `dir="rtl"` enjekte edilir (Apple Books ve
Kindle'ın doğru yöne sayfa çevirmesi için EPUB OPF'sinde
`page-progression-direction="rtl"`); DOCX `<w:bidi/>` + `<w:rtl/>`,
PPTX `rtl="1"`, XLSX sağdan sola sayfa görünümü, ODT/ODS/ODP
`style:writing-mode="rl-tb"`, RTF `\rtldoc` ve ASS/SSA hizalama
kodu yansıtması (`\an1` ↔ `\an3`, `\an4` ↔ `\an6`, vb.). Orta
hizalamalar dokunulmaz.

## Kısayollar

| Kısayol | Eylem |
|---|---|
| `Ctrl+Enter` | Çeviriyi başlat |
| `Ctrl+O` | Dosyalarda gözat |
| `Ctrl+F` | Geçmiş aramasına odaklan |
| `Ctrl+P` | Aktif kuyruğu duraklat |
| `Ctrl+G` | Aktif kuyruğu sürdür |
| `Delete` | Seçili geçmiş girişlerini sil |

`Ctrl+P` / `Ctrl+G`, bir metin girişinin odakta olduğu zaman
bastırılır, böylece yazmayla çakışmaz.

## Bir şey ters gidince

Başarısız bir görev hata kodu ve yerelleştirilmiş bir mesajla
kırmızı durum gösterir — yaygın olanlar için
[sorun giderme kılavuzu](../troubleshooting.md)'na bak (`AUTH_ERROR`,
`QUOTA_ERROR`, `FFMPEG_NOT_FOUND`, vb.).
