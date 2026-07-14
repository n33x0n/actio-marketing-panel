measurement_incident_until: 2026-08-15

# Kontekst biznesowy — SENDLY (wstrzykiwany do promptu raportu)

> Odpowiednik cmo_context.md dla marki SENDLY. Żywy dziennik: incydenty pomiaru,
> stałe decyzje właściciela, fakty zweryfikowane, zmiany na koncie. Aktualizowany
> przy każdej zmianie/decyzji, żeby raport nie flagował artefaktów i nie rekomendował
> rzeczy już rozstrzygniętych.

## Aktywne incydenty pomiaru
- **Faza launchu (do ~2026-08-15):** GA4 sendly zbiera dane dopiero od startu serwisu (~lipiec 2026). Brak pełnego okna „poprzedni tydzień" → porównania week-over-week są puste lub oparte na niepełnym oknie. NIE oceniaj wydajności po tym oknie, NIE flaguj braku danych jako spadku.
- **Konwersja rejestracji NIE jest jeszcze mierzona (ważne):** utworzenie konta nie ma eventu w GA4. Dostępne, ale MYLĄCE: `form_start` = ktoś zaczął formularz (~38/28d na /pl/rejestracja/); `ads_conversion_PURCHASE_1` (54) = konwersja Google Ads odpalana na WIDOKU strony /pl/rejestracja/ (nie na sukcesie, wartość 0). NIE interpretuj tych liczb jako rejestracji. Realny event `sign_up` na ekranie sukcesu — do dodania w sendly-www.

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
- 2026-07-14 — Uruchomienie pipeline raportowego SENDLY (profil marki na wspólnym kodzie z Actio). Start: mail + push do Tomka; Hubert dołączony później na sygnał.
