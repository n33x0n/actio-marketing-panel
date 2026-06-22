<?php
/**
 * Plugin Name: Actio – GSC site verification (meta tag)
 * Description: Wstrzykuje <meta name="google-site-verification"> do <head> na wszystkich stronach – re-weryfikacja Google Search Console metodą HTML-tag (niezależną od GA4 / Site Kit / GTM, więc odporną na zmiany tagów). ZALECANE: zostawić na stałe – usunięcie pliku zdejmie weryfikację i GSC może znów się rozpiąć.
 * Version: 1.0.0
 * Author: Actio Marketing
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
add_action( 'wp_head', function () {
	echo "\n" . '<meta name="google-site-verification" content="djDlTZ-n98ePbwDPpvlZ5JfCFUvgx1LbbmQMMCrldCo" />' . "\n";
}, 1 );
