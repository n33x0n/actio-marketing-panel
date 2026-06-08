<?php
/**
 * Plugin Name: Actio — Schema.org Injector (Complete Replacement)
 * Description: Pełny schema.org JSON-LD markup. Zastępuje moduł Schema Rank Math (DISABLE go w Rank Math → Dashboard po wgraniu tego pluginu). Generuje: Organization, LocalBusiness, WebSite, WebPage, Service (per /uslugi/* slug), Article (blog posts), BreadcrumbList oraz FAQPage (per slug z registry — auto-updated przez autopublisher).
 * Version: 2.0.1
 * Author: Tom Lebioda
 * Author URI: https://tomlebioda.com
 * Contact: hello@tomlebioda.com
 *
 * INSTALACJA:
 *   1. Wgraj plik do /wp-content/mu-plugins/ przez FTP/cPanel
 *   2. WP → Rank Math → Dashboard → wyłącz moduł "Schema" (toggle off)
 *   3. Plugin ładuje się automatycznie (mu-plugins = must-use, no activation needed)
 *   4. Weryfikacja: Google Rich Results Test → wklej URL → sprawdź FAQPage + Service emit
 *
 * AUTO-UPDATE:
 *   FAQPage registry (`actio_faqpage_registry()`) jest auto-uzupełniana przez autopublisher Python
 *   przed markerem `// === FAQ_AUTO_INSERT_AFTER ===`.
 */

if ( ! defined( 'ABSPATH' ) ) exit;

// ─── KONFIGURACJA FIRMY (zmień tu gdy się zmienia) ──────────────────────────
const ACTIO_BASE_URL     = 'https://actio.pl';
const ACTIO_BRAND_NAME   = 'Actio';
const ACTIO_LEGAL_NAME   = 'SYNTELL S.A.';
const ACTIO_TAX_ID       = '7831703009';
const ACTIO_VAT_ID       = 'PL7831703009';
const ACTIO_KRS          = '0000476527';
const ACTIO_REGON        = '302523655';
const ACTIO_LOGO_URL     = 'https://actio.pl/wp-content/uploads/2025/09/ACTIO-LOGO-PODSTAWOWE.webp';
const ACTIO_STREET       = 'Plac Wolności 18';
const ACTIO_POSTAL       = '61-739';
const ACTIO_CITY         = 'Poznań';
const ACTIO_COUNTRY      = 'PL';
const ACTIO_GEO_LAT      = 52.40869;
const ACTIO_GEO_LON      = 16.93331;
const ACTIO_PRICE_RANGE  = '$$';

// Mapping /uslugi/* slug → serviceType opis (dla Service schema)
function actio_service_map(): array {
    return [
        'sip-trunk'                                                            => 'SIP Trunk dla firm',
        'wirtualny-numer-komorkowy-voip'                                       => 'Wirtualny numer komórkowy VoIP',
        'wirtualna-centrala'                                                   => 'Wirtualna centrala telefoniczna',
        '3cx-phone-system'                                                     => '3CX Phone System',
        'sms-przez-voip'                                                       => 'SMS przez VoIP',
        'sms-api'                                                              => 'SMS API dla firm',
        'wirtualny-fax'                                                        => 'Wirtualny fax online',
        'ankiety-telefoniczne'                                                 => 'Ankiety telefoniczne IVR',
        'rozwiazania-sztucznej-inteligencji-ai-w-komunikacji'                  => 'AI w komunikacji telefonicznej',
        'nowoczesna-komunikacja-glosowa-z-voip'                                => 'Komunikacja głosowa VoIP',
        'nowoczesna-komunikacja-video-spotkania-twarza-w-twarz-bez-barier'     => 'Wideokonferencje firmowe',
        'przekierowanie-polaczen'                                              => 'Przekierowanie połączeń',
        'poczta-glosowa'                                                       => 'Poczta głosowa',
    ];
}

// ─── FAQPage REGISTRY (per-slug Q&A — AUTO-UPDATED by autopublisher) ────────
function actio_faqpage_registry(): array {
    return [

        // === FAQ_ENTRY_START: wirtualny-numer-komorkowy-voip ===
        'wirtualny-numer-komorkowy-voip' => [
            ['q' => 'Czym różni się wirtualny numer komórkowy od zwykłej karty SIM?',
             'a' => 'Wirtualny numer nie wymaga fizycznej karty. Działa w aplikacji w telefonie pracownika. Jest niezależny od operatora sieci komórkowej i działa wszędzie gdzie jest internet.'],
            ['q' => 'Czy mogę przenieść mój obecny numer komórkowy do Actio?',
             'a' => 'Tak, robimy portację numerów komórkowych w 24 godziny. Zachowujesz numer, zmieniasz operatora.'],
            ['q' => 'Jakiego sprzętu potrzebuję?',
             'a' => 'Wystarczy smartfon (Android lub iOS) z internetem. Pracownik instaluje aplikację, loguje się i numer działa.'],
            ['q' => 'Co z roamingiem?',
             'a' => 'Wirtualny numer komórkowy działa wszędzie gdzie jest internet (Wi-Fi). W roamingu możesz używać tej samej aplikacji bez dodatkowych opłat za połączenia przychodzące.'],
            ['q' => 'Jak długo trwa aktywacja?',
             'a' => 'Nowy numer komórkowy aktywujemy w 24 godziny. Portacja istniejącego numeru – również 24 godziny.'],
            ['q' => 'Czy mogę testować przed podpisaniem umowy?',
             'a' => 'Tak. Oferujemy okres testowy z bezpłatną wyceną dopasowaną do firmy.'],
            ['q' => 'Jak działa wirtualny numer komórkowy?',
             'a' => 'Wirtualny numer komórkowy działa w aplikacji zainstalowanej na smartfonie. Połączenia są transmitowane przez internet (technologia VoIP), zamiast przez tradycyjną sieć GSM. Aplikacja loguje się do naszej platformy i przypisuje numer pracownikowi – nie wymaga karty SIM ani drugiego telefonu.'],
            ['q' => 'Ile kosztuje wirtualny numer komórkowy dla firmy?',
             'a' => 'Koszt zależy od liczby numerów i pakietu połączeń. Oferujemy elastyczne plany dla firm różnej wielkości – od kilku numerów dla małego zespołu po setki dla większych organizacji. Każda firma otrzymuje bezpłatną wycenę dopasowaną do jej potrzeb.'],
            ['q' => 'Czy mogę mieć kilka wirtualnych numerów na jednym telefonie?',
             'a' => 'Tak, jeden pracownik może obsługiwać wiele wirtualnych numerów z jednej aplikacji – np. numer ogólny działu i numer bezpośredni handlowca. Wszystkie połączenia trafiają na ten sam telefon, ale system rozróżnia, na który numer dzwoni klient.'],
        ],
        // === FAQ_ENTRY_END: wirtualny-numer-komorkowy-voip ===

        // === FAQ_ENTRY_START: wirtualny-numer-telefonu-dla-firm ===
        'wirtualny-numer-telefonu-dla-firm' => [
            ['q' => 'Czym różni się wirtualny numer od zwykłego numeru stacjonarnego?',
             'a' => 'Wirtualny numer nie jest przypisany do fizycznej linii telefonicznej ani konkretnej lokalizacji. Działa przez internet (VoIP), co pozwala kierować połączenia do dowolnego urządzenia lub grupy pracowników, niezależnie od miejsca ich przebywania. Zwykły numer stacjonarny jest powiązany z konkretnym adresem i wymaga fizycznej infrastruktury.'],
            ['q' => 'Jak szybko można uruchomić wirtualny numer?',
             'a' => 'Uruchomienie wirtualnego numeru trwa zazwyczaj od kilku godzin do jednego dnia roboczego. Nie wymaga instalacji sprzętu ani wizyty technika – konfiguracja odbywa się zdalnie przez panel administracyjny dostawcy.'],
            ['q' => 'Czy wirtualny numer można przenieść od innego operatora?',
             'a' => 'Tak, przeniesienie istniejącego numeru telefonicznego do nowego operatora VoIP jest możliwe i odbywa się zgodnie z procedurą przenoszalności numerów (MNP/LNP) regulowaną przez UKE. Proces trwa zazwyczaj kilka dni roboczych i nie powoduje przerwy w odbieraniu połączeń.'],
            ['q' => 'Ile kosztuje wirtualny numer telefonu dla firmy?',
             'a' => 'Koszt zależy od rodzaju numeru, liczby linii i wybranych funkcji. Podstawowy abonament za wirtualny numer zaczyna się od kilkudziesięciu złotych miesięcznie. W przypadku rozbudowanych systemów z kolejkowaniem, IVR i analityką cena jest wyższa, ale nadal znacznie niższa niż utrzymanie tradycyjnej centrali PABX. Najlepiej poprosić o indywidualną wycenę dopasowaną do potrzeb firmy.'],
            ['q' => 'Czy wirtualny numer działa na telefonie komórkowym?',
             'a' => 'Tak, wirtualny numer może być skierowany na telefon komórkowy, aplikację mobilną VoIP lub softphone na komputerze. Pracownik odbiera połączenia przychodzące na wirtualny numer niezależnie od tego, gdzie się znajduje, pod warunkiem dostępu do internetu lub sieci GSM.'],
            ['q' => 'Czy można mieć kilka wirtualnych numerów w jednej firmie?',
             'a' => 'Tak, firmy mogą posiadać dowolną liczbę wirtualnych numerów – np. oddzielne numery dla różnych działów, oddziałów, kampanii marketingowych lub produktów. Wszystkie numery mogą być zarządzane z poziomu jednego panelu administracyjnego.'],
            ['q' => 'Czy wirtualny numer zapewnia bezpieczeństwo rozmów?',
             'a' => 'Rzetelni operatorzy VoIP stosują szyfrowanie transmisji głosu (protokół SRTP i TLS), co zabezpiecza rozmowy przed przechwyceniem. Ważne jest, aby wybrać dostawcę z własną infrastrukturą w Polsce i potwierdzonymi standardami bezpieczeństwa, szczególnie jeśli firma przetwarza wrażliwe dane klientów.'],
        ],
        // === FAQ_ENTRY_END: wirtualny-numer-telefonu-dla-firm ===

        // === FAQ_ENTRY_START: numer-voip-dla-firm ===
        'numer-voip-dla-firm' => [
            ['q' => 'Czy numer VoIP różni się od zwykłego numeru telefonu?',
             'a' => 'Dla osoby dzwoniącej z zewnątrz numer VoIP wygląda i działa identycznie jak tradycyjny numer stacjonarny lub komórkowy. Różnica leży w technologii przesyłu głosu – zamiast sieci telefonicznej PSTN używane jest łącze internetowe.'],
            ['q' => 'Czy mogę przenieść istniejący numer stacjonarny do VoIP?',
             'a' => 'Tak. Procedura przeniesienia numeru (portability) pozwala zachować dotychczasowy numer i przenieść go do operatora VoIP. Czas przeniesienia zależy od poprzedniego operatora i wynosi zazwyczaj od kilku do kilkunastu dni roboczych.'],
            ['q' => 'Jakie łącze internetowe jest potrzebne do korzystania z numerów VoIP?',
             'a' => 'Jedno równoczesne połączenie głosowe wymaga około 80-100 kbps pasma. Standardowe łącze szerokopasmowe wystarczy dla kilkudziesięciu jednoczesnych rozmów. Ważniejsza od przepustowości jest stabilność i niskie opóźnienia połączenia internetowego.'],
            ['q' => 'Czy numer VoIP działa podczas awarii internetu?',
             'a' => 'Podczas przerwy w dostępie do internetu numer VoIP nie będzie dostępny na urządzeniach w biurze. Dobrą praktyką jest skonfigurowanie przekierowania awaryjnego na numer komórkowy, które operator aktywuje automatycznie w przypadku braku dostępności linii.'],
            ['q' => 'Ile kosztuje numer VoIP dla firmy?',
             'a' => 'Koszt zależy od operatora, liczby numerów i wybranego pakietu. Abonament za numer VoIP zaczyna się zazwyczaj od kilku złotych miesięcznie. W porównaniu z tradycyjnymi liniami ISDN oszczędności na rachunkach za połączenia mogą wynieść od 30 do 60 procent.'],
            ['q' => 'Czy pracownik może używać firmowego numeru VoIP na telefonie komórkowym?',
             'a' => 'Tak. Większość operatorów udostępnia aplikację mobilną lub umożliwia konfigurację klienta SIP na smartfonie. Pracownik dzwoni i odbiera połączenia ze swojego firmowego numeru VoIP niezależnie od miejsca, w którym się znajduje.'],
            ['q' => 'Jak wygląda obsługa techniczna numerów VoIP?',
             'a' => 'Profesjonalni operatorzy zapewniają wsparcie techniczne przez telefon, e-mail lub chat, często w trybie 24/7. Actio oferuje dedykowanego opiekuna technicznego dla klientów biznesowych oraz umowy SLA określające gwarantowany czas reakcji i usunięcia awarii.'],
            ['q' => 'Czy numery VoIP można używać do wysyłania faksów?',
             'a' => 'Tak, istnieje możliwość obsługi faksów przez VoIP w technologii T.38 lub za pomocą usługi faks-na-e-mail. Tradycyjne faksy analogowe podłączone przez adapter ATA również mogą współpracować z numerami VoIP, choć jakość transmisji może być zmienna w zależności od parametrów łącza.'],
        ],
        // === FAQ_ENTRY_END: numer-voip-dla-firm ===

        // === FAQ_ENTRY_START: telefonia-voip-dla-firm ===
        'telefonia-voip-dla-firm' => [
            ['q' => 'Czy telefonia VoIP jest odpowiednia dla małych firm?',
             'a' => 'Tak. Telefonia VoIP jest skalowalna i opłacalna niezależnie od wielkości firmy. Małe firmy mogą zacząć od kilku numerów i rozbudowywać system wraz z rozwojem działalności. Modele abonamentowe eliminują wysokie koszty wejścia charakterystyczne dla tradycyjnych central telefonicznych.'],
            ['q' => 'Jakiego łącza internetowego potrzebuję do VoIP?',
             'a' => 'Do obsługi jednego połączenia VoIP w dobrej jakości wystarczy około 100 kbps pasma w obu kierunkach. W praktyce firma z 20 równoczesnymi połączeniami potrzebuje łącza o przepustowości co najmniej 10 Mbps. Ważniejsza od szybkości jest jednak stabilność połączenia i niskie opóźnienia (latency poniżej 150 ms).'],
            ['q' => 'Czy mogę zachować dotychczasowy numer telefonu przy przejściu na VoIP?',
             'a' => 'Tak. Przeniesienie numeru (portability) to standardowa procedura regulowana prawem telekomunikacyjnym. Operator VoIP przeprowadza migrację numerów, a cały proces odbywa się bez długotrwałej przerwy w dostępności.'],
            ['q' => 'Czy VoIP działa podczas awarii internetu?',
             'a' => 'W przypadku awarii łącza internetowego standardowe połączenia VoIP nie są dostępne. Dobrzy dostawcy oferują jednak mechanizmy awaryjne, takie jak automatyczne przekierowanie połączeń na numer komórkowy lub zapasowe łącze. Warto omówić scenariusze awaryjne z dostawcą przed podpisaniem umowy.'],
            ['q' => 'Ile kosztuje telefonia VoIP dla firmy?',
             'a' => 'Koszty zależą od liczby użytkowników, wybranych funkcji i modelu rozliczenia. Typowy abonament za stanowisko w modelu chmurowym wynosi od kilkudziesięciu do kilkuset złotych miesięcznie. Do tego dochodzą koszty połączeń wychodzących, choć wielu operatorów oferuje pakiety z nielimitowanymi połączeniami krajowymi.'],
            ['q' => 'Czym różni się VoIP od tradycyjnej centrali telefonicznej (PBX)?',
             'a' => 'Tradycyjna centrala PBX wymaga dedykowanego sprzętu zainstalowanego w siedzibie firmy i fizycznych łączy telefonicznych. VoIP działa przez internet, co eliminuje koszty sprzętu i okablowania. Wirtualna centrala VoIP oferuje te same funkcje co fizyczna PBX, a często znacznie więcej, przy niższych kosztach wdrożenia i utrzymania.'],
            ['q' => 'Czy telefonia VoIP jest bezpieczna?',
             'a' => 'Przy odpowiedniej konfiguracji i wyborze sprawdzonego dostawcy – tak. Kluczowe elementy to szyfrowanie transmisji (SRTP/TLS), silne uwierzytelnianie dostępu do panelu administracyjnego oraz monitoring ruchu pod kątem nieautoryzowanych połączeń. Należy unikać konfigurowania systemów VoIP bez podstawowych zabezpieczeń, ponieważ niezabezpieczone centrale są celem ataków hakerskich.'],
            ['q' => 'Jak długo trwa wdrożenie VoIP w firmie?',
             'a' => 'Dla małych firm wdrożenie może zająć od kilku dni do dwóch tygodni. W przypadku dużych organizacji z wieloma lokalizacjami i złożonymi wymaganiami proces trwa zwykle od czterech do ośmiu tygodni. Czas migracji numerów zależy od procedur obowiązującego operatora i wynosi zazwyczaj od kilku do kilkunastu dni roboczych.'],
        ],
        // === FAQ_ENTRY_END: telefonia-voip-dla-firm ===

        // === FAQ_AUTO_INSERT_AFTER === (autopublisher dodaje nowe wpisy przed tą linią)
    ];
}

// ─── SCHEMA NODES ───────────────────────────────────────────────────────────
// Brand variants (literówki + wariacje nazwy które ludzie wpisują w Google)
// "Aktio" — pozycja 16,8 w GSC z 14 imp/m (literówka defense)
// "Actio.pl"/"Actio Telefonia VoIP" — common variants
function actio_brand_alternate_names(): array {
    return ['Aktio', 'Actio.pl', 'Actio Telefonia VoIP'];
}

function actio_organization_node(): array {
    return [
        '@type'         => 'Organization',
        '@id'           => ACTIO_BASE_URL . '/#organization',
        'name'          => ACTIO_BRAND_NAME,
        'alternateName' => actio_brand_alternate_names(),
        'legalName'     => ACTIO_LEGAL_NAME,
        'url'           => ACTIO_BASE_URL,
        'logo'         => [
            '@type' => 'ImageObject',
            '@id'   => ACTIO_BASE_URL . '/#logo',
            'url'   => ACTIO_LOGO_URL,
        ],
        'taxID'        => ACTIO_TAX_ID,
        'vatID'        => ACTIO_VAT_ID,
        'identifier'   => [
            ['@type' => 'PropertyValue', 'name' => 'KRS',   'value' => ACTIO_KRS],
            ['@type' => 'PropertyValue', 'name' => 'REGON', 'value' => ACTIO_REGON],
        ],
        'sameAs'       => [
            'https://www.wikidata.org/wiki/Q140132189',
            'https://aleo.com/int/company/syntell-spolka-akcyjna',
            'https://opencorporates.com/companies/pl/0000476527',
            'https://rejestr.io/krs/476527',
        ],
        'address'      => actio_postal_address(),
        'contactPoint' => actio_contact_points(),
        'areaServed'   => ['@type' => 'Country', 'name' => 'Polska'],
    ];
}

function actio_postal_address(): array {
    return [
        '@type'           => 'PostalAddress',
        'streetAddress'   => ACTIO_STREET,
        'postalCode'      => ACTIO_POSTAL,
        'addressLocality' => ACTIO_CITY,
        'addressCountry'  => ACTIO_COUNTRY,
    ];
}

function actio_contact_points(): array {
    return [
        [
            '@type'             => 'ContactPoint',
            'contactType'       => 'customer service',
            'name'              => 'Biuro Obsługi Klienta',
            'telephone'         => '+48-61-648-90-00',
            'email'             => 'bok@actio.pl',
            'availableLanguage' => 'Polish',
            'hoursAvailable'    => [
                '@type'     => 'OpeningHoursSpecification',
                'dayOfWeek' => ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'opens'     => '08:00',
                'closes'    => '16:00',
            ],
        ],
        [
            '@type'             => 'ContactPoint',
            'contactType'       => 'sales',
            'name'              => 'Dział Handlowy',
            'telephone'         => '+48-61-648-90-00',
            'email'             => 'sales@actio.pl',
            'availableLanguage' => 'Polish',
            'hoursAvailable'    => [
                '@type'     => 'OpeningHoursSpecification',
                'dayOfWeek' => ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'opens'     => '08:00',
                'closes'    => '16:00',
            ],
        ],
        [
            '@type'             => 'ContactPoint',
            'contactType'       => 'technical support',
            'name'              => 'Pomoc Techniczna',
            'telephone'         => '+48-61-648-90-09',
            'email'             => 'pomoc@actio.pl',
            'availableLanguage' => 'Polish',
            'hoursAvailable'    => [
                '@type'     => 'OpeningHoursSpecification',
                'dayOfWeek' => ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'opens'     => '08:00',
                'closes'    => '18:00',
            ],
        ],
    ];
}

function actio_local_business_node(): array {
    return [
        '@type'         => 'LocalBusiness',
        '@id'           => ACTIO_BASE_URL . '/#localbusiness',
        'name'          => ACTIO_BRAND_NAME,
        'alternateName' => actio_brand_alternate_names(),
        'image'         => ACTIO_LOGO_URL,
        'url'           => ACTIO_BASE_URL,
        'telephone'     => '+48-61-648-90-00',
        'email'         => 'bok@actio.pl',
        'address'       => actio_postal_address(),
        'geo'           => [
            '@type'     => 'GeoCoordinates',
            'latitude'  => ACTIO_GEO_LAT,
            'longitude' => ACTIO_GEO_LON,
        ],
        'priceRange'    => ACTIO_PRICE_RANGE,
        'openingHoursSpecification' => [
            [
                '@type'     => 'OpeningHoursSpecification',
                'dayOfWeek' => ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'opens'     => '08:00',
                'closes'    => '16:00',
            ],
        ],
        'parentOrganization' => ['@id' => ACTIO_BASE_URL . '/#organization'],
    ];
}

function actio_website_node(): array {
    return [
        '@type'           => 'WebSite',
        '@id'             => ACTIO_BASE_URL . '/#website',
        'url'             => ACTIO_BASE_URL,
        'name'            => 'Actio Telefonia VoIP',
        'inLanguage'      => 'pl-PL',
        'publisher'       => ['@id' => ACTIO_BASE_URL . '/#organization'],
        'potentialAction' => [
            '@type'       => 'SearchAction',
            'target'      => [
                '@type'       => 'EntryPoint',
                'urlTemplate' => ACTIO_BASE_URL . '/?s={search_term_string}',
            ],
            'query-input' => 'required name=search_term_string',
        ],
    ];
}

function actio_webpage_node( string $url, string $title, ?string $description = null ): array {
    $node = [
        '@type'      => 'WebPage',
        '@id'        => rtrim( $url, '/' ) . '/#webpage',
        'url'        => $url,
        'name'       => $title,
        'isPartOf'   => ['@id' => ACTIO_BASE_URL . '/#website'],
        'inLanguage' => 'pl-PL',
    ];
    if ( $description ) {
        $node['description'] = $description;
    }
    return $node;
}

function actio_breadcrumb_node( array $items ): array {
    $list = [];
    $pos = 1;
    foreach ( $items as $item ) {
        $list[] = [
            '@type'    => 'ListItem',
            'position' => $pos++,
            'name'     => $item['name'],
            'item'     => $item['url'],
        ];
    }
    return [
        '@type'           => 'BreadcrumbList',
        '@id'             => actio_current_url() . '#breadcrumbs',
        'itemListElement' => $list,
    ];
}

function actio_service_node( string $service_url, string $service_type, string $name, ?string $description = null ): array {
    $node = [
        '@type'       => 'Service',
        '@id'         => rtrim( $service_url, '/' ) . '/#service',
        'name'        => $name,
        'serviceType' => $service_type,
        'url'         => $service_url,
        'provider'    => ['@id' => ACTIO_BASE_URL . '/#organization'],
        'areaServed'  => ['@type' => 'Country', 'name' => 'Polska'],
        'offers'      => [
            '@type'         => 'Offer',
            'url'           => ACTIO_BASE_URL . '/cennik/',
            'priceCurrency' => 'PLN',
            'availability'  => 'https://schema.org/InStock',
        ],
    ];
    if ( $description ) {
        $node['description'] = $description;
    }
    return $node;
}

function actio_article_node( WP_Post $post ): array {
    return [
        '@type'            => 'Article',
        '@id'              => get_permalink( $post ) . '#article',
        'headline'         => get_the_title( $post ),
        'datePublished'    => get_the_date( 'c', $post ),
        'dateModified'     => get_the_modified_date( 'c', $post ),
        'author'           => [
            '@type' => 'Person',
            'name'  => get_the_author_meta( 'display_name', $post->post_author ),
        ],
        'publisher'        => ['@id' => ACTIO_BASE_URL . '/#organization'],
        'mainEntityOfPage' => get_permalink( $post ),
        'inLanguage'       => 'pl-PL',
    ];
}

function actio_faqpage_node( array $faq_items ): array {
    $main_entity = [];
    foreach ( $faq_items as $item ) {
        if ( empty( $item['q'] ) || empty( $item['a'] ) ) continue;
        $main_entity[] = [
            '@type'          => 'Question',
            'name'           => $item['q'],
            'acceptedAnswer' => [
                '@type' => 'Answer',
                'text'  => $item['a'],
            ],
        ];
    }
    return [
        '@type'      => 'FAQPage',
        '@id'        => actio_current_url() . '#faqpage',
        'mainEntity' => $main_entity,
    ];
}

function actio_current_url(): string {
    return ( is_ssl() ? 'https://' : 'http://' ) . $_SERVER['HTTP_HOST'] . strtok( $_SERVER['REQUEST_URI'], '?' );
}

// ─── MAIN EMITTER ───────────────────────────────────────────────────────────
function actio_emit_schema(): void {
    if ( is_admin() ) return;

    $graph = [ actio_organization_node(), actio_website_node() ];

    $url   = actio_current_url();
    $title = trim( wp_title( '|', false, '' ), ' |' ) ?: get_bloginfo( 'name' );
    $desc  = is_singular() ? ( get_the_excerpt() ?: null ) : null;

    $graph[] = actio_webpage_node( $url, $title, $desc );

    // Homepage + /kontakt/ → LocalBusiness
    if ( is_front_page() || ( is_page() && in_array( get_post_field( 'post_name' ), ['kontakt'], true ) ) ) {
        $graph[] = actio_local_business_node();
    }

    // /uslugi/{slug}/ → Service schema
    $current_slug = null;
    $path = trim( parse_url( $_SERVER['REQUEST_URI'], PHP_URL_PATH ), '/' );
    if ( strpos( $path, 'uslugi/' ) === 0 ) {
        $slug = trim( substr( $path, strlen( 'uslugi/' ) ), '/' );
        $current_slug = $slug;
        $map = actio_service_map();
        if ( isset( $map[ $slug ] ) ) {
            $service_url  = ACTIO_BASE_URL . '/uslugi/' . $slug . '/';
            $page_title   = get_the_title() ?: $map[ $slug ];
            $page_desc    = get_the_excerpt() ?: null;
            $graph[] = actio_service_node( $service_url, $map[ $slug ], $page_title, $page_desc );
        }
    } elseif ( is_singular() ) {
        global $post;
        if ( $post && ! empty( $post->post_name ) ) {
            $current_slug = $post->post_name;
        }
    }

    // Blog post → Article
    if ( is_single() ) {
        global $post;
        if ( $post instanceof WP_Post ) {
            $graph[] = actio_article_node( $post );
        }
    }

    // FAQPage — gdy slug w registry
    if ( $current_slug ) {
        $faq_reg = actio_faqpage_registry();
        if ( isset( $faq_reg[ $current_slug ] ) && ! empty( $faq_reg[ $current_slug ] ) ) {
            $graph[] = actio_faqpage_node( $faq_reg[ $current_slug ] );
        }
    }

    // BreadcrumbList
    $crumbs = [ ['name' => 'Strona główna', 'url' => ACTIO_BASE_URL . '/'] ];
    if ( is_page() || is_single() ) {
        $crumbs[] = ['name' => $title, 'url' => $url];
    }
    if ( count( $crumbs ) > 1 ) {
        $graph[] = actio_breadcrumb_node( $crumbs );
    }

    $payload = [
        '@context' => 'https://schema.org',
        '@graph'   => $graph,
    ];

    echo "\n<!-- Actio Schema Injector (mu-plugin v2.0.0) -->\n";
    echo '<script type="application/ld+json">';
    echo wp_json_encode( $payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
    echo "</script>\n";
}
add_action( 'wp_head', 'actio_emit_schema', 5 );

// ─── DISABLE Rank Math schema output (uniknij duplikatów) ──────────────────
add_filter( 'rank_math/json_ld', '__return_empty_array', 999 );
