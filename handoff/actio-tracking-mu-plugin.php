<?php
/**
 * Plugin Name: Actio – Tracking Override (Site Kit fix + Meta Pixel)
 * Description: Naprawia problem z Site Kit duplikującym `generate_lead` bez parametrów. Blokuje Site Kit dla tego eventu i firuje własny z pełnym enrichment (lead_type, value, currency, phone_number, link_text, link_location, form_id, email). Plus Meta Pixel base code + 4 standard events (PageView, ViewContent na /uslugi/*, Lead na tel/form, Contact na mailto). Persistuje przez updates (mu-plugins ładują się przed zwykłymi pluginami).
 * Version: 1.6.0 (pierwsza_usluga: token-match całej ścieżki + landingi + blog/is_single + rejestracja; v1.4 email_click+gclid)
 * Author: Tom Lebioda
 * Author URI: https://tomlebioda.com
 *
 * INSTALACJA:
 *   1. Wgraj do /wp-content/mu-plugins/ przez FTP/cPanel
 *   2. Plugin ładuje się automatycznie (mu-plugins = must-use, no activation)
 *   3. Weryfikacja: F12 → Network → kliknij `tel:` link → szukaj POST do google-analytics.com z `lead_type=phone` w params
 *
 * DZIAŁANIE:
 *   - Blokuje Site Kit `_googlesitekit.gtagEvent` dla `generate_lead`
 *   - Wstrzykuje własny listener na phone clicks + CF7 form submits + registration confirm
 *   - Firuje `gtag('event', 'generate_lead', {...})` z pełnym enrichment per URL (Lookup Table 1:1 z GTM)
 *
 * @since 1.0.0
 */

if ( ! defined( 'ABSPATH' ) ) exit;

const ACTIO_GA4_MEASUREMENT_ID = 'G-W864FFJXKQ';
const ACTIO_META_PIXEL_ID      = '1302897478062983';  // ACTIO_Meta (pierwotny)
const ACTIO_META_PIXEL_ID_2    = '1011432604693030';  // pixel konta reklamowego (boost 3G, 29.05)

/**
 * Lookup Table URL → wartość konwersji (PLN). 1:1 z GTM `Lead Value by URL`.
 * Aktualizować równocześnie z GTM jeśli wartości się zmienią.
 */
function actio_lead_value_lookup() {
    return array(
        '/uslugi/sip-trunk/'                                                       => 2400,
        '/uslugi/3cx-phone-system/'                                                => 3000,
        '/uslugi/twoj-3cx-moze-wiecej-odkryj-sip-trunk-z-obsluga-sms/'             => 3000,
        '/uslugi/sms-api/'                                                         => 3600,
        '/uslugi/blyskawiczna-komunikacja-sms-tam-gdzie-sa-twoi-klienci/'          => 3600,
        '/uslugi/efektywna-komunikacja-sms-dla-twojej-firmy/'                      => 3600,
        '/uslugi/sms-przez-voip/'                                                  => 3600,
        '/uslugi/wirtualna-centrala/'                                              => 3300,
        '/uslugi/actio-mobile/'                                                    => 360,
        '/uslugi/wirtualny-numer-komorkowy-voip/'                                  => 360,
        '/uslugi/rozwiazania-sztucznej-inteligencji-ai-w-komunikacji/'             => 3000,
        '/uslugi/ankiety-telefoniczne/'                                            => 3000,
        '/uslugi/nowoczesna-komunikacja-glosowa-z-voip/'                           => 1200,
        '/uslugi/nowoczesna-komunikacja-video-spotkania-twarza-w-twarz-bez-barier/' => 1200,
        '/uslugi/wideokonferencja/'                                                => 1200,
        '/uslugi/telekonferencja/'                                                 => 1200,
        '/uslugi/wirtualny-fax/'                                                   => 600,
        '/uslugi/poczta-glosowa/'                                                  => 600,
        '/uslugi/przekierowanie-polaczen/'                                         => 600,
        '/uslugi/zarzadzanie-nieodebranymi-polaczeniami/'                          => 600,
        '/uslugi/wsparcie-sprzedazy/'                                              => 600,
        '/uslugi/zachowaj-swoj-numer-i-przejdz-do-actio-szybko-bezplatnie-i-bez-przerw-w-dzialaniu/' => 600,
        '/wirtualny-numer-telefonu-dla-firm/'                                      => 1200,
    );
}

const ACTIO_LEAD_VALUE_DEFAULT = 900;

/**
 * Meta Pixel base code → <head> priority 1 (jak najwcześniej, przed innymi skryptami).
 * PageView firuje się natychmiast. Pozostałe eventy (ViewContent/Lead/Contact) w footer IIFE.
 */
add_action( 'wp_head', function() {
    $pixel_id  = ACTIO_META_PIXEL_ID;
    $pixel_id2 = ACTIO_META_PIXEL_ID_2;
    ?>
<!-- Meta Pixel Code (Actio mu-plugin v1.3 – 2 piksele) -->
<script>
!function(f,b,e,v,n,t,s)
{if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '<?php echo esc_js( $pixel_id ); ?>');
fbq('init', '<?php echo esc_js( $pixel_id2 ); ?>');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id=<?php echo esc_attr( $pixel_id ); ?>&ev=PageView&noscript=1"
/></noscript>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id=<?php echo esc_attr( $pixel_id2 ); ?>&ev=PageView&noscript=1"
/></noscript>
<!-- End Meta Pixel Code -->
    <?php
}, 1 );

/**
 * Inject tracking JS przed </body>. Priority 99 = po Site Kit (ten ma priority ~10).
 */
add_action( 'wp_footer', function() {
    $lookup = wp_json_encode( actio_lead_value_lookup(), JSON_UNESCAPED_SLASHES );
    $ga4_id = ACTIO_GA4_MEASUREMENT_ID;
    $default = ACTIO_LEAD_VALUE_DEFAULT;
    $is_blog = is_single() ? 'true' : 'false';
    ?>
<script id="actio-tracking-override">
(function() {
    'use strict';
    var GA4_ID = '<?php echo esc_js( $ga4_id ); ?>';
    var LEAD_VALUE_MAP = <?php echo $lookup; ?>;
    var DEFAULT_VALUE = <?php echo (int) $default; ?>;
    var ACTIO_IS_BLOG = <?php echo $is_blog; ?>;

    function leadValueByUrl(path) {
        // Strip trailing slash to be tolerant, then try exact match
        if (LEAD_VALUE_MAP[path] !== undefined) return LEAD_VALUE_MAP[path];
        var alt = path.endsWith('/') ? path.slice(0, -1) : path + '/';
        if (LEAD_VALUE_MAP[alt] !== undefined) return LEAD_VALUE_MAP[alt];
        return DEFAULT_VALUE;
    }

    // ─── gclid capture (Google Ads click ID) ────────────────────────────
    // gclid jest w URL tylko na stronie wejścia → łapiemy do cookie 90 dni
    // (okno konwersji Ads), żeby był dostępny przy kliknięciu maila kilka stron później.
    function actioGetParam(name) {
        var m = window.location.search.match(new RegExp('[?&]' + name + '=([^&]+)'));
        return m ? decodeURIComponent(m[1]) : '';
    }
    function actioSetCookie(name, value, days) {
        var d = new Date(); d.setTime(d.getTime() + days * 86400000);
        document.cookie = name + '=' + encodeURIComponent(value) + ';expires=' + d.toUTCString() + ';path=/;SameSite=Lax';
    }
    function actioGetCookie(name) {
        var m = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]+)'));
        return m ? decodeURIComponent(m[2]) : '';
    }
    // Capture na wejściu (jeśli click ID w URL)
    ['gclid', 'gbraid', 'wbraid'].forEach(function(k) {
        var v = actioGetParam(k);
        if (v) actioSetCookie('actio_' + k, v, 90);
    });
    // Zwraca {gclid,gbraid,wbraid} z naszego cookie; fallback na _gcl_aw (Google linker, format GCL.<ts>.<gclid>)
    function actioClickIds() {
        var out = {
            gclid: actioGetCookie('actio_gclid'),
            gbraid: actioGetCookie('actio_gbraid'),
            wbraid: actioGetCookie('actio_wbraid'),
        };
        if (!out.gclid) {
            var gcl = actioGetCookie('_gcl_aw');
            if (gcl) { var p = gcl.split('.'); if (p.length >= 3) out.gclid = p.slice(2).join('.'); }
        }
        return out;
    }

    function fireLead(params) {
        var leadValue = leadValueByUrl(window.location.pathname);
        // Meta Pixel Lead (parallel z GA4 generate_lead) – swallow jeśli fbq nie ready
        try {
            if (typeof window.fbq === 'function') {
                window.fbq('track', 'Lead', {
                    value: leadValue,
                    currency: 'PLN',
                    content_category: params.lead_type || 'unknown',
                    content_name: window.location.pathname,
                });
            }
        } catch (e) { /* swallow */ }

        if (typeof window.gtag !== 'function') {
            // Fallback – push do dataLayer (GTM przejmie jeśli załadowany)
            window.dataLayer = window.dataLayer || [];
            window.dataLayer.push(Object.assign({ event: 'generate_lead' }, params));
            return;
        }
        var defaultParams = {
            value: leadValue,
            currency: 'PLN',
            actio_tracker: 'mu-plugin-v1',  // żeby odróżnić od Site Kit (event_source: site-kit)
            send_to: GA4_ID,
        };
        var merged = Object.assign(defaultParams, params);
        try { window.gtag('event', 'generate_lead', merged); } catch (e) { /* swallow */ }
    }

    // ─── Total block: WSZYSTKIE generate_lead bez `actio_tracker` ──────
    // gtag() level monkeypatch – łapie WSZYSTKIE ścieżki (Site Kit gtagEvent,
    // events providers WPForms/CF7, direct gtag calls, każde inne).
    // Pozostawiamy tylko nasz mu-plugin event (z markerem `actio_tracker: 'mu-plugin-v1'`).
    function installGtagBlock() {
        if (typeof window.gtag !== 'function') return false;
        if (window._actio_gtag_patched) return true;
        var origGtag = window.gtag;
        window.gtag = function() {
            // gtag('event', 'generate_lead', {...params})
            if (arguments[0] === 'event' && arguments[1] === 'generate_lead') {
                var params = arguments[2] || {};
                if (params.actio_tracker !== 'mu-plugin-v1') {
                    // Block – nie nasz event, ignoruj
                    if (window._actio_debug) {
                        console.warn('[Actio Tracking] BLOCKED foreign generate_lead:', params);
                    }
                    return;
                }
            }
            return origGtag.apply(this, arguments);
        };
        window._actio_gtag_patched = true;
        return true;
    }
    // Aplikuj natychmiast + retry (gtag może być dopiero ładowane)
    if (!installGtagBlock()) {
        var gtagAttempts = 0;
        var gtagIv = setInterval(function() {
            gtagAttempts++;
            if (installGtagBlock() || gtagAttempts > 100) clearInterval(gtagIv);  // 10 sek max
        }, 100);
    }

    // Plus: dataLayer.push level block (GTM-driven events)
    function installDataLayerBlock() {
        if (!window.dataLayer || window._actio_dl_patched) return false;
        var origPush = window.dataLayer.push.bind(window.dataLayer);
        window.dataLayer.push = function() {
            for (var i = 0; i < arguments.length; i++) {
                var ev = arguments[i];
                // GTM-style: { event: 'generate_lead', ... }
                if (ev && ev.event === 'generate_lead' && ev.actio_tracker !== 'mu-plugin-v1') {
                    if (window._actio_debug) {
                        console.warn('[Actio Tracking] BLOCKED foreign dataLayer generate_lead:', ev);
                    }
                    return;
                }
                // gtag-style w dataLayer: [0]='event', [1]='generate_lead', [2]={...}
                if (Array.isArray(ev) && ev[0] === 'event' && ev[1] === 'generate_lead') {
                    var p = ev[2] || {};
                    if (p.actio_tracker !== 'mu-plugin-v1') {
                        if (window._actio_debug) {
                            console.warn('[Actio Tracking] BLOCKED foreign dataLayer array event:', ev);
                        }
                        return;
                    }
                }
            }
            return origPush.apply(this, arguments);
        };
        window._actio_dl_patched = true;
        return true;
    }
    installDataLayerBlock();

    // Backwards-compat: zostaw Site Kit specific block (część eventów może iść tylko tędy)
    function blockSiteKit() {
        if (window._googlesitekit && window._googlesitekit.gtagEvent) {
            var original = window._googlesitekit.gtagEvent;
            window._googlesitekit.gtagEvent = function(name, data) {
                if (name === 'generate_lead') return; // Block
                return original.call(this, name, data);
            };
            return true;
        }
        return false;
    }
    if (!blockSiteKit()) {
        var skAttempts = 0;
        var skIv = setInterval(function() {
            skAttempts++;
            if (blockSiteKit() || skAttempts > 50) clearInterval(skIv);
        }, 100);
    }

    // ─── Meta Pixel: ViewContent na /uslugi/* (rich kontekst dla optimization) ──
    try {
        if (typeof window.fbq === 'function' && window.location.pathname.indexOf('/uslugi/') === 0) {
            window.fbq('track', 'ViewContent', {
                content_category: 'usluga',
                content_name: document.title || window.location.pathname,
                content_ids: [window.location.pathname],
                value: leadValueByUrl(window.location.pathname),
                currency: 'PLN',
            });
        }
    } catch (e) { /* swallow */ }

    // ─── User property: pierwsza_usluga (pierwsza usługa, którą user się zainteresował) ──
    // Ustawiane RAZ (localStorage), re-assert na każdej stronie żeby user property trzymało się usera w GA4.
    function actioServiceCategory(path) {
        path = (path || '').toLowerCase();
        // Token-match na CAŁEJ ścieżce (usługi + landingi + blog). Pierwszy trafiony wygrywa – kolejność ważna przy nakładaniu.
        var tokens = [
            ['rejestracja', 'rejestracja'],
            ['likwidacja-sieci-3g', '3g'],
            ['sip-trunk', 'sip-trunk'],   // przed 3cx: strona "twoj-3cx...odkryj-sip-trunk" = oferta sip-trunk
            ['isdn', 'sip-trunk'],
            ['3cx', '3cx'],
            ['komorkow', 'actio-mobile'],
            ['actio-mobile', 'actio-mobile'],
            ['cennik-mobile', 'actio-mobile'],
            ['sms', 'sms-api'],
            ['centrala', 'wirtualna-centrala'],
            ['sztucznej-inteligencji', 'ai'],
            ['voicebot', 'ai'],
            ['ankiety-telefoniczne', 'ai'],
            ['numer', 'wirtualny-numer'],
            ['fax', 'voip'],
            ['przekierowan', 'voip'],
            ['poczta-glosowa', 'voip'],
            ['wideokonf', 'voip'],
            ['telekonf', 'voip'],
            ['wsparcie-sprzedazy', 'voip'],
            ['glosow', 'voip'],
            ['voip', 'voip']
        ];
        for (var i = 0; i < tokens.length; i++) {
            if (path.indexOf(tokens[i][0]) !== -1) return tokens[i][1];
        }
        if (path.indexOf('/uslugi/') === 0) return 'voip';  // każda usługa bez trafienia = generyczny voip
        if (typeof ACTIO_IS_BLOG !== 'undefined' && ACTIO_IS_BLOG) return 'blog';  // wpis blogowy bez produktu
        return null;  // home/kontakt/cennik/legal/ostickets = brak kategorii
    }
    function actioSetFirstService() {
        try {
            var svc = localStorage.getItem('actio_first_service');
            if (!svc) {
                svc = actioServiceCategory(window.location.pathname);
                if (svc) localStorage.setItem('actio_first_service', svc);
            }
            if (!svc) return true;  // brak usługi na tej stronie – nie ponawiaj
            if (typeof window.gtag === 'function') {
                window.gtag('set', 'user_properties', { pierwsza_usluga: svc });
                return true;
            }
            return false;  // mamy svc, ale gtag jeszcze nie gotowy – ponów
        } catch (e) { return true; }
    }
    if (!actioSetFirstService()) {
        var fsAttempts = 0;
        var fsIv = setInterval(function() {
            fsAttempts++;
            if (actioSetFirstService() || fsAttempts > 50) clearInterval(fsIv);  // 5 sek max
        }, 100);
    }

    // ─── Listener: mailto: clicks → Meta Pixel Contact + GA4 email_click ──
    document.addEventListener('click', function(e) {
        var link = e.target.closest && e.target.closest('a[href^="mailto:"]');
        if (!link) return;
        var href = link.getAttribute('href') || '';
        var email = href.replace(/^mailto:/i, '').split('?')[0];
        var text = (link.innerText || link.textContent || '').trim().substring(0, 100);
        // Meta Pixel Contact (do obu pikseli)
        try {
            if (typeof window.fbq === 'function') {
                window.fbq('track', 'Contact', {
                    content_category: 'email',
                    content_name: email,
                });
            }
        } catch (err) { /* swallow */ }
        // GA4 email_click – OSOBNY event (nie generate_lead), z gclid dla atrybucji Ads
        try {
            if (typeof window.gtag === 'function') {
                var ids = actioClickIds();
                window.gtag('event', 'email_click', {
                    email_address: email,
                    link_text: text,
                    link_location: window.location.pathname,
                    lead_type: 'email',
                    gclid: ids.gclid || undefined,
                    gbraid: ids.gbraid || undefined,
                    wbraid: ids.wbraid || undefined,
                    send_to: GA4_ID,
                });
            }
        } catch (err) { /* swallow */ }
    }, true);

    // ─── Normalizacja numeru do E.164 (+48 dla PL) ─────────────────────
    // Fix: linki tel: na stronie bywają bez prefiksu (np. tel:616489000) → GA4 pokazywał błędne "+616489000".
    function actioNormalizePhone(raw) {
        var p = (raw || '').replace(/^tel:/i, '').replace(/[^\d+]/g, '');  // zostaw cyfry i +
        if (p.indexOf('00') === 0) p = '+' + p.slice(2);                   // 0048... -> +48...
        if (p.charAt(0) === '+') return p;                                  // ma już kod kraju
        var d = p.replace(/\D/g, '');
        if (d.length === 9) return '+48' + d;                               // PL lokalny 9-cyfrowy (616489000)
        if (d.length === 11 && d.indexOf('48') === 0) return '+' + d;       // 48XXXXXXXXX
        return d ? '+' + d : '';
    }

    // ─── Listener: phone clicks `tel:*` ─────────────────────────────────
    document.addEventListener('click', function(e) {
        var link = e.target.closest && e.target.closest('a[href^="tel:"]');
        if (!link) return;
        var href = link.getAttribute('href') || '';
        var phone = actioNormalizePhone(href);
        var text = (link.innerText || link.textContent || '').trim().substring(0, 100);
        fireLead({
            lead_type: 'phone',
            phone_number: phone,
            link_text: text,
            link_location: window.location.pathname,
        });
    }, true);

    // ─── Listener: CF7 form submit (event from CF7 JS) ─────────────────
    document.addEventListener('wpcf7mailsent', function(e) {
        var form = e.target;
        if (!form || !form.querySelector) return;
        var emailInput = form.querySelector('input[type="email"], input[name*="mail"]');
        var phoneInput = form.querySelector('input[name*="tel"], input[name*="phone"], input[name*="telefon"]');
        fireLead({
            lead_type: 'form',
            form_id: String((e.detail && e.detail.contactFormId) || ''),
            form_location: window.location.pathname,
            email: emailInput ? (emailInput.value || '') : '',
            phone_number: phoneInput ? actioNormalizePhone(phoneInput.value || '') : '',
        });
    }, true);

    // ─── (Optional) Diagnostic w konsoli devel ─────────────────────────
    if (window.location.search.indexOf('actio_debug=1') !== -1) {
        window._actio_debug = true;
        var _ids = actioClickIds();
        console.log('[Actio Tracking Override v1.4] active. GA4=' + GA4_ID + ' + Meta Piksele=<?php echo esc_js( ACTIO_META_PIXEL_ID ); ?>,<?php echo esc_js( ACTIO_META_PIXEL_ID_2 ); ?>. LookupTable=' + Object.keys(LEAD_VALUE_MAP).length + ' entries. Events: PageView, ViewContent (/uslugi/*), Lead (tel/CF7), Contact+email_click (mailto:). gclid=' + (_ids.gclid || '(brak)') + '. Gtag/dataLayer/SiteKit block – 3 lines.');
    }
})();
</script>
    <?php
}, 99 );  // Priority 99 = bardzo późno, po wszystkich innych skryptach
