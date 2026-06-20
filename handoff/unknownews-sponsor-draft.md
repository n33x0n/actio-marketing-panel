# Unknownews (Jakub Mrugalski) – sponsoring, wrzesień 2026

**2 sloty pod rząd:** 2. tydzień września (slot 1) + 3. tydzień września (slot 2).
Decyzja Toma 20.06.2026. Deadline przygotowania kreacji: ~25.08.2026.

## Format slotu (z analizy realnych wydań)

Każdy sponsoring = DWA elementy:
1. **Szary box sponsorski** (góra newslettera): otwarcie „Sponsorem tego wydania newslettera jest **[NAZWA]** – [kto]." + 3–4 krótkie akapity value-first + wyróżniony (bold) URL. Czasem P.S.
2. **Wpis #7 [sponsorowane]** w liście linków: `**[Tytuł] [sponsorowane]**` + URL + `INFO: [2–3 zdania]`.

**Ton:** konwersacyjny, techniczny, ZERO sprzedażowego bełkotu (Mrugalski wytyka i może sam przeredagować). Najlepiej działają sponsoringi prowadzone wartością/użytecznością, nie hasłem „kup nasz produkt".

## Tracking / UTM

| | Slot 1 (Sendly) | Slot 2 (SIP Trunk/3CX) |
|---|---|---|
| Domena | sendly.link | actio.pl |
| GA4 | `G-FLRPGGJ9G9` (jest, + consent banner) | `G-W864FFJXKQ` (jest, generate_lead) |
| URL docelowy z UTM | `https://sendly.link/?utm_source=unknownews&utm_medium=newsletter&utm_campaign=sponsor_wrzesien_2026&utm_content=slot1_sendly` | `https://actio.pl/uslugi/sip-trunk/?utm_source=unknownews&utm_medium=newsletter&utm_campaign=sponsor_wrzesien_2026&utm_content=slot2_siptrunk3cx` |

**TODO przed startem:**
- Sendly: potwierdzić URL konwersji (signup) – `/rejestracja` nie ma w statycznym `out/`, signup pewnie przez `/panel` lub `/form`; ustawić event konwersji (rejestracja/założenie konta) w GA4 G-FLRPGGJ9G9.
- Pomiar: filtr GA4 po `utm_campaign=sponsor_wrzesien_2026` (sesje + konwersje per slot przez utm_content).
- Mrugalski linkuje przez własny wrapper (sendy.uw-team.org) – ale URL docelowy MUSI mieć nasze UTM, żeby GA4 przypisał źródło.
- Rozważyć dedykowaną ofertę dla czytelników (np. „dla Unknownews: 200 SMS testowych zamiast 100") – mierzalne i Mrugalski lubi konkret dla swojej społeczności.

---

## SLOT 1 — Sendly (SMS API) — 2. tydzień września

### Box sponsorski (wersja robocza)

Sponsorem tego wydania newslettera jest **Sendly** – nowy, polski operator SMS API (marka ACTIO, operatora zarejestrowanego w UKE).

Jeśli kiedykolwiek wpinałeś wysyłkę SMS-ów do swojej aplikacji – kody 2FA, alerty, powiadomienia transakcyjne – wiesz, że u większości dostawców zaczyna się od abonamentu, minimów wysyłki albo umowy na start. Sendly idzie inaczej: czyste REST API i płatność za faktycznie wysłane wiadomości (pay-as-you-go), bez abonamentu i bez minimów.

Wysyłasz jednym requestem (autoryzacja Bearer), odbierasz statusy dostarczenia webhookiem (DLR), ustawiasz własny sender ID, a stawki zaczynają się od 0,075 zł/SMS. Infrastruktura w Polsce, SLA 99,9%, a SMS-y wyślesz nawet prosto z centrali VoIP (SIP MESSAGE).

Na start dostajesz **100 SMS-ów gratis, bez podawania karty** – akurat tyle, żeby wpiąć to we własny kod i sprawdzić, czy robi robotę:
**https://sendly.link**

### Box sponsorski – wariant z curl (dla devów)

Sponsorem tego wydania newslettera jest **Sendly** – nowy, polski operator SMS API (marka ACTIO, operatora zarejestrowanego w UKE).

Wysłanie SMS-a z własnej aplikacji – kodu 2FA, alertu, powiadomienia – wygląda u nas tak:

    curl -X POST https://msg-api.actio.pl/api/sms \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"from":"TwojaFirma","to":"48732129000","body":"Twój kod: 482910"}'

Jeden endpoint, autoryzacja Bearer, czysty JSON – bez SDK. To `from` z przykładu to nadpis, czyli własna nazwa nadawcy zamiast numeru – SMS dociera do klienta podpisany Twoją firmą. Płacisz tylko za faktycznie wysłane wiadomości, od 0,075 zł/SMS, bez abonamentu i bez minimów wysyłki. Statusy dostarczenia odbierasz webhookiem (DLR), a infrastruktura stoi w Polsce (SLA 99,9%).

Na start **100 SMS-ów gratis, bez podawania karty** – akurat tyle, żeby przetestować na produkcji własnego kodu:
**https://sendly.link**

### Wpis #7 [sponsorowane]

**Sendly – polski SMS API bez abonamentu, 100 SMS gratis na test [sponsorowane]**
https://sendly.link
INFO: Potrzebujesz wysyłać SMS-y z własnej aplikacji (2FA, alerty, powiadomienia transakcyjne)? Sendly daje czyste REST API z płatnością za wysłane wiadomości – bez abonamentu i bez minimów. Autoryzacja Bearer, webhooki ze statusami (DLR), własny sender ID, stawki od 0,075 zł/SMS, operator zarejestrowany w UKE. Na start 100 SMS gratis bez karty.

---

## SLOT 2 — ACTIO (SIP Trunk / 3CX) — 3. tydzień września

### Box sponsorski (wersja robocza)

Sponsorem tego wydania newslettera jest **ACTIO** – polski operator telekomunikacyjny zarejestrowany w UKE, tym razem od strony firmowej telefonii.

Jeśli ogarniasz telefonię w firmie albo u klienta, znasz ten ból: stare łącza ISDN, centrala na sztywno, licencje liczone od każdego użytkownika. ACTIO robi to inaczej – **SIP Trunk** podłączysz do dowolnej centrali z obsługą SIP (3CX, Asterisk/FreePBX, Yeastar, też MS Teams w trybie Direct Routing), z polskimi numerami +48 i przeniesieniem dotychczasowych (MNP).

Do tego **3CX** jako nowoczesna centrala w chmurze lub na własnym serwerze: aplikacja na telefon i komputer, wideo i czat, a licencja liczona **od liczby jednoczesnych połączeń, a nie od liczby pracowników** – więc koszt nie rośnie razem z zespołem. ACTIO jest partnerem 3CX od 2009 roku i wdraża to z polskim wsparciem.

Konkrety: dostępność 99,9% (SLA), a przy przeniesieniu numeru pierwsze 3 miesiące bez abonamentu:
**https://actio.pl/uslugi/sip-trunk/**

### Wpis #7 [sponsorowane]

**ACTIO – SIP Trunk i 3CX dla firm od polskiego operatora [sponsorowane]**
https://actio.pl/uslugi/sip-trunk/
INFO: Telefonia dla firmy przez internet, bez przestarzałych łączy ISDN. Łącze SIP Trunk podłączysz do dowolnej centrali (3CX, Asterisk, Yeastar, a także Microsoft Teams), na polskich numerach +48 i z możliwością przeniesienia dotychczasowego numeru. W 3CX płacisz za liczbę jednoczesnych rozmów, a nie za każdego pracownika – koszt nie rośnie razem z zespołem. Polski operator zarejestrowany w UKE, dostępność 99,9%, partner 3CX od 2009 roku.
