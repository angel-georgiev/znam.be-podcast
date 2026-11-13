#!/usr/bin/env python3
"""One-off import of the old SoundCloud podcast feed into this repo.

Reads the SoundCloud RSS feed and writes:
  sources/soundcloud-feed.xml      archived copy of the original feed
  _data/show.json                  show-level metadata
  _episodes/<slug>.html            one file per published item (85 full, 4 bonus, 1 trailer)
  assets/cover.jpg                 show artwork (original, 1000x1000)
  assets/episodes/<slug>.jpg       per-episode artwork

Mapping (see PLAN.md):
  "Епизод #N ..." / "#N ..."      -> episode_type "full", number N
  "Практика #N ..."               -> nested as `practice` inside episode N (not its own item)
  "#I".."#IV" English episodes    -> episode_type "bonus"
  "Представяне ..."               -> episode_type "trailer"

Episode GUIDs are kept exactly as SoundCloud published them, so podcast apps that
follow the feed move treat these as the same episodes.

Audio is not downloaded here; `source_audio_url` is kept for scripts/copy_audio_to_r2.py.

Usage: python3 scripts/import_soundcloud.py [--feed FILE_OR_URL] [--no-images]
"""
import argparse
import email.utils
import html
import json
import pathlib
import re
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET

FEED_URL = "https://feeds.soundcloud.com/users/soundcloud:users:772017865/sounds.rss"
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
ROOT = pathlib.Path(__file__).resolve().parent.parent
URL_RE = re.compile(r"(https?://[^\s<>\"]+[^\s<>\".,;:!?)\]])")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "znam.be-podcast-import"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def text(el, path):
    return (el.findtext(path, namespaces=NS) or "").strip()


def slug_of(enclosure_url: str) -> str:
    # https://feeds.soundcloud.com/stream/1304918113-znambe-praktika-85-....mp3
    name = enclosure_url.rsplit("/", 1)[-1].removesuffix(".mp3")
    name = re.sub(r"^\d+-znambe-", "", name)
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


def to_html(plain: str) -> str:
    """Plain-text show notes -> paragraphs with escaped text and clickable links."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", plain) if p.strip()]
    out = []
    for p in paras:
        esc = html.escape(p, quote=False)
        esc = URL_RE.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', esc)
        out.append("<p>" + esc.replace("\n", "<br>\n") + "</p>")
    return "\n".join(out)


def short_title(title: str) -> str:
    """Title without the "Епизод #N " / "#N " / "#IV " prefix (used as itunes:title)."""
    return re.sub(r"^(?:Епизод |Практика )?#[0-9IVX]+\s+", "", title).strip()


def duration_label(hms: str) -> str:
    h, m, s = (int(x) for x in hms.split(":"))
    total = h * 60 + m + (1 if s >= 30 else 0)
    if total == 0:
        return f"{s} сек"
    return f"{total // 60} ч {total % 60} мин" if total >= 60 else f"{total} мин"


def classify(title: str):
    if m := re.match(r"Практика #(\d+)", title):
        return "practice", int(m.group(1))
    if m := re.match(r"(?:Епизод )?#(\d+)\b", title):
        return "full", int(m.group(1))
    if re.match(r"#[IVX]+\b", title):
        return "bonus", None
    if title.startswith("Представяне"):
        return "trailer", None
    raise ValueError(f"unclassified item: {title}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default=str(ROOT / "sources/soundcloud-feed.xml"))
    ap.add_argument("--no-images", action="store_true")
    args = ap.parse_args()

    raw = fetch(args.feed) if args.feed.startswith("http") else pathlib.Path(args.feed).read_bytes()
    (ROOT / "sources").mkdir(exist_ok=True)
    (ROOT / "sources/soundcloud-feed.xml").write_bytes(raw)

    ch = ET.fromstring(raw).find("channel")
    owner = ch.find("itunes:owner", NS)
    show = {
        "title": text(ch, "title"),
        "description": text(ch, "description"),
        "language": text(ch, "language"),
        "copyright": text(ch, "copyright"),
        "author": text(ch, "itunes:author"),
        "owner_name": text(owner, "itunes:name"),
        "owner_email": text(owner, "itunes:email"),
        "explicit": text(ch, "itunes:explicit") in ("yes", "true"),
        "categories": [c.get("text") for c in ch.findall("itunes:category", NS)],
        "source_feed": FEED_URL,
    }
    (ROOT / "_data").mkdir(exist_ok=True)
    (ROOT / "_data/show.json").write_text(json.dumps(show, ensure_ascii=False, indent=2) + "\n")

    (ROOT / "assets/episodes").mkdir(parents=True, exist_ok=True)
    if not args.no_images and not (ROOT / "assets/cover.jpg").exists():
        (ROOT / "assets/cover.jpg").write_bytes(fetch(ch.find("itunes:image", NS).get("href")))

    items, practices = [], {}
    for it in ch.findall("item"):
        title = text(it, "title")
        kind, num = classify(title)
        enc = it.find("enclosure")
        slug = slug_of(enc.get("url"))
        img = it.find("itunes:image", NS)
        image = None
        if img is not None:
            image = f"/assets/episodes/{slug}.jpg"
            dest = ROOT / image.lstrip("/")
            if not args.no_images and not dest.exists():
                dest.write_bytes(fetch(img.get("href")))
        rec = {
            "title": title,
            "date": email.utils.parsedate_to_datetime(text(it, "pubDate")).isoformat(),
            "guid": text(it, "guid"),
            "audio_file": f"{slug}.mp3",
            "audio_bytes": int(enc.get("length")),
            "duration": text(it, "itunes:duration"),
            "duration_label": duration_label(text(it, "itunes:duration")),
            "image": image,
            "description": text(it, "description"),
            "source_url": text(it, "link"),
            "source_audio_url": enc.get("url"),
        }
        if kind == "practice":
            assert num not in practices, f"duplicate practice #{num}"
            rec["description_html"] = to_html(rec["description"])
            rec["short_title"] = short_title(title)
            practices[num] = rec
        else:
            items.append((slug, kind, num, rec))

    out_dir = ROOT / "_episodes"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir()
    numbers = set()
    for slug, kind, num, rec in items:
        fm = {"title": rec["title"], "short_title": short_title(rec["title"]), "date": rec["date"],
              "guid": rec["guid"], "episode_type": kind}
        if num is not None:
            assert num not in numbers, f"duplicate episode #{num}"
            numbers.add(num)
            fm["number"] = num
        fm.update({k: v for k, v in rec.items() if k not in fm and v is not None})
        if num in practices:
            fm["practice"] = {k: v for k, v in practices.pop(num).items() if v is not None}
        lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items()]
        lines += ["---", to_html(rec["description"]), ""]
        (out_dir / f"{slug}.html").write_text("\n".join(lines))

    assert not practices, f"practice clips without an episode: {sorted(practices)}"
    counts = {k: sum(1 for i in items if i[1] == k) for k in ("full", "bonus", "trailer")}
    print(f"{counts}, episode numbers {min(numbers)}-{max(numbers)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
