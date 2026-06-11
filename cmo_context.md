measurement_incident_until: 2026-06-12

## Aktywne incydenty pomiaru
- 03.06–09.06 ~10:20: po migracji multilang consent default=denied → GA4/Ads liczyły ~13% ruchu (kliki Ads były normalne ~2400/d). Sesje/konwersje z tych dat są NIEDOSZACOWANE ~5×. NIE oceniaj kampanii po conv z tego okna i NIE pisz „kampania nie konwertuje" na bazie tych dat. Naprawione 09.06 ~10:20 (granted-default, mu-plugin actio-consent-grant.php).
- Do ~12.06 okno 7d nadal zawiera dni z zepsutym pomiarem → „0 konwersji w 7d" to artefakt. Czysta ocena CPA/ROAS per kampania możliwa od ~12–14.06.

## Stałe decyzje właściciela (nie rekomenduj wbrew nim)
- `syntell` / `syntell s.a` w BRAND: ZOSTAJE jako obrona brandu (to nasza nazwa prawna – SYNTELL S.A.). NIE sugeruj dodawania jako negatyw.
- Consent granted-default na actio.pl: świadoma, stała decyzja. NIE flaguj braku banera/zgód jako problemu.
- SEARCH_SMSAPI_PL_ALL: spauzowana ŚWIADOMIE 09.06 (kategoria należy do konkurenta SMSAPI.pl, QS 2, brak konwersji strukturalny). NIE sugeruj wznowienia ani zmian budżetu.
- QS `actio` (BRAND) i `3cx` (3CX) = 3: przyczyną jest Landing Page Experience = BELOW_AVERAGE (trafność reklam jest ABOVE_AVERAGE). Fix = szybkość LP, w toku u developera. NIE sugeruj przepisywania reklam pod QS.
- SEARCH_3CX_PL_ALL: 09.06 podbite STAWKI 5→10 zł (kampania traciła 41% IS na rankingu; lost_budget=0, wydaje ~1/3 budżetu). NIE sugeruj podnoszenia budżetu dopóki lost_budget_pct ≈ 0. Monitor efektu do ~15.06.
- SEARCH_BRAND_PL_DESKTOP: TARGET_IMPRESSION_SHARE z maxCPC 30 zł to celowa strategia (maksymalizacja IS na brandzie). NIE sugeruj obniżania CPC ani zmiany biddingu.
- DEMAND_GEN (SIPTRUNK + 3G): ocena i ewentualne cięcia budżetu DOPIERO po czystym oknie pomiaru (~12–14.06). Znany problem jakości placementów (dziecięce kanały gamingowe YT) – decyzja o content suitability po danych konwersji.

## Fakty zweryfikowane (nie flaguj ponownie)
- Negatyw `agencja` [P] w BRAND DZIAŁA: zero wystąpień search termów z „agencja" po 09.06 (data dodania). Term `actio agencja pracy` widoczny w oknie 7d pochodzi z 03/07.06 – sprzed negatywu. NIE rekomenduj `agencja pracy` ani weryfikacji.
- Norma capture-rate (sesje GA4 ÷ kliki Ads) = **40–47%**, NIE 90% – część klików naturalnie nie kończy się sesją (bounce przed JS, prefetch). Osiągnięte: 09.06=44%, 10.06=40% – pomiar odbudowany, temat zamknięty.
- Brief LP-speed WYSŁANY do developera 10.06 (page cache/CF APO + reCAPTCHA poza formularzami + jQuery defer + konsolidacja tagów). Status: czekamy na wdrożenie – NIE rekomenduj ponownej eskalacji, monitoruj TTFB/QS.
- Lista placementów YT (Demand Gen) wygenerowana 11.06 → `dg_placements_yt.tsv` (171 kanałów, 21,8 tys. klików / 2425 zł, top = dziecięce kanały gamingowe). Gotowa na review 12–14.06; NIC nie wykluczone.

## Agenda review 12–14.06 (czyste okno pomiaru)
1. CPA/ROAS per kampania (BRAND, 3CX, DG_SIPTRUNK, DG_3G) na danych od 10.06.
2. Decyzja DG: skala/cięcie/content suitability + ewentualne wykluczenia z dg_placements_yt.tsv.
3. Negatywy EN-pricing dla 3CX (`hosted pricing`, `cost`) – ocenić intencję na czystych danych.
4. BRAND IS: czy 74→90%+; jeśli nie i lostRank wysoki → maxCPC 40 zł.

## Dziennik zmian na koncie (najnowsze u góry)
- 11.06: capture-rate FINALNIE potwierdzony: 09.06=44%, 10.06=40% (pełny czysty dzień) – poziom sprzed incydentu, pomiar odbudowany. Leady 10.06: tylko 1 (źródło not set) – pierwszy realny sygnał wolumenu po naprawie; oceniać w oknie 12–14.06, nie po jednym dniu.
- 10.06: utworzona lista Customer Match `ACTIO_CRM_KLIENCI_B2B` (userLists/9406277210, CONTACT_INFO, 540 dni) – PUSTA, czeka na eksport z CRM; uploader: customer_match_upload.py. Do niczego nie podpięta – nie raportuj jako aktywnej grupy odbiorców.
- 10.06: odbudowa pomiaru POTWIERDZONA – capture-rate 5% (08.06, przed fixem) → 37% (09.06, dzień mieszany; część po fixie ~50%). Pierwsza konwersja w Ads po incydencie: BRAND `actio voip` 09.06 (import GA4→Ads działa). DG nadal 0 conv – oczekiwane (atrybucja gclid przez okno incydentu + lag importu), ocena 12–14.06 bez zmian.
- 09.06: SMSAPI → PAUSED; 3CX stawki ad group + keywords 5→10 zł; BRAND + negatyw `agencja` [PHRASE]; tracking naprawiony ~10:20 (consent granted-default).
- 08.06: BRAND maxCPC (TIS ceiling) 20→30 zł; IS 15%→72%.
- 30.05: de-inflacja `generate_lead` – usunięta reguła GA4 zawyżająca ~7× (86% leadów fake: page_view /kontakt → generate_lead) + dedup tagów GTM. Realny baseline po: ~12–13 leadów/tydz (2–5/dzień). Dane sprzed 30.05 mają ZAWYŻONE conv – nie używaj ich do oceny ROAS.
