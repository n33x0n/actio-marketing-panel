# GTM brief: dynamic conv_value dla `generate_lead`

**Cel**: każdy lead w Google Ads ma wartość zależną od strony, na której powstał (a nie flat 1000 zł jak dziś). To pozwoli Smart Biddingowi widzieć że lead z `/uslugi/sip-trunk/` jest wart 2400 zł, a lead z home – 900 zł, i bidować odpowiednio.

**Stack**: zmiany tylko w GTM (kontener `GTM-56N7NT77`). Custom dimensions w GA4 i Ads conv action już gotowe – po publish GTM Tom przełączy `always_use_default=False` w Ads przez API.

**Szacowany czas**: 15 min w GTM + publish.

---

## Krok 1: Zmienna `Lead Value by URL` (Lookup Table)

GTM → **Zmienne** → **Nowa** → typ: **Tabela wyszukiwania (Lookup Table)**.

Nazwa: `Lead Value by URL`

Zmienna wejściowa: `{{Page Path}}`

Wiersze (kolejność ważna – pierwsze dopasowanie wygrywa, ale w Lookup Table jest exact match, więc kolejność nie ma znaczenia poza czytelnością):

| Wejście (Page Path) | Wyjście (Value) |
|---|---|
| `/uslugi/sip-trunk/` | `2400` |
| `/uslugi/3cx-phone-system/` | `3000` |
| `/uslugi/twoj-3cx-moze-wiecej-odkryj-sip-trunk-z-obsluga-sms/` | `3000` |
| `/uslugi/sms-api/` | `3600` |
| `/uslugi/blyskawiczna-komunikacja-sms-tam-gdzie-sa-twoi-klienci/` | `3600` |
| `/uslugi/efektywna-komunikacja-sms-dla-twojej-firmy/` | `3600` |
| `/uslugi/sms-przez-voip/` | `3600` |
| `/uslugi/wirtualna-centrala/` | `3300` |
| `/uslugi/actio-mobile/` | `360` |
| `/uslugi/wirtualny-numer-komorkowy-voip/` | `360` |
| `/uslugi/rozwiazania-sztucznej-inteligencji-ai-w-komunikacji/` | `3000` |
| `/uslugi/ankiety-telefoniczne/` | `3000` |
| `/uslugi/nowoczesna-komunikacja-glosowa-z-voip/` | `1200` |
| `/uslugi/nowoczesna-komunikacja-video-spotkania-twarza-w-twarz-bez-barier/` | `1200` |
| `/uslugi/wideokonferencja/` | `1200` |
| `/uslugi/telekonferencja/` | `1200` |
| `/uslugi/wirtualny-fax/` | `600` |
| `/uslugi/poczta-glosowa/` | `600` |
| `/uslugi/przekierowanie-polaczen/` | `600` |
| `/uslugi/zarzadzanie-nieodebranymi-polaczeniami/` | `600` |
| `/uslugi/wsparcie-sprzedazy/` | `600` |
| `/uslugi/zachowaj-swoj-numer-i-przejdz-do-actio-szybko-bezplatnie-i-bez-przerw-w-dzialaniu/` | `600` |

**Set Default Value** (na dole) → `900` (dla `/`, `/kontakt/`, `/blog/*` i wszystkich pozostałych URL).

Save.

---

## Krok 2: Stała `PLN` (Constant)

GTM → **Zmienne** → **Nowa** → typ: **Stała**.

Nazwa: `Currency PLN`
Wartość: `PLN`

Save.

(Alternatywa: można nie tworzyć osobnej zmiennej i wpisać `PLN` bezpośrednio w polu currency w tagu – ale stała jest czystsza na przyszłość.)

---

## Krok 3: Tag `GA4 - generate lead - form submission` – dodać `value` + `currency`

GTM → **Tagi** → kliknij ten tag → sekcja **Event Parameters**.

Tag już ma 3 rzędy (od 15.05): `form_id`, `form_location`, `lead_type`. Dodać dwa nowe wiersze:

| Parameter Name | Value |
|---|---|
| `value` | `{{Lead Value by URL}}` |
| `currency` | `{{Currency PLN}}` (albo wpisać `PLN` jako tekst) |

Save.

---

## Krok 4: Tag `GA4 - generate lead - phone click` – dodać `value` + `currency`

GTM → **Tagi** → kliknij ten tag → sekcja **Event Parameters**.

Tag już ma 4 rzędy: `phone_number`, `link_location`, `lead_type`, `link_text`. Dodać dwa nowe wiersze:

| Parameter Name | Value |
|---|---|
| `value` | `{{Lead Value by URL}}` |
| `currency` | `{{Currency PLN}}` |

Save.

(`{{Lead Value by URL}}` patrzy na `Page Path` strony skąd klik, więc telefon w headerze `/uslugi/sip-trunk/` dostanie 2400 zł, w `/uslugi/actio-mobile/` – 360 zł.)

---

## Krok 5: Preview + Publish

1. **Preview** (prawy górny róg w GTM, Tag Assistant) → odpal `actio.pl`.
2. Wejdź na `/uslugi/sip-trunk/` (przykład) → wypełnij CF7 form → sprawdź w Tag Assistant:
   - tag `GA4 - generate lead - form submission` odpalił się
   - w Event Parameters jest: `value: 2400`, `currency: PLN`, `lead_type: form`, `form_location: /uslugi/sip-trunk/`
3. Wejdź na `/uslugi/actio-mobile/` → kliknij w numer telefonu (link `tel:`) → sprawdź:
   - tag `GA4 - generate lead - phone click` odpalił się
   - w Event Parameters: `value: 360`, `currency: PLN`, `lead_type: phone`
4. **GA4 DebugView** (Admin → DebugView) – ten sam event powinien pokazać te same parametry.
5. Jeśli OK → **Submit** (prawy górny) → opis: "generate_lead enrichment: dynamic value per URL + currency" → **Publish**.

---

## Krok 6: Po publish – daj znać Tomowi

Tom przełączy w Ads conversion action `actio - GA4 (web) generate_lead`:
- `always_use_default = False` (zacznie brać `value` z eventu GA4)
- `default_value = 1000` zostaje jako fallback (gdyby event GA4 nie miał `value`)

To zrobi się przez API, nie wymaga klikania w Ads GUI.

---

## Notatka: dlaczego nie odwrotnie

Jeśli przełączymy `always_use_default=False` **przed** publish GTM:
- eventy GA4 nadal NIE wysyłają `value`
- Ads zobaczy każdy lead jako `value=0`
- Smart Bidding zaczyna optymalizować pod tCPA jakby leady były bezwartościowe
- 24-48h zniekształconych danych

Dlatego: **GTM publish FIRST, Ads switch SECOND.**

---

## Mapowanie wartości – źródło

| Usługa | First-year revenue | Close rate | conv_value |
|---|---|---|---|
| SIP Trunk (sam) | 600 zł | – | – |
| SIP Trunk (+ ruch) | 4000 zł | 60% | 2400 zł |
| Wirtualna Centrala (+ trunk upsell) | 5500 zł | 60% | 3300 zł |
| 3CX (licencja + wdrożenie) | 5000 zł | 60% | 3000 zł |
| SMS API | 6000 zł | 60% | 3600 zł |
| Actio Mobile (1 numer) | 600 zł | 60% | 360 zł |

Liczby od Huberta (mail 18.05). Close rate 6/10 = 60% (6 zamkniętych umową, 1 czeka na portację numerów, 2 zawieszone, 1 odpadł).

Default `900 zł` dla generic pages (home, /kontakt/, blog) = konserwatywny średni weighted, do podkręcenia po 30 dniach danych.
