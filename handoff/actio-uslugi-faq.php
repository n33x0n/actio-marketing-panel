<?php
/**
 * Plugin Name: Actio – FAQ + FAQPage na stronach usług (GEO/AI-SEO, task A2)
 * Description: Dodaje widoczny blok FAQ + znacznik schema.org FAQPage (JSON-LD) na money-stronach usług, które go nie mają: /uslugi/sip-trunk, /uslugi/3cx-phone-system, /uslugi/wirtualna-centrala, /uslugi/sms-api. Cel: dać AI (ChatGPT/Perplexity/Google AI) i wyszukiwarkom gotowe, cytowalne pary pytanie-odpowiedź → podnieść AI Share of Voice. NIEZALEŻNY od actio-schema-mu-plugin.php (ten obsługuje wirtualny-numer + blog) – zero kolizji i zero ryzyka nadpisania przez autopublisher. Output-buffer (template_redirect), scoped do 4 slugów, idempotentny, odwracalny (usunięcie pliku = stan sprzed). Treść FAQ oparta na realnej ofercie Actio.
 * Version: 1.0.0
 * Author: Actio Marketing
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function actio_uslugi_faq_data() {
	return array(
		'/uslugi/sip-trunk' => array(
			'Czym jest SIP Trunk i czym różni się od tradycyjnych łączy ISDN?' => 'SIP Trunk to wirtualne łącze głosowe działające przez internet (VoIP), które zastępuje fizyczne linie ISDN/PSTN. Podłącza Twoją centralę telefoniczną do publicznej sieci przez protokół SIP – bez dzierżawy łączy miedzianych, taniej i z łatwą skalowalnością.',
			'Czy zachowam swój obecny numer telefonu?' => 'Tak. Actio jest operatorem zarejestrowanym w UKE i obsługuje przeniesienie numerów (MNP). Zachowujesz dotychczasową numerację, a pierwsze 3 miesiące są bez opłat abonamentowych.',
			'Ile jednoczesnych połączeń (kanałów) obsługuje SIP Trunk?' => 'Tyle, ile potrzebujesz. Liczbę kanałów dobiera się do skali firmy i zwiększa w dowolnym momencie bez wymiany sprzętu – w przeciwieństwie do ISDN, gdzie liczba kanałów jest ograniczona fizycznie.',
			'Z jakimi centralami współpracuje SIP Trunk Actio?' => 'Ze standardem SIP, więc z większością central: 3CX, Asterisk/FreePBX, Yeastar, a także Microsoft Teams w trybie Direct Routing.',
			'Ile można zaoszczędzić, przechodząc na SIP Trunk?' => 'Koszty połączeń i utrzymania spadają zwykle o kilkadziesiąt procent względem tradycyjnych łączy – znika dzierżawa linii, a stawki za rozmowy są niższe.',
			'Czy SIP Trunk obsługuje SMS?' => 'Tak. Actio oferuje SIP Trunk z obsługą SMS (wysyłka i odbiór), dzięki czemu numeru firmowego używasz także do komunikacji SMS.',
			'Jak wygląda wdrożenie i ile trwa?' => 'Konfiguracja SIP Trunku to zwykle kwestia godzin – wystarczy centrala z obsługą SIP i dostęp do internetu. Polskie wsparcie techniczne Actio pomaga w uruchomieniu.',
			'Jaka jest dostępność i jakość połączeń?' => 'Infrastruktura Actio działa z dostępnością 99,9% (SLA) na redundantnej architekturze i obsługuje kodeki HD Voice dla wysokiej jakości dźwięku.',
		),
		'/uslugi/3cx-phone-system' => array(
			'Czym jest 3CX i co daje firmie?' => '3CX to nowoczesna centrala telefoniczna (PBX) działająca w chmurze lub na serwerze, z aplikacją na komputer i telefon, wideokonferencjami, czatem i integracjami z CRM.',
			'Czy Actio jest partnerem 3CX?' => 'Tak. Actio współpracuje z 3CX od 2009 roku – wdraża system i dostarcza licencje wraz z polskim wsparciem technicznym.',
			'Ile kosztuje 3CX i czy płacę za każdego użytkownika?' => 'W modelu 3CX nie płacisz za użytkownika. Licencja zależy od liczby jednoczesnych połączeń, a nie od liczby pracowników, co obniża koszt przy rosnącym zespole.',
			'Czy mogę podłączyć 3CX do numerów Actio?' => 'Tak. Przez SIP Trunk Actio podłączasz 3CX do publicznej sieci i korzystasz z polskich numerów +48, z możliwością zachowania dotychczasowego numeru (MNP).',
			'Czy 3CX działa zdalnie i na telefonie komórkowym?' => 'Tak. Aplikacja 3CX na smartfon i komputer pozwala pracownikom dzwonić z firmowego numeru z dowolnego miejsca z dostępem do internetu.',
			'Z jakimi systemami integruje się 3CX?' => 'Między innymi z Microsoft 365, Google Workspace, Salesforce, HubSpot, Zendesk i Freshdesk – dane dzwoniącego i historia połączeń trafiają do CRM.',
			'Czy 3CX obsługuje wideokonferencje i czat?' => 'Tak. 3CX ma wbudowane wideokonferencje, czat zespołowy oraz czat na stronie WWW (live chat).',
			'Jak wygląda wdrożenie 3CX z Actio?' => 'Actio dobiera licencję i konfigurację do potrzeb firmy, podłącza SIP Trunk i numery oraz zapewnia wsparcie – uruchomienie jest możliwe w krótkim czasie.',
		),
		'/uslugi/wirtualna-centrala' => array(
			'Czym jest wirtualna centrala telefoniczna?' => 'To centrala (PBX) działająca w chmurze Actio – bez kupowania i utrzymywania sprzętu. Numerami, kolejkami i przekierowaniami zarządzasz wygodnie przez panel.',
			'Ile kosztuje wirtualna centrala?' => 'Od 49 zł miesięcznie, bez inwestycji w sprzęt i bez opłat za każdego użytkownika.',
			'Jakie funkcje ma wirtualna centrala Actio?' => 'Między innymi IVR (zapowiedzi i menu głosowe), kolejki i grupy, przekierowania warunkowe (np. wg godzin pracy), nagrywanie rozmów oraz historię połączeń.',
			'Czy zachowam swój numer?' => 'Tak. Actio, jako operator zarejestrowany w UKE, przeniesie Twój numer (MNP), a pierwsze 3 miesiące są bez opłat abonamentowych.',
			'Czy centrala sprawdzi się przy pracy zdalnej i wielu lokalizacjach?' => 'Tak. Cały zespół działa pod jednym numerem niezależnie od lokalizacji, a połączenia są kolejkowane i rozdzielane jak w call center.',
			'Czy potrzebuję specjalnego sprzętu?' => 'Nie. Wystarczy internet i aplikacja/softphone lub telefon IP – centrala działa w chmurze.',
			'Czy mogę zintegrować centralę z CRM?' => 'Tak. Integracja jest możliwa przez API oraz przez SIP/3CX z popularnymi systemami CRM.',
			'Jaka jest niezawodność usługi?' => 'Dostępność na poziomie 99,9% (SLA) na redundantnej infrastrukturze.',
		),
		'/uslugi/sms-api' => array(
			'Czym jest SMS API Actio?' => 'To interfejs (REST API), który pozwala wysyłać i odbierać SMS-y bezpośrednio z Twojego systemu – CRM, sklepu czy aplikacji – bez ręcznej obsługi.',
			'Do czego służy SMS API?' => 'Do automatycznych powiadomień (potwierdzenia zamówień, przypomnienia o wizytach, kody, alerty) oraz do dwukierunkowej komunikacji SMS z klientami.',
			'Jak zintegrować SMS API z moim systemem?' => 'Przez REST API z dokumentacją online. Integracja zajmuje zwykle kilka godzin pracy dewelopera; dostępne są gotowe ścieżki do popularnych systemów.',
			'Ile kosztuje wysyłka SMS?' => 'Od 0,075 zł netto za SMS – stawka zależy od wolumenu wysyłki.',
			'Czy mogę wysyłać SMS z nazwy lub numeru firmy?' => 'Tak. Zachowujesz pole nadawcy (nazwa lub numer firmowy), co zwiększa rozpoznawalność i zaufanie odbiorców.',
			'Czy SMS API obsługuje odbiór SMS (dwukierunkowo)?' => 'Tak. Obsługuje komunikację 2-way SMS – odpowiedzi klientów odbierasz przez API lub panel.',
			'Czy otrzymam potwierdzenia dostarczenia (DLR)?' => 'Tak. API zwraca statusy dostarczenia przez webhooki, więc wiesz, które wiadomości dotarły do odbiorców.',
			'Czy mogę połączyć SMS API z numerem VoIP lub SIP Trunk?' => 'Tak. Numer firmowy w Actio może obsługiwać jednocześnie połączenia głosowe i SMS.',
		),
	);
}

add_action( 'template_redirect', function () {
	$path = rtrim( strtok( isset( $_SERVER['REQUEST_URI'] ) ? $_SERVER['REQUEST_URI'] : '', '?' ), '/' );
	$data = actio_uslugi_faq_data();
	if ( ! isset( $data[ $path ] ) ) {
		return;
	}
	$faq = $data[ $path ];

	ob_start( function ( $html ) use ( $faq ) {
		if ( ! is_string( $html ) || stripos( $html, '</body>' ) === false ) {
			return $html;
		}
		if ( strpos( $html, 'actio-faq-section' ) !== false ) {
			return $html; // idempotentny
		}

		// 1. widoczny blok FAQ (accordion)
		$items = '';
		$entities = array();
		foreach ( $faq as $q => $a ) {
			$items .= '<details class="actio-faq-item" style="border-bottom:1px solid #e5e7eb;padding:16px 0;">'
				. '<summary style="cursor:pointer;font-weight:600;font-size:1.05rem;list-style:none;">' . esc_html( $q ) . '</summary>'
				. '<div style="margin-top:10px;color:#444;line-height:1.65;">' . esc_html( $a ) . '</div></details>';
			$entities[] = array(
				'@type'          => 'Question',
				'name'           => $q,
				'acceptedAnswer' => array( '@type' => 'Answer', 'text' => $a ),
			);
		}
		$section = '<section class="actio-faq-section" style="max-width:880px;margin:48px auto;padding:0 20px;">'
			. '<h2 style="font-size:1.6rem;margin-bottom:8px;">Najczęstsze pytania (FAQ)</h2>' . $items . '</section>';

		// 2. znacznik FAQPage (JSON-LD)
		$ld = array(
			'@context'   => 'https://schema.org',
			'@type'      => 'FAQPage',
			'mainEntity' => $entities,
		);
		$jsonld = '<script type="application/ld+json">'
			. wp_json_encode( $ld, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE )
			. '</script>';

		$block = "\n" . $section . "\n" . $jsonld . "\n";

		// wstaw przed stopką (naturalne miejsce); fallback przed </body>
		if ( preg_match( '/<footer[\s>]/i', $html, $m, PREG_OFFSET_CAPTURE ) ) {
			$pos = $m[0][1];
			return substr( $html, 0, $pos ) . $block . substr( $html, $pos );
		}
		return str_ireplace( '</body>', $block . '</body>', $html );
	} );
}, 1 );
