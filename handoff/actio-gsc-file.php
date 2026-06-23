<?php
/**
 * Plugin Name: Actio – GSC HTML-file verification
 * Description: Serwuje plik weryfikacyjny Google Search Console pod rootem witryny (/googlebb2717269f552354.html). Potrzebne, bo konto FTP jest chrootowane do /wp-content/mu-plugins/ (brak dostępu do web-roota). NIE USUWAĆ po weryfikacji – Google sprawdza okresowo, usunięcie zdejmie weryfikację.
 * Version: 1.0.0
 * Author: Actio Marketing
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
if ( isset( $_SERVER['REQUEST_URI'] ) ) {
	$p = strtok( $_SERVER['REQUEST_URI'], '?' );
	if ( $p === '/googlebb2717269f552354.html' ) {
		header( 'Content-Type: text/html; charset=UTF-8' );
		echo 'google-site-verification: googlebb2717269f552354.html';
		exit;
	}
}
