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
- **Conquesting brandów konkurencji jest ŚWIADOMY:** „sms api"/„smsapi" to główna fraza docelowa — NIE rekomenduj dodania `smsapi` jako negatyw (decyzja Toma 17.07). `serwersms` zanegatywowany. Jeśli koszt na „smsapi" rośnie bez konwersji, rekomenduj osobną grupę conquesting z kreacją „SMS API prosto od operatora, bez pośredników", a nie wykluczenie frazy.

## Fakty zweryfikowane (nie flaguj ponownie)
- Prepaid: konto może wydać maksymalnie tyle, ile ma salda — brak nieograniczonego długu (to cecha, nie problem).
- Strona jest w pełni prerenderowana i „agent-ready" (llms.txt, OpenAPI, agent-skills) — ruch/cytowania z botów AI to zamierzony efekt.

## Agenda review
- (do uzupełnienia po pierwszych tygodniach danych)

## Dziennik zmian na koncie (najnowsze u góry)
- 2026-07-24 — Search term „smsa api" (1 klik, 6 zł): najpewniej literówka frazy core „sms api" (ew. marka kurierska SMSA) — ŚWIADOMIE NIE zanegatywowana (typo naszej frazy może konwertować); obserwuj, nie rekomenduj negatywu po pojedynczym kliku.
- 2026-07-23 — Literówka w RSA grupy 1 („za sMS-y") poprawiona: nowa reklama 817978874366 APPROVED/ENABLED, stara 816987463634 SPAUZOWANA. Zweryfikowane po datach: kliki „aws sms api" (17.07) i „iot sms gateway" (21.07) są SPRZED dodania negatywów — negatywy szczelne, NIE flaguj tych fraz jako przecieków.
- 2026-07-22 — Negatywy kampanii dodane: `telesign`[B], `iot sms gateway`[P]. Wcześniej (18.07) dodane: `aws`, `smseagle`, `sinch`, `smpp`, `eagle` [B]. Istnieją też m.in. `yeastar`, `zakup punktów`, `serwersms` — NIE rekomenduj ponownego dodawania tych negatywów. `cloud`/`platform`/`iot`(broad) świadomie NIE blokowane (mogą opisywać nasz produkt).
- 2026-07-22 — Landing QS ZROBIONY (sendly-www v1.4.99): /pl/produkty/sms-api/ ma pasek zaufania pod CTA (100 SMS gratis / bez karty i umowy / operator UKE / 0,075 zł = echo nagłówków RSA) + „bramka SMS dla firm" w subtitle (exact match keywordów grupy 1). Komponent QS „strona docelowa" aktualizuje się z opóźnieniem — oceniaj od ~29.07; do tego czasu NIE rekomenduj ponownie „popraw stronę docelową".
- 2026-07-22 — Import konwersji offline gclid URUCHOMIONY: strona łapie gclid first-party, po realnej rejestracji rekord idzie do KV, dzienny job 07:05 na ra wysyła do Google Ads przez Data Manager API. Akcja „SENDLY Rejestracja – import (gclid)" id 7693745003 jest DODATKOWA (nie wlicza się do kolumny „Konwersje", tylko „Wszystkie konwersje"). Konwersje z Ads od userów bez zgody cookies będą widoczne tą ścieżką (modelowane). NIE rekomenduj „wdrożenia offline conversion import" — działa.
- 2026-07-18 — Grupa 6 „Conquesting | SMSAPI" UTWORZONA (kampania 24033405542): keywordy `smsapi`/`smsapi api` [EXACT], dedykowany RSA („SMS API prosto od operatora, bez pośredników, 100 SMS gratis"), landing /pl/produkty/sms-api/; grupa 1 negatywuje `smsapi` wewnętrznie (lejek do grupy 6). NIE rekomenduj już „wydzielenia grupy conquesting" — istnieje. Koszt na smsapi bez konwersji przy małym wolumenie = akceptowany koszt strategii (decyzja Toma 17.07).
- 2026-07-18 — Rejestracje spoza formularza www (bezpośrednio w panelu, np. klient „Melo" 17.07) NIE są widoczne w GA4 — licznik sign_up to dolne oszacowanie; nie flaguj rozjazdu GA4 vs panel jako błędu pomiaru.
- 2026-07-17 — 504/500 z originu w statystykach CF to host ACTIO (rejestracja/panel), poza kontrolą www sendly.link; flaguj tylko wyraźne wzrosty tygodniowe.
- 2026-07-16 — Stawki CPC podniesione (decyzja Toma): grupa "1. SMS API / Bramka SMS" 3→6 zł, pozostałe 4 grupy 3→4,50 zł. Powód: lostRank 44–90% przy 3 zł, 0 kliknięć/7dni. Oceniaj efekt od 17.07; jeśli lostRank nadal >40% po 2–3 dniach, rekomenduj kolejną korektę.
- 2026-07-17 — `serwersms` [PHRASE] dodany jako negatyw kampanii (decyzja Toma). `smsapi` NIE negatywowany — conquesting świadomy. `lead_dimensions` sendly cofnięte do `()` — breakdown leadów jest zahardkodowany na schemat ACTIO (form_id/phone_number/link_location); dla sendly rzucał 400. Licznik `sign_up` działa z osobnego syncu, więc raport nic nie traci.
- 2026-07-16 — Konwersje Ads włączone przez API: `sign_up` (GŁÓWNA, SIGNUP) + `generate_lead` (dodatkowa). Raport od teraz może oceniać kampanię po sign_up (dane od 15.07).
- 2026-07-15 — Kampania "SENDLY | Search PL | SMS API" (24033405542) utworzona (Manual CPC 3 zł, 100 zł/dz, PAUSED) i odpauzowana przez Toma. Uruchomiony serwer MCP (mcp.sendly.link) + hub dokumentacji (/dokumentacja: SMS API / API Reference / MCP) + artykuł blog o MCP.
- 2026-07-14 — Uruchomienie pipeline raportowego SENDLY (profil marki na wspólnym kodzie z Actio). Start: mail + push do Tomka; Hubert dołączony później na sygnał.
