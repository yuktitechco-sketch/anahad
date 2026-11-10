"""Shared code for Anahad: verse bank, picking verses, rendering posts and reels."""
import csv, datetime, hashlib, html, json, os, random, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
STATE_PATH = os.path.join(ROOT, "data", "state.json")
FONTS = "file://" + os.path.join(ROOT, "node_modules", "@fontsource")


# ---------------------------------------------------------------- data
def load_bank():
    with open(os.path.join(ROOT, "data", "verse_bank.csv"), encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return {r["ID"]: r for r in rows}


def load_state():
    return json.load(open(STATE_PATH, encoding="utf-8"))


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def today_local():
    tz = datetime.timezone(datetime.timedelta(hours=CFG["timezone_offset_hours"]))
    return datetime.datetime.now(tz).date()


def pick(bank, state, kind, date, taken):
    """Next unused, source-matched verse for this kind ('post' or 'reel') and date."""
    blocked = set(state["used"]) | set(state["skipped"]) | set(taken)
    limit = CFG["max_chars"][kind]

    def ok(r):
        return (r["Status"] == CFG["only_status"] and r["ID"] not in blocked
                and len(r["Original"]) <= limit and r["Hindi meaning"] and r["English meaning"]
                # Hindi and Sanskrit verses are used only once their meaning is written as an essence, not a literal translation
                and (r["Religion / section"] not in CFG.get("essence_only_sections", []) or r.get("Meaning style") == "Essence"))

    wanted = CFG["rotation"][kind][date.weekday()]
    pool = [r for r in bank.values() if ok(r) and r["Religion / section"] == wanted]
    if not pool:  # section used up: fall back to anything that is left
        pool = [r for r in bank.values() if ok(r)]
    if not pool:
        raise SystemExit("The verse bank has no unused, source-matched verses left.")
    pool.sort(key=lambda r: r["ID"])
    random.Random(wanted + kind).shuffle(pool)  # fixed order per section, so runs are repeatable
    return pool[0]


def caption(row):
    tags = CFG["hashtags"]
    return "\n".join([
        row["Original"], "", row["Hindi meaning"], "", row["English meaning"], "",
        f"— {row['Author / Text']}, {row['Reference']}", ".",
        "अनहद · Anahad — a verse a day from the world's sacred texts.",
        "The lines under the verse give its essence in our own words, not a word-for-word translation.", ".",
        (tags["_all"] + " " + tags.get(row["Religion / section"], "")).strip(),
    ])


# ---------------------------------------------------------------- rendering
def script_of(text):
    for ch in text:
        o = ord(ch)
        if 0x0900 <= o <= 0x097F: return "deva"
        if 0x0B80 <= o <= 0x0BFF: return "tamil"
        if 0x0600 <= o <= 0x06FF: return "arabic"
        if 0x4E00 <= o <= 0x9FFF: return "cjk"
    return "latin"


VERSE_STYLE = {  # font stack, size factor, extra css
    "deva": ("Tiro", 1.0, ""),
    "tamil": ("NTamil", 0.74, ""),
    "arabic": ("NArabic", 1.0, "direction: rtl; line-height: 1.9;"),
    "cjk": ("'Noto Serif CJK SC', 'Noto Serif SC', serif", 0.95, "letter-spacing: .06em;"),
    "latin": ("Cormorant", 1.0, "font-weight: 500;"),
}

FACES = f"""
@font-face {{ font-family: Tiro; src: url({FONTS}/tiro-devanagari-hindi/files/tiro-devanagari-hindi-devanagari-400-normal.woff2); }}
@font-face {{ font-family: Tiro; src: url({FONTS}/tiro-devanagari-hindi/files/tiro-devanagari-hindi-latin-400-normal.woff2); unicode-range: U+0000-00FF; }}
@font-face {{ font-family: NTamil; src: url({FONTS}/noto-serif-tamil/files/noto-serif-tamil-tamil-400-normal.woff2); }}
@font-face {{ font-family: NArabic; src: url({FONTS}/noto-naskh-arabic/files/noto-naskh-arabic-arabic-500-normal.woff2); }}
@font-face {{ font-family: Cormorant; font-weight: 500; src: url({FONTS}/cormorant-garamond/files/cormorant-garamond-latin-500-normal.woff2); unicode-range: U+0000-00FF, U+2000-206F; }}
@font-face {{ font-family: Cormorant; font-weight: 500; src: url({FONTS}/cormorant-garamond/files/cormorant-garamond-latin-ext-500-normal.woff2); unicode-range: U+0100-024F, U+1E00-1EFF; }}
@font-face {{ font-family: Cormorant; font-weight: 500; font-style: italic; src: url({FONTS}/cormorant-garamond/files/cormorant-garamond-latin-500-italic.woff2); }}
@font-face {{ font-family: Cormorant; font-weight: 600; src: url({FONTS}/cormorant-garamond/files/cormorant-garamond-latin-600-normal.woff2); }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
:root {{ --s: 1; }}
"""

# shrinks the text block until it fits its box
FIT = """<script>document.fonts.ready.then(() => { const b = document.querySelector('.body'), i = document.querySelector('.inner');
let s = 1; while ((i.scrollHeight > b.clientHeight || i.scrollWidth > b.clientWidth) && s > .5) { s -= .03; document.documentElement.style.setProperty('--s', s); } });</script>"""

FLAME = "M0 -100 C34 -58 52 -28 52 4 A52 52 0 0 1 -52 4 C-52 -28 -34 -58 0 -100z"


def _chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if shutil.which(name):
            return name
    raise SystemExit("Chrome was not found.")


def _shot(page, png, w, h):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(page)
    try:
        subprocess.run([_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", f"--window-size={w},{h}", "--virtual-time-budget=5000",
                        f"--screenshot={png}", "file://" + f.name], check=True, capture_output=True)
    finally:
        os.unlink(f.name)


def _jpg(png, jpg):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", png, "-q:v", "2", jpg], check=True)
    os.unlink(png)


def _parts(row):
    sec = row["Religion / section"]
    tag_hi, tag_en = CFG["tags"].get(sec, ["वाणी", "WISDOM"])
    font, factor, extra = VERSE_STYLE[script_of(row["Original"])]
    orig = row["Original"]
    if "\n" not in orig and "। " in orig:  # a one-line chaupai: break it at the half-way mark
        orig = orig.replace("। ", "।\n", 1)
    verse = "<br>".join(html.escape(l) for l in orig.split("\n"))
    if script_of(orig) in ("deva", "tamil", "arabic") and max(len(l) for l in orig.split("\n")) <= 48:
        extra += " white-space: nowrap;"  # keep each line of the verse whole; the text shrinks to fit instead
    return dict(tag_hi=html.escape(tag_hi), tag_en=html.escape(tag_en), font=font, factor=factor, extra=extra, verse=verse,
                hi=html.escape(row["Hindi meaning"]), en=html.escape(row["English meaning"]),
                src=html.escape(row["Author / Text"].upper()) + " · " + html.escape(row["Reference"]),
                name_hi=CFG["page_name_hi"], name_en=CFG["page_name_en"])


def render_post(row, jpg):
    """1080x1350 picture post (parchment)."""
    p = _parts(row)
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{FACES}
body {{ width: 1080px; height: 1350px; overflow: hidden; color: #2A1F1A;
  background: radial-gradient(ellipse at 50% 38%, #FBF4E2 0%, #F4EAD5 55%, #EADBBB 100%); }}
.frame {{ position: absolute; inset: 44px; border: 1.5px solid #D99A2B; }}
.frame:after {{ content: ""; position: absolute; inset: 9px; border: 1px solid rgba(217,154,43,.45); }}
.tag {{ position: absolute; top: 96px; left: 0; right: 0; text-align: center; font: 600 24px Cormorant; letter-spacing: .34em; color: #B5532E; }}
.tag span {{ font-family: Tiro; letter-spacing: 0; font-size: 27px; font-weight: 400; margin-right: 18px; }}
.mark {{ position: absolute; top: 152px; left: 50%; transform: translateX(-50%); }}
.body {{ position: absolute; top: 240px; bottom: 205px; left: 110px; right: 110px; display: flex; flex-direction: column; justify-content: center; }}
.inner {{ display: flex; flex-direction: column; align-items: center; text-align: center; }}
.verse {{ font: 400 calc(56px * {p['factor']} * var(--s))/1.62 {p['font']}; {p['extra']} }}
.rule {{ width: 150px; height: 2px; background: #D99A2B; margin: calc(54px * var(--s)) 0 calc(46px * var(--s)); position: relative; flex: none; }}
.rule:after {{ content: ""; position: absolute; left: 50%; top: -5px; width: 12px; height: 12px; background: #D99A2B; transform: translateX(-50%) rotate(45deg); }}
.hi {{ font: 400 calc(33px * var(--s))/1.6 Tiro; color: #3b2d25; }}
.en {{ font: italic 500 calc(35px * var(--s))/1.4 Cormorant; color: #5a463a; margin-top: calc(30px * var(--s)); }}
.src {{ position: absolute; bottom: 150px; left: 0; right: 0; text-align: center; font: 600 25px Cormorant; letter-spacing: .32em; color: #B8801C; }}
.name {{ position: absolute; bottom: 92px; left: 0; right: 0; text-align: center; font: 400 30px Tiro; color: #2A1F1A; }}
.name b {{ font: 600 22px Cormorant; letter-spacing: .4em; margin-left: 16px; color: #6b5548; }}
</style></head><body>
<div class="frame"></div>
<div class="tag"><span>{p['tag_hi']}</span>{p['tag_en']}</div>
<svg class="mark" width="54" height="54" viewBox="0 0 54 54"><circle cx="27" cy="27" r="25.5" fill="none" stroke="#D99A2B" stroke-width="1.5"/>
<path d="M27 11c5 6 7.5 10 7.5 14.2A7.5 7.5 0 0 1 27 32.7a7.5 7.5 0 0 1-7.5-7.5C19.5 21 22 17 27 11z" fill="#D99A2B"/>
<path d="M14.5 35.5h25c-1.8 5-6.5 8-12.5 8s-10.7-3-12.5-8z" fill="#B5532E"/></svg>
<div class="body"><div class="inner">
  <div class="verse">{p['verse']}</div><div class="rule"></div>
  <div class="hi">{p['hi']}</div><div class="en">{p['en']}</div>
</div></div>
<div class="src">{p['src']}</div>
<div class="name">{p['name_hi']}<b>{p['name_en']}</b></div>
{FIT}</body></html>"""
    png = jpg[:-4] + ".png"
    _shot(page, png, 1080, 1350)
    _jpg(png, jpg)


def _reel_page(row, step):
    """One frame of the reel. step 0..4 reveals: nothing, verse, Hindi, English, source."""
    p = _parts(row)
    rnd = random.Random(int(hashlib.md5(row["ID"].encode()).hexdigest(), 16))
    stars = "".join(f'<circle cx="{rnd.uniform(0, 1080):.0f}" cy="{rnd.uniform(0, 1920):.0f}" r="{rnd.uniform(.8, 2.6):.1f}" '
                    f'opacity="{rnd.uniform(.2, .8):.2f}"/>' for _ in range(120))
    show = lambda n: "" if step >= n else "visibility: hidden;"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{FACES}
body {{ width: 1080px; height: 1920px; overflow: hidden; color: #FBEFD0;
  background: radial-gradient(ellipse at 50% 40%, #5a1d3a 0%, #2a1035 48%, #0d0718 100%); }}
svg.sky {{ position: absolute; inset: 0; }}
.tag {{ position: absolute; top: 420px; left: 0; right: 0; text-align: center; font: 600 30px Cormorant; letter-spacing: .34em; color: #F2B755; }}
.tag span {{ font-family: Tiro; letter-spacing: 0; font-size: 34px; font-weight: 400; margin-right: 20px; }}
.body {{ position: absolute; top: 500px; bottom: 560px; left: 96px; right: 96px; display: flex; flex-direction: column; justify-content: center; }}
.inner {{ display: flex; flex-direction: column; align-items: center; text-align: center; }}
.verse {{ font: 400 calc(64px * {p['factor']} * var(--s))/1.62 {p['font']}; {p['extra']} {show(1)} }}
.rule {{ width: 170px; height: 2px; background: #E0A63A; margin: calc(56px * var(--s)) 0 calc(48px * var(--s)); position: relative; flex: none; {show(2)} }}
.rule:after {{ content: ""; position: absolute; left: 50%; top: -6px; width: 14px; height: 14px; background: #E0A63A; transform: translateX(-50%) rotate(45deg); }}
.hi {{ font: 400 calc(40px * var(--s))/1.6 Tiro; color: #F1E2C0; {show(2)} }}
.en {{ font: italic 500 calc(43px * var(--s))/1.4 Cormorant; color: #DCC8A4; margin-top: calc(34px * var(--s)); {show(3)} }}
.src {{ position: absolute; bottom: 470px; left: 0; right: 0; text-align: center; font: 600 28px Cormorant; letter-spacing: .32em; color: #F2B755; {show(4)} }}
.name {{ position: absolute; bottom: 395px; left: 0; right: 0; text-align: center; font: 400 36px Tiro; {show(4)} }}
.name b {{ font: 600 24px Cormorant; letter-spacing: .4em; margin-left: 16px; color: #DCC8A4; }}
</style></head><body>
<svg class="sky" width="1080" height="1920" viewBox="0 0 1080 1920"><defs>
<radialGradient id="glow"><stop offset="0" stop-color="#FFE9A8" stop-opacity=".9"/><stop offset=".4" stop-color="#F2A93B" stop-opacity=".4"/><stop offset="1" stop-color="#F2A93B" stop-opacity="0"/></radialGradient>
<linearGradient id="fl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFBE6"/><stop offset=".55" stop-color="#FFC44A"/><stop offset="1" stop-color="#E8782A"/></linearGradient>
<filter id="b"><feGaussianBlur stdDeviation="12"/></filter></defs>
<g fill="#F6E3B0">{stars}</g>
<g transform="translate(540 300)">
<circle r="150" fill="none" stroke="#D99A2B" stroke-width="2" opacity=".5"/><circle r="186" fill="none" stroke="#D99A2B" stroke-width="1.5" opacity=".28"/>
<circle r="222" fill="none" stroke="#D99A2B" stroke-width="1" opacity=".14"/><circle cy="-8" r="130" fill="url(#glow)"/>
<g transform="scale(.62)"><path d="{FLAME}" fill="#FFB52E" filter="url(#b)"/><path d="{FLAME}" fill="url(#fl)"/>
<path d="{FLAME}" transform="translate(0 14) scale(.34)" fill="#FFFBEA"/>
<path d="M-100 60 H100 C88 104 48 124 0 124 S-88 104 -100 60z" fill="#C8643A"/><path d="M-100 60 H100" stroke="#FFD27A" stroke-width="6" stroke-linecap="round"/></g></g>
</svg>
<div class="tag"><span>{p['tag_hi']}</span>{p['tag_en']}</div>
<div class="body"><div class="inner">
  <div class="verse">{p['verse']}</div><div class="rule"></div>
  <div class="hi">{p['hi']}</div><div class="en">{p['en']}</div>
</div></div>
<div class="src">{p['src']}</div>
<div class="name">{p['name_hi']}<b>{p['name_en']}</b></div>
{FIT}</body></html>"""


def render_reel(row, mp4, cover_jpg):
    """1080x1920, 15 second reel: the verse, then its meanings, fade in one after another. The sound track is silent."""
    tmp = tempfile.mkdtemp()
    try:
        frames = []
        for step in range(5):
            png = os.path.join(tmp, f"s{step}.png")
            _shot(_reel_page(row, step), png, 1080, 1920)
            frames.append(png)
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for png in frames:
            cmd += ["-loop", "1", "-framerate", "30", "-t", "16", "-i", png]
        # a silent sound track: the music is attached by Instagram when the reel is published
        cmd += ["-f", "lavfi", "-t", "15", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        offsets = [0.8, 5.0, 8.5, 11.5]
        chain, last = [], "0:v"
        for n, off in enumerate(offsets, start=1):
            chain.append(f"[{last}][{n}:v]xfade=transition=fade:duration=1:offset={off}[x{n}]")
            last = f"x{n}"
        chain.append(f"[{last}]fade=t=out:st=14.4:d=0.6,format=yuv420p[v]")
        cmd += ["-filter_complex", ";".join(chain), "-map", "[v]", "-map", "5:a", "-t", "15", "-r", "30",
                "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", mp4]
        subprocess.run(cmd, check=True)
        _jpg(frames[4], cover_jpg)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_review(days, jpg):
    """One contact sheet for the whole week, so approval is a single look."""
    cells = ""
    for d in days:
        base = "file://" + os.path.join(ROOT, "queue", d["date"])
        label = datetime.date.fromisoformat(d["date"]).strftime("%a %d %b")
        cells += (f'<div class="day"><h2>{label}</h2><img class="p" src="{base}/post.jpg"><small>POST · {html.escape(d["post"]["ref"])}</small>'
                  f'<img class="r" src="{base}/reel_cover.jpg"><small>REEL · {html.escape(d["reel"]["ref"])}</small></div>')
    n = len(days)
    w = 40 + n * 330
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body {{ margin: 0; width: {w}px; background: #1d1512; font-family: sans-serif; color: #f4ead5; }}
.grid {{ display: flex; gap: 30px; padding: 30px 35px; }} .day {{ width: 300px; }}
h2 {{ font-size: 24px; margin: 0 0 12px; text-align: center; }} img {{ width: 300px; display: block; border-radius: 6px; }}
small {{ display: block; font-size: 14px; letter-spacing: .08em; margin: 8px 0 22px; text-align: center; color: #d9b36a; }}
</style></head><body><div class="grid">{cells}</div></body></html>"""
    png = jpg[:-4] + ".png"
    _shot(page, png, w, 1090)
    _jpg(png, jpg)
