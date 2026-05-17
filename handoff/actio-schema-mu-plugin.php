<?php
/**
 * Plugin Name: Actio — Schema.org Injector (Complete Replacement)
 * Description: Pełny schema.org JSON-LD markup. Zastępuje moduł Schema Rank Math (DISABLE go w Rank Math → Dashboard po wgraniu tego pluginu). Generuje: Organization, LocalBusiness, WebSite, WebPage, Service (per /uslugi/* slug), Article (blog posts), BreadcrumbList oraz FAQPage (per slug z registry — auto-updated przez autopublisher).
 * Version: 2.0.0
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

        // === FAQ_AUTO_INSERT_AFTER === (autopublisher dodaje nowe wpisy przed tą linią)
    ];
}

// ─── SCHEMA NODES ───────────────────────────────────────────────────────────
function actio_organization_node(): array {
    return [
        '@type'        => 'Organization',
        '@id'          => ACTIO_BASE_URL . '/#organization',
        'name'         => ACTIO_BRAND_NAME,
        'legalName'    => ACTIO_LEGAL_NAME,
        'url'          => ACTIO_BASE_URL,
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
