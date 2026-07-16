measurement_incident_until: 2026-08-15

# Kontekst biznesowy — SENDLY (wstrzykiwany do promptu raportu)

> Odpowiednik cmo_context.md dla marki SENDLY. Żywy dziennik: incydenty pomiaru,
> stałe decyzje właściciela, fakty zweryfikowane, zmiany na koncie. Aktualizowany
> przy każdej zmianie/decyzji, żeby raport nie flagował artefaktów i nie rekomendował
> rzeczy już rozstrzygniętych.

## Aktywne incydenty pomiaru
- **Faza launchu (do ~2026-08-15):** GA4 sendly zbiera dane dopiero od startu serwisu (~lipiec 2026). Brak pełnego okna „poprzedni tydzień" → porównania week-over-week są puste lub oparte na niepełnym oknie. NIE oceniaj wydajności po tym oknie, NIE flaguj braku danych jako spadku.
- **Konwersja rejestracji JEST mierzona od 2026-07-15:** event `sign_up` odpala się na SUKCESIE rejestracji (sendly-www v1.4.69+), oznaczony jako kluczowe zdarzenie GA4 i zaimportowany do Google Ads jako GŁÓWNA konwersja (kategoria SIGNUP, id 7686393241). `generate_lead` (formularz kontaktu) = konwersja dodatkowa. Dane liczą się od 2026-07-15 — wcześniejszych rejestracji w GA4 nie ma. Nadal MYLĄCE (ignoruj jako konwersje): `form_start` (start formularza), `sign_up_open` (wejście na formularz), `ads_conversion_PURCHASE_1` (stary tag na widok strony; NIE został zaimportowany do konta Ads — temat zamknięty). NIE rekomenduj już „wdrożenia eventu sign_up" ani „przepięcia konwersji" — zrobione.
- **Ruch dev z referral localhost:8765 (13–15.07):** testy własne Toma (klik z lokalnego devu na produkcję). Od v1.4.68 gtag nie wysyła z localhost, ale sesje z referrerem localhost mogą się jeszcze zdarzyć — traktuj jako ruch wewnętrzny, nie organiczny wzrost.

## Stałe decyzje właściciela (nie rekomenduj wbrew nim)
- Pozycjonowanie: „SMS API prosto od operatora, bez pośredników, pay-as-you-go, 100 SMS gratis". Nie sugeruj modelu abonamentowego ani pośredników.
- Produkt 2FA/OTP jest świadomie ukryty (nie ma go w API) — nie rekomenduj promocji tej strony.
- Google Ads sendly działa na koncie SYNTELL S.A. (255-647-3852, spółka matka Sendly i Actio).

## Fakty zweryfikowane (nie flaguj ponownie)
- Prepaid: konto może wydać maksymalnie tyle, ile ma salda — brak nieograniczonego długu (to cecha, nie problem).
- Strona jest w pełni prerenderowana i „agent-ready" (llms.txt, OpenAPI, agent-skills) — ruch/cytowania z botów AI to zamierzony efekt.

## Agenda review
- (do uzupełnienia po pierwszych tygodniach danych)

## Dziennik zmian na koncie (najnowsze u góry)
- 2026-07-16 — Konwersje Ads włączone przez API: `sign_up` (GŁÓWNA, SIGNUP) + `generate_lead` (dodatkowa). Raport od teraz może oceniać kampanię po sign_up (dane od 15.07). lead_dimensions=(language, registration_type) włączone w raporcie.
- 2026-07-15 — Kampania "SENDLY | Search PL | SMS API" (24033405542) utworzona (Manual CPC 3 zł, 100 zł/dz, PAUSED) i odpauzowana przez Toma. Uruchomiony serwer MCP (mcp.sendly.link) + hub dokumentacji (/dokumentacja: SMS API / API Reference / MCP) + artykuł blog o MCP.
- 2026-07-14 — Uruchomienie pipeline raportowego SENDLY (profil marki na wspólnym kodzie z Actio). Start: mail + push do Tomka; Hubert dołączony później na sygnał.
