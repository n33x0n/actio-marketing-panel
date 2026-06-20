# Sendly.link – reklama „Klątwa Protokołu (Samiec Alfa)" – pakiet promptów

Komiksowa reklama wg scenariusza (6 kadrów + czołówka w stylu Marvela).
Formaty: **16:9 (YouTube)** + **9:16 (Social)**.

## Wybór narzędzi (tokeno-oszczędnie)

1. **Kadry/stille:** Midjourney v7 (lub Flux.1) – najlepsza kontrola stylu komiksu, grosze za kadr.
2. **Animacja:** Kling 2.x **image-to-video** (ze stilli) – ułamek kosztu text-to-video.
3. **Audio:** ElevenLabs (lektor + SFX + muzyka).
4. Fallback ultra-tani: Hailuo/MiniMax i2v zamiast Klinga.
- NIE: Sora / Veo 3 text-to-video (najdroższe; natywne audio Veo zbędne, bo robimy je w ElevenLabs).

## Oba formaty

- Master generuj **16:9** (`--ar 16:9`), potem wariant **9:16** (`--ar 9:16`).
- 9:16 recompose: kadrowanie ciaśniej na twarzy, kolumny kodu pionowo, onomatopeje układane w pionie, napisy pełna szerokość dołu. Kadr 1 (szeroki) i Kadr 5 (akcja) wymagają realnego przekomponowania pod pion – reszta to przekadrowanie.
- W Klingu przy imporcie ustaw proporcję zgodną ze stillem (16:9 albo 9:16).

---

## CZOŁÓWKA (czołówka Marvel-style, ~3-4 s)

Szybki montaż przewracanych paneli komiksu z naszej historii (wycinki kadrów 1-5) kartkujących się jak strony w intrze Marvel Studios, tusz + halftone, narastający blaszany fanfar, ląduje na rozbłysku logo **SENDLY.LINK** (gradient/błękit) – lock-up jak czerwone logo Marvela.

```
Midjourney (sekwencja 4-6 stilli): rapid flipping comic-book pages montage, Marvel Studios intro style, fragments of a developer-Jedi story flashing on turning pages, bold ink outlines, halftone shading, dramatic blue-and-red lighting, motion energy --ar 16:9   (wariant: --ar 9:16)
Kling: fast page-flip motion, pages turning toward camera, quick cuts, camera push-in, ends locking on a glowing SENDLY.LINK logo reveal
```

---

## CZĘŚĆ 1 — ElevenLabs: lektor i głosy (model Eleven v3)

| Rola | Głos | Ustawienia |
|---|---|---|
| Narrator (Superadmin) | głęboki męski, „zwiastun kinowy", lekko ironiczny | Stability 40, Style 45, wolno |
| Grzegorz | młody dev 25-35, desperacja → triumf | Stability 30, Style 60 |
| Mariola | ciepły kobiecy, codzienny, zaniepokojony | Stability 55, Style 30 |

```
[KADR 1 – Narrator]
[deep cinematic movie-trailer voice, slow, slightly amused]
Poznaj Grzesia. [pause] Grzegorz uważa, że korzystanie z gotowego A-P-I do wysyłki SMS-ów… to kapitulacja. [pause] Grzegorz to samiec alfa kodowania.

[KADR 2 – Grzegorz]
[muttering under his breath, frustrated, tense]
Dlaczego protokół S-M-P-P mi znowu odrzuca autoryzację? [exhales] Przecież zmieniłem tylko jedną spację…

[KADR 3 – Grzegorz]
[screaming, desperate, anguished]
NIE! [pause] NIE!! [pause] NIE!!!

[KADR 4 – Grzegorz, myśl]
[calm, determined, almost whispering, inner voice]
Koniec z ciemną stroną kodu. Koniec z szukaniem brakującego średnika przez osiem godzin…

[KADR 4 – Narrator]
[epic, building tension, reverent]
Grzegorz zrozumiał, że prawdziwy mistrz nie marnuje Mocy na Stack Overflow. [pause] Prawdziwy mistrz wybiera gotowe rozwiązania.

[KADR 5 – Grzegorz]
[shouting proudly, triumphant, heroic]
Niech Sendly kropka link będzie ze mną! Przechodzę na produkcję w piątek o szesnastej i nic mnie nie powstrzyma!

[KADR 5 – Mariola]
[soft, concerned, a little confused]
Grześ, czy u ciebie wszystko okej? Słyszałam jakieś wrzaski i krzyki.

[KADR 6 – Narrator]
[warm, confident, modern, clear]
Nie bądź jak Grzegorz. Wejdź na sendly kropka link i zacznij korzystać z SMS-ów na pełnej epie!
```
Uwaga TTS: skróty fonetycznie (A-P-I, S-M-P-P, „sendly kropka link", „szesnastej”). `HTTP 200 OK` tylko na ekranie.

---

## CZĘŚĆ 2 — ElevenLabs: efekty dźwiękowe (Sound Effects, EN)

```
INTRO:   Bold orchestral brass stinger with comic page-flip whooshes, Marvel-style intro hit, 3s
KADR 1:  Aggressive rapid mechanical keyboard typing, machine-gun rhythm, loud clacky switches, 4s
KADR 3:  Rising digital error alarm into a massive cinematic impact explosion, then sudden dead silence and a single heartbeat, 3s
KADR 4:  Dusty fabric whoosh pulling cloth, soft magical shimmer sparkle, puff of dust, 2s
KADR 5a: Lightsaber ignition and fast swing, deep electric hum with energy crackle, 2s
KADR 5b: Clean bright positive UI success chime, message delivered notification, 1s
TRANS:   Cinematic whoosh transition, deep sub bass riser, 1s
```

---

## CZĘŚĆ 3 — ElevenLabs: muzyka (ElevenLabs Music, 1 prompt)

```
Cinematic branded ad score, ~60 seconds. Opens with a bold Marvel-style orchestral brass fanfare and page-flip energy (intro), then three movements with seamless transitions:
(1) dark, tense, ominous — low pulsing synth and uneasy strings building dread (a developer's nightmare);
(2) heroic turn — triumphant Star Wars-inspired orchestral fanfare, soaring brass, epic choir, victorious as the hero awakens;
(3) clean resolve — bright modern minimal tech ambient, calm, confident, premium SaaS outro.
Epic, emotional, professional, polished.
```

---

## CZĘŚĆ 4 — Wizualizacja (Midjourney → Kling)

Styl bazowy (dopisz do KAŻDEGO kadru): `dynamic American comic-book / graphic-novel style, bold ink outlines, dramatic cinematic lighting, halftone shading, vivid colors`. Flaga `--ar 16:9` (master) lub `--ar 9:16` (social).

```
KADR 1 [MJ still]: Wide cinematic shot, dark room lit only by cold pale-blue monitor glow. Young man (Grzegorz) from behind in a gaming chair, hands a motion-blur of speed, dramatic dust, translucent floating lines of code (PHP, Java, Python) levitating around him, big stylized comic onomatopoeia "RAT-AT-AT!" "KLAK!", golden rectangular narrator caption box at top. --ar 16:9
  [Kling motion]: subtle camera push-in, flickering monitor light, hands vibrating with speed, floating code drifts slowly.
  [9:16 recompose]: tighter vertical on the silhouette + monitor, code columns stacked vertically.

KADR 2 [MJ still]: American/medium shot, Grzegorz from the front, face twisted in rage and desperation, eyes wide, sweat on forehead, glasses reflecting thousands of lines of burning blood-red stack-trace error, ragged-edged speech bubble. --ar 16:9
  [Kling motion]: slow zoom on the eyes, error reflection scrolling in the glasses, sweat drips.

KADR 3 [MJ still]: Extreme close-up of Grzegorz's face, both hands clutching head, messy hair, background exploding in red error light, labels "CONNECTION_REFUSED" "AUTH_FAILED" crushing him, huge jagged screaming bubble "NIE! NIE!! NIE!!!". --ar 16:9
  [Kling motion]: rapid shake, red light pulsing, ends in a white super-explosion flash. (cut to: Grzegorz jolts awake in bed, sweaty, then calms and walks to wardrobe.)

KADR 4 [MJ still]: Grzegorz in a dynamic pose before an open wardrobe glowing mystical blue, pulling out a dusty Jedi robe. Meme poster on the wardrobe "It works on my machine" with a burning server. He removes a "I turn coffee into code" t-shirt, puts on Master's robes. Onomatopoeia "Fsssshh! PUFF!" dust. --ar 16:9
  [Kling motion]: blue glow pulsing from wardrobe, dust particles rising, robe lifting.

KADR 5 [MJ still]: Powerful action shot — Grzegorz in Jedi robes mid-spin igniting a bright-blue lightsaber, blade slicing a floating red text "StackOverflowError: Room full of tears". Behind him a monitor glows "HTTP 200 OK — SMS Sent (0.001s)". Onomatopoeia "ZUUUMMM! KHHYYYYZZZ!". Star-Wars-style bottom caption "SENDLY.LINK – POTĘŻNE API. ZERO REFACTORINGU. JASNA STRONA SMS-ÓW". --ar 16:9
  [Kling motion]: lightsaber ignites and swings, sparks, slow-mo spin. (then a woman, Mariola, opens the door; Grzegorz looks down, blushes, fidgets fingers.)
  [9:16 recompose]: vertical hero pose, lightsaber along the vertical axis, caption full-width bottom.

KADR 6 [MJ still]: Total mood shift — bright, clean, modern tech-blue background. Elegant smartphone showing a minimal working Sendly.link panel with green "STATUS: DELIVERED", a steaming cup of coffee beside it, large modern narrator caption box, Avengers-style bold bottom logo caption "SENDLY.LINK – SERWIS DLA PROFESJONALISTÓW". --ar 16:9
  [Kling motion]: gentle parallax, steam rising from coffee, subtle UI shimmer, green status pulse.
```

## Pipeline

Czołówka + kadry (MJ) → animacja (Kling i2v) → montaż → lektor + SFX (ElevenLabs) → muzyka (ElevenLabs Music) → napisy na ekranie wg scenariusza → eksport 16:9 (YT) i przekomponowany 9:16 (Social).
