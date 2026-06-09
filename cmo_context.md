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

## Dziennik zmian na koncie (najnowsze u góry)
- 09.06: SMSAPI → PAUSED; 3CX stawki ad group + keywords 5→10 zł; BRAND + negatyw `agencja` [PHRASE]; tracking naprawiony ~10:20 (consent granted-default).
- 08.06: BRAND maxCPC (TIS ceiling) 20→30 zł; IS 15%→72%.
- 30.05: de-inflacja `generate_lead` – usunięta reguła GA4 zawyżająca ~7× (86% leadów fake: page_view /kontakt → generate_lead) + dedup tagów GTM. Realny baseline po: ~12–13 leadów/tydz (2–5/dzień). Dane sprzed 30.05 mają ZAWYŻONE conv – nie używaj ich do oceny ROAS.
