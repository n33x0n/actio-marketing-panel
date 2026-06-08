<?php
/**
 * Plugin Name: Actio – 3CX H1 fix
 * Description: Promuje główny nagłówek "3CX Phone System" z H2 na H1 na /uslugi/3cx-phone-system/ (SEO / post-click QS – strona nie miała żadnego H1). Output-buffer, scoped do tej jednej strony, idempotentny (jeśli pojawi się jakikolwiek H1, nic nie robi), odwracalny (usunięcie pliku przywraca stan). Nie zmienia treści ani designu Elementora – tylko tag nagłówka.
 * Version: 1.0.0
 * Author: Actio Marketing
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_action( 'template_redirect', function () {
	$uri = isset( $_SERVER['REQUEST_URI'] ) ? $_SERVER['REQUEST_URI'] : '';
	if ( strpos( $uri, '/uslugi/3cx-phone-system' ) === false ) {
		return;
	}
	ob_start( function ( $html ) {
		if ( ! is_string( $html ) || $html === '' ) {
			return $html;
		}
		// Jeśli strona ma już jakikolwiek <h1> – nie ruszaj (np. Hubert dodał w Elementorze).
		if ( stripos( $html, '<h1' ) !== false ) {
			return $html;
		}
		// Promuj pierwszy nagłówek "3CX Phone System" z h2 na h1 (tolerancja atrybutów/whitespace).
		$out = preg_replace(
			'#<h2(\s[^>]*)?>(\s*3CX Phone System\s*)</h2>#i',
			'<h1$1>$2</h1>',
			$html,
			1
		);
		return ( null === $out ) ? $html : $out;
	} );
} );
