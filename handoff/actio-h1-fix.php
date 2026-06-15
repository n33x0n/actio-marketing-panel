<?php
/**
 * Plugin Name: Actio – H1 fix (money-pages)
 * Description: Promuje hero (pierwszy nagłówek z klasą elementor-heading-title, renderowany jako H2) -> H1 na kluczowych money-stronach PL, które po migracji nie mają ŻADNEGO H1 (audyt SEO 2026-06-15, finding A5). Output-buffer, scoped do whitelisty dokładnych ścieżek, idempotentny (jeśli istnieje jakikolwiek H1 – nie rusza), odwracalny (usunięcie pliku = stan sprzed). Styl bez zmian – Elementor styluje .elementor-heading-title niezależnie od tagu. /uslugi/3cx-phone-system/ obsługuje osobny actio-3cx-h1.php (brak nakładki). /en/ /de/ celowo pominięte (pakiet i18n: A6/B3/C1).
 * Version: 1.0.0
 * Author: Actio Marketing
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_action( 'template_redirect', function () {
	$uri  = strtok( isset( $_SERVER['REQUEST_URI'] ) ? $_SERVER['REQUEST_URI'] : '', '?' );
	$path = rtrim( $uri, '/' ); // home -> '' ; /cennik/ -> /cennik

	$targets = array(
		'',                                              // strona główna
		'/uslugi',                                       // hub usług
		'/telefonia-voip-dla-firm',
		'/uslugi/sip-trunk',
		'/uslugi/wirtualny-numer-komorkowy-voip',
		'/cennik',
		'/kontakt',
	);
	if ( ! in_array( $path, $targets, true ) ) {
		return;
	}

	ob_start( function ( $html ) {
		if ( ! is_string( $html ) || $html === '' ) {
			return $html;
		}
		// Jeśli strona ma już jakikolwiek <h1> (np. Hubert dodał w Elementorze) – nie ruszaj.
		if ( stripos( $html, '<h1' ) !== false ) {
			return $html;
		}
		// Promuj PIERWSZY nagłówek elementor-heading-title z H2 na H1 (zachowuje atrybuty/klasy).
		$out = preg_replace(
			'#<h2([^>]*elementor-heading-title[^>]*)>(.*?)</h2>#is',
			'<h1$1>$2</h1>',
			$html,
			1
		);
		return ( null === $out ) ? $html : $out;
	} );
} );
