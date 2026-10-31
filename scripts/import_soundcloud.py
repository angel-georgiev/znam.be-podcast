#!/usr/bin/env python3
"""One-off import of the old SoundCloud podcast feed into this repo.

Reads the SoundCloud RSS feed and writes:
  sources/soundcloud-feed.xml      archived copy of the original feed
  _data/show.json                  show-level metadata
  _episodes/<date>-<slug>.md       one file per episode (front matter only)
  assets/cover.jpg                 show artwork
  assets/episodes/<slug>.jpg       per-episode artwork

Audio is NOT downloaded here; each episode keeps `source_audio_url` so a separate
step can copy the MP3s to R2 under `audio_file`.

Episode GUIDs are kept exactly as SoundCloud published them, so podcast apps that
follow the feed move treat these as the same episodes, not 160 new ones.

Usage: python3 scripts/import_soundcloud.py [--feed FILE_OR_URL] [--no-images]
"""
import argparse
import email.utils
import json
import pathlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

FEED_URL = "https://feeds.soundcloud.com/users/soundcloud:users:772017865/sounds.rss"
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
ROOT = pathlib.Path(__file__).resolve().parent.parent


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "znam.be-podcast-import"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def kind_of(title: str) -> str:
    if title.startswith("Практика"):
        return "practice"
    if title.startswith("Епизод") or re.match(r"#\d+", title):
        return "episode"
    return "other"


def slug_of(enclosure_url: str) -> str:
    # https://feeds.soundcloud.com/stream/1304918113-znambe-praktika-85-....mp3
    name = enclosure_url.rsplit("/", 1)[-1].removesuffix(".mp3")
    name = re.sub(r"^\d+-znambe-", "", name)
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


def text(el, path):
    return (el.findtext(path, namespaces=NS) or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default=FEED_URL)
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
        "owner_name": text(owner, "itunes:name") if owner is not None else "",
        "owner_email": text(owner, "itunes:email") if owner is not None else "",
        "explicit": text(ch, "itunes:explicit") in ("yes", "true"),
        "categories": [c.get("text") for c in ch.findall("itunes:category", NS)],
        "image": "/assets/cover.jpg",
        "source_feed": args.feed if args.feed.startswith("http") else FEED_URL,
    }
    (ROOT / "_data").mkdir(exist_ok=True)
    (ROOT / "_data/show.json").write_text(json.dumps(show, ensure_ascii=False, indent=2) + "\n")

    img_dir = ROOT / "assets/episodes"
    img_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_images:
        cover = ch.find("itunes:image", NS).get("href")
        # SoundCloud avatar URLs accept size suffixes; "-original" is the upload itself.
        (ROOT / "assets/cover.jpg").write_bytes(fetch(cover))

    ep_dir = ROOT / "_episodes"
    ep_dir.mkdir(exist_ok=True)
    seen = set()
    items = ch.findall("item")
    for it in items:
        title = text(it, "title")
        enc = it.find("enclosure")
        slug = slug_of(enc.get("url"))
        assert slug not in seen, f"duplicate slug {slug}"
        seen.add(slug)
        date = email.utils.parsedate_to_datetime(text(it, "pubDate"))
        num = re.search(r"#(\d+)", title)
        img = it.find("itunes:image", NS)
        image_path = None
        if img is not None:
            image_path = f"/assets/episodes/{slug}.jpg"
            dest = ROOT / image_path.lstrip("/")
            if not args.no_images and not dest.exists():
                dest.write_bytes(fetch(img.get("href")))

        fm = {
            "title": title,
            "date": date.isoformat(),
            "guid": text(it, "guid"),
            "kind": kind_of(title),
            "number": int(num.group(1)) if num else None,
            "audio_file": f"{slug}.mp3",
            "audio_bytes": int(enc.get("length")),
            "audio_type": enc.get("type"),
            "duration": text(it, "itunes:duration"),
            "explicit": text(it, "itunes:explicit") in ("yes", "true"),
            "image": image_path,
            "description": text(it, "description"),
            "source_url": text(it, "link"),
            "source_audio_url": enc.get("url"),
        }
        # JSON scalars are valid YAML, which sidesteps quoting/escaping problems.
        lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items() if v is not None] + ["---", ""]
        (ep_dir / f"{date:%Y-%m-%d}-{slug}.md").write_text("\n".join(lines))

    total = sum(int(i.find("enclosure").get("length")) for i in items)
    print(f"{len(items)} episodes, {total / 1e9:.2f} GB of audio referenced", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
