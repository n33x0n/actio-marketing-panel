<?php
/**
 * Plugin Name: Actio – redirecty migracyjne (interim)
 * Description: Tymczasowe 301 dla ~85 URL-i które padły po migracji (audyt SEO 2026-06-15): cała sekcja /pomoc-techniczna/opisy-konfiguracji/* → /instrukcje-konfiguracji/, /taryfa/* + /cennik/cennik-actio-* → /cennik/, pod-usługi, literówki, soft-404. Hook 'init' (przed redirectami Rank Math/WP), żeby przebić istniejące 301→home. Cele zweryfikowane 200. Reguły scoped (nie łapią żywych stron). DOCELOWO przenieść do Rank Math Redirections i zdjąć ten plik (Todoist B5). Odwracalne.
 * Version: 1.0.0
 * Author: Actio Marketing
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_action( 'init', function () {
	if ( is_admin()
		|| ( defined( 'DOING_AJAX' ) && DOING_AJAX )
		|| ( defined( 'DOING_CRON' ) && DOING_CRON )
		|| ( defined( 'REST_REQUEST' ) && REST_REQUEST )
		|| ( PHP_SAPI === 'cli' ) ) {
		return;
	}
	$path = strtok( isset( $_SERVER['REQUEST_URI'] ) ? $_SERVER['REQUEST_URI'] : '', '?' );
	if ( $path === '' || $path === '/' ) {
		return;
	}
	$base = 'https://actio.pl';

	// Dopasowania dokładne (klucz bez trailing slash).
	$exact = array(
		'/uslugi/3px-phone-system'                                         => '/uslugi/3cx-phone-system/',
		'/blog'                                                            => '/artykuly/',
		'/rejestracja/rejestracja-konta-actio-free'                        => '/rejestracja/',
		'/numery-voip-pelny-przewodnik-jak-dzialaja-jak-wybrac-i-dla-kogo' => '/blog/2025/12/15/numery-voip-pelny-przewodnik-jak-dzialaja-jak-wybrac-i-ile-kosztuja/',
		'/uslugi/sms-przez-voip-2'                                         => '/uslugi/sms-przez-voip/',
		'/wirtualny-numer-telefonu-dla-firm'                               => '/blog/2026/05/19/wirtualny-numer-telefonu-dla-firm/',
		'/numer-voip-dla-firm'                                             => '/blog/2026/05/13/numer-voip-dla-firm/',
		'/stabilna-telefonia-zamiast-thulium-telecube'                     => '/blog/2026/04/30/jak-przeniesc-numer-do-actio-przewodnik-po-portowaniu-numerow-stacjonarnych-i-komorkowych/',
		'/category/voip'                                                   => '/uslugi/',
	);
	$key = rtrim( $path, '/' );
	if ( isset( $exact[ $key ] ) ) {
		wp_redirect( $base . $exact[ $key ], 301 );
		exit;
	}

	// Reguły regex (kolejność = pierwsza pasująca wygrywa). Scoped tak, by nie łapać żywych stron.
	$rules = array(
		array( '#^/pomoc-techniczna/opisy-konfiguracji/#i', '/instrukcje-konfiguracji/' ),
		array( '#^/pomoc-techniczna/?$#i',                  '/instrukcje-konfiguracji/' ),
		array( '#^/taryfa(/|$)#i',                          '/cennik/' ),
		array( '#^/cennik/cennik-actio-#i',                 '/cennik/' ),
		array( '#^/uslugi/numery-telefoniczne(/|$)#i',      '/uslugi/' ),
		array( '#^/uslugi/wirtualna-centrala/.+#i',         '/uslugi/wirtualna-centrala/' ),
	);
	foreach ( $rules as $r ) {
		if ( preg_match( $r[0], $path ) ) {
			wp_redirect( $base . $r[1], 301 );
			exit;
		}
	}
} );
