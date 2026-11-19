"""Render the animated SVG cards for the GitHub profile README into cards/.

Reads data/contributions.json (refreshed daily by the GitHub Action) and
data/portrait.txt, embeds subset fonts as base64 WOFF, and writes:

  cards/hero.svg       name, role, status + ASCII portrait that prints in
  cards/heatmap.svg    contribution graph in brand blue
  cards/activity.svg   contributions per month + streak stats
  cards/tile-*.svg     three linked stat tiles (count-up, swing-in, shine)
  cards/repo-*.svg     one card per featured repo

Everything shown through <img> must be self-contained: inline <style> with
CSS keyframes, SMIL, embedded fonts. No scripts, no external requests.

  STATIC=1 python scripts/render_readme_cards.py   -> final frame only (for screenshots)
"""
from __future__ import annotations

import base64
import json
import os
import textwrap
import urllib.request
from collections import OrderedDict
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
STATIC = os.environ.get("STATIC") == "1"
USER = os.environ.get("GH_USER", "KarthickRaja46")

# ---------------------------------------------------------------- profile ---
PROFILE = {
    "first": "Karthick",
    "last": "Raja",
    "greeting": "> hello, world. i'm",
    "role": "Data Analyst & Power BI Developer",
    "stack": "SQL · Python · DAX · Power BI · ETL pipelines",
    "status": "Open to Data Analyst roles · Dubai, UAE",
}

TILES = [  # (slug, label, accent, value, format, caption)
    ("sql", "SQL", "blue", 40, "{:.0f}+", "SQL queries for KPI reporting, latency analysis & alerting"),
    ("powerbi", "POWER BI", "purple", 2.3, "${:.1f}M", "in sales analysed across 5-page Power BI dashboards"),
    ("python", "PYTHON", "teal", 100, "{:.0f}K+", "records through validated Python ETL pipelines"),
]

FEATURED = [  # repo name -> fallbacks used when the API has no value
    ("API-Performance-Monitoring-Analytics", {"lang": "Python"}),
    ("Business-Performance-Customer-Intelligence", {"lang": "Power BI"}),
    ("Banking-Performance-Analytics", {"lang": "Power BI"}),
    ("Real-Estate-Price-Prediction", {"lang": "Python"}),
]

# ------------------------------------------------------------------ theme ---
C = {
    "bg": "#0d1117", "panel": "#161b22", "line": "#30363d", "ink": "#e6edf3",
    "muted": "#8b949e", "faint": "#2d333b",
    "blue": "#70a5fd", "purple": "#bf91f3", "teal": "#38bdae",
}
HEAT = ["#161b22", "#1d3459", "#2b5597", "#4a7fd8", "#70a5fd"]
LANG = {"Python": "#3572A5", "Power BI": "#F2C811", "SQL": "#e38c00", "C#": "#178600",
        "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "HTML": "#e34c26"}

# Page timeline (seconds): cards play top to bottom.
T_HERO, T_HEAT, T_BARS, T_TILES, T_REPOS = 0.0, 1.9, 3.1, 4.4, 5.6

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
@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}
@keyframes pulse{0%{transform:scale(1);opacity:.7}100%{transform:scale(3.2);opacity:0}}
@keyframes nudge{0%,70%,100%{transform:none}80%{transform:translate(3px,-3px)}90%{transform:translate(-1px,1px)}}
@keyframes swing{0%{opacity:0;transform:translateY(70px) rotate(-9deg)}
 55%{opacity:1;transform:translateY(-8px) rotate(2.5deg)}75%{transform:translateY(3px) rotate(-1deg)}100%{opacity:1;transform:none}}
@keyframes sweep{0%{transform:translateX(-200px) skewX(-20deg)}22%,100%{transform:translateX(480px) skewX(-20deg)}}
.fb{transform-box:fill-box;transform-origin:center}
.fbb{transform-box:fill-box;transform-origin:50% 100%}
"""
FREEZE_CSS = """
*{animation:none!important}
.cnt{visibility:hidden!important}.cnt-final{visibility:visible!important}
.shine-fx,.pulse-fx{display:none!important}
.shine-text{fill:%s!important}
""" % C["blue"]


def svg(w: int, h: int, body: str, fonts: list[str], title: str, extra_css: str = "") -> str:
    faces = "".join(font_face(f) for f in fonts)
    freeze = FREEZE_CSS if STATIC else f"@media (prefers-reduced-motion:reduce){{{FREEZE_CSS}}}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
            f"<style>{faces}{BASE_CSS}{extra_css}{freeze}</style>{body}</svg>")


def anim(name: str, delay: float, dur: float, extra: str = "") -> str:
    return f'style="animation:{name} {dur}s {delay:.3f}s both{(" " + extra) if extra else ""}"'


def smil(markup: str) -> str:
    """SMIL is dropped entirely in STATIC mode so the file shows its end state."""
    return "" if STATIC else markup


def frame(w: int, h: int, r: int = 16, fill: str = C["bg"]) -> str:
    return (f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{r}" '
            f'fill="{fill}" stroke="{C["line"]}"/>')


def write(name: str, content: str) -> None:
    CARDS.mkdir(exist_ok=True)
    (CARDS / name).write_text(content, encoding="utf-8")
    print(f"  cards/{name:<22} {len(content.encode()) / 1024:6.1f} KB")


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
    return {
        "total": sum(d["count"] for d in days),
        "active": sum(1 for d in days if d["count"]),
        "span": len(days),
        "current": cur, "longest": best,
        "busiest": top,
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


def fetch_repo(name: str) -> dict:
    url = f"https://api.github.com/repos/{USER}/{name}"
    headers = {"User-Agent": "readme-cards", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return json.load(r)
    except Exception as e:  # offline or rate limited: fall back to config
        print(f"  ! {name}: {e}")
        return {}


# ------------------------------------------------------------------ cards ---
def hero() -> str:
    W, H = 840, 330
    p = PROFILE
    portrait = (ROOT / "data" / "portrait.txt").read_text().rstrip("\n").split("\n")

    # terminal window with the portrait
    wx, wy, ww, wh = 520, 26, 294, 278
    lh, fs = 10.0, 9.2
    cols = max(len(r) for r in portrait)
    px = wx + (ww - cols * fs * 0.6) / 2
    py = wy + 40 + (wh - 48 - len(portrait) * lh) / 2

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
        inner = "".join(escape(t) if k == "sp" else f'<tspan class="{k}">{escape(t)}</tspan>' for k, t in spans)
        rows.append(f'<text x="{px:.1f}" y="{py + i * lh:.1f}" class="m4 a" xml:space="preserve" '
                    f'font-size="{fs}" {anim("fade", 0.5 + i * 0.045, 0.25)}>{inner}</text>')

    shine = smil(
        '<animateTransform attributeName="gradientTransform" type="translate" '
        'values="-260 0;360 0;360 0" keyTimes="0;.3;1" dur="5s" begin="1.6s" repeatCount="indefinite"/>')
    body = f"""
<defs>
 <radialGradient id="glow" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(80 40) scale(520 300)">
  <stop offset="0" stop-color="{C['blue']}" stop-opacity=".16"/><stop offset="1" stop-color="{C['blue']}" stop-opacity="0"/>
 </radialGradient>
 <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="140" y2="0">
  <stop offset="0" stop-color="{C['blue']}"/><stop offset=".5" stop-color="#ffffff"/><stop offset="1" stop-color="{C['blue']}"/>
  {shine}
 </linearGradient>
</defs>
{frame(W, H)}
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="url(#glow)"/>
<text x="48" y="66" class="m4 a" font-size="14" fill="{C['muted']}" {anim('rise', 0.05, 0.6)}>{escape(p['greeting'])}<tspan fill="{C['blue']}" {anim('blink', 0, 1.1, 'infinite step-end')}> _</tspan></text>
<text x="44" y="134" class="g7 a" font-size="66" fill="{C['ink']}" letter-spacing="-1.5" {anim('rise', 0.2, 0.8)}>{escape(p['first'])}</text>
<text x="44" y="202" class="g7 a shine-text" font-size="66" fill="url(#shine)" letter-spacing="-1.5" {anim('rise', 0.4, 0.8)}>{escape(p['last'])}</text>
<text x="48" y="244" class="g5 a" font-size="20" fill="{C['ink']}" {anim('rise', 0.6, 0.7)}>{escape(p['role'])}</text>
<text x="48" y="270" class="m4 a" font-size="12.5" fill="{C['muted']}" {anim('rise', 0.75, 0.7)}>{escape(p['stack'])}</text>
<g class="a" {anim('rise', 0.9, 0.7)}>
 <rect x="48" y="286" width="{len(p['status']) * 7.25 + 42:.0f}" height="26" rx="13" fill="{C['panel']}" stroke="{C['line']}"/>
 <circle cx="63" cy="299" r="4" fill="{C['teal']}"/>
 <circle class="fb pulse-fx" cx="63" cy="299" r="4" fill="none" stroke="{C['teal']}" stroke-width="1.5" style="animation:pulse 1.8s 1.2s infinite ease-out"/>
 <text x="76" y="303.5" class="m4" font-size="12" fill="{C['ink']}">{escape(p['status'])}</text>
</g>
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
                     f'fill="{HEAT[lv]}"{stroke} style="animation-delay:{T_HEAT + 0.2 + w * 0.018 + wd * 0.006:.2f}s"/>')
        if d["d"].day <= 7 and wd == 0 and d["d"].month not in seen and w < weeks - 2:
            seen.add(d["d"].month)
            parts.append(f'<text x="{x:.1f}" y="{y0 - 9}" class="m4" font-size="10.5" fill="{C["muted"]}">'
                         f'{d["d"].strftime("%b")}</text>')
    for wd, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        parts.append(f'<text x="{x0 - 8}" y="{y0 + wd * step + cell - 2:.1f}" text-anchor="end" class="m4" '
                     f'font-size="9.5" fill="{C["muted"]}">{lab}</text>')
    lx = W - 24 - 34 - 5 * 15 - 34  # room for 'less' + 5 swatches + 'more'
    legend = "".join(f'<rect x="{lx + 34 + i * 15}" y="{H - 25}" width="11" height="11" rx="2" fill="{c}"'
                     f'{" stroke=%s" % repr(C["faint"]) if i == 0 else ""}/>' for i, c in enumerate(HEAT))
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


def repo_card(i: int, name: str, fallback: dict) -> str:
    W, H = 410, 150
    info = fetch_repo(name)
    desc = info.get("description") or fallback.get("desc") or ""
    lang = fallback.get("lang") or info.get("language") or ""
    stars = info.get("stargazers_count", 0)
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
<g class="fb" style="animation:nudge 3.4s {t0 + 1.5:.2f}s infinite"><path d="M{W - 30} 34l9-9M{W - 28} 25h7v7" stroke="{C['muted']}" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></g>
</g>"""
    # 10px transparent margin below so stacked rows of cards don't touch
    return svg(W, H + 10, body, ["grotesk500", "grotesk700", "mono400"], f"{name}: {desc}")


# ------------------------------------------------------------------- main ---
def main() -> None:
    days = load_days()
    st = stats(days)
    print(f"Rendering cards ({'STATIC' if STATIC else 'animated'}): {st['total']} contributions, "
          f"streak {st['current']}/{st['longest']}, active {st['active']}/{st['span']}")
    write("hero.svg", hero())
    write("heatmap.svg", heatmap(days, st))
    write("activity.svg", activity(days, st))
    for i, t in enumerate(TILES):
        write(f"tile-{t[0]}.svg", tile(i, *t))
    for i, (name, fb) in enumerate(FEATURED):
        write(f"repo-{i + 1}.svg", repo_card(i, name, fb))


if __name__ == "__main__":
    main()
