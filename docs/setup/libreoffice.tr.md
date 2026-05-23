---
description: AI Translate'in macOS ve Linux'ta eski Office formatlarını (.doc, .xls, .ppt) ve ODF dosyalarını (.odt, .ods, .odp) çevirebilmesi için LibreOffice'i kur.
---

# LibreOffice (Office formatları)

Office çeviri pipeline'ı, mevcut en iyi arka ucu bu sırayla seçer:

1. **win32com** (Windows + kurulu MS Office) — en yüksek sadakat
2. **LibreOffice UNO** (çapraz platform) — win32com olmadığında
   geri dönüş
3. **python-docx / openpyxl / python-pptx** (yalnızca modern
   formatlar) — yukarıdakilerden hiçbiri kullanılamadığında saf
   Python geri dönüşü

LibreOffice, Linux ve macOS'ta eski `.doc` / `.xls` / `.ppt` için
**tek yoldur** ve modern Office formatları için de bu platformlarda
önerilen yoldur (saf Python arka ucundan daha iyi sadakat, özellikle
tablolar ve gömülü nesneler için).

## Kurulum

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    Veya <https://www.libreoffice.org/download/download/> adresinden
    indir.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Windows'taki masaüstü uygulaması genellikle MS Office kurulu
    olarak **win32com** kullanır — MS Office eksikse LibreOffice
    *geri dönüş*tür. <https://www.libreoffice.org/download/download/>
    adresinden kur.

## Doğrulama

```bash
soffice --version
```

macOS'ta "command not found" alırsan, ikili
`/Applications/LibreOffice.app/Contents/MacOS/soffice` konumundadır.
Uygulama, yaygın kurulum yolları boyunca onu otomatik keşfeder, ancak
gerekirse **Ayarlar → Genel → LibreOffice yolu** içinde geçersiz
kılabilirsin.

## Neyi güçlendirir

LibreOffice aktif arka uç olduğunda:

| Özellik | Not |
|---|---|
| **Modern Office** (`.docx`, `.xlsx`, `.pptx`) | win32com kullanılamadığında geri dönüş olarak kullanılır |
| **Eski Office** (`.doc`, `.xls`, `.ppt`) | Gerekli — saf Python bunları okuyamaz |
| **ODF** (`.odt`, `.ods`, `.odp`) | **ODF'yi otomatik dönüştür** açıkken round-trip dönüştürme için kullanılır |
| **Eski / ODF → OOXML otomatik dönüştürme** | Gerekli |

## Arka plan süreci

LibreOffice ilk kez gerektiğinde, uygulama headless modda bir
`soffice` süreci başlatır ve onu çeviriler arasında canlı tutar
(`office_lifecycle.py`). Uygulama çıkışında otomatik olarak kapanır.

## Uyarılar

!!! warning "İlk çalıştırma başlangıç süresi"
    LibreOffice'e dokunan ilk çeviri, `soffice`'nin başlaması için
    ~5-10 saniye bekler. Sonraki çeviriler aynı süreci yeniden
    kullanır ve hızlıdır.

!!! info "JVM çökme günlükleri"
    LibreOffice'in Java bileşeni segfault olduğunda zaman zaman
    `hs_err_pid*.log` dosyaları üretir. Uygulama bunları, proje
    klasörünü kirletmesinler diye geçici bir dizine yönlendirir.

!!! tip "Eski / ODF otomatik dönüştürme"
    Düzenli olarak `.doc` / `.xls` / `.ppt` çeviriyorsan **Ayarlar →
    Çeviri → Eski formatı otomatik dönüştür**'ü etkinleştir. Pipeline
    bunları önce `.docx` / `.xlsx` / `.pptx`'e (via
    `convert_to_modern_format`) dönüştürür, modern kopyayı çevirir,
    sonra geri dönüştürür. Sadakat, eski formatı doğrudan
    çevirmekten çok daha yüksektir.
