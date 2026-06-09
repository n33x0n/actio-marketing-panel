<?php
/**
 * Plugin Name: Actio – Consent grant (TYMCZASOWE) + Umami strip
 * Description: TYMCZASOWE (decyzja biznesowa 2026-06-09): wymusza consent GRANTED dla WSZYSTKICH, żeby GA4/Ads liczyło 100% ruchu. Po migracji multilang (03.06) inline'owy bootstrap theme'a ustawił consent default = denied dla świeżych userów → pomiar spadł do ~13% (tylko ci, co klikną „Akceptuję"), realtime ≈ 0. Ten plugin nadpisuje to przez `gtag('consent','update', granted)` wstrzyknięty przed </head> (w oknie wait_for_update=500ms, więc pierwszy page_view leci jako G111) + ustawia localStorage.cookiesAccepted, dzięki czemu od 2. odsłony bootstrap sam ustawia granted i baner się nie pokazuje. Dodatkowo usuwa zepsuty beacon Umami (mws02-51895.wykr.es, 400 na /api/send) wstrzykiwany przez „Head & Footer Code".
 * UWAGA: to świadomie obchodzi zgodę użytkownika (niezgodne z RODO). DO ZDJĘCIA przy wdrożeniu CookieYes / powrocie do consent-gated. Odwracalne: usunięcie pliku przywraca stan sprzed.
 * Version: 1.0.0
 * Author: Actio Marketing
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_action( 'template_redirect', function () {
	if ( is_admin() ) {
		return;
	}
	if ( ( defined( 'DOING_AJAX' ) && DOING_AJAX )
		|| ( defined( 'REST_REQUEST' ) && REST_REQUEST )
		|| ( defined( 'DOING_CRON' ) && DOING_CRON )
		|| is_feed() ) {
		return;
	}

	ob_start( function ( $html ) {
		if ( ! is_string( $html ) || $html === '' || stripos( $html, '</head>' ) === false ) {
			return $html;
		}

		// 1) Wytnij zepsuty beacon Umami (mws02-51895.wykr.es) – Head & Footer Code.
		$html = preg_replace(
			'#<script[^>]*src=["\']https?://[^"\']*wykr\.es/[^"\']*["\'][^>]*>\s*</script>#i',
			'',
			$html
		);

		// 2) Wymuś consent GRANTED dla wszystkich (override denied-default).
		$inject = '<script>/* Actio: tymczasowy granted-default (decyzja 2026-06-09) */'
			. "try{localStorage.setItem('cookiesAccepted','true');}catch(e){}"
			. 'window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
			. "gtag('consent','update',{'analytics_storage':'granted','ad_storage':'granted','ad_user_data':'granted','ad_personalization':'granted'});"
			. '</script>';

		return preg_replace( '#</head>#i', $inject . '</head>', $html, 1 );
	} );
} );
