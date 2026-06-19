<?php
/**
 * Plugin Name: Actio – FAQ + tabele + blok „Dlaczego Actio" na stronach usług (GEO/AI-SEO, taski A2 + A6 + A7)
 * Description: Dodaje na money-stronach usług (a) widoczny blok FAQ + schema.org FAQPage, (b) tabele porównawcze oraz (c) blok „Dlaczego Actio" (zebrane fakty z liczbami). FAQ na: /uslugi/sip-trunk, /uslugi/3cx-phone-system, /uslugi/wirtualna-centrala, /uslugi/sms-api. Tabele na: /uslugi/sip-trunk, /uslugi/3cx-phone-system, /uslugi/wirtualny-numer-komorkowy-voip. Blok „Dlaczego Actio" na 5 stronach usług + /o-nas. Cel: dać AI (ChatGPT/Perplexity/Google AI) i wyszukiwarkom gotowe, cytowalne fakty, porównania i Q&A → podnieść AI Share of Voice. NIEZALEŻNY od actio-schema-mu-plugin.php – zero kolizji i zero ryzyka nadpisania przez autopublisher. Output-buffer (template_redirect), scoped do slugów, idempotentny, odwracalny (usunięcie pliku = stan sprzed). Tabele = porównania kategorii (nasza technologia vs tradycyjny/typowy model), bez nazywania konkurentów.
 * Version: 1.2.0
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

function actio_uslugi_tabele_data() {
	return array(
		'/uslugi/sip-trunk' => array(
			'title' => 'SIP Trunk vs tradycyjne łącza ISDN / PSTN',
			'cols'  => array( 'Cecha', 'SIP Trunk (Actio)', 'Tradycyjne ISDN / PSTN' ),
			'rows'  => array(
				array( 'Technologia', 'Głos przez internet (VoIP/SIP)', 'Fizyczne łącza miedziane' ),
				array( 'Koszt połączeń i utrzymania', 'Niższy – bez dzierżawy linii', 'Wyższy – dzierżawa + wyższe stawki' ),
				array( 'Liczba kanałów (połączeń równoległych)', 'Skalowalna w dowolnym momencie', 'Ograniczona fizycznie' ),
				array( 'Sprzęt', 'Wystarczy centrala z obsługą SIP + internet', 'Wymaga linii i osprzętu operatora' ),
				array( 'Zachowanie numeru (MNP)', 'Tak – operator zarejestrowany w UKE', 'Zależne od operatora' ),
				array( 'Obsługa SMS na numerze firmowym', 'Tak', 'Zwykle brak' ),
				array( 'Czas wdrożenia', 'Zwykle godziny', 'Dni – tygodnie' ),
				array( 'Dostępność (SLA)', '99,9%', 'Zależne od infrastruktury' ),
			),
		),
		'/uslugi/3cx-phone-system' => array(
			'title' => '3CX z Actio vs klasyczny model licencyjny „per-user”',
			'cols'  => array( 'Cecha', '3CX z Actio', 'Klasyczny model per-user' ),
			'rows'  => array(
				array( 'Model licencji', 'Wg liczby jednoczesnych połączeń', 'Opłata za każdego użytkownika' ),
				array( 'Koszt przy rosnącym zespole', 'Stały – nie rośnie z liczbą pracowników', 'Rośnie z każdym kolejnym użytkownikiem' ),
				array( 'Praca zdalna i mobilna', 'Aplikacja na telefon i komputer w cenie', 'Często wymaga dodatkowego sprzętu' ),
				array( 'Wideokonferencje i czat', 'Wbudowane', 'Zwykle dopłata lub brak' ),
				array( 'Integracje z CRM', 'M365, Salesforce, HubSpot, Zendesk i inne', 'Ograniczone' ),
				array( 'Numery i SIP Trunk', 'Polskie numery +48 przez Actio (z MNP)', 'Zależne od operatora' ),
				array( 'Wsparcie', 'Polski zespół, partner 3CX od 2009 r.', 'Zależne od dostawcy' ),
			),
		),
		'/uslugi/wirtualny-numer-komorkowy-voip' => array(
			'title' => 'Wirtualny numer komórkowy VoIP vs zwykła karta SIM / GSM',
			'cols'  => array( 'Cecha', 'Wirtualny numer komórkowy (Actio)', 'Zwykła karta SIM / GSM' ),
			'rows'  => array(
				array( 'Karta SIM w telefonie', 'Niepotrzebna – numer działa przez internet (SIP/VoIP)', 'Wymagana fizyczna karta SIM' ),
				array( 'Liczba urządzeń na jednym numerze', 'Wiele (telefon, komputer, aplikacja)', 'Jedno urządzenie z kartą' ),
				array( 'Praca zdalna / wiele lokalizacji', 'Tak – z dowolnego miejsca z internetem', 'Ograniczona zasięgiem sieci GSM' ),
				array( 'Koszt', 'Do 40% taniej', 'Standardowe stawki komórkowe' ),
				array( 'Integracja z centralą / CRM', 'Tak (SIP, 3CX, API)', 'Brak' ),
				array( 'Zachowanie numeru (MNP)', 'Tak – operator zarejestrowany w UKE', 'Tak, zależnie od operatora' ),
				array( 'Numer komórkowy bez umowy GSM', 'Tak', 'Nie' ),
			),
		),
	);
}

function actio_uslugi_why_facts() {
	// Blok „Dlaczego Actio" – te same fakty na wszystkich stronach (kategoria: zaufanie/E-E-A-T).
	// Bez twardego „wieku firmy" (A5 nierozstrzygnięty) – używamy zweryfikowanego „partner 3CX od 2009".
	return array(
		array( '99,9% dostępności (SLA)', 'Redundantna infrastruktura operatora i kodeki HD Voice.' ),
		array( 'Operator zarejestrowany w UKE', 'Z prawem przenoszenia numerów (MNP) – zachowujesz dotychczasowy numer.' ),
		array( 'Klienci klasy PGE', 'Zaufały nam firmy z sektora energetycznego, kolejowego, medycznego i publicznego.' ),
		array( 'Bez opłat za użytkownika', 'W 3CX płacisz za jednoczesne połączenia, nie za każdego pracownika.' ),
		array( 'Integracje z CRM', 'Microsoft 365, Salesforce, HubSpot, Zendesk i inne popularne systemy.' ),
		array( 'Polskie wsparcie techniczne', 'Własny zespół mówiący po polsku; partner 3CX od 2009 r.' ),
	);
}

function actio_uslugi_why_slugs() {
	return array(
		'/uslugi/sip-trunk',
		'/uslugi/3cx-phone-system',
		'/uslugi/wirtualna-centrala',
		'/uslugi/sms-api',
		'/uslugi/wirtualny-numer-komorkowy-voip',
		'/o-nas',
	);
}

add_action( 'template_redirect', function () {
	$path  = rtrim( strtok( isset( $_SERVER['REQUEST_URI'] ) ? $_SERVER['REQUEST_URI'] : '', '?' ), '/' );
	$faqs  = actio_uslugi_faq_data();
	$tabs  = actio_uslugi_tabele_data();
	$faq   = isset( $faqs[ $path ] ) ? $faqs[ $path ] : null;
	$table = isset( $tabs[ $path ] ) ? $tabs[ $path ] : null;
	$why   = in_array( $path, actio_uslugi_why_slugs(), true );
	if ( $faq === null && $table === null && ! $why ) {
		return;
	}

	ob_start( function ( $html ) use ( $faq, $table, $why ) {
		if ( ! is_string( $html ) || stripos( $html, '</body>' ) === false ) {
			return $html;
		}
		if ( strpos( $html, 'actio-faq-section' ) !== false || strpos( $html, 'actio-tabela-section' ) !== false || strpos( $html, 'actio-why-section' ) !== false ) {
			return $html; // idempotentny
		}

		// 0. blok „Dlaczego Actio" (zebrane fakty z liczbami) – na górze wstrzykiwanej sekcji
		$whyblock = '';
		if ( $why ) {
			$cards = '';
			foreach ( actio_uslugi_why_facts() as $f ) {
				$cards .= '<div style="flex:1 1 240px;min-width:220px;border:1px solid #e5e7eb;border-radius:8px;padding:18px 20px;background:#ffffff;">'
					. '<div style="font-size:1.1rem;font-weight:700;color:#ee7f17;margin-bottom:6px;line-height:1.3;">' . esc_html( $f[0] ) . '</div>'
					. '<div style="font-size:0.95rem;color:#444444;line-height:1.55;">' . esc_html( $f[1] ) . '</div></div>';
			}
			$whyblock = '<section class="actio-why-section" style="max-width:920px;margin:48px auto;padding:0 20px;">'
				. '<h2 style="font-size:1.6rem;margin-bottom:18px;">Dlaczego Actio?</h2>'
				. '<div style="display:flex;flex-wrap:wrap;gap:14px;">' . $cards . '</div></section>';
		}

		// 1. tabela porównawcza (jeśli zdefiniowana dla slugu) – nad FAQ
		$tableblock = '';
		if ( $table ) {
			$thead = '<tr>';
			foreach ( $table['cols'] as $i => $c ) {
				$bg = ( $i === 1 ) ? 'background:#ee7f17;color:#ffffff;' : 'background:#f3f4f6;color:#1d2233;';
				$thead .= '<th style="text-align:left;padding:12px 14px;font-size:0.98rem;border:1px solid #e5e7eb;' . $bg . '">' . esc_html( $c ) . '</th>';
			}
			$thead .= '</tr>';
			$tbody = '';
			foreach ( $table['rows'] as $r ) {
				$tbody .= '<tr>';
				foreach ( $r as $i => $cell ) {
					$style = 'padding:11px 14px;border:1px solid #e5e7eb;line-height:1.5;font-size:0.95rem;vertical-align:top;';
					if ( $i === 0 ) {
						$style .= 'font-weight:600;color:#1d2233;background:#fafbfc;';
					} elseif ( $i === 1 ) {
						$style .= 'background:#fff8ee;color:#1d2233;';
					} else {
						$style .= 'color:#555555;';
					}
					$tbody .= '<td style="' . $style . '">' . esc_html( $cell ) . '</td>';
				}
				$tbody .= '</tr>';
			}
			$tableblock = '<section class="actio-tabela-section" style="max-width:880px;margin:48px auto;padding:0 20px;">'
				. '<h2 style="font-size:1.6rem;margin-bottom:16px;">' . esc_html( $table['title'] ) . '</h2>'
				. '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;">'
				. '<thead>' . $thead . '</thead><tbody>' . $tbody . '</tbody></table></div></section>';
		}

		// 2. widoczny blok FAQ (accordion) + znacznik FAQPage (JSON-LD)
		$faqblock = '';
		if ( $faq ) {
			$items    = '';
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
			$ld     = array(
				'@context'   => 'https://schema.org',
				'@type'      => 'FAQPage',
				'mainEntity' => $entities,
			);
			$jsonld = '<script type="application/ld+json">'
				. wp_json_encode( $ld, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE )
				. '</script>';
			$faqblock = $section . "\n" . $jsonld;
		}

		$block = "\n" . $whyblock . "\n" . $tableblock . "\n" . $faqblock . "\n";

		// Wstaw NAD globalnym blokiem CTA "Rozwijasz komunikację w firmie?".
		// Kotwica: ostatni kontener Elementora e-parent (sekcja top-level) przed tekstem CTA.
		// Globalny blok CTA występuje w 2 wariantach tekstu zależnie od strony:
		// "Rozwijasz komunikację w firmie?" (strony usług) i "Czy poprawiacie komunikację…" (/o-nas itp.).
		// Bierzemy najwcześniejsze wystąpienie któregokolwiek (ASCII bez diakrytyki = offset bajtowy).
		$insert_at = false;
		$cta       = false;
		foreach ( array( 'Rozwijasz komunikac', 'poprawiacie komunikac' ) as $needle ) {
			$p = stripos( $html, $needle );
			if ( $p !== false && ( $cta === false || $p < $cta ) ) {
				$cta = $p;
			}
		}
		if ( $cta !== false
			&& preg_match_all( '/<div\s+class="[^"]*\be-parent\b[^"]*"[^>]*>/i', substr( $html, 0, $cta ), $mm, PREG_OFFSET_CAPTURE ) ) {
			$insert_at = $mm[0][ count( $mm[0] ) - 1 ][1];
		}
		// Fallback: przed stopką, ostatecznie przed </body>.
		if ( $insert_at === false && preg_match( '/<footer[\s>]/i', $html, $m, PREG_OFFSET_CAPTURE ) ) {
			$insert_at = $m[0][1];
		}
		if ( $insert_at === false ) {
			return str_ireplace( '</body>', $block . '</body>', $html );
		}
		return substr( $html, 0, $insert_at ) . $block . substr( $html, $insert_at );
	} );
}, 1 );
