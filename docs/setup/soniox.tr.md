---
description: AI Translate'in Live sayfasında gerçek zamanlı konuşmadan metne için Soniox'u yapılandır — konuşmacı diyarizasyonunu, sözlük terimlerini ve canlı çeviriyi destekler.
---

# Soniox (STT)

Soniox WebSocket API üzerinden gerçek zamanlı konuşmadan metne.
**[Altyazı](../features/generate-subtitle.md)** ve
**[Canlı Çeviri](../features/live-translation.md)** sayfaları
tarafından, STT yöntemi olarak Soniox'u seçtiğinde kullanılır.

## Neden Soniox

- **Gerçek zamanlı** — konuşmacı hala konuşurken tokenler gelir.
- **Konuşmacı diyarizasyonu** — token başına konuşmacı etiketleri
  (örn. _Konuşmacı 1: Merhaba…_).
- **Akış içi çeviri** — Soniox transkribe ederken çevirebilir,
  ekstra bir LLM gidiş-dönüşü tasarrufu sağlar.
- **Çok dilli** — kaynak dili akış ortasında bile otomatik algılar.

## Bir API anahtarı al

1. <https://console.soniox.com> adresinde kaydol
2. **API keys** → **Create new API key** aç
3. Kopyala (`Bearer ...` gibi görünür; sadece tokeni `Bearer ` ön
   eki olmadan kopyala).

Fiyatlandırma ses dakikası başına ölçülür (yazım sırasında
~$0.005 / dakika) — bkz. <https://soniox.com/pricing>.

## Uygulamada yapılandır

**Ayarlar → Servis**:

1. Anahtarı **Soniox API anahtarı** içine yapıştır → **Kaydet**

**Ayarlar → Live** *(canlı çeviri için)* veya **Ayarlar → Altyazı**
*(altyazı oluşturma için)*:

1. **STT yöntemi**'ni **Soniox** olarak ayarla

## Neyi güçlendirir

| Sayfa | Soniox'u şu durumda kullan |
|---|---|
| **Altyazı** | SRT'de konuşmacı etiketleri istediğin çoklu konuşmacı kayıtları (röportajlar, paneller, toplantılar) |
| **Canlı Çeviri** | Gerçek zamanlı toplantı altyazılaması, özellikle birden fazla konuşmacıyla |

## Sözlük terimleri

Soniox WebSocket'i tanımayı önyargılamak için bir terim sözlüğü
kabul eder. Uygulama aktif sözlük girişlerini otomatik olarak iletir —
marka adları / özel isimler / jargon daha güvenilir bir şekilde
tanınır.

## Uyarılar

!!! warning "Sadece çevrimiçi"
    Soniox yalnızca buluttur; eğer sesin hassasiysa (tıbbi, hukuki),
    yerine Whisper (yerel) kullan.

!!! info "Yeniden bağlanma"
    WebSocket geçici hatalarda üstel geri çekilme ile otomatik olarak
    yeniden bağlanır. Uzun oturumlar kısa ağ kesintilerinden bağlı
    kalır.

## Yaygın hatalar

| Hata | Olası neden |
|---|---|
| `AUTH_ERROR` | Yanlış / süresi dolmuş API anahtarı. Ayarlar → Servis'te tekrar yapıştır. |
| `QUOTA_ERROR` | Plan sınırı aşıldı. |
| `CONNECTION_ERROR` | Ağ engellendi / güvenlik duvarı. Farklı bir ağdan tekrar dene. |
