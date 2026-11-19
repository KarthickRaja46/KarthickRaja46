"""Render the animated SVG cards for the GitHub profile README.

Reads data/contributions.json (refreshed daily by the GitHub Action),
data/portrait.txt, data/dashboards.json + data/thumbs/*.jpg and the GitHub
API, embeds subset fonts as base64 WOFF, and writes every card twice:

  cards/*.svg          dark theme (default)
  cards/light/*.svg    light theme, served via <picture> prefers-color-scheme

Cards: hero, heatmap, activity, tile-*, sec-*, dash-*, report, repo-*,
stack, contact, btn-*.

Everything shown through <img> must be self-contained: inline <style> with
CSS keyframes, SMIL, embedded fonts and images. No scripts, no external requests.

  STATIC=1 python scripts/render_readme_cards.py   -> final frame only (for screenshots)
"""
from __future__ import annotations

import base64
import json
import os
import textwrap
import urllib.request
from collections import Counter, OrderedDict
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent
STATIC = os.environ.get("STATIC") == "1"
USER = os.environ.get("GH_USER", "KarthickRaja46")
OUT = ROOT / "cards"  # switched per theme in main()

# ---------------------------------------------------------------- profile ---
PROFILE = {
    "first": "Karthick",
    "last": "Raja",
    "role": "Data Analyst & BI Analyst",
    "stack": "SQL · Python · DAX · Power BI · ETL pipelines",
}

TILES = [  # (slug, label, accent, value, format, caption)
    ("sql", "SQL", "blue", 40, "{:.0f}+", "SQL queries for KPI reporting, latency analysis & alerting"),
    ("powerbi", "POWER BI", "purple", 2.3, "${:.1f}M", "in sales analysed across 5-page Power BI dashboards"),
    ("python", "PYTHON", "teal", 100, "{:.0f}K+", "records through validated Python ETL pipelines"),
]

FEATURED = [  # Python / ML / tooling projects (the dashboards have their own gallery)
    ("Real-Estate-Price-Prediction", {"lang": "Python"}),
    ("Bird-Species-Audio-Classification", {"lang": "Python"}),
    ("Investment-Portfolio-Analytics", {"lang": "Excel"}),
    ("Data-Analyst-Job-Tracker", {"lang": "JavaScript",
                                  "desc": "Job application tracker built with Node.js and Express, persisted to Azure Blob Storage."}),
]

STACK = [  # (group, accent, [(monogram, name, colour)]); PYTHON spans two columns
    ("DATA", "blue", [("SQ", "SQL", "#e38c00"), ("My", "MySQL", "#00758f"), ("PQ", "Power Query", "#2b7bb9")]),
    ("BI", "purple", [("BI", "Power BI", "#f2c811"), ("DX", "DAX", "#00a4ef"), ("XL", "Excel", "#21a366")]),
    ("PYTHON", "teal", [("Py", "Python", "#3776ab"), ("Pd", "Pandas", "#7a5af8"), ("Np", "NumPy", "#4dabcf"),
                        ("Mp", "Matplotlib", "#11557c"), ("Sn", "Seaborn", "#2e8b9e"), ("St", "Streamlit", "#ff4b4b")]),
    ("TOOLS", "blue", [("Gt", "Git", "#f05032"), ("GH", "GitHub", "#6e7681"), ("Az", "Azure Blob", "#0078d4")]),
]

CONTACT = {
    "headline": "Let's turn your data into decisions.",
    "sub": "Dashboards, SQL and Python. Reach out on LinkedIn or by email.",
    "buttons": [  # (slug, label, detail, icon)
        ("linkedin", "LinkedIn", "/in/karthick-raja", "in"),
        ("email", "Email", "karthiikarthii46@gmail.com", "mail"),
        ("portfolio", "Portfolio", "karthickraja.page", "globe"),
    ],
}

# ------------------------------------------------------------------ theme ---
THEMES = {
    "dark": {
        "bg": "#0d1117", "panel": "#161b22", "line": "#30363d", "ink": "#e6edf3",
        "muted": "#8b949e", "faint": "#2d333b", "shine": "#ffffff", "rail": "#11161d",
        "blue": "#70a5fd", "purple": "#bf91f3", "teal": "#38bdae",
        "heat": ["#161b22", "#1d3459", "#2b5597", "#4a7fd8", "#70a5fd"],
    },
    "light": {
        "bg": "#ffffff", "panel": "#f6f8fa", "line": "#d0d7de", "ink": "#1f2328",
        "muted": "#59636e", "faint": "#e3e8ee", "shine": "#b9d3ff", "rail": "#eef1f5",
        "blue": "#2f6fde", "purple": "#8250df", "teal": "#13877a",
        "heat": ["#eef1f5", "#c7dbfb", "#8fb5f5", "#5389ea", "#2f6fde"],
    },
}
C: dict = {}
LANG = {"Python": "#3572A5", "Power BI": "#F2C811", "SQL": "#e38c00", "C#": "#178600", "Excel": "#21a366",
        "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "HTML": "#e34c26", "PowerShell": "#012456"}

# Page timeline (seconds): cards play top to bottom.
T_HEAT, T_BARS, T_TILES, T_GALLERY, T_REPORT, T_REPOS, T_STACK, T_CONTACT = 1.9, 3.1, 4.4, 5.2, 5.8, 6.4, 6.8, 7.2

# ------------------------------------------------------------------ fonts ---
FONT_FILES = {
    "grotesk500": ("Space Grotesk", 500, "space-grotesk-latin-500-normal.woff"),
    "grotesk700": ("Space Grotesk", 700, "space-grotesk-latin-700-normal.woff"),
    "mono400": ("JetBrains Mono", 400, "jetbrains-mono-latin-400-normal.woff"),
    "mono700": ("JetBrains Mono", 700, "jetbrains-mono-latin-700-normal.woff"),
}
_font_cache: dict[str, str] = {}


def font_face(key: str) -> str:
    """Subset a font to printable ASCII + a few symbols and return an @font-face rule."""
    if key not in _font_cache:
        family, weight, fname = FONT_FILES[key]
        opts = subset.Options()
        opts.flavor = "woff"
        # mono: no ligatures (JetBrains Mono's calt table drags in ~600 glyphs)
        opts.layout_features = ["kern"] if "mono" in key else ["kern", "liga"]
        opts.name_IDs = ["*"]
        opts.hinting = False
        opts.desubroutinize = True
        font = subset.load_font(str(ROOT / "fonts" / fname), opts)
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=list(range(0x20, 0x7F)) + [0xB7, 0x2022])
        sub.subset(font)
        buf = BytesIO()
        subset.save_font(font, buf, opts)
        b64 = base64.b64encode(buf.getvalue()).decode()
        _font_cache[key] = (f"@font-face{{font-family:'{family}';font-weight:{weight};"
                            f"src:url(data:font/woff;base64,{b64}) format('woff')}}")
    return _font_cache[key]


# -------------------------------------------------------------- svg shell ---
BASE_CSS = """
.g5{font-family:'Space Grotesk',sans-serif;font-weight:500}
.g7{font-family:'Space Grotesk',sans-serif;font-weight:700}
.m4{font-family:'JetBrains Mono',monospace;font-weight:400}
.m7{font-family:'JetBrains Mono',monospace;font-weight:700}
.a{animation-fill-mode:both;animation-timing-function:cubic-bezier(.2,.7,.2,1)}
@keyframes rise{from{opacity:0;transform:translateY(22px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes pop{0%{opacity:0;transform:scale(0)}70%{opacity:1;transform:scale(1.25)}100%{opacity:1;transform:scale(1)}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes growx{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes wipe{from{transform:scaleX(1)}to{transform:scaleX(0)}}
@keyframes lit{from{opacity:.12;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}
@keyframes pulse{0%{transform:scale(1);opacity:.7}100%{transform:scale(3.2);opacity:0}}
@keyframes nudge{0%,70%,100%{transform:none}80%{transform:translate(3px,-3px)}90%{transform:translate(-1px,1px)}}
@keyframes swing{0%{opacity:0;transform:translateY(70px) rotate(-9deg)}
 55%{opacity:1;transform:translateY(-8px) rotate(2.5deg)}75%{transform:translateY(3px) rotate(-1deg)}100%{opacity:1;transform:none}}
@keyframes sweep{0%{transform:translateX(-200px) skewX(-20deg)}22%,100%{transform:translateX(980px) skewX(-20deg)}}
.fb{transform-box:fill-box;transform-origin:center}
.fbb{transform-box:fill-box;transform-origin:50% 100%}
.fbl{transform-box:fill-box;transform-origin:0 50%}
.fbr{transform-box:fill-box;transform-origin:100% 50%}
"""


def freeze_css() -> str:
    return ("*{animation:none!important}"
            ".cnt{visibility:hidden!important}.cnt-final{visibility:visible!important}"
            ".shine-fx,.pulse-fx,.fx{display:none!important}"
            f".shine-text{{fill:{C['blue']}!important}}")


def svg(w: int, h: int, body: str, fonts: list[str], title: str, extra_css: str = "") -> str:
    faces = "".join(font_face(f) for f in fonts)
    fz = freeze_css()
    freeze = fz if STATIC else f"@media (prefers-reduced-motion:reduce){{{fz}}}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
            f"<style>{faces}{BASE_CSS}{extra_css}{freeze}</style>{body}</svg>")


def anim(name: str, delay: float, dur: float, extra: str = "") -> str:
    return f'style="animation:{name} {dur}s {delay:.3f}s both{(" " + extra) if extra else ""}"'


def smil(markup: str) -> str:
    """SMIL is dropped entirely in STATIC mode so the file shows its end state."""
    return "" if STATIC else markup


def frame(w: int, h: int, r: int = 16, fill: str | None = None) -> str:
    return (f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{r}" '
            f'fill="{fill or C["bg"]}" stroke="{C["line"]}"/>')


def arrow(x: float, y: float, colour: str, delay: float, size: float = 9) -> str:
    """Little north-east arrow that nudges every few seconds."""
    return (f'<g class="fb" style="animation:nudge 3.2s {delay:.2f}s infinite"><path d="M{x} {y + size}l{size}-{size}'
            f'M{x + 2} {y}h{size - 2}v{size - 2}" stroke="{colour}" stroke-width="1.8" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round"/></g>')


def write(name: str, content: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"  {OUT.relative_to(ROOT).as_posix()}/{name:<20} {len(content.encode()) / 1024:6.1f} KB")


# ------------------------------------------------------------------- data ---
def load_days() -> list[dict]:
    data = json.loads((ROOT / "data" / "contributions.json").read_text())
    return [{**d, "d": date.fromisoformat(d["date"])} for d in data["days"]]


def stats(days: list[dict]) -> dict:
    today = days[-1]["d"]
    by = {d["d"]: d["count"] for d in days}
    # current streak: ends today, or yesterday if today has nothing yet
    cur, day = 0, today if by.get(today) else today - timedelta(days=1)
    while by.get(day):
        cur, day = cur + 1, day - timedelta(days=1)
    best = run = 0
    for d in days:
        run = run + 1 if d["count"] else 0
        best = max(best, run)
    top = max(days, key=lambda d: d["count"])
    week = [0] * 7  # Mon..Sun
    for d in days:
        week[d["d"].weekday()] += d["count"]
    return {
        "total": sum(d["count"] for d in days),
        "active": sum(1 for d in days if d["count"]),
        "span": len(days),
        "current": cur, "longest": best,
        "busiest": top, "weekday": week,
    }


def months(days: list[dict]) -> list[tuple[str, str, int]]:
    last = days[-1]["d"]
    keys = []
    y, m = last.year, last.month
    for _ in range(12):
        keys.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    totals = OrderedDict((k, 0) for k in reversed(keys))
    for d in days:
        k = (d["d"].year, d["d"].month)
        if k in totals:
            totals[k] += d["count"]
    return [(date(y, m, 1).strftime("%b"), date(y, m, 1).strftime("%B %Y"), v) for (y, m), v in totals.items()]


def api(path: str):
    headers = {"User-Agent": "readme-cards", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def load_repos() -> list[dict]:
    """Public, non-fork repos with a 'tool' field. Cached in data/repos.json so a
    failed API call (rate limit, offline) falls back to yesterday's numbers."""
    cache = ROOT / "data" / "repos.json"
    try:
        raw = [r for r in api(f"/users/{USER}/repos?per_page=100&type=owner") if not r["fork"]]
        old = {r["name"]: r for r in json.loads(cache.read_text())} if cache.exists() else {}
        repos = []
        for r in raw:
            if r["name"].lower() == USER.lower():
                continue  # the profile repo itself
            tool = r["language"]
            if not tool:  # Power BI / Excel repos have no detectable language
                prev = old.get(r["name"])
                if prev and prev.get("pushed_at") == r["pushed_at"]:
                    tool = prev["tool"]
                else:
                    tree = api(f"/repos/{USER}/{r['name']}/git/trees/{r['default_branch']}?recursive=1")
                    paths = [t["path"].lower() for t in tree.get("tree", [])]
                    tool = ("Power BI" if any(p.endswith(".pbix") for p in paths) else
                            "Excel" if any(p.endswith((".xlsx", ".xlsm")) for p in paths) or "excel" in (r["description"] or "").lower()
                            else "Other")
            repos.append({"name": r["name"], "description": r["description"], "stars": r["stargazers_count"],
                          "language": r["language"], "tool": tool, "pushed_at": r["pushed_at"]})
        cache.write_text(json.dumps(repos, indent=1))
        return repos
    except Exception as e:
        print(f"  ! repo API failed ({e}); using cache")
        return json.loads(cache.read_text()) if cache.exists() else []


# ------------------------------------------------------------------ cards ---
def hero() -> str:
    W, H = 840, 330
    p = PROFILE
    portrait = (ROOT / "data" / "portrait.txt").read_text().rstrip("\n").split("\n")

    # terminal window with the portrait
    wx, wy, ww, wh = 520, 26, 294, 278
    inner = wh - 48
    lh = min(10.0, inner / len(portrait))
    fs = lh * 0.92
    cols = max(len(r) for r in portrait)
    px = wx + (ww - cols * fs * 0.6) / 2
    py = wy + 40 + (inner - len(portrait) * lh) / 2 + lh * 0.8

    def glyph_class(ch: str) -> str:
        return "pi" if ch in "@%#" else "pb" if ch in "*+=" else "pm"

    rows = []
    for i, row in enumerate(portrait):
        spans, cur, buf = [], None, ""
        for ch in row:
            k = "sp" if ch == " " else glyph_class(ch)
            if k != cur and buf:
                spans.append((cur, buf)); buf = ""
            cur = k; buf += ch
        if buf:
            spans.append((cur, buf))
        txt = "".join(escape(t) if k == "sp" else f'<tspan class="{k}">{escape(t)}</tspan>' for k, t in spans)
        rows.append(f'<text x="{px:.1f}" y="{py + i * lh:.1f}" class="m4 a" xml:space="preserve" '
                    f'font-size="{fs:.2f}" {anim("fade", 0.5 + i * 0.04, 0.25)}>{txt}</text>')

    shine = smil(
        '<animateTransform attributeName="gradientTransform" type="translate" '
        'values="-260 0;360 0;360 0" keyTimes="0;.3;1" dur="5s" begin="1.6s" repeatCount="indefinite"/>')
    body = f"""
<defs>
 <radialGradient id="glow" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(80 40) scale(520 300)">
  <stop offset="0" stop-color="{C['blue']}" stop-opacity=".16"/><stop offset="1" stop-color="{C['blue']}" stop-opacity="0"/>
 </radialGradient>
 <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="140" y2="0">
  <stop offset="0" stop-color="{C['blue']}"/><stop offset=".5" stop-color="{C['shine']}"/><stop offset="1" stop-color="{C['blue']}"/>
  {shine}
 </linearGradient>
</defs>
{frame(W, H)}
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="url(#glow)"/>
<text x="44" y="120" class="g7 a" font-size="66" fill="{C['ink']}" letter-spacing="-1.5" {anim('rise', 0.1, 0.8)}>{escape(p['first'])}</text>
<text x="44" y="188" class="g7 a shine-text" font-size="66" fill="url(#shine)" letter-spacing="-1.5" {anim('rise', 0.3, 0.8)}>{escape(p['last'])}</text>
<text x="48" y="234" class="g5 a" font-size="20" fill="{C['ink']}" {anim('rise', 0.5, 0.7)}>{escape(p['role'])}</text>
<text x="48" y="262" class="m4 a" font-size="12.5" fill="{C['muted']}" {anim('rise', 0.65, 0.7)}>{escape(p['stack'])}</text>
<g class="a" {anim('fade', 0.3, 0.6)}>
 <rect x="{wx}" y="{wy}" width="{ww}" height="{wh}" rx="10" fill="{C['panel']}" stroke="{C['line']}"/>
 <path d="M{wx} {wy + 28}h{ww}" stroke="{C['line']}"/>
 <circle cx="{wx + 16}" cy="{wy + 14}" r="4.5" fill="#ff5f57"/><circle cx="{wx + 31}" cy="{wy + 14}" r="4.5" fill="#febc2e"/><circle cx="{wx + 46}" cy="{wy + 14}" r="4.5" fill="#28c840"/>
 <text x="{wx + ww / 2}" y="{wy + 18}" text-anchor="middle" class="m4" font-size="11" fill="{C['muted']}">~/portrait.txt</text>
</g>
{''.join(rows)}"""
    css = f".pi{{fill:{C['ink']}}}.pb{{fill:{C['blue']}}}.pm{{fill:{C['muted']}}}"
    return svg(W, H, body, ["grotesk500", "grotesk700", "mono400"],
               f"{p['first']} {p['last']} - {p['role']}", css)


def heatmap(days: list[dict], st: dict) -> str:
    W, H = 840, 200
    heat = C["heat"]
    first = days[0]["d"]
    start = first - timedelta(days=(first.weekday() + 1) % 7)  # back to Sunday
    weeks = (days[-1]["d"] - start).days // 7 + 1
    x0, y0 = 46, 74
    step = (W - x0 - 22) / weeks
    cell = step - 3
    parts, seen = [], set()
    for d in days:
        w = (d["d"] - start).days // 7
        wd = (d["d"].weekday() + 1) % 7
        x, y = x0 + w * step, y0 + wd * step
        lv = d["level"]
        stroke = f' stroke="{C["faint"]}" stroke-width=".6"' if lv == 0 else ""
        parts.append(f'<rect class="c" x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.4" '
                     f'fill="{heat[lv]}"{stroke} style="animation-delay:{T_HEAT + 0.2 + w * 0.018 + wd * 0.006:.2f}s"/>')
        if d["d"].day <= 7 and wd == 0 and d["d"].month not in seen and w < weeks - 2:
            seen.add(d["d"].month)
            parts.append(f'<text x="{x:.1f}" y="{y0 - 9}" class="m4" font-size="10.5" fill="{C["muted"]}">'
                         f'{d["d"].strftime("%b")}</text>')
    for wd, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        parts.append(f'<text x="{x0 - 8}" y="{y0 + wd * step + cell - 2:.1f}" text-anchor="end" class="m4" '
                     f'font-size="9.5" fill="{C["muted"]}">{lab}</text>')
    lx = W - 24 - 34 - 5 * 15 - 34  # room for 'less' + 5 swatches + 'more'
    legend = "".join(f'<rect x="{lx + 34 + i * 15}" y="{H - 25}" width="11" height="11" rx="2" fill="{c}"'
                     f'{" stroke=%s" % repr(C["faint"]) if i == 0 else ""}/>' for i, c in enumerate(heat))
    body = f"""{frame(W, H)}
<g class="a" {anim('fade', T_HEAT, 0.5)}>
 <text x="24" y="36" class="g5" font-size="16" fill="{C['ink']}">Contribution graph</text>
 <text x="{W - 24}" y="36" text-anchor="end" class="m4" font-size="12" fill="{C['muted']}"><tspan fill="{C['blue']}" class="m7">{st['total']:,}</tspan> contributions in the last year</text>
</g>
{''.join(parts)}
<g class="a" {anim('fade', T_HEAT + 1.0, 0.5)}>
 <text x="{lx + 28}" y="{H - 16}" text-anchor="end" class="m4" font-size="10" fill="{C['muted']}">less</text>{legend}
 <text x="{lx + 34 + 5 * 15 + 2}" y="{H - 16}" class="m4" font-size="10" fill="{C['muted']}">more</text>
</g>"""
    css = ".c{transform-box:fill-box;transform-origin:center;animation:pop .35s both}"
    return svg(W, H, body, ["grotesk500", "mono400", "mono700"],
               f"{st['total']} contributions in the last year", css)


def activity(days: list[dict], st: dict) -> str:
    W, H = 840, 290
    ms = months(days)
    peak = max(v for _, _, v in ms) or 1
    best_i = max(range(len(ms)), key=lambda i: ms[i][2])
    base, top, x0, step, bw = 236, 92, 34, 40.5, 26
    parts = []
    for i, (lab, _, v) in enumerate(ms):
        h = max(3, (base - top) * v / peak)
        x = x0 + i * step
        fill = C["blue"] if i == best_i else C["faint"]
        parts.append(f'<rect class="fbb a" x="{x}" y="{base - h:.1f}" width="{bw}" height="{h:.1f}" rx="4" fill="{fill}" '
                     f'{anim("grow", T_BARS + 0.25 + i * 0.06, 0.7)}/>')
        parts.append(f'<text x="{x + bw / 2}" y="{base + 20}" text-anchor="middle" class="m4" font-size="10.5" '
                     f'fill="{C["blue"] if i == best_i else C["muted"]}">{lab}</text>')
        if i == best_i:
            parts.append(f'<text class="fbb a m7" x="{x + bw / 2}" y="{base - h - 9:.1f}" text-anchor="middle" font-size="13" '
                         f'fill="{C["blue"]}" {anim("pop", T_BARS + 1.2, 0.45)}>{v}</text>')
    b = st["busiest"]
    tiles = [
        (str(st["current"]), "day streak now"),
        (str(st["longest"]), "longest streak"),
        (f"{st['active']}", f"active days of {st['span']}"),
        (str(b["count"]), f"busiest day · {b['d'].strftime('%b %d')}"),
    ]
    sx, sy = 548, 72
    for i, (num, lab) in enumerate(tiles):
        cx, cy = sx + (i % 2) * 138, sy + (i // 2) * 96
        parts.append(f'<g class="a" {anim("rise", T_BARS + 0.5 + i * 0.12, 0.6)}>'
                     f'<rect x="{cx}" y="{cy}" width="128" height="84" rx="10" fill="{C["panel"]}" stroke="{C["line"]}"/>'
                     f'<text x="{cx + 14}" y="{cy + 44}" class="g7" font-size="30" fill="{C["ink"]}">{num}</text>'
                     f'<text x="{cx + 14}" y="{cy + 66}" class="m4" font-size="10" fill="{C["muted"]}">{escape(lab)}</text></g>')
    body = f"""{frame(W, H)}
<g class="a" {anim('fade', T_BARS, 0.5)}>
 <text x="24" y="38" class="g5" font-size="16" fill="{C['ink']}">Contributions per month</text>
 <text x="24" y="58" class="m4" font-size="11.5" fill="{C['muted']}">best month: <tspan fill="{C['blue']}">{ms[best_i][1]}</tspan> · {ms[best_i][2]} contributions</text>
 <path d="M{x0 - 6} {base}H{x0 + 12 * step - 8}" stroke="{C['line']}"/>
</g>
{''.join(parts)}"""
    return svg(W, H, body, ["grotesk500", "grotesk700", "mono400", "mono700"],
               f"Contributions per month; current streak {st['current']} days, longest {st['longest']}")


def tile(i: int, slug: str, label: str, accent: str, value: float, fmt: str, caption: str) -> str:
    W, H = 270, 200
    ac = C[accent]
    t0 = T_TILES + i * 0.22
    frames_n, fd = 18, 0.05
    t_count = t0 + 0.45
    counts = []
    for k in range(1, frames_n + 1):
        v = value * (1 - (1 - k / frames_n) ** 3)  # ease-out
        final = k == frames_n
        txt = escape(fmt.format(value if final else v))
        if STATIC:
            if final:
                counts.append(f'<text x="22" y="122" class="g7" font-size="54" fill="{C["ink"]}" letter-spacing="-1">{txt}</text>')
            continue
        begin = t_count + (k - 1) * fd
        setter = (f'<set attributeName="visibility" to="visible" begin="{begin:.2f}s" fill="freeze"/>' if final else
                  f'<set attributeName="visibility" to="visible" begin="{begin:.2f}s" dur="{fd}s"/>')
        cls = "cnt-final" if final else "cnt"
        counts.append(f'<text x="22" y="122" class="g7 {cls}" font-size="54" fill="{C["ink"]}" letter-spacing="-1" '
                      f'visibility="hidden">{txt}{setter}</text>')
    cap = textwrap.wrap(caption, 32)[:2]
    cap_svg = "".join(f'<text x="22" y="{152 + j * 17}" class="m4" font-size="11.5" fill="{C["muted"]}">{escape(c)}</text>'
                      for j, c in enumerate(cap))
    body = f"""<defs>
 <clipPath id="clip-{slug}"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14"/></clipPath>
 <linearGradient id="sh-{slug}" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".10"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
 <radialGradient id="gl-{slug}" cx="1" cy="0" r="1"><stop offset="0" stop-color="{ac}" stop-opacity=".22"/><stop offset="1" stop-color="{ac}" stop-opacity="0"/></radialGradient>
</defs>
<g class="a" style="transform-box:view-box;transform-origin:50% 100%;animation:swing 1.1s {t0:.2f}s both cubic-bezier(.3,.7,.3,1)">
 <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="{C['panel']}" stroke="{ac}" stroke-opacity=".45"/>
 <rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="url(#gl-{slug})"/>
 <rect x="22" y="22" width="{len(label) * 8.4 + 20:.0f}" height="22" rx="11" fill="{ac}" fill-opacity=".14"/>
 <text x="32" y="37" class="m7" font-size="11.5" letter-spacing="1.2" fill="{ac}">{escape(label)}</text>
 <circle class="fb pulse-fx" cx="{W - 30}" cy="33" r="9" fill="none" stroke="{ac}" stroke-width="1.5" style="animation:pulse 2.4s {t0 + 1.2:.2f}s infinite ease-out"/>
 <g class="fb" style="animation:nudge 3s {t0 + 1.6:.2f}s infinite">
  <circle cx="{W - 30}" cy="33" r="13" fill="{ac}" fill-opacity=".14"/>
  <path d="M{W - 35} 38l10-10M{W - 33} 28h8v8" stroke="{ac}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
 </g>
 {''.join(counts)}
 {cap_svg}
 <rect x="22" y="{H - 8}" width="{W - 44}" height="2" rx="1" fill="{ac}" fill-opacity=".5"/>
 <g clip-path="url(#clip-{slug})"><rect class="shine-fx" x="0" y="-20" width="110" height="{H + 40}" fill="url(#sh-{slug})" style="animation:sweep 6s {t0 + 1.4:.2f}s infinite ease-in-out"/></g>
</g>"""
    return svg(W, H, body, ["grotesk700", "mono400", "mono700"], f"{label}: {fmt.format(value)} {caption}")


def section(slug: str, title: str, sub: str, delay: float) -> str:
    """Slim heading strip that introduces a group of cards."""
    W, H = 840, 64
    body = f"""<g class="a" {anim('rise', delay, 0.6)}>
<rect x="0" y="30" width="4" height="22" rx="2" fill="{C['blue']}"/>
<text x="16" y="48" class="g7" font-size="21" fill="{C['ink']}">{escape(title)}</text>
<text x="{W}" y="48" text-anchor="end" class="m4" font-size="11.5" fill="{C['muted']}">{escape(sub)}</text>
<rect class="fbl a" x="16" y="60" width="{W - 16}" height="1" fill="{C['line']}" {anim('growx', delay + 0.2, 0.9)}/>
</g>"""
    return svg(W, H, body, ["grotesk700", "mono400"], f"{title}. {sub}")


def dash_card(i: int, d: dict) -> str:
    W, H = 270, 222
    t0 = T_GALLERY + i * 0.14
    tx, ty, tw, th = 10, 10, 250, 141
    b64 = base64.b64encode((ROOT / "data" / "thumbs" / f"{d['slug']}.jpg").read_bytes()).decode()
    live = bool(d.get("live"))
    badge = ""
    if live:
        badge = f"""<g>
 <rect x="{tx + 10}" y="{ty + 10}" width="52" height="20" rx="10" fill="#0d1117" fill-opacity=".78"/>
 <circle cx="{tx + 22}" cy="{ty + 20}" r="3.5" fill="#3fb950"/>
 <circle class="fb pulse-fx" cx="{tx + 22}" cy="{ty + 20}" r="3.5" fill="none" stroke="#3fb950" stroke-width="1.4" style="animation:pulse 1.8s {t0 + 1:.2f}s infinite ease-out"/>
 <text x="{tx + 31}" y="{ty + 24}" class="m7" font-size="9.5" letter-spacing=".8" fill="#ffffff">LIVE</text>
</g>"""
    action = "open live dashboard" if live else "view repository"
    body = f"""<defs><clipPath id="th-{d['slug']}"><rect x="{tx}" y="{ty}" width="{tw}" height="{th}" rx="8"/></clipPath></defs>
<g class="a" {anim('rise', t0, 0.7)}>
{frame(W, H, 14, C['panel'])}
<g clip-path="url(#th-{d['slug']})">
 <image x="{tx}" y="{ty}" width="{tw}" height="{th}" preserveAspectRatio="xMidYMid slice" href="data:image/jpeg;base64,{b64}"/>
 <rect class="fbr fx" x="{tx}" y="{ty}" width="{tw}" height="{th}" fill="{C['faint']}" style="animation:wipe .9s {t0 + 0.25:.2f}s both cubic-bezier(.7,0,.2,1);transform:scaleX(0)"/>
</g>
<rect x="{tx + .5}" y="{ty + .5}" width="{tw - 1}" height="{th - 1}" rx="8" fill="none" stroke="{C['line']}"/>
{badge}
<text x="14" y="{ty + th + 26}" class="g7" font-size="15" fill="{C['ink']}">{escape(d['title'])}</text>
<text x="14" y="{ty + th + 44}" class="m4" font-size="10.2" fill="{C['muted']}">{escape(d['caption'])}</text>
<text x="14" y="{ty + th + 62}" class="m4" font-size="9.5" fill="{C['blue']}">{escape(d['tag'].upper())} · {action}</text>
{arrow(W - 28, ty + th + 14, C['blue'], t0 + 1.4)}
</g>"""
    return svg(W, H + 10, body, ["grotesk700", "mono400", "mono700"],
               f"{d['title']} Power BI dashboard: {d['caption']}")


def donut_segments(cx: float, cy: float, r: float, items: list[tuple[str, int, str]], delay: float, sw: float) -> str:
    total = sum(v for _, v, _ in items) or 1
    circ = 2 * 3.14159265 * r
    out, acc = [], 0.0
    for k, (_, v, col) in enumerate(items):
        seg = circ * v / total
        gap = 2.5 if len(items) > 1 else 0
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-width="{sw}" '
            f'stroke-dasharray="{max(seg - gap, 0.1):.2f} {circ:.2f}" stroke-dashoffset="{-acc:.2f}" '
            f'transform="rotate(-90 {cx} {cy})" class="a" {anim("fade", delay + k * 0.15, 0.5)}/>')
        acc += seg
    return "".join(out)


def report(st: dict, repos: list[dict], n_dash_live: int) -> str:
    W, H = 840, 380
    tools = Counter(r["tool"] for r in repos)
    palette = {"Power BI": "#f2c811", "Python": C["blue"], "Excel": "#21a366", "JavaScript": "#f1e05a",
               "TypeScript": "#3178c6", "HTML": "#e34c26", "C#": "#53b453", "PowerShell": C["purple"], "Other": C["muted"]}
    ranked = tools.most_common()
    if len(ranked) > 6:  # keep the legend honest: top 5 named tools + everything else as Other
        named = [(t, n) for t, n in ranked if t != "Other"][:5]
        other = len(repos) - sum(n for _, n in named)
        ranked = named + [("Other", other)]
    items = [(t, n, palette.get(t, C["teal"])) for t, n in ranked]
    pbi = tools.get("Power BI", 0)
    stars = sum(r["stars"] for r in repos)
    refreshed = date.today().strftime("%d %b %Y")
    x0 = 70  # right of the nav rail

    # nav rail (Power BI-style page icons)
    rail = [f'<path d="M17 1h39v{H - 2}H17a16 16 0 0 1-16-16V17A16 16 0 0 1 17 1z" fill="{C["rail"]}"/>',
            f'<path d="M56 1v{H - 2}" stroke="{C["line"]}"/>']
    icons = ["M-6 4v-6M0 4v-10M6 4v-3", "M-6-5h12v10h-12z", "M-6 5a6 6 0 0 1 12 0M0-6v6", "M-6-3h12M-6 2h8"]
    for k, dpath in enumerate(icons):
        y = 40 + k * 44
        on = k == 0
        rail.append(f'<rect x="12" y="{y - 14}" width="32" height="28" rx="7" fill="{C["blue"] if on else "none"}" fill-opacity=".16"/>'
                    f'<path transform="translate(28 {y})" d="{dpath}" stroke="{C["blue"] if on else C["muted"]}" '
                    f'stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')

    def chip(x: float, label: str) -> str:
        w = len(label) * 6.6 + 34
        return (f'<rect x="{x}" y="22" width="{w:.0f}" height="26" rx="6" fill="{C["panel"]}" stroke="{C["line"]}"/>'
                f'<text x="{x + 10}" y="39" class="m4" font-size="10.5" fill="{C["ink"]}">{escape(label)}</text>'
                f'<path d="M{x + w - 17} 33l4 4 4-4" stroke="{C["muted"]}" stroke-width="1.5" fill="none" stroke-linecap="round"/>'), w

    c1, w1 = chip(0, "Last 12 months")
    c2, w2 = chip(0, "All repositories")
    chips = (f'<g transform="translate({W - 24 - w1 - w2 - 10:.0f} 0)">{c1}</g>'
             f'<g transform="translate({W - 24 - w2:.0f} 0)">{c2}</g>')

    kpis = [(str(len(repos)), "public repositories", C["blue"]),
            (str(pbi), "Power BI reports", "#f2c811"),
            (str(n_dash_live), "live dashboards", "#3fb950"),
            (f"{st['total']:,}", "contributions / yr", C["purple"])]
    kw = (W - x0 - 24 - 3 * 12) / 4
    kpi_svg = []
    for k, (num, lab, col) in enumerate(kpis):
        kx = x0 + k * (kw + 12)
        kpi_svg.append(f'<g class="a" {anim("rise", T_REPORT + 0.25 + k * 0.1, 0.6)}>'
                       f'<rect x="{kx:.1f}" y="66" width="{kw:.1f}" height="80" rx="8" fill="{C["panel"]}" stroke="{C["line"]}"/>'
                       f'<rect x="{kx:.1f}" y="66" width="4" height="80" rx="2" fill="{col}"/>'
                       f'<text x="{kx + 18:.1f}" y="107" class="g7" font-size="30" fill="{C["ink"]}">{num}</text>'
                       f'<text x="{kx + 18:.1f}" y="130" class="m4" font-size="10.5" fill="{C["muted"]}">{escape(lab)}</text></g>')

    # visual 1: donut of repos by tool
    vy, vh = 160, H - 160 - 18
    v1w = 330
    cx, cy, r = x0 + 92, vy + 40 + (vh - 40) / 2, 58
    legend = []
    for k, (t, n, col) in enumerate(items[:6]):
        ly = vy + 58 + k * 22
        legend.append(f'<g class="a" {anim("fade", T_REPORT + 0.8 + k * 0.1, 0.4)}>'
                      f'<rect x="{x0 + 178}" y="{ly - 9}" width="10" height="10" rx="2.5" fill="{col}"/>'
                      f'<text x="{x0 + 196}" y="{ly}" class="m4" font-size="10.5" fill="{C["ink"]}">{escape(t)}</text>'
                      f'<text x="{x0 + v1w - 14}" y="{ly}" text-anchor="end" class="m7" font-size="10.5" fill="{C["muted"]}">{n}</text></g>')
    v1 = (f'<rect x="{x0}" y="{vy}" width="{v1w}" height="{vh}" rx="8" fill="{C["panel"]}" stroke="{C["line"]}"/>'
          f'<text x="{x0 + 16}" y="{vy + 26}" class="g5" font-size="13" fill="{C["ink"]}">Repositories by tool</text>'
          f'<text x="{x0 + v1w - 16}" y="{vy + 26}" text-anchor="end" class="m4" font-size="12" fill="{C["muted"]}">...</text>'
          + donut_segments(cx, cy, r, items, T_REPORT + 0.5, 18)
          + f'<text x="{cx}" y="{cy + 6}" text-anchor="middle" class="g7" font-size="24" fill="{C["ink"]}">{len(repos)}</text>'
          f'<text x="{cx}" y="{cy + 22}" text-anchor="middle" class="m4" font-size="9" fill="{C["muted"]}">repos</text>'
          + "".join(legend))

    # visual 2: contributions by weekday
    v2x = x0 + v1w + 12
    v2w = W - 24 - v2x
    wk = st["weekday"]
    peak = max(wk) or 1
    best = wk.index(max(wk))
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    base_y, top_y = vy + vh - 34, vy + 58
    bw = 30
    gap = (v2w - 40 - 7 * bw) / 6
    bars = []
    for k, v in enumerate(wk):
        bx = v2x + 20 + k * (bw + gap)
        bh = max(3, (base_y - top_y) * v / peak)
        col = C["blue"] if k == best else C["faint"]
        bars.append(f'<rect class="fbb a" x="{bx:.1f}" y="{base_y - bh:.1f}" width="{bw}" height="{bh:.1f}" rx="4" fill="{col}" '
                    f'{anim("grow", T_REPORT + 0.6 + k * 0.07, 0.6)}/>'
                    f'<text x="{bx + bw / 2:.1f}" y="{base_y - bh - 7:.1f}" text-anchor="middle" class="m4 a" font-size="9.5" '
                    f'fill="{C["blue"] if k == best else C["muted"]}" {anim("fade", T_REPORT + 1.1 + k * 0.07, 0.4)}>{v}</text>'
                    f'<text x="{bx + bw / 2:.1f}" y="{base_y + 18}" text-anchor="middle" class="m4" font-size="10" '
                    f'fill="{C["blue"] if k == best else C["muted"]}">{names[k]}</text>')
    v2 = (f'<rect x="{v2x}" y="{vy}" width="{v2w}" height="{vh}" rx="8" fill="{C["panel"]}" stroke="{C["line"]}"/>'
          f'<text x="{v2x + 16}" y="{vy + 26}" class="g5" font-size="13" fill="{C["ink"]}">Contributions by weekday</text>'
          f'<text x="{v2x + v2w - 16}" y="{vy + 26}" text-anchor="end" class="m4" font-size="10.5" fill="{C["muted"]}">peak: <tspan fill="{C["blue"]}">{names[best]}</tspan></text>'
          f'<path d="M{v2x + 14} {base_y}H{v2x + v2w - 14}" stroke="{C["line"]}"/>' + "".join(bars))

    body = f"""{frame(W, H)}
<g class="a" {anim('fade', T_REPORT, 0.5)}>{''.join(rail)}</g>
<g class="a" {anim('fade', T_REPORT + 0.1, 0.5)}>
 <text x="{x0}" y="36" class="g7" font-size="18" fill="{C['ink']}">GitHub Analytics Report</text>
 <text x="{x0}" y="54" class="m4" font-size="10.5" fill="{C['muted']}">Page 1 of 1 · data refreshed {refreshed}</text>
 {chips}
</g>
{''.join(kpi_svg)}
<g class="a" {anim('rise', T_REPORT + 0.4, 0.6)}>{v1}</g>
<g class="a" {anim('rise', T_REPORT + 0.5, 0.6)}>{v2}</g>"""
    return svg(W, H, body, ["grotesk500", "grotesk700", "mono400", "mono700"],
               f"GitHub analytics report: {len(repos)} repositories, {pbi} Power BI reports, "
               f"{st['total']} contributions; busiest weekday {names[best]}")


def repo_card(i: int, name: str, fallback: dict, repos: dict) -> str:
    W, H = 410, 150
    info = repos.get(name, {})
    desc = info.get("description") or fallback.get("desc") or ""
    lang = fallback.get("lang") or info.get("language") or ""
    stars = info.get("stars", 0)
    t0 = T_REPOS + i * 0.15
    lines = textwrap.wrap(desc, 52)
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] = lines[1][:49].rstrip() + "..."
    desc_svg = "".join(f'<text x="22" y="{74 + j * 18}" class="g5" font-size="13" fill="{C["muted"]}">{escape(l)}</text>'
                       for j, l in enumerate(lines))
    title = name if len(name) <= 38 else name[:36] + "..."
    meta_x = 22
    meta = ""
    if lang:
        meta += (f'<circle cx="{meta_x + 5}" cy="{H - 27}" r="5" fill="{LANG.get(lang, C["muted"])}"/>'
                 f'<text x="{meta_x + 16}" y="{H - 23}" class="m4" font-size="11" fill="{C["muted"]}">{escape(lang)}</text>')
        meta_x += 16 + len(lang) * 6.7 + 18
    meta += (f'<path transform="translate({meta_x} {H - 34}) scale(.75)" fill="{C["muted"]}" d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"/>'
             f'<text x="{meta_x + 16}" y="{H - 23}" class="m4" font-size="11" fill="{C["muted"]}">{stars}</text>')
    body = f"""<g class="a" {anim('rise', t0, 0.7)}>
{frame(W, H, 12, C['panel'])}
<path transform="translate(22 24)" fill="{C['muted']}" d="M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.25.25 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z"/>
<text x="46" y="37" class="g7" font-size="15.5" fill="{C['blue']}">{escape(title)}</text>
{desc_svg}
{meta}
{arrow(W - 30, 25, C['muted'], t0 + 1.5)}
</g>"""
    # 10px transparent margin below so stacked rows of cards don't touch
    return svg(W, H + 10, body, ["grotesk500", "grotesk700", "mono400"], f"{name}: {desc}")


def stack_card() -> str:
    W, gap = 840, 14
    spans = [2 if len(items) > 3 else 1 for _, _, items in STACK]
    unit = (W - 48 - (sum(spans) - 1) * gap) / sum(spans)
    rows_max = max(-(-len(items) // sp) for (_, _, items), sp in zip(STACK, spans))
    H = 92 + rows_max * 38 + 14
    parts, n, gx = [], 0, 24.0
    for c, ((group, accent, items), sp) in enumerate(zip(STACK, spans)):
        ac = C[accent]
        gw = unit * sp + gap * (sp - 1)
        parts.append(f'<g class="a" {anim("fade", T_STACK + c * 0.08, 0.5)}>'
                     f'<text x="{gx:.1f}" y="78" class="m7" font-size="11" letter-spacing="1.4" fill="{ac}">{group}</text>'
                     f'<rect x="{gx:.1f}" y="86" width="{gw:.1f}" height="1" fill="{C["line"]}"/></g>')
        base_x = gx
        for k, (mono, name, col) in enumerate(items):
            gx = base_x + (k % sp) * (unit + gap)
            col_w = unit
            y = 98 + (k // sp) * 38
            dark_text = col.lower() in ("#f2c811", "#f1e05a")
            parts.append(f'<g class="a" {anim("lit", T_STACK + 0.3 + n * 0.06, 0.45)}>'
                         f'<rect x="{gx}" y="{y}" width="{col_w:.1f}" height="30" rx="8" fill="{C["panel"]}" stroke="{C["line"]}"/>'
                         f'<rect x="{gx + 5}" y="{y + 5}" width="20" height="20" rx="5" fill="{col}"/>'
                         f'<text x="{gx + 15}" y="{y + 19}" text-anchor="middle" class="m7" font-size="9" '
                         f'fill="{"#1f2328" if dark_text else "#ffffff"}">{escape(mono)}</text>'
                         f'<text x="{gx + 34}" y="{y + 19.5}" class="g5" font-size="12.5" fill="{C["ink"]}">{escape(name)}</text></g>')
            n += 1
        gx = base_x + gw + gap
    body = f"""{frame(W, H)}
<g class="a" {anim('fade', T_STACK, 0.5)}>
 <text x="24" y="40" class="g7" font-size="18" fill="{C['ink']}">Toolkit</text>
 <text x="{W - 24}" y="40" text-anchor="end" class="m4" font-size="11" fill="{C['muted']}">what I use to go from raw data to decisions</text>
</g>
{''.join(parts)}"""
    names = ", ".join(nm for _, _, items in STACK for _, nm, _ in items)
    return svg(W, H, body, ["grotesk500", "grotesk700", "mono400", "mono700"], f"Toolkit: {names}")


def contact_card() -> str:
    W, H = 840, 170
    # tiny rising chart motif on the right
    pts = [(0, 52), (34, 44), (68, 48), (102, 30), (136, 34), (170, 14), (204, 4)]
    ox, oy = W - 260, 52
    path = "M" + " L".join(f"{ox + x} {oy + y}" for x, y in pts)
    dots = "".join(f'<circle class="fb a" cx="{ox + x}" cy="{oy + y}" r="3.5" fill="{C["blue"]}" '
                   f'{anim("pop", T_CONTACT + 0.5 + k * 0.1, 0.4)}/>' for k, (x, y) in enumerate(pts))
    plen = 230
    body = f"""<defs><radialGradient id="cg" cx="1" cy="1" r="1"><stop offset="0" stop-color="{C['purple']}" stop-opacity=".18"/><stop offset="1" stop-color="{C['purple']}" stop-opacity="0"/></radialGradient></defs>
{frame(W, H)}
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="url(#cg)"/>
<text x="36" y="76" class="g7 a" font-size="32" fill="{C['ink']}" letter-spacing="-.6" {anim('rise', T_CONTACT, 0.7)}>{escape(CONTACT['headline'])}</text>
<text x="38" y="110" class="m4 a" font-size="12.5" fill="{C['muted']}" {anim('rise', T_CONTACT + 0.15, 0.7)}>{escape(CONTACT['sub'])}</text>
<path d="{path}" fill="none" stroke="{C['blue']}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"
 stroke-dasharray="{plen}" style="stroke-dashoffset:0;animation:draw 1.4s {T_CONTACT + 0.3:.2f}s both ease-out"/>
{dots}
<path d="{path} L{ox + 204} {oy + 70} L{ox} {oy + 70}Z" fill="{C['blue']}" fill-opacity=".08" class="a" {anim('fade', T_CONTACT + 1.2, 0.8)}/>"""
    css = f"@keyframes draw{{from{{stroke-dashoffset:{plen}}}to{{stroke-dashoffset:0}}}}"
    return svg(W, H, body, ["grotesk700", "mono400"], f"{CONTACT['headline']} {CONTACT['sub']}", css)


ICONS = {
    "in": lambda x, y, c: (f'<rect x="{x}" y="{y}" width="26" height="26" rx="6" fill="#0a66c2"/>'
                           f'<text x="{x + 13}" y="{y + 18.5}" text-anchor="middle" class="m7" font-size="13" fill="#fff">in</text>'),
    "mail": lambda x, y, c: (f'<rect x="{x}" y="{y}" width="26" height="26" rx="6" fill="{c}" fill-opacity=".16"/>'
                             f'<path d="M{x + 6} {y + 8}h14v10h-14zM{x + 6} {y + 8}l7 6 7-6" stroke="{c}" stroke-width="1.6" '
                             f'fill="none" stroke-linejoin="round"/>'),
    "globe": lambda x, y, c: (f'<rect x="{x}" y="{y}" width="26" height="26" rx="6" fill="{c}" fill-opacity=".16"/>'
                              f'<circle cx="{x + 13}" cy="{y + 13}" r="7" stroke="{c}" stroke-width="1.6" fill="none"/>'
                              f'<path d="M{x + 6} {y + 13}h14M{x + 13} {y + 6}c-4 4-4 10 0 14M{x + 13} {y + 6}c4 4 4 10 0 14" '
                              f'stroke="{c}" stroke-width="1.4" fill="none"/>'),
}


def button(i: int, slug: str, label: str, detail: str, icon: str) -> str:
    W, H = 270, 72
    t0 = T_CONTACT + 0.5 + i * 0.12
    ac = [C["blue"], C["purple"], C["teal"]][i % 3]
    d = detail if len(detail) <= 30 else detail[:28] + "..."
    body = f"""<g class="a" {anim('rise', t0, 0.6)}>
{frame(W, H, 12, C['panel'])}
<rect x="0.5" y="{H - 3}" width="{W - 1}" height="2.5" rx="1" fill="{ac}" fill-opacity=".55"/>
{ICONS[icon](18, 23, ac)}
<text x="56" y="34" class="g7" font-size="15" fill="{C['ink']}">{escape(label)}</text>
<text x="56" y="52" class="m4" font-size="10" fill="{C['muted']}">{escape(d)}</text>
{arrow(W - 32, 28, ac, t0 + 1.2)}
</g>"""
    return svg(W, H, body, ["grotesk700", "mono400", "mono700"], f"{label}: {detail}")


# ------------------------------------------------------------------- main ---
def main() -> None:
    global OUT
    days = load_days()
    st = stats(days)
    repos = load_repos()
    by_name = {r["name"]: r for r in repos}
    dashes = json.loads((ROOT / "data" / "dashboards.json").read_text(encoding="utf-8"))
    n_live = sum(1 for d in dashes if d.get("live"))
    print(f"Rendering cards ({'STATIC' if STATIC else 'animated'}): {st['total']} contributions, "
          f"streak {st['current']}/{st['longest']}, {len(repos)} repos")
    for theme, out in (("dark", ROOT / "cards"), ("light", ROOT / "cards" / "light")):
        C.clear()
        C.update(THEMES[theme])
        OUT = out
        write("hero.svg", hero())
        write("heatmap.svg", heatmap(days, st))
        write("activity.svg", activity(days, st))
        for i, t in enumerate(TILES):
            write(f"tile-{t[0]}.svg", tile(i, *t))
        write("sec-dashboards.svg", section("dashboards", "Power BI dashboards",
                                            f"{n_live} live · click a card to open it", T_GALLERY - 0.2))
        for i, d in enumerate(dashes):
            write(f"dash-{d['slug']}.svg", dash_card(i, d))
        write("report.svg", report(st, repos, n_live))
        write("sec-projects.svg", section("projects", "Python, ML & tools", "selected repositories", T_REPOS - 0.2))
        for i, (name, fb) in enumerate(FEATURED):
            write(f"repo-{i + 1}.svg", repo_card(i, name, fb, by_name))
        write("stack.svg", stack_card())
        write("contact.svg", contact_card())
        for i, b in enumerate(CONTACT["buttons"]):
            write(f"btn-{b[0]}.svg", button(i, *b))


if __name__ == "__main__":
    main()
