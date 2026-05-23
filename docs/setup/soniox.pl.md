---
description: Skonfiguruj Soniox dla speech-to-text w czasie rzeczywistym na stronie Live AI Translate — obsługuje diaryzację mówców, terminy glosariusza i tłumaczenie na żywo.
---

# Soniox (STT)

Speech-to-text w czasie rzeczywistym przez Soniox WebSocket API.
Używane przez strony **[Subtitle](../features/generate-subtitle.md)**
i **[Live Translation](../features/live-translation.md)** gdy wybierasz
Soniox jako metodę STT.

## Dlaczego Soniox

- **Czas rzeczywisty** — tokeny przybywają, gdy mówca wciąż mówi.
- **Diaryzacja mówcy** — etykiety mówcy per-token (np.
  _Speaker 1: Hi…_).
- **Tłumaczenie w strumieniu** — Soniox może tłumaczyć podczas
  transkrybowania, oszczędzając dodatkową rundę LLM.
- **Wielojęzyczny** — auto-wykrywa język źródłowy nawet w środku
  strumienia.

## Pobierz klucz API

1. Zarejestruj się na <https://console.soniox.com>
2. Otwórz **API keys** → **Create new API key**
3. Skopiuj go (wygląda jak `Bearer ...`; skopiuj sam token bez
   prefiksu `Bearer `).

Cena jest mierzona za minutę audio (~$0.005 / minutę w czasie
pisania) — zobacz <https://soniox.com/pricing>.

## Konfiguruj w aplikacji

W **Settings → Service**:

1. Wklej klucz w **Soniox API key** → **Save**

W **Settings → Live** *(dla tłumaczenia na żywo)* lub
**Settings → Subtitle** *(dla generowania napisów)*:

1. Ustaw **STT method** na **Soniox**

## Co zasila

| Strona | Używaj Soniox, gdy |
|---|---|
| **Subtitle** | Nagrania wielomówcowe (wywiady, panele, spotkania), gdzie chcesz etykiet mówców w SRT |
| **Live Translation** | Tłumaczenie napisów spotkań w czasie rzeczywistym, zwłaszcza z wieloma mówcami |

## Terminy glosariusza

Soniox WebSocket akceptuje glosariusz terminów do biasu rozpoznawania.
Aplikacja automatycznie przekazuje twoje aktywne wpisy glosariusza —
nazwy marek / nazwy własne / żargon są rozpoznawane bardziej
niezawodnie.

## Zastrzeżenia

!!! warning "Tylko online"
    Soniox jest tylko chmurowy; jeśli twój dźwięk jest wrażliwy
    (medyczny, prawny), użyj Whisper (lokalny) zamiast tego.

!!! info "Ponowne połączenie"
    WebSocket auto-reconnectuje na błędach przejściowych z
    eksponencjalnym backoffem. Długie sesje pozostają połączone
    przez krótkie zaniki sieci.

## Częste błędy

| Error | Prawdopodobna przyczyna |
|---|---|
| `AUTH_ERROR` | Zły / wygasły klucz API. Wklej ponownie w Settings → Service. |
| `QUOTA_ERROR` | Przekroczono limit planu. |
| `CONNECTION_ERROR` | Sieć zablokowana / firewall. Spróbuj ponownie z innej sieci. |
