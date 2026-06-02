# Tracking rejestracji konta klienta – wklejka GTM do aplikacji "Odbieraczka"

**Co**: dodać Google Tag Manager (kontener `GTM-56N7NT77`) do aplikacji `rejestracja-demo.actio.pl`. Po wdrożeniu każde otwarcie strony `/registration_confirm/<token>` automatycznie wyśle konwersję do GA4 + Google Ads (`generate_lead` z `value=1500 PLN`, `lead_type=registration`).

**Dlaczego**: aktualnie po kliknięciu maila potwierdzającego rejestrację – Google Ads nie wie że klient ukończył rejestrację. Smart Bidding optymalizuje się tylko na form submit z `actio.pl` (samo wypełnienie formularza), bez sygnału że klient zaakceptował i założył konto.

**Czas wdrożenia**: 5 min (2 wklejki w Blade template) + 5 min weryfikacji.

---

## Krok 1: Dodaj GTM snippet do `<head>` głównego layoutu

Otwórz główny Blade layout aplikacji (zazwyczaj `resources/views/welcome.blade.php` lub `resources/views/app.blade.php` – ten który renderuje `<title>Odbieraczka</title>`).

Wklej **jak najwyżej w `<head>`**, najlepiej zaraz po `<meta charset="utf-8">` i `<meta name="viewport">`, ale **PRZED** wszystkimi `<link>` i `<script>`:

```html
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','GTM-56N7NT77');</script>
<!-- End Google Tag Manager -->
```

## Krok 2: Dodaj GTM noscript do `<body>`

W tym samym Blade template, **bezpośrednio po `<body>`** (pierwsza rzecz w body):

```html
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-56N7NT77"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
```

To wszystko. Nie trzeba zmieniać `app.js`, Vue komponentów, route'ów ani żadnej logiki. Tag jest skonfigurowany w GTM po naszej stronie – odpali się automatycznie przy każdym pageview na `/registration_confirm/<token>`.

---

## Po wdrożeniu – weryfikacja

### Test 1: Browser DevTools (Hubert/dev, 2 min)

1. Otwórz w przeglądarce: `https://rejestracja-demo.actio.pl/registration_confirm/<dowolny-token-testowy>`
2. F12 → zakładka **Network** → filter `gtm.js`
3. Powinien być request do `googletagmanager.com/gtm.js?id=GTM-56N7NT77` → status 200

Jeśli tak – GTM się ładuje. Jeśli nie – snippet źle wklejony (np. nie w głównym layoutie który `/registration_confirm/` używa).

### Test 2: Tag Assistant (Tom, 3 min)

1. Otwórz: https://tagassistant.google.com/
2. Add domain: `rejestracja-demo.actio.pl/registration_confirm/<token>`
3. Connect
4. Po załadowaniu strony powinieneś zobaczyć w liście tag fired:
   - **`GA4 - generate lead - registration`** | Event: `generate_lead`
   - Event parameters: `lead_type: "registration"`, `value: "1500"`, `currency: "PLN"`, `form_location: "/registration_confirm/<token>"`

### Test 3: GA4 DebugView (Tom, 5 min)

1. GA4 → Admin → DebugView
2. Otwórz `/registration_confirm/<token>` w Chrome (z włączonym GA Debugger extension lub `?_dbg=1` query)
3. W DebugView pojawi się event `generate_lead` z parametrami value=1500, currency=PLN, lead_type=registration

Po teście – Ads zacznie liczyć te konwersje w ciągu ~24h.

---

## Co jeszcze warto wiedzieć

- **Konwersja `generate_lead`** w Ads już istnieje (jako GA4-imported, ID 7309180047) – nie trzeba tworzyć nowej. Tylko dodajemy nowe źródło która ją wyzwala.
- **`lead_type=registration`** – nowa wartość obok istniejących `form` i `phone`. Pozwoli w GA4 i w panel positive report odróżnić: kliki tel vs wypełnienie formularza vs faktyczne ukończenie rejestracji.
- **Wartość 1500 zł** – konserwatywny mid-range (form lead value ~900-1200, faktyczna usługa 360-3600). To bardziej "confirmed lead" niż "purchase", ale **dużo lepszy sygnał dla Smart Bidding** niż obecny brak konwersji.
- **GTM-56N7NT77** to ten sam kontener który już działa na `actio.pl` – jeden kontener obsługuje wiele domen, nie ma kolizji. Nasz tag firingu odpali się WYŁĄCZNIE na URL `rejestracja-demo.actio.pl/registration_confirm/*` (filtr regex w trigerze).
- **Cross-domain linker** który Hubert wdrożył 16.05 będzie współpracował automatycznie – sesja użytkownika będzie kontynuowana między `actio.pl` (gdzie kliknął ad) → mail → `rejestracja-demo.actio.pl` (gdzie potwierdza). Smart Bidding zobaczy konwersję przypisaną do oryginalnej kampanii / KW.

---

## SPA caveat (warto pamiętać na przyszłość)

Aplikacja "Odbieraczka" to SPA Vue. GTM trigger typu `pageview` odpala się TYLKO przy initial page load (HTML render). Jeśli kiedyś Vue Router będzie nawigował między widokami client-side (bez full page reload), tag NIE odpali się przy zmianie route'a.

Dla `/registration_confirm/<token>` to nie problem – ten URL otwiera się jako bezpośrednie wejście z maila (zawsze full page load). Ale jeśli kiedyś dodacie inne konwersje w SPA (np. "potwierdź email", "skompletuj profil") – trzeba będzie albo:
- Dodać `dataLayer.push({event: 'sign_up_complete'})` w Vue komponencie po sukcesie, plus dedicated trigger Custom Event w GTM, lub
- Użyć "History Change" trigger w GTM (ale ten jest mniej niezawodny dla Vue Router).

Na razie nie trzeba – `/registration_confirm/` zawsze ładuje się świeżo.
