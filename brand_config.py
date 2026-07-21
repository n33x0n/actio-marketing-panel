"""Profile marek dla pipeline'u raportowego (multi-brand na wspolnym kodzie).

Wybor profilu: zmienna srodowiskowa BRAND (domyslnie "actio").
Profil "actio" MUSI odwzorowywac dotychczasowe zaszyte wartosci 1:1 (zero regresji).
Profil "sendly" = nowa marka (SMS API), dane z konta SENDLY zamiast Actio.

Konsumenci (analyze.py, ga4.py, geo_report.py, panel_positive_report.py,
email_sender.py, alerts.py, ai_bot_report.py, db.py) czytaja pola tego profilu
zamiast literalow. Nazwy pol sa STABILNE — nie zmieniaj bez aktualizacji konsumentow.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


# --- prompt raportu CMO: profil "actio" (skopiowany 1:1 z analyze.REPORT_PROMPT) ---
ACTIO_REPORT_PROMPT = """Jesteś senior performance marketing CMO dla firmy Actio (B2B VoIP / telefonia internetowa).

KRYTYCZNE: poniżej masz LIVE state konta (kampanie i negatywy bezpośrednio z API). To jest ŹRÓDŁO PRAWDY.
Jeśli search term/keyword wygląda na śmieciowy ale jest już w aktywnych negatywach — NIE sugeruj go ponownie dodawać (to historia w 7-dniowym oknie sprzed dodania negatywu).
Jeśli kampania jest ENABLED w live state — NIE sugeruj jej pauzowania ze względu na "powinna być wstrzymana".

### LIVE state konta (źródło prawdy, {date})
{live_account_state}

Realny lead-event w GA4 to `generate_lead` (klik tel: + submit form na /kontakt/ + form na landingach inline).
Lead source (`generate_lead`) jest poprawnie skonfigurowany.

### KRYTYCZNY KONTEKST — incydenty i decyzje właściciela (źródło prawdy, aktualizowane na bieżąco)
Poniższy dziennik NADPISUJE wnioski z danych. NIE flaguj opisanych incydentów jako nowych awarii.
NIE dawaj rekomendacji sprzecznych ze „stałymi decyzjami właściciela" — zostały już rozważone i odrzucone/postanowione.
Jeśli aktywny incydent pomiaru obejmuje część okna 7d, każdą liczbę konwersji z tego okna traktuj jako artefakt i zaznacz to wprost.

{cmo_context}

### ZASADY WNIOSKOWANIA (twarde, nie łam ich)
- Rekomendację „zwiększ budżet" wolno dać TYLKO gdy lost_budget_pct > 10. Gdy kampania traci na rankingu (lost_rank_pct >> lost_budget_pct), dźwignią są STAWKI lub QS — nie budżet.
- Kampanie DEMAND_GEN nie mają metryk IS/lost_rank/lost_budget (specyfika kanału) — wartości 0 to „nie dotyczy", nie problem.
- Rekomendacje dot. QS opieraj WYŁĄCZNIE o komponenty QS z LIVE state (trafność reklamy / jakość strony docelowej / przewidywany CTR): wskazuj komponent BELOW_AVERAGE. Jeśli trafność reklamy jest ABOVE_AVERAGE, NIE sugeruj przepisywania reklam — problem leży gdzie indziej.
- Zanim zarekomendujesz negatyw dla search terma, sprawdź w LIVE state czy identyczny/nadrzędny negatyw już istnieje ORAZ czy data search terma nie jest sprzed dodania negatywu.
- Nie rekomenduj pauzowania/wznawiania/zmian budżetu kampanii wymienionych w „stałych decyzjach" powyżej.

Mając poniższe dane, napisz **krótki raport po polsku** w formacie markdown z trzema sekcjami:

## Daily digest
1-2 zdania: co się stało ostatnio. Podaj konkretne liczby (kliknięcia, koszt, konwersje, CPA jeśli istotny).

## Anomalie
Lista 0-5 punktów. Każdy punkt: co odbiega od normy + konkretne liczby. Tylko realne anomalie — jeśli nic się nie wyróżnia, napisz "brak istotnych anomalii".

**WAŻNE — klasyfikacja każdej anomalii**:
- **Zacznij każdy punkt od emoji** — 🟢 jeśli to anomalia pozytywna (wzrost, sukces, lepszy wynik niż norma, rekord) lub 🔴 jeśli negatywna (spadek, problem, gorszy wynik, zmarnowany budżet, wysokie CPA, niski QS).
- Nie używaj innych emoji ani znaków zastępczych. Każdy bullet musi mieć dokładnie 🟢 lub 🔴 jako pierwszy znak po `-` lub `*`.

Przykłady:
- 🟢 BRAND `actio voip` PHRASE: 4 konwersje za 5.93 zł = CPA 1.48 zł — **rekord tygodnia**.
- 🔴 SEARCH_VOIP_PL_ALL: 8 klików / 15.76 zł / 0 konwersji — pali budżet bez efektu.

## Rekomendacje
Lista 1-5 konkretnych akcji do podjęcia DZIŚ. Każda akcja musi być jednoznaczna (np. "dodaj frazę X jako negative w kampanii Y", nie "rozważ optymalizację"). Priorytetyzuj wpływ na realne leady (`generate_lead` z Polski), nie fake metryki.

NIE pisz wstępu ani podsumowania. Zacznij od `## Daily digest`. Krótko, rzeczowo, bez emoji.

DANE:

### GA4 — konwersje per źródło/medium (ostatnie 7 dni)
{ga4_conversions_by_source}

### GA4 — konwersje per źródło/medium (poprzedni tydzień, 8-14 dni temu, do porównania w-o-w)
{ga4_conversions_by_source_prev}

### GA4 — leady (`generate_lead`) per landing+source (7 dni)
{ga4_leads_per_landing}

### GA4 — lead_type breakdown (form vs phone, custom dims z GTM od 12.05)
{lead_type_breakdown_7d}

### GA4 — który formularz CF7 (2485=stary inline vs 123446=nowy modal global)
{lead_form_id_breakdown_7d}

### GA4 — który numer telefonu kliknięty
{lead_phone_number_breakdown_7d}

### Google Ads — kampanie (ostatnie 7 dni, kolumny is_pct/lost_budget_pct/lost_rank_pct = Lost IS %)
{ads_campaigns_7d}

### Google Ads — kampanie (poprzedni tydzień, 8-14 dni temu, do porównania w-o-w)
{ads_campaigns_7d_prev}

### Google Ads — performance assetów (sitelinks/callouts/call ext, 7 dni)
{ads_assets_perf_7d}

### Kampania SEARCH_COMPETITOR_PL — szczegóły (7 dni)

Podkampania bidująca na keywordy konkurentów (welyo/halonet/plfon/zadarma itd.). Treść reklamy bez nazw konkurentów (Google policy). W raporcie omów osobno: ROI tej kampanii, jakie konkurenty generują kliki, jakie search terms wpadają (sygnał intencji rynku).

**Performance kampanii:**
{competitor_campaign_7d}

**Keywordy COMPETITOR — co generuje kliki:**
{competitor_keywords_7d}

**Search terms — co realnie wpisują ludzie:**
{competitor_search_terms_7d}

### Google Ads — top 20 search terms wg kosztu (7 dni)
{ads_search_terms_top20_7d}

### Google Ads — top 20 keywords (7 dni)
{ads_keywords_7d}

### GSC — kliki/impresje per dzień (7 dni)
{gsc_totals_7d}

### GSC — top 10 zapytań organic (7 dni)
{gsc_queries_7d}

### GSC — top 10 stron landing (7 dni)
{gsc_pages_7d}
"""


# --- prompt raportu: profil "sendly" (nowa marka, SMS API, faza launchu) ---
# UWAGA: sendly na launchu ma SWIEZY GA4 (brak danych poprzedniego tygodnia) — prompt
# jawnie toleruje pustke w-o-w. Uzywa tylko placeholderow, ktore collect_data_summary
# dostarcza; sekcje actio-specyficzne (competitor, form_id CF7) SA POMINIETE.
# TODO(wiring/dostepy): potwierdzic nazwe eventu konwersji sendly (rejestracja) w GA4.
SENDLY_REPORT_PROMPT = """Jesteś senior growth / performance marketing analitykiem dla SENDLY — SMS API polskiego operatora telekomunikacyjnego (marka spółki Syntell S.A. / ACTIO). Produkt: wysyłka SMS przez REST API, bez pośredników, pay-as-you-go, 100 SMS gratis na start. Kluczowa konwersja to REJESTRACJA konta (założenie konta → aktywacja → pierwsza wysyłka).

KRYTYCZNE: poniżej masz LIVE state konta Google Ads (kampanie i negatywy bezpośrednio z API). To jest ŹRÓDŁO PRAWDY. Jeśli kampania jest ENABLED w live state — NIE sugeruj jej pauzowania „bo powinna być wstrzymana".

### LIVE state konta (źródło prawdy, {date})
{live_account_state}

### KONTEKST — faza, incydenty i decyzje właściciela (źródło prawdy)
Poniższy dziennik NADPISUJE wnioski z danych. SENDLY jest w FAZIE LAUNCHU — GA4 zbiera dopiero od startu, więc porównania „tydzień do tygodnia" mogą być puste lub oparte na niepełnym oknie. NIE flaguj braku danych z poprzedniego tygodnia jako spadku ani awarii. NIE dawaj rekomendacji sprzecznych ze „stałymi decyzjami właściciela".

{cmo_context}

### ZASADY WNIOSKOWANIA (twarde)
- Traktuj niski wolumen na starcie jako normę fazy launchu, nie anomalię — chyba że dane wskazują konkretny problem (np. budżet palony bez rejestracji).
- Rekomendację „zwiększ budżet" wolno dać TYLKO gdy kampania realnie ogranicza się budżetem (lost_budget_pct > 10), nie przy braku konwersji z innych powodów.
- Priorytetyzuj wpływ na REJESTRACJE (realne konto SENDLY z Polski), nie na sesje czy kliknięcia.
- Jeśli sekcja jest pusta („brak danych"), po prostu ją pomiń — nie zgaduj.

Mając poniższe dane, napisz **krótki raport po polsku** w formacie markdown z trzema sekcjami:

## Daily digest
1-2 zdania: co się stało ostatnio (ruch, rejestracje, koszt/CPA jeśli są kampanie). Konkretne liczby.

## Anomalie
Lista 0-5 punktów. Każdy: co odbiega od normy + liczby. Jeśli nic — „brak istotnych anomalii".
**Zacznij każdy punkt od emoji** — 🟢 (pozytywna) lub 🔴 (negatywna). Dokładnie jeden z tych dwóch jako pierwszy znak po `-`.

## Rekomendacje
Lista 1-5 konkretnych akcji na DZIŚ. Jednoznacznych. Priorytet: więcej rejestracji, mniej marnowanego budżetu.

NIE pisz wstępu ani podsumowania. Zacznij od `## Daily digest`. Krótko, rzeczowo.

DANE:

### GA4 — sesje/konwersje per źródło/medium (ostatnie 7 dni)
{ga4_conversions_by_source}

### GA4 — per źródło/medium (poprzedni tydzień, do porównania w-o-w; może być puste na launchu)
{ga4_conversions_by_source_prev}

### GA4 — konwersje (rejestracje) per landing+source (7 dni)
{ga4_leads_per_landing}

### Google Ads — kampanie (ostatnie 7 dni)
{ads_campaigns_7d}

### Google Ads — kampanie (poprzedni tydzień)
{ads_campaigns_7d_prev}

### Google Ads — top 20 search terms wg kosztu (7 dni)
{ads_search_terms_top20_7d}

### Google Ads — top 20 keywords (7 dni)
{ads_keywords_7d}

### GSC — kliki/impresje per dzień (7 dni)
{gsc_totals_7d}

### GSC — top 10 zapytań organic (7 dni)
{gsc_queries_7d}

### GSC — top 10 stron landing (7 dni)
{gsc_pages_7d}

### SEO — okazje: strony z widocznością ale ~0 klików (28 dni)
{seo_opportunities}

WSKAZÓWKA do sekcji SEO (operacjonalizacja content-refresh): to strony które JUŻ rankują, ale nie dowożą klików. Jeśli w kolumnie „flaga" jest „ZLY JEZYK" (polska fraza serwowana pod /en//de//ua/) — to priorytetowa anomalia: mamy pozycję organic, ale tracimy niemal 100% klików przez zły język serwowanej strony. Rekomenduj wzmocnienie POLSKIEJ wersji strony (rozbudowa treści pod te zapytania + linkowanie wewnętrzne) — NIE ruszaj hreflang/canonical (są poprawne). Pozostałe wiersze = kandydaci do content-refresh: rozbuduj treść pod „top_zapytanie" i pokrewne frazy z GSC. Priorytetyzuj po liczbie impresji.
"""


# --- prompt sekcji "Trendy na dzisiaj": profil "actio" (newsjacking B2B telco) ---
ACTIO_TRENDS_PROMPT = """Jestes strategiem marketingu B2B (newsjacking / real-time marketing) dla ACTIO - polskiego operatora telekomunikacyjnego dla firm (marka spolki SYNTELL S.A., wpis w rejestrze UKE, wlasna infrastruktura w Polsce).

OFERTA ACTIO - do tego szukasz powiazan; w KAZDEJ pozycji wskaz konkretna usluge z tej listy:
- SIP Trunk - podlaczenie dowolnej centrali (3CX, Asterisk, FreePBX, Microsoft Teams) do sieci publicznej; JEDYNY w Polsce z dwukierunkowym SMS na firmowym numerze
- Wirtualna centrala w chmurze - IVR, kolejkowanie polaczen, przekierowania wg godzin pracy, nagrywanie rozmow, statystyki; od 49 zl/mc, bez sprzetu
- 3CX Phone System - wdrozenia i licencje, partner 3CX od 2009
- Wirtualny numer komorkowy +48 - firmowy numer bez karty SIM, z obsluga SMS, dzialajacy na komputerze, telefonie i w aplikacji
- Numery stacjonarne, infolinie 800/801, przenoszenie numerow (MNP) bez przerwy w dzialaniu
- AI voicebot - asystent glosowy odbierajacy polaczenia 24/7
- SMS API (Sendly) - masowa i transakcyjna wysylka SMS z systemow firmowych

KLIENCI ACTIO: firmy B2B - e-commerce i logistyka, przychodnie i gabinety, kancelarie, biura rachunkowe, contact center, agencje, firmy z praca zdalna i handlowcami w terenie.

Dostajesz liste dzisiejszych trendow wyszukiwan w Polsce (Google Trends) z kontekstem newsowym. Zadanie: znalezc te, ktore da sie WIARYGODNIE polaczyc z konkretna usluga ACTIO - tak, zeby szybka reakcja (wpis na blogu, post w social media, reklama) przyciagnela uwage firm i ruch na actio.pl.

Typowe mosty dla telekomunikacji B2B (czego szukac):
- awarie sieci i operatorow, przerwy w uslugach -> niezawodnosc, SLA 99,9%, wlasna infrastruktura
- zmiany technologiczne i regulacyjne (wygaszanie 3G/2G, decyzje UKE, prawo komunikacji elektronicznej, RODO, zgody na SMS)
- praca zdalna i hybrydowa, powroty do biur, rynek pracy -> centrala w chmurze, numer nalezacy do firmy a nie do pracownika
- szczyty ruchu w firmach (Black Friday, sezony sprzedazowe, dlugie weekendy, wydarzenia masowe) -> kolejkowanie, IVR, oddzwanianie, przekierowania
- oszustwa telefoniczne, spoofing, bezpieczenstwo komunikacji -> firmowy numer zamiast prywatnego, kontrola nad historia rozmow
- AI w obsludze klienta -> AI voicebot
- wydarzenia branzowe klientow (e-commerce, medycyna, logistyka) -> konkretne zastosowanie u nich

Zasady:
- Zostaw TYLKO trendy z realnym, nienaciaganym mostem do konkretnej uslugi ACTIO. Lepiej mniej, ale trafnych. Moze byc 0, jesli dzis nic nie pasuje.
- Odrzuc tematy drazliwe (tragedie, smierc, polityka, konflikty) - tam newsjacking szkodzi marce B2B.
- Odrzuc trendy czysto konsumenckie i rozrywkowe bez przelozenia na firmy (celebryci, sport, seriale), chyba ze masz mocny biznesowy most (np. wielki mecz = szczyt zamowien w gastronomii = przeciazona infolinia).
- Maksymalnie 10 pozycji, ale liczba ma WYNIKAC z tego, ile trendow naprawde spelnia kryterium: moze byc 0, 2, 5 albo 10. Nie dobieraj na sile do zadnej liczby i nie dorzucaj slabszych pozycji, zeby bylo ich wiecej. Kazda pozycja musi bronic sie sama.
- Nazwe marki pisz ZAWSZE wielkimi literami: ACTIO. Uzywaj polpauzy, nigdy pauzy.

Dla kazdego zostawionego trendu podaj:
- "trend": nazwa trendu
- "service": ktora usluga ACTIO z listy wyzej (krotko, np. "Wirtualna centrala" albo "SIP Trunk + SMS")
- "angle": na czym polega most miedzy trendem a ta usluga (1 zdanie, konkretnie, bez lania wody)
- "format": najlepszy format reakcji - "wpis na blogu", "post social", "reklama" lub "newsletter" + 2-4 slowa doprecyzowania
- "copy": gotowa propozycja tresci PO POLSKU (1-2 zdania), nawiazujaca do trendu i konczaca sie naturalnym mostem do ACTIO

Zwroc WYLACZNIE poprawny JSON, bez komentarza:
{{"items":[{{"trend":"...","service":"...","angle":"...","format":"...","copy":"..."}}]}}

Dzisiejsze trendy (PL):
{trends}
"""

# --- prompt sekcji "Trendy na dzisiaj": profil "sendly" (przeniesiony 1:1 z trends.py, zero regresji) ---
SENDLY_TRENDS_PROMPT = """Jesteś strategiem kreatywnego marketingu (newsjacking / real-time marketing) dla SENDLY — SMS API polskiego operatora telekomunikacyjnego (marka spółki Syntell S.A. / ACTIO). Produkt: wysyłka SMS przez REST API, pay-as-you-go, bez pośredników, 100 SMS gratis na start; typowe zastosowania: powiadomienia transakcyjne, kody 2FA/OTP, SMS marketing i masowa wysyłka dla firm oraz e-commerce.

Dostajesz listę dzisiejszych trendów wyszukiwań w Polsce (Google Trends) z kontekstem newsowym. Zadanie: znaleźć te trendy, które da się KREATYWNIE i WIARYGODNIE podpiąć pod markę/usługę SENDLY, tak żeby szybka reakcja reklamowa albo wpis na blogu przyciągnął ruch na sendly.link.

Zasady:
- Zostaw TYLKO trendy z realnym, nienaciąganym powiązaniem z SMS API / powiadomieniami / 2FA / e-commerce / komunikacją z klientem. Lepiej mniej, ale trafnych.
- Odrzucaj naciągane skojarzenia i tematy drażliwe (tragedie, polityka, śmierć) — tam newsjacking szkodzi marce.
- Maksymalnie 10 pozycji. Może być mniej. Może być 0, jeśli nic dziś nie pasuje.

Dla każdego zostawionego trendu podaj:
- "trend": nazwa trendu
- "angle": jak wiarygodnie podpiąć go pod SMS API SENDLY (1 zdanie)
- "blog": czy warto zrobić z tego wpis na blogu, czy to raczej krótka reklama (krótko, np. "tak — poradnik ..." albo "raczej reklama")
- "ad_copy": gotowy, kreatywny tekst reklamy PO POLSKU (1-2 zdania), nawiązujący do trendu i kończący się subtelnym hakiem do SENDLY

Zwróć WYŁĄCZNIE poprawny JSON, bez komentarza, w formacie:
{{"items":[{{"trend":"...","angle":"...","blog":"...","ad_copy":"..."}}]}}

Dzisiejsze trendy (PL):
{trends}
"""


@dataclass(frozen=True)
class BrandProfile:
    # tozsamosc
    id: str                       # "actio" / "sendly"
    name: str                     # nazwa w tytulach maili/push/H1: "Actio" / "Sendly"
    report_slug: str              # slug plikow/frontmatter: "actio-marketing" / "sendly-marketing"

    # LLM / prompt
    report_prompt: str
    openrouter_referer: str
    openrouter_title: str
    context_file: str             # plik kontekstu obok skryptu: "cmo_context.md" / "context_sendly.md"

    # GA4
    excluded_countries: tuple[str, ...]
    lead_event: str
    lead_dimensions: tuple[str, ...]  # custom dims GTM do breakdownu leadow; () = pomin (nie zarejestrowane)
    ga4_property_default: str     # default dla geo_report gdy env pusty

    # Ads
    ads_enabled: bool
    competitor_campaign: str | None   # nazwa kampanii konkurencyjnej do osobnej sekcji; None = brak

    # GSC / GEO
    site_url: str                 # gsc_brand siteUrl, np. "https://actio.pl/"
    brand_query: str              # filtr brandowy w GSC, np. "actio"
    gsc_site_filter: tuple[str, ...] | None  # None = wszystkie property SA; allowlist = izolacja marki
    gsc_property: str  # siteUrl dla gsc_brand: URL-prefix ("https://x/") lub domain ("sc-domain:x")

    # raport CEO (panel_positive_report) — wartosci konwersji per produkt
    conv_value: dict              # mapa fragment-nazwy -> wartosc PLN  (WERYFIKOWANE przy wiringu)
    conv_value_default: float

    # AI bot report
    ai_bot_enabled: bool          # actio ma feed ai_bot_hits (CF middleware); sendly na razie nie
    ai_bot_domain: str

    # alerty
    cpa_max: float
    currency: str

    # db
    test_phones: tuple[str, ...]

    # email
    from_name: str
    obsidian_reports_path: str

    # cloudflare (nowy konektor: AI Crawl Control + edge HTTP health)
    cloudflare_enabled: bool

    # geo_monitor (AI Share of Voice — odpytywanie silnikow AI)
    geo_queries: tuple[str, ...]
    geo_brands: dict          # nazwa -> regex (marka docelowa + konkurenci)
    geo_target: str           # klucz marki docelowej w geo_brands
    geo_system_prompt: str

    # --- sekcja "Trendy na dzisiaj" (newsjacking) ---
    trends_prompt: str = ""
    trends_fields: tuple[tuple[str, str], ...] = ()
    trends_intro: str = ""
    trends_empty: str = ""


ACTIO = BrandProfile(
    id="actio",
    name="Actio",
    report_slug="actio-marketing",
    report_prompt=ACTIO_REPORT_PROMPT,
    trends_prompt=ACTIO_TRENDS_PROMPT,
    trends_fields=(
        ("trend", "Trend"),
        ("service", "Usługa ACTIO"),
        ("angle", "Jak podpiąć"),
        ("format", "Format"),
        ("copy", "Propozycja treści"),
    ),
    trends_intro=(
        "Trendy wyszukiwań w Polsce (Google Trends) z realnym powiązaniem z konkretną usługą ACTIO. "
        "Propozycje do weryfikacji przed publikacją."
    ),
    trends_empty="_Dziś żaden trend nie ma sensownego, nienaciąganego powiązania z ofertą ACTIO._",
    openrouter_referer="https://actio.pl",
    openrouter_title="Actio Marketing CMO-layer",
    context_file="cmo_context.md",
    excluded_countries=("Singapore", "United States"),
    lead_event="generate_lead",
    lead_dimensions=("lead_type", "form_id", "form_location", "phone_number", "link_location"),
    ga4_property_default="366851699",
    ads_enabled=True,
    competitor_campaign="SEARCH_COMPETITOR_PL",
    site_url="https://actio.pl/",
    brand_query="actio",
    gsc_site_filter=("https://actio.pl/",),  # tylko actio.pl (SA widzi tez sendly.link po dodaniu — izolacja)
    gsc_property="https://actio.pl/",
    conv_value={
        # z panel_positive_report.py (notatka metodologiczna, dynamiczne od 18.05)
        "sip trunk": 2400,
        "3cx": 3000,
        "sms api": 3600,
        "wirtualna centrala": 3300,
        "actio mobile": 360,
        "rejestracja": 1500,
        "voip": 1200,
    },
    conv_value_default=900,
    ai_bot_enabled=True,
    ai_bot_domain="actio.pl",
    cpa_max=50.0,
    currency="zł",
    test_phones=("0", "000000000", "48600000000", "600000000", "600100200", "48000000000"),
    from_name="Actio Marketing Reports",
    obsidian_reports_path="projects/actio-marketing-reports",
    cloudflare_enabled=False,  # actio ma wlasny ai_bot_hits (CF middleware) — nie dublujemy
    geo_queries=(
        "najlepszy operator VoIP dla firm w Polsce",
        "VoIP dla firm ktory operator wybrac",
        "ranking operatorow VoIP dla firm 2026",
        "operator VoIP B2B Polska",
        "ranking wirtualnych central telefonicznych dla firm 2026",
        "porownanie SIP trunk dla firm w Polsce",
        "3CX wdrozenie Polska partner",
        "ranking dostawcow SMS API w Polsce",
        "wirtualny numer komorkowy VoIP dla firm",
    ),
    geo_brands={
        "Actio": r"\bactio\b", "EasyCall": r"\beasy ?call\b", "FCN": r"\bfcn\b",
        "Zadarma": r"\bzadarma\b", "Welyo": r"\bwelyo\b", "Halonet": r"\bhalo ?net\b",
        "PLFON": r"\bplfon\b|peoplefone", "Platan": r"\bplatan\b", "Telestrada": r"\btelestrada\b",
        "Spikon": r"\bspikon\b", "Ringostat": r"\bringostat\b", "SuperVoIP": r"\bsupervoip\b",
        "TeleCube": r"\btelecube\b", "Systell": r"\bsystell\b", "Fonet": r"\bfonet\b",
        "Aiton Caldwell": r"aiton\s*caldwell", "VoIPStudio": r"\bvoip ?studio\b",
        "Orange": r"\borange\b", "smsapi": r"\bsmsapi\b",
    },
    geo_target="Actio",
    geo_system_prompt=(
        "Jestes asystentem doradzajacym polskim firmom wybor dostawcy uslug telekomunikacyjnych/VoIP. "
        "Odpowiadaj po polsku, rzeczowo, i wymieniaj KONKRETNYCH dostawcow/operatorow z nazwy. "
        "Maksymalnie kilka zdan."
    ),
)


SENDLY = BrandProfile(
    id="sendly",
    name="Sendly",
    report_slug="sendly-marketing",
    report_prompt=SENDLY_REPORT_PROMPT,
    trends_prompt=SENDLY_TRENDS_PROMPT,
    trends_fields=(
        ("trend", "Trend"),
        ("angle", "Jak podpiąć pod SENDLY"),
        ("blog", "Na blog?"),
        ("ad_copy", "Sugerowany tekst reklamy"),
    ),
    trends_intro=(
        "Trendy z Google Trends (PL) z potencjałem do szybkiej reakcji reklamowej pod SMS API SENDLY. "
        "Ocena i kreacje wygenerowane automatycznie – zweryfikuj przed publikacją."
    ),
    trends_empty="_Dziś brak trendów z sensownym, nienaciąganym powiązaniem z SENDLY._",
    openrouter_referer="https://sendly.link",
    openrouter_title="Sendly Marketing CMO-layer",
    context_file="context_sendly.md",
    excluded_countries=("Singapore", "United States"),
    lead_event="sign_up",  # event rejestracji (odpalany z sendly-www v1.4.69)
    lead_dimensions=(),  # breakdown fn jest zahardkodowany na schemat ACTIO/GTM (form_id/form_location/phone_number/link_location) -> dla sendly (language/registration_type) rzuca 400; skip do czasu parametryzacji. Licznik sign_up i tak leci z osobnego syncu ga4.
    ga4_property_default="",  # z env GA4_PROPERTY_ID (brak sensownego defaultu)
    ads_enabled=True,        # konto SYNTELL S.A. 255-647-3852 (spolka matka)
    competitor_campaign=None,  # sendly nie ma jeszcze kampanii konkurencyjnej
    site_url="https://sendly.link/",
    brand_query="sendly",
    gsc_site_filter=("https://sendly.link/", "sc-domain:sendly.link"),  # izolacja od actio.pl
    gsc_property="sc-domain:sendly.link",  # SA ma property typu Domain, nie URL-prefix
    conv_value={
        # TODO(biznes): wartosc rejestracji SENDLY do ustalenia z Tomem/Hubertem.
        "rejestracja": 0,
    },
    conv_value_default=0,
    ai_bot_enabled=False,    # sendly nie ma jeszcze feedu ai_bot_hits — sekcja pomijana
    ai_bot_domain="sendly.link",
    cpa_max=50.0,
    currency="zł",
    test_phones=(),          # numery testowe sendly nieznane
    from_name="Sendly Marketing Reports",
    obsidian_reports_path="projects/sendly-marketing-reports",
    cloudflare_enabled=True,  # sendly.link jest na CF — AI Crawl Control + edge HTTP health przez API
    geo_queries=(
        "najlepsze SMS API dla firm w Polsce",
        "ranking dostawcow SMS API w Polsce 2026",
        "tanie SMS API do wysylki SMS dla firm",
        "SMS API od operatora telekomunikacyjnego w Polsce",
        "bramka SMS API dla programistow",
        "masowa wysylka SMS przez API dla firm",
        "SMS API do powiadomien i kodow 2FA",
        "porownanie dostawcow SMS API w Polsce",
        "integracja SMS API z WooCommerce sklep",
    ),
    geo_brands={
        "Sendly": r"\bsendly\b", "SMSAPI": r"\bsmsapi(?:\.pl)?\b", "SerwerSMS": r"serwer\s?sms",
        "SMSlabs": r"\bsmslabs\b", "mProfi": r"\bmprofi\b", "ProSMS": r"\bprosms\b",
        "GudMobi": r"\bgudmobi\b", "SMSCenter": r"\bsmscenter\b", "Twilio": r"\btwilio\b",
        "Vonage": r"\bvonage\b", "Infobip": r"\binfobip\b",
        "MessageBird": r"\bmessagebird\b|\bbird\.com\b", "LOX24": r"\blox24\b",
    },
    geo_target="Sendly",
    geo_system_prompt=(
        "Jestes asystentem doradzajacym polskim firmom wybor dostawcy SMS API / bramki SMS do wysylki wiadomosci. "
        "Odpowiadaj po polsku, rzeczowo, i wymieniaj KONKRETNYCH dostawcow z nazwy. "
        "Maksymalnie kilka zdan."
    ),
)


_PROFILES: dict[str, BrandProfile] = {"actio": ACTIO, "sendly": SENDLY}


def get_brand(name: str | None = None) -> BrandProfile:
    """Zwraca profil marki. Wybor: arg > env BRAND > 'actio' (domyslnie actio = brak regresji)."""
    key = (name or os.environ.get("BRAND", "actio")).strip().lower()
    try:
        return _PROFILES[key]
    except KeyError:
        raise RuntimeError(
            f"Nieznana marka '{key}'. Dostepne: {', '.join(sorted(_PROFILES))}. "
            f"Ustaw zmienna BRAND."
        )
