---
description: Çeviriler arasında tutarlı terminoloji uygulamak için özel sözlük setlerini yönetin — CSV içe/dışa aktarma, dil çifti başına kapsam, proje başına önceliklendirme.
---

# Sözlük

Her çeviri işinde belirli terimleri belirli çevirilere kilitleyin.
Marka adları, ürün terminolojisi, teknik jargon veya tutarlı tutmak
istediğiniz karakter adları için yararlıdır.

## Nasıl çalışır

Bir sözlük, bir **set** içinde gruplanmış (kaynak terim, hedef terim)
çiftlerinin listesidir. Bir seti açtığınızda, uygulamadaki her LLM
çağrısı, ilgili girişlerin prompt'a enjekte edildiğini alır — böylece
LLM çevirmeden önce "OpenAI için 'OpenAI' kullan, '开放AI' değil" görür.

Birden fazla set aynı anda aktif olabilir. Yalnızca kaynağı veya
hedefi batch metninde görünen girişler prompt'a eklenir (çağrı başına
sıkıştırma), bu yüzden 5.000 girişli bir sözlük token açısından ucuz kalır.

## Adım adım

1. Kenar çubuğunda **Sözlük**'e tıklayın.
2. **Yeni set**'e tıklayın (`Ctrl+N`) ve bir ad verin (örn. "Acme Projesi").
3. Solda set seçiliyken, sağ panel girişlerini gösterir.
4. Yeni bir giriş oluşturmak için **Ekle**'ye tıklayın. Doldurun:
    - **Kaynak** — orijinal terim
    - **Hedef** — uygulanacak çeviri
    - İsteğe bağlı bir yorum / not
5. Her terim için tekrarlayın.
6. Çevirilerde kullanmak için set adındaki **Aktif** kutusunu işaretleyin.

## Setleri aktif/pasif yapma

Her set adının yanındaki **Aktif** kutusu, girişlerinin LLM
prompt'larına enjekte edilip edilmeyeceğini kontrol eder. 50 pasif
seti depolamada bırakıp yalnızca mevcut proje için ihtiyacınız olan
2'sini açabilirsiniz.

## İçe/Dışa Aktar (CSV)

- **Dışa Aktar** — bir set seçin, **Dışa Aktar**'a tıklayın → `.csv`
  olarak kaydedin. İki sütun: `source`, `target` (UTF-8, virgülle
  ayrılmış, RFC 4180 quoting).
- **İçe Aktar** — **İçe Aktar**'a tıklayın → bir `.csv` seçin →
  hedef set seçin (mevcut veya yeni). Yinelenen kaynakta değiştir-veya-atla
  istemi alırsınız.

CSV formatı round-trip yapar, böylece Dışa Aktar → Excel'de düzenle →
İçe Aktar güvenlidir.

## Arama ve filtreleme

`Ctrl+F` arama kutusuna odaklanır. Herhangi bir alt dize yazın ve
girişler (ve set listesi) eşleşmelere filtrelenir; eşleşen alt dize
vurgulanır. Aramayı temizlemek tam listeyi geri yükler.

Arama **aksana duyarsız ve büyük/küçük harfe duyarsızdır** — `cafe`,
`café`'yi bulur ve tersi.

## Yerinde düzenleme

Düzenlemek için herhangi bir hücreye tıklayın. Sonraki hücreye
geçmek için `Tab`'a basın. Geri almak için `Esc`'e basın. Satırın
dışına tıkladığınızda otomatik kaydetme tetiklenir. Boş kaynak veya
hedef geçersiz bir girdi kaydetmek yerine satırı geri alır.

## Silme

- **Tek bir girişi sil** — seçin, `Del`'e basın. Bir onay diyaloğu
  göreceksiniz.
- **Tüm bir seti sil** — seti seçin, `Del`'e basın. Diyalog, sildiğiniz
  şeyi bilmeniz için kaskat girdi sayısını gösterir.

## Kısayollar

| Kısayol | Eylem |
|---|---|
| `Ctrl+N` | Yeni set |
| `Ctrl+F` | Aramaya odaklan |
| `Del` | Seçili giriş / seti sil |

## İpuçları

!!! tip "Set başına kapsam"
    Bir set *mantıksal* bir gruplamadır. Proje başına, müşteri başına,
    domain başına (tıbbi / hukuk / gaming) — anlamlı olan şekilde
    grupla. Yalnızca mevcut işle ilgili setleri aktifleştirin.

!!! tip "Sözlük çeviriyi geçersiz kılmaz"
    LLM'e sözlük girişlerini kullanma talimatı verilir, ancak bu yine
    de bir ipucudur — son derece beceriksiz zorlanmış çeviriler hala
    yüzeye çıkabilir. Tam cümleler yerine basit `terim → çeviri`
    çiftleri kullanın.
