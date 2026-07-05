"""Generator postów social (FB + IG) – matryca FILAR×FORMAT×BRANŻA + anty-powtórka.

Cel: dopełnić kalendarz FB do 2 postów/dzień (09:00 + 17:00) do końca czerwca 2026
oraz zbudować pełny harmonogram IG (50 postów), bez powtarzania tematów.

- build_unified_plan(): deterministyczny przydział (pillar, format, industry, intent)
  na 50 slotów (25 dni × 2), z regułami rotacji. FB tworzony tylko dla slotów `fb_needed`
  (14 dni mają już post FB → dla nich FB tylko PM; IG dostaje pełne 50).
- generate(): LLM copy (Sonnet 4.6) + grafika (Nano Banana, 4:5 wspólna dla FB+IG) → DB.
- commit_schedule(): FB → natywny scheduling; IG → status 'queued' (cron dopublikuje).

Anty-powtórka: (1) matryca = unikalna para (pillar,format) w całym planie + brak tego
samego filaru dwa dni z rzędu + 2 różne filary/dzień; (2) semantyczna – _is_topic_repeat
na 'angle' vs ostatnie 7 postów kanału.

Uruchamiać na Mikrusie (grafiki IG muszą leżeć tam, gdzie webhook je serwuje).
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib

import autopublish as ap
import db
import social_publish as sp
from chainlit_image_gen import generate_social_image

DB = sp.db_path

# === MATRYCA ===

PILLARS = {
    "sip_trunk":          {"label": "SIP Trunk", "url": "https://actio.pl/uslugi/sip-trunk/", "utm": "sip_trunk", "general": False,
                            "desc": "Elastyczne kanały głosowe przez internet dla istniejącej centrali; zamiennik drogich traktów ISDN, płatność wg realnego ruchu."},
    "3cx":                {"label": "Centrala 3CX", "url": "https://actio.pl/uslugi/3cx-phone-system/", "utm": "3cx", "general": False,
                            "desc": "Centrala w chmurze: kolejki, IVR, nagrywanie, aplikacja na telefon i komputer, integracja z CRM, praca hybrydowa."},
    "sms_api":            {"label": "SMS API", "url": "https://actio.pl/uslugi/sms-api/", "utm": "sms_api", "general": False,
                            "desc": "Bramka SMS REST do CRM/sklepu/aplikacji: automatyczne powiadomienia, kody, potwierdzenia, przypomnienia."},
    "sms_voip":           {"label": "SMS przez VoIP", "url": "https://actio.pl/uslugi/sms-przez-voip/", "utm": "sms_voip", "general": False,
                            "desc": "Wysyłka SMS z firmowego numeru VoIP (tego samego, z którego dzwonisz); wysoki odczyt ~90%."},
    "wirtualna_centrala": {"label": "Wirtualna Centrala", "url": "https://actio.pl/uslugi/wirtualna-centrala/", "utm": "wirtualna_centrala", "general": False,
                            "desc": "Jeden numer dla całej firmy: inteligentne przekierowania, kolejki, statystyki rozmów, wiele oddziałów bez działu IT."},
    "actio_mobile":       {"label": "Actio Mobile", "url": "https://actio.pl/uslugi/actio-mobile/", "utm": "actio_mobile", "general": False,
                            "desc": "Wirtualny numer komórkowy bez karty SIM, na telefonie/komputerze/tablecie; mobilność pracowników."},
    "ai_voicebot":        {"label": "AI w komunikacji", "url": "https://actio.pl/uslugi/rozwiazania-sztucznej-inteligencji-ai-w-komunikacji/", "utm": "ai", "general": False,
                            "desc": "Voicebot odbiera i kieruje proste sprawy, automatyczna transkrypcja i streszczenia rozmów, mniej powtarzalnej pracy."},
    "wirtualny_numer":    {"label": "Wirtualny numer", "url": "https://actio.pl/wirtualny-numer-telefonu-dla-firm/", "utm": "wirtualny_numer", "general": False,
                            "desc": "Profesjonalny numer (lokalny lub komórkowy) bez nowej linii i sprzętu; przekierowania, poczta głosowa, każde urządzenie."},
    "portacja_3g":        {"label": "Likwidacja 3G / portacja numeru", "url": "https://actio.pl/likwidacja-sieci-3g-zachowaj-numer-komorkowy-dzieki-voip/", "utm": "likwidacja_3g", "general": False,
                            "desc": "Operatorzy wyłączają 3G; przeniesienie numeru do VoIP Actio bez zmian, połączenia i SMS przez internet."},
    "voip_edukacja":      {"label": "VoIP – edukacja", "url": "https://actio.pl/uslugi/nowoczesna-komunikacja-glosowa-z-voip/", "utm": "czym_jest_voip", "general": True,
                            "desc": "Telefonia przez internet zamiast tradycyjnej linii: tańsze połączenia, praca z dowolnego miejsca, łatwa rozbudowa."},
    "cennik":             {"label": "Cennik / elastyczność", "url": "https://actio.pl/cennik/", "utm": "bez_abonamentu", "general": True,
                            "desc": "Elastyczne rozliczenie – płacisz za realne użycie, bez sztywnych abonamentów; telefonia skaluje się z firmą."},
    "wirtualny_fax":      {"label": "Wirtualny Fax", "url": "https://actio.pl/uslugi/wirtualny-fax/", "utm": "wirtualny_fax", "general": False,
                            "desc": "Fax przez internet: wysyłka i odbiór jako e-mail/PDF, archiwizacja cyfrowa, bez urządzenia faksowego."},
    "poczta_glosowa":     {"label": "Poczta głosowa", "url": "https://actio.pl/uslugi/poczta-glosowa/", "utm": "poczta_glosowa", "general": False,
                            "desc": "Wiadomości głosowe dostępne wszędzie, powiadomienia, voicemail-to-email; żaden telefon nie ginie."},
    "przekierowania":     {"label": "Przekierowanie połączeń", "url": "https://actio.pl/uslugi/przekierowanie-polaczen/", "utm": "przekierowania", "general": False,
                            "desc": "Reguły przekierowań (zajęty/brak odpowiedzi/godziny pracy); połączenie zawsze trafia tam, gdzie trzeba."},
    "ankiety_ivr":        {"label": "Ankiety telefoniczne (IVR/CATI)", "url": "https://actio.pl/uslugi/ankiety-telefoniczne/", "utm": "ankiety_ivr", "general": False,
                            "desc": "Automatyczne ankiety i badania telefoniczne, IVR, nagrywanie odpowiedzi, raporty; bez angażowania konsultantów."},
    "wideokonferencje":   {"label": "Wideokonferencje", "url": "https://actio.pl/uslugi/wideokonferencja/", "utm": "wideokonferencje", "general": False,
                            "desc": "Telekonferencje i wideospotkania online dla zespołu i klientów, bez instalacji, w jednym ekosystemie."},
    "heritage_trust":     {"label": "Heritage / zaufanie", "url": "https://actio.pl/", "utm": "heritage", "general": True,
                            "desc": "Actio = marka SYNTELL S.A., operator z Poznania od 1996; klienci m.in. grupa PGE, Koleje Wielkopolskie; polskie wsparcie."},
    "kontakt_cta":        {"label": "Kontakt / wycena", "url": "https://actio.pl/kontakt/", "utm": "wycena", "general": True,
                            "desc": "Bezpłatna wycena w 24h, doradztwo bez żargonu, dobór najprostszego rozwiązania telefonii dla firmy."},
}

FORMATS = {
    "problem_solution": "Zacznij od konkretnego bólu firmy, potem pokaż jak usługa go rozwiązuje.",
    "lista_korzysci":   "Krótki wstęp + 3 konkretne korzyści jako lista z ✅. Zwięźle.",
    "mit_vs_fakt":      "Obal mit lub porównaj z tradycyjnym/starym podejściem (przed → po).",
    "case_branzowy":    "Mini-scenariusz: jak firma z konkretnej branży realnie używa tej usługi.",
    "edukacja_pojecie": "Wyjaśnij pojęcie albo jak to działa – prosto, bez technicznego żargonu.",
    "cta_oferta":       "Mocne, konkretne CTA (wycena/rejestracja/kontakt). Krótko, do rzeczy.",
}
AM_FORMATS = ["edukacja_pojecie", "lista_korzysci", "mit_vs_fakt", "problem_solution"]
PM_FORMATS = ["cta_oferta", "case_branzowy", "problem_solution"]

INDUSTRIES = {
    "ecommerce":          "sklep internetowy / e-commerce",
    "kancelaria_prawna":  "kancelaria prawna",
    "przychodnia_med":    "przychodnia / placówka medyczna",
    "biuro_rachunkowe":   "biuro rachunkowe",
    "logistyka_transport": "firma logistyczna / transportowa",
    "hotel_horeca":       "hotel / gastronomia (HoReCa)",
    "agencja_marketingowa": "agencja marketingowa",
    "contact_center":     "contact center / biuro obsługi klienta",
}
_IND_KEYS = list(INDUSTRIES)

# Priorytet doboru (niedoreprezentowane filary pierwsze – tiebreak przy równym count)
_PILLAR_PRIORITY = [
    "wirtualny_fax", "poczta_glosowa", "przekierowania", "ankiety_ivr", "wideokonferencje",
    "portacja_3g", "sip_trunk", "3cx", "sms_api", "sms_voip", "wirtualna_centrala",
    "actio_mobile", "ai_voicebot", "wirtualny_numer", "cennik", "voip_edukacja",
    "heritage_trust", "kontakt_cta",
]

# Istniejące posty FB (date → pillar slotu AM) – dla nich AM nie tworzy nowego FB, tylko PM.
# Lipiec 2026: brak ręcznego kalendarza AM → puste, więc AM+PM = pełne FB+IG (2 posty/dzień jak czerwiec).
EXISTING = {}

WINDOW_START = datetime.date(2026, 7, 6)
WINDOW_END = datetime.date(2026, 7, 31)
AM_TIME, PM_TIME = "09:00", "17:00"


def _window_dates() -> list[str]:
    out, d = [], WINDOW_START
    while d <= WINDOW_END:
        out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


# === PRZYDZIAŁ SLOTÓW ===

def build_unified_plan() -> list[dict]:
    """Zwróć 50 slotów (25 dni × AM+PM) z (pillar, format, industry, intent, fb_needed)."""
    used_pairs: set[tuple] = set()
    pillar_count = {p: 0 for p in PILLARS}
    for pil in EXISTING.values():
        pillar_count[pil] += 1

    def pick_format(pillar: str, allowed: list[str]) -> str | None:
        for fmt in allowed:
            if (pillar, fmt) not in used_pairs:
                return fmt
        return None

    def pick_pillar(intent_formats: list[str], blocked: set[str]) -> tuple[str, str] | None:
        ranked = sorted(PILLARS, key=lambda p: (pillar_count[p], _PILLAR_PRIORITY.index(p)))
        for pil in ranked:
            if pil in blocked:
                continue
            fmt = pick_format(pil, intent_formats)
            if fmt:
                return pil, fmt
        return None

    plan: list[dict] = []
    prev_pillars: set[str] = set()
    prev_inds: set[str] = set()
    ind_cursor = 0

    for date in _window_dates():
        today_pillars: set[str] = set()
        today_inds: set[str] = set()
        existing_pillar = EXISTING.get(date)
        # look-ahead: jutrzejszy STAŁY (istniejący) filar – nie wolno go dziś użyć (kolizja sąsiednich dni)
        nxt = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        next_fixed = {EXISTING[nxt]} if nxt in EXISTING else set()
        day_slots = []

        # --- AM slot ---
        if existing_pillar:
            fmt = pick_format(existing_pillar, AM_FORMATS) or AM_FORMATS[0]
            used_pairs.add((existing_pillar, fmt))
            am = {"date": date, "time": AM_TIME, "intent": "am_edu", "pillar": existing_pillar,
                  "format": fmt, "fb_needed": False}
        else:
            blocked = today_pillars | prev_pillars | next_fixed
            res = pick_pillar(AM_FORMATS, blocked) or pick_pillar(AM_FORMATS, today_pillars | next_fixed) or pick_pillar(AM_FORMATS, today_pillars)
            pil, fmt = res
            used_pairs.add((pil, fmt))
            pillar_count[pil] += 1
            am = {"date": date, "time": AM_TIME, "intent": "am_edu", "pillar": pil,
                  "format": fmt, "fb_needed": True}
        today_pillars.add(am["pillar"])
        day_slots.append(am)

        # --- PM slot (zawsze nowy, fb_needed) ---
        blocked = today_pillars | prev_pillars | next_fixed
        res = pick_pillar(PM_FORMATS, blocked) or pick_pillar(PM_FORMATS, today_pillars | next_fixed) or pick_pillar(PM_FORMATS, today_pillars)
        pil, fmt = res
        used_pairs.add((pil, fmt))
        pillar_count[pil] += 1
        pm = {"date": date, "time": PM_TIME, "intent": "pm_cta", "pillar": pil,
              "format": fmt, "fb_needed": True}
        today_pillars.add(pil)
        day_slots.append(pm)

        # --- industry per slot ---
        for s in day_slots:
            if PILLARS[s["pillar"]]["general"]:
                s["industry"] = None
                continue
            chosen = None
            for i in range(len(_IND_KEYS)):
                cand = _IND_KEYS[(ind_cursor + i) % len(_IND_KEYS)]
                if cand not in prev_inds and cand not in today_inds:
                    chosen = cand
                    ind_cursor = (ind_cursor + i + 1) % len(_IND_KEYS)
                    break
            if chosen is None:  # relaks: tylko unikaj dzisiejszych
                for i in range(len(_IND_KEYS)):
                    cand = _IND_KEYS[(ind_cursor + i) % len(_IND_KEYS)]
                    if cand not in today_inds:
                        chosen = cand
                        ind_cursor = (ind_cursor + i + 1) % len(_IND_KEYS)
                        break
            s["industry"] = chosen
            today_inds.add(chosen)

        plan.extend(day_slots)
        prev_pillars = today_pillars
        prev_inds = today_inds

    return plan


def validate_plan(plan: list[dict]) -> list[str]:
    """Zwróć listę naruszeń reguł (pusta = OK)."""
    errs = []
    # 2 sloty/dzień, 2 różne filary
    by_day: dict[str, list[dict]] = {}
    for s in plan:
        by_day.setdefault(s["date"], []).append(s)
    for date, slots in by_day.items():
        if len(slots) != 2:
            errs.append(f"{date}: {len(slots)} slotów (oczekiwano 2)")
        if len({s["pillar"] for s in slots}) < 2:
            errs.append(f"{date}: ten sam filar w obu slotach ({[s['pillar'] for s in slots]})")
        if len({s["intent"] for s in slots}) < 2:
            errs.append(f"{date}: ten sam intent w obu slotach")
    # brak tego samego filaru dwa dni z rzędu
    days = sorted(by_day)
    for i in range(1, len(days)):
        a = {s["pillar"] for s in by_day[days[i - 1]]}
        b = {s["pillar"] for s in by_day[days[i]]}
        if a & b:
            errs.append(f"{days[i]}: filar powtórzony z {days[i-1]}: {a & b}")
    # unikalna para (pillar, format)
    pairs = [(s["pillar"], s["format"]) for s in plan]
    dupes = {p for p in pairs if pairs.count(p) > 1}
    if dupes:
        errs.append(f"Powtórzone pary (pillar,format): {dupes}")
    # FB count: auto-FB = wszystkie sloty minus AM zajete recznym kalendarzem (EXISTING).
    # Czerwiec: 50 - 14 = 36. Lipiec (EXISTING={}): 52 - 0 = 52 (pelne 2 FB/dzien).
    fb = sum(1 for s in plan if s["fb_needed"])
    expected_fb = len(plan) - len(EXISTING)
    if fb != expected_fb:
        errs.append(f"FB-needed = {fb} (oczekiwano {expected_fb})")
    return errs


# === COPY (LLM) ===

def _link_utm(pillar: str) -> str:
    p = PILLARS[pillar]
    sep = "&" if "?" in p["url"] else "?"
    return f"{p['url']}{sep}utm_source=facebook&utm_medium=organic&utm_campaign={p['utm']}"


def _build_social_prompt(slot: dict, channel: str, recent: list[dict]) -> str:
    p = PILLARS[slot["pillar"]]
    ind = INDUSTRIES.get(slot["industry"] or "", "") if slot.get("industry") else ""
    ind_line = f"- Branża / kontekst odbiorcy: {ind}\n" if ind else ""
    fmt_instr = FORMATS[slot["format"]]
    recent_block = "\n".join(f"- {r.get('slug','')}: {r.get('keyword','')[:80]}" for r in recent) or "(brak)"
    _tag_rule = ("Hashtagi: każdy = jeden wyraz, lowercase, BEZ polskich znaków (ą→a, ł→l, ż→z...), "
                 "BEZ spacji w środku, oddzielone spacją. Marka to #actio (nie #aktio).")
    if channel == "facebook":
        ch_rules = ("- To post na FACEBOOK. NIE wstawiaj URL ani hashtagów w 'body' (dodam je osobno).\n"
                    "- 3-6 krótkich linijek, można 1-2 emoji, zakończ miękkim CTA bez linku.\n"
                    f"- hashtags: 3-5 sztuk. {_tag_rule}")
    else:
        ch_rules = ("- To post na INSTAGRAM. NIE wstawiaj URL w 'body' (link jest w bio).\n"
                    "- 3-6 krótkich linijek, można emoji, zakończ CTA typu 'Napisz' / 'Sprawdź – link w bio'.\n"
                    f"- hashtags: 8-15 sztuk, mix ogólnych i niszowych. {_tag_rule}")
    return f"""Jesteś social media managerem Actio (polski operator VoIP B2B, marka SYNTELL S.A., od 1996; klienci m.in. grupa PGE, Koleje Wielkopolskie).

Napisz JEDEN krótki post sprzedażowo-edukacyjny.

USŁUGA (filar): {p['label']}
Opis usługi: {p['desc']}
FORMAT posta: {slot['format']} — {fmt_instr}
{ind_line}INTENT: {"edukacja/wartość" if slot['intent']=='am_edu' else "produkt/konwersja (CTA)"}

ZASADY KANAŁU:
{ch_rules}

STYL: nie używaj długiego myślnika / pauzy (—). Jedyny dozwolony myślnik to półpauza (–).

NIE POWTARZAJ tych ostatnich postów (inny kąt, inne słowa):
{recent_block}

Zwróć DOKŁADNIE w tym formacie, każda sekcja po swoim znaczniku (bez JSON, bez ```):
<<<BODY>>>
treść posta (może być wielolinijkowa, BEZ linku, BEZ hashtagów)
<<<HASHTAGS>>>
#tag1 #tag2 #tag3
<<<ANGLE>>>
5-8 słów: konkretny kąt/hook tego posta (po polsku)
<<<IMAGE>>>
krótki opis sceny na grafikę + 3-6 słów nagłówka PL (realistyczne zdjęcie biznesowe, kontekst usługi/branży)"""


def _parse_sections(raw: str) -> dict:
    import re
    out = {"body": "", "hashtags": "", "angle": "", "image": ""}
    parts = re.split(r"<<<\s*(BODY|HASHTAGS|ANGLE|IMAGE)\s*>>>", raw)
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].lower()] = parts[i + 1].strip()
    return out


def generate_copy(slot: dict, channel: str) -> dict:
    path = DB()
    recent = db.fetch_recent_social_topics(path, channel, 7)
    sec = _parse_sections(ap._call_llm(_build_social_prompt(slot, channel, recent)))
    angle = sec["angle"].strip()
    sig = f"{angle} {slot.get('industry') or ''}"
    if angle and ap._is_topic_repeat(sig, recent):
        note = "\n\nUWAGA: poprzedni wariant był zbyt podobny do ostatnich postów. Zmień kąt i słownictwo."
        sec = _parse_sections(ap._call_llm(_build_social_prompt(slot, channel, recent) + note))
        angle = sec["angle"].strip()
    body = sec["body"].strip().strip("`").strip().replace("—", "–")  # pauza → półpauza
    if not body:
        raise ValueError(f"Pusty body z LLM (parse fail): {sec}")
    tags = [t for t in sec["hashtags"].replace(",", " ").split() if t.strip()]
    tags_str = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
    if channel == "facebook":
        final = f"{body}\n\n🔗 {_link_utm(slot['pillar'])}"
        if tags_str:
            final += f"\n\n{tags_str}"
        link = _link_utm(slot["pillar"])
    else:
        final = body + (f"\n\n{tags_str}" if tags_str else "") + "\n\n📲 Link w bio"
        link = None
    return {
        "copy": final,
        "hashtags": json.dumps(tags, ensure_ascii=False),
        "link_utm": link,
        "image_brief": sec["image"].strip() or body[:120],
        "angle": angle,
        "topic_tokens": " ".join(sorted(ap._topic_tokens(angle, slot.get("industry") or ""))),
    }


def _slot_id(slot: dict) -> str:
    return f"{slot['date']}_{slot['time'].replace(':', '')}"


def generate_image(slot: dict, brief: str) -> str:
    """Jedna grafika 4:5 (1080×1350) na slot – wspólna dla FB i IG. Zwróć ścieżkę."""
    out_dir = sp._SOCIAL_IMG_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = generate_social_image(brief, "pion", out_dir)
    dest = out_dir / f"{_slot_id(slot)}.png"
    if tmp.resolve() != dest.resolve():
        tmp.replace(dest)
    return str(dest)


# === ORKIESTRATOR ===

def generate(dry_run: bool = False, limit: int | None = None, only_channel: str | None = None) -> dict:
    """Wygeneruj copy + grafiki dla planu i zapisz do DB (status 'generated')."""
    path = DB()
    db.init_db(path)
    plan = build_unified_plan()
    errs = validate_plan(plan)
    print(f"Plan: {len(plan)} slotów, FB-needed={sum(s['fb_needed'] for s in plan)}; naruszenia reguł: {errs or 'BRAK'}")
    if errs:
        raise SystemExit("Plan nie przeszedł walidacji – przerwane.")

    if dry_run:
        for s in plan:
            fb = "FB+IG" if s["fb_needed"] else "IG"
            print(f"  {s['date']} {s['time']} [{s['intent']:6}] {s['pillar']:20} · {s['format']:16} · {s.get('industry') or '-':20} → {fb}")
        return {"plan": len(plan), "dry_run": True}

    stats = {"images": 0, "fb": 0, "ig": 0, "errors": 0}
    done = 0
    for slot in plan:
        if limit and done >= limit:
            break
        primary = "facebook" if slot["fb_needed"] else "instagram"
        try:
            prim_copy = generate_copy(slot, primary)
            img = generate_image(slot, prim_copy["image_brief"])
            stats["images"] += 1
            rows = {primary: prim_copy}
            if slot["fb_needed"] and (only_channel in (None, "instagram")):
                rows["instagram"] = generate_copy(slot, "instagram")
            for ch in (["facebook", "instagram"] if slot["fb_needed"] else ["instagram"]):
                if only_channel and ch != only_channel:
                    continue
                c = rows.get(ch) or generate_copy(slot, ch)
                db.insert_social_post(path, {
                    "channel": ch, "scheduled_time": f"{slot['date']} {slot['time']}",
                    "slot_intent": slot["intent"], "pillar": slot["pillar"], "format": slot["format"],
                    "industry": slot.get("industry"), "topic_tokens": c["topic_tokens"],
                    "copy": c["copy"], "hashtags": c["hashtags"], "link_utm": c["link_utm"],
                    "image_path": img, "image_brief": c["image_brief"], "status": "generated",
                })
                stats["fb" if ch == "facebook" else "ig"] += 1
            done += 1
            print(f"  ✓ {_slot_id(slot)} {slot['pillar']}/{slot['format']}")
        except Exception as e:
            stats["errors"] += 1
            print(f"  ✗ {_slot_id(slot)} {type(e).__name__}: {e}")
    print(f"Generated: {stats}")
    return stats


def commit_schedule(dry_run: bool = False) -> dict:
    """FB: zaplanuj posty 'generated' natywnie. IG: przełącz 'generated'→'queued' (cron dopublikuje)."""
    path = DB()
    page_token = sp.get_page_token()
    taken = sp.fb_scheduled_dates(page_token)
    stats = {"fb_scheduled": 0, "fb_skip_taken": 0, "ig_queued": 0, "errors": 0}

    for post in db.fetch_social_posts(path, channel="facebook", status="generated"):
        date = post["scheduled_time"][:10]
        hhmm = post["scheduled_time"][11:16]
        # Ochrona: jeśli na ten dzień+godzinę już coś jest (np. ponowny run), pomiń poranny istniejący slot.
        if hhmm in ("09:00", "11:00") and date in taken:
            stats["fb_skip_taken"] += 1
            continue
        if dry_run:
            stats["fb_scheduled"] += 1
            continue
        r = sp.schedule_fb_photo_post(post["image_path"], post["copy"], post["scheduled_time"], page_token)
        if r.get("ok"):
            db.update_social_post(path, post["id"], status="scheduled", fb_post_id=r["post_id"])
            stats["fb_scheduled"] += 1
        else:
            db.update_social_post(path, post["id"], status="failed", error_log=r.get("error"))
            stats["errors"] += 1
        import time as _t; _t.sleep(2)

    for post in db.fetch_social_posts(path, channel="instagram", status="generated"):
        if not dry_run:
            db.update_social_post(path, post["id"], status="queued")
        stats["ig_queued"] += 1

    print(f"commit_schedule: {stats}")
    return stats


if __name__ == "__main__":
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--dry-run", action="store_true", help="tylko wypisz plan")
    ap_.add_argument("--generate", action="store_true", help="generuj copy+grafiki do DB")
    ap_.add_argument("--commit", action="store_true", help="zaplanuj FB + zakolejkuj IG")
    ap_.add_argument("--limit", type=int, default=None, help="ogranicz liczbę slotów (próbka)")
    ap_.add_argument("--channel", default=None, help="tylko facebook|instagram")
    a = ap_.parse_args()
    if a.dry_run:
        generate(dry_run=True)
    elif a.generate:
        generate(limit=a.limit, only_channel=a.channel)
    elif a.commit:
        commit_schedule()
    else:
        generate(dry_run=True)
