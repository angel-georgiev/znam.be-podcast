#!/usr/bin/env python3
"""Copy episode audio from SoundCloud to the R2 bucket, one file at a time per worker.

For every `_episodes/*.md` entry (and its nested `practice`), downloads `source_audio_url`
and uploads it to R2 at `episodes/<audio_file>`, using the Cloudflare REST API.
Files already public at MEDIA_BASE with the expected size are skipped, so the script can
be re-run after interruptions. Each download is checked against `audio_bytes` before upload.

Env: CLOUDFLARE_API_TOKEN (R2 edit), CLOUDFLARE_ACCOUNT_ID
Usage: python3 scripts/copy_audio_to_r2.py [--workers 3] [--dry-run]
"""
import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUCKET = "znambe-podcast"
MEDIA_BASE = "https://media.znam.be/episodes/"
UA = {"User-Agent": "znam.be-podcast-migrate"}


def front_matter(path: pathlib.Path) -> dict:
    """Parse the JSON-scalar YAML front matter written by import_soundcloud.py.

    Nested mappings (e.g. `practice:`) are written as a single JSON object value.
    """
    block = path.read_text().split("---", 2)[1]
    out = {}
    for line in block.strip().splitlines():
        k, v = line.split(": ", 1)
        out[k] = json.loads(v)
    return out


def jobs():
    for f in sorted((ROOT / "_episodes").glob("*.html")):
        fm = front_matter(f)
        for item in (fm, fm.get("practice")):
            if item and item.get("source_audio_url"):
                yield item["audio_file"], item["source_audio_url"], int(item["audio_bytes"])


def remote_size(name: str):
    req = urllib.request.Request(MEDIA_BASE + name, method="HEAD", headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return int(r.headers.get("Content-Length", -1))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def copy(name, src, size, token, account, dry):
    if remote_size(name) == size:
        return name, "skip"
    if dry:
        return name, "would copy"
    with tempfile.TemporaryFile() as tmp:
        with urllib.request.urlopen(urllib.request.Request(src, headers=UA), timeout=600) as r:
            while chunk := r.read(1 << 20):
                tmp.write(chunk)
        got = tmp.tell()
        if got != size:
            return name, f"ERROR size {got} != {size}"
        tmp.seek(0)
        url = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{BUCKET}/objects/episodes/{name}"
        req = urllib.request.Request(url, data=tmp, method="PUT", headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "audio/mpeg",
            "Content-Length": str(size),
        })
        with urllib.request.urlopen(req, timeout=900) as r:
            res = json.load(r)
        if not res.get("success"):
            return name, f"ERROR upload {res.get('errors')}"
    after = remote_size(name)
    return name, "ok" if after == size else f"ERROR remote size {after} != {size}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    token, account = os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"]
    todo = list(jobs())
    print(f"{len(todo)} files, {sum(j[2] for j in todo) / 1e9:.2f} GB", flush=True)
    errors = 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(copy, *j, token, account, a.dry_run) for j in todo]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            try:
                name, status = fut.result()
            except Exception as e:  # keep going; a re-run picks up failures
                name, status = "?", f"ERROR {e!r}"
            errors += status.startswith("ERROR")
            print(f"[{i}/{len(todo)}] {status} {name}", flush=True)
    print(f"done, {errors} errors", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
