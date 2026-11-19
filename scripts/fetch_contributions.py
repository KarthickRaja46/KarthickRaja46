"""Scrape the public GitHub contribution calendar into data/contributions.json.

No token needed: it reads the same HTML the profile page loads. Private
contributions are included only if "Include private contributions on my
profile" is switched on in GitHub settings.

Usage:  python scripts/fetch_contributions.py [username]
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

USER = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GH_USER", "KarthickRaja46"))
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "contributions.json"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (readme-cards)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def main() -> None:
    html = fetch(f"https://github.com/users/{USER}/contributions")

    cells = {}  # component id -> (date, level)
    for m in re.finditer(r"<td\b[^>]*>", html):
        tag = m.group(0)
        d = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        i = re.search(r'id="(contribution-day-component-[\d-]+)"', tag)
        lv = re.search(r'data-level="(\d)"', tag)
        if d and i:
            cells[i.group(1)] = (d.group(1), int(lv.group(1)) if lv else 0)

    counts = {}
    for m in re.finditer(r'<tool-tip\b[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', html):
        text = m.group(2).strip()
        n = re.match(r"([\d,]+) contributions?", text)
        counts[m.group(1)] = int(n.group(1).replace(",", "")) if n else 0

    if not cells:
        sys.exit("No contribution cells found - GitHub may have changed its markup.")

    days = sorted(
        ({"date": d, "count": counts.get(cid, 0), "level": lv} for cid, (d, lv) in cells.items()),
        key=lambda x: x["date"],
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"user": USER, "fetched": date.today().isoformat(), "days": days}, indent=1))
    total = sum(x["count"] for x in days)
    print(f"{USER}: {len(days)} days, {total} contributions -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
