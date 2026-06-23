<?php
/**
 * Plugin Name: Actio – SEO titles (money-pages)
 * Description: Nadpisuje <title> na kluczowych money-stronach PL (audyt SEO 2026-06-15, A3+A4): keyword z przodu, USP, brand na końcu. Czyni tytuł DETERMINISTYCZNYM mimo dwóch aktywnych wtyczek SEO (Rank Math + Yoast) – hook na 3 filtrach (core + Yoast + Rank Math), nasz wygrywa (priorytet 99999). Tylko whitelista dokładnych ścieżek; reszta bez zmian. Odwracalne (usunięcie pliku = stan sprzed). Pełen tytuł (z „| Actio") = brak doklejania suffixu przez wtyczkę.
 * Version: 1.0.0
 * Author: Actio Marketing
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function actio_seo_title_map() {
	return array(
		''                                          => 'Telefonia VoIP dla firm – polski operator B2B | Actio',
		'/uslugi'                                   => 'Usługi VoIP dla firm – telefonia, centrala, SMS | Actio',
		'/telefonia-voip-dla-firm'                  => 'Telefonia VoIP dla firm – kompletna komunikacja | Actio',
		'/uslugi/sip-trunk'                         => 'SIP Trunk dla firm – podłącz centralę do VoIP | Actio',
		'/uslugi/wirtualny-numer-komorkowy-voip'    => 'Wirtualny numer komórkowy VoIP – GSM bez karty SIM | Actio',
		'/uslugi/ai-voicebot'                       => 'AI Voicebot dla firm – inteligentny asystent głosowy | Actio',
		'/cennik'                                   => 'Cennik telefonii VoIP dla firm – pakiety i ceny | Actio',
	);
}

function actio_seo_title_override( $title ) {
	if ( is_admin() ) {
		return $title;
	}
	$path = rtrim( strtok( isset( $_SERVER['REQUEST_URI'] ) ? $_SERVER['REQUEST_URI'] : '', '?' ), '/' );
	$map  = actio_seo_title_map();
	return isset( $map[ $path ] ) ? $map[ $path ] : $title;
}

// Hook na wszystkich trzech ścieżkach renderu <title> – wygrywa ostatni (99999).
add_filter( 'pre_get_document_title', 'actio_seo_title_override', 99999 );
add_filter( 'wpseo_title', 'actio_seo_title_override', 99999 );             // Yoast
add_filter( 'rank_math/frontend/title', 'actio_seo_title_override', 99999 ); // Rank Math
