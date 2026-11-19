"""Download one screenshot per dashboard in data/dashboards.json and save a
small 16:9 JPEG thumbnail to data/thumbs/<slug>.jpg for the gallery cards.

Run again when you add a dashboard or update a screenshot:
    python scripts/make_thumbs.py
"""
import json
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
USER = "KarthickRaja46"
W, H = 520, 293  # 2x the size shown on the card


def main() -> None:
    out = ROOT / "data" / "thumbs"
    out.mkdir(parents=True, exist_ok=True)
    for d in json.loads((ROOT / "data" / "dashboards.json").read_text(encoding="utf-8")):
        url = (f"https://raw.githubusercontent.com/{USER}/{d['repo']}/main/"
               + urllib.parse.quote(d["image"]))
        im = Image.open(BytesIO(urllib.request.urlopen(url, timeout=60).read())).convert("RGB")
        # centre-crop to 16:9, then downscale
        tw = min(im.width, int(im.height * W / H))
        th = int(tw * H / W)
        left, top = (im.width - tw) // 2, 0
        im = im.crop((left, top, left + tw, top + th)).resize((W, H), Image.LANCZOS)
        path = out / f"{d['slug']}.jpg"
        im.save(path, quality=78, optimize=True, progressive=True)
        print(f"{d['slug']:<8} {path.stat().st_size / 1024:5.1f} KB  <- {d['repo']}/{d['image']}")


if __name__ == "__main__":
    main()
