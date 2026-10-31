# Podcast hosting plan

Goal: a static, low-cost setup that

1. stores the audio files and episode artwork,
2. serves a homepage where visitors can browse and play episodes,
3. publishes an RSS feed that Apple Podcasts, Spotify, Pocket Casts, etc. can subscribe to.

## Decision (updated)

`znam.be` DNS is on Cloudflare, so everything runs on Cloudflare:

- **Site + RSS feed + images → Cloudflare Pages** (built from this repo), at `podcast.znam.be`.
- **Audio → Cloudflare R2**, behind a custom domain, e.g. `media.znam.be`.

Why not put the site in R2 too: an R2 bucket is a plain file store. It does not serve
`index.html` for `/` or `/episodes/foo/`, so the site's pages would 404 unless we add
URL-rewrite rules or a Worker in front. It also gives no build step, preview deploys or
`_redirects`/`_headers` files. Cloudflare Pages provides all of that for free. Pages caps
single files at 25 MiB, which is why audio goes to R2.

Cloudflare has been steering new projects from Pages toward Workers with static assets.
Either works for this; we'll pick whichever the dashboard currently recommends when we set it up.

The GitHub Pages analysis below is kept for reference.

## Short answer: can this be static on GitHub Pages?

**The website and the RSS feed: yes.** An RSS feed is just an XML file; nothing about podcasting needs a server.

**The audio files: possible, but not recommended long term.** The limits that matter:

| Limit (GitHub docs) | Value | What it means for us |
|---|---|---|
| Published Pages site size | 1 GB | ~17 one-hour episodes at 128 kbps stereo (~58 MB/h), ~35 at 64 kbps mono (~29 MB/h) |
| Pages bandwidth | 100 GB/month (soft) | ~2,000–3,500 full episode downloads per month |
| Single file in git | 100 MB hard, 50 MB warning | Long episodes at higher bitrates won't fit |
| Git history | every committed MP3 stays forever | Repo only grows, clones get slow, deleting doesn't shrink it without rewriting history |

Podcast apps also auto-download every new episode for every subscriber, so bandwidth scales with subscribers, not with website visits.

**Recommendation:** site + feed + images on GitHub Pages; audio in object storage, referenced by URL from the feed. If you want zero extra accounts to start, put audio on Pages and move it later — but only if the custom domain is in place first (see "Feed URL" below), so moving the files doesn't break anything for subscribers.

### Audio storage options

| Option | Cost | Notes |
|---|---|---|
| **Cloudflare R2** (recommended) | 10 GB free, then ~$0.015/GB-month; **no egress fees** | Needs a custom domain (e.g. `media.znam.be`) for production; the `r2.dev` URL is rate-limited. Easiest if `znam.be` DNS is on Cloudflare. |
| GitHub Releases assets | Free, 2 GB per file | No extra account. Download URLs redirect to a GitHub CDN; I have not verified that every podcast app (and Apple's byte-range check) is happy with that — would test before relying on it. |
| Backblaze B2 + Cloudflare | Very cheap | More moving parts than R2. |
| Audio in this repo (Pages) | Free | Fine for the first handful of episodes; see limits above. |

## Feed URL — the one decision that is hard to undo

Once directories have the feed, the feed URL is effectively permanent. Moving it later requires an HTTP 301 redirect plus `<itunes:new-feed-url>`. GitHub Pages alone cannot issue 301s. Cloudflare can, through Pages `_redirects` or Redirect Rules, which is another reason to serve everything through Cloudflare. Still:

- Serve the site on a domain we control from day one, e.g. `podcast.znam.be` or `znam.be`, not `angel-georgiev.github.io/...`.
- Feed lives at a stable path, e.g. `https://podcast.znam.be/feed.xml`, and never moves.
- Audio URLs should also be on our domain (`media.znam.be/...`), so the storage provider can change without touching published enclosure URLs.

## Architecture

```
repo (main branch)
├── _config.yml                # show-level metadata: title, author, owner email, language, category, artwork
├── _episodes/                 # one Markdown file per episode
│   └── 2026-11-15-001-slug.md # front matter + show notes
├── assets/
│   ├── cover.jpg              # show artwork, 3000×3000
│   └── episodes/001.jpg       # optional per-episode artwork
├── index.html                 # homepage: episode list, latest episode player, subscribe links
├── _layouts/episode.html      # episode page: artwork, <audio> player, show notes
├── feed.xml                   # RSS 2.0 + iTunes/Podcasting 2.0 namespaces, generated from _episodes
├── scripts/add-episode        # reads an MP3, fills in duration + byte size, uploads, creates the .md stub
├── _headers                   # Cloudflare Pages: Content-Type + short cache for feed.xml
└── .github/workflows/ci.yml   # validate feed + check audio URLs (Cloudflare Pages does the build/deploy)
```

Audio files are not in the repo. `scripts/add-episode` uploads them to R2 (via `wrangler` or the S3-compatible API) with `Content-Type: audio/mpeg`.

**Caching:** Cloudflare caches at the edge. `feed.xml` needs a short `Cache-Control` (e.g. 5–15 min) so apps see new episodes quickly. Audio files never change once published (new edit = new filename), so they can be cached for a long time.

**Generator:** Jekyll. GitHub Pages supports it natively, episodes are just Markdown files with front matter, and the feed is a Liquid template over the same data the homepage uses — one source of truth. (Eleventy or Astro would also work; they'd need an Actions build, which we'll have anyway, so this is a preference, not a constraint.)

**Episode front matter (draft):**

```yaml
title: "Episode title"
number: 1
date: 2026-11-15T08:00:00+02:00
audio_url: https://media.znam.be/episodes/001-slug.mp3
audio_bytes: 41234567        # required by RSS <enclosure length>
duration: "00:43:12"         # itunes:duration
image: /assets/episodes/001.jpg
summary: "One-line description for apps and the homepage"
explicit: false
```

`audio_bytes` and `duration` are tedious and error-prone by hand, so `scripts/add-episode` will compute them (via `ffprobe`) and write the stub.

**Player:** the browser's native `<audio controls preload="none">`. No library needed; `preload="none"` keeps page loads from burning bandwidth.

## RSS feed requirements (what directories check)

- RSS 2.0 with `xmlns:itunes` and `xmlns:podcast` namespaces.
- Channel: `title`, `link`, `description`, `language`, `itunes:author`, `itunes:owner` with email (Spotify/Apple use it to verify ownership), `itunes:image`, `itunes:category`, `itunes:explicit`, `podcast:guid`, `podcast:locked`.
- Item: `title`, `guid` (stable, never changes), `pubDate`, `enclosure url/length/type="audio/mpeg"`, `itunes:duration`, `itunes:episode`, `description`, optional `itunes:image`.
- Artwork: square JPEG/PNG, 1400–3000 px, RGB.
- Audio host must support HTTP byte-range requests (Apple requires it). R2 does; I believe Pages does too but haven't verified.

## Delivery phases

1. **Skeleton** — Jekyll site, `_config.yml`, layouts, empty feed. Placeholder episode to exercise everything.
2. **Cloudflare Pages** — connect this repo, set build command `jekyll build`, attach `podcast.znam.be`.
3. **Audio storage** — R2 bucket + custom domain `media.znam.be`; API token for uploads.
4. **Tooling** — `scripts/add-episode`; CI step that validates the feed XML and checks each `audio_url` returns 200 with the declared size.
5. **Content** — real artwork, show description, first episode(s). Validate with a feed validator (e.g. Podbase or Cast Feed Validator).
6. **Submit** — Apple Podcasts Connect, Spotify for Creators, Podcast Index (which feeds many smaller apps), YouTube Music/others as desired. Add the resulting subscribe links to the homepage.
7. **Optional** — download stats (static hosting gives none; OP3 is a free, open prefix-based analytics service), transcripts (`podcast:transcript`), chapters.

## Migration from SoundCloud

Source: https://soundcloud.com/znambe, feed
`https://feeds.soundcloud.com/users/soundcloud:users:772017865/sounds.rss`.

`scripts/import_soundcloud.py` has imported the metadata. It produced 160 items (2020-01 → 2022-07): 71 "Епизод", 70 "Практика", 19 other.
Each one became an `_episodes/*.md` file with its SoundCloud GUID preserved. Show metadata is in `_data/show.json`, and all artwork (3000×3000 per episode) is in `assets/`.
An archived copy of the original feed is in `sources/`.

What's left:

- **Audio:** 9.38 GB in total, served by SoundCloud as 320 kbps mono MP3s, which is far more than speech needs.
  - Option A: copy the files as-is. No quality loss, the 10 GB R2 free tier is almost full, and costs remain negligible (~$0.015/GB-month).
  - Option B: re-encode to 96 kbps mono. About 2.8 GB total, and smaller downloads for listeners.
  - The copy step (download from `source_audio_url`, upload to R2 as `audio_file`) needs an R2 API token. It runs either in a cloud session with the token stored as an environment secret, or locally.
- **Show cover is 1000×1000.** Apple requires at least 1400×1400, so a new cover image is needed (3000×3000 ideal).
- **Moving subscribers:** the old feed is likely already listed in Apple Podcasts and Spotify. To move listeners over without them noticing:
  1. Publish the new feed with the same GUIDs (done in the data), plus `<itunes:new-feed-url>`.
  2. Make the old feed URL redirect (301) to `https://podcast.znam.be/feed.xml`. SoundCloud's own setting for this (if it still exists) needs to be checked in the account. Without a redirect, update the feed URL manually in Apple Podcasts Connect and Spotify for Creators.
  3. Keep the SoundCloud tracks online until the directories show the new feed.

## Content intake

Show metadata, artwork and episodes will come from a folder the owner is assembling.
Useful per episode: the audio file (preferably the final master, WAV or high-bitrate MP3 so
we control the encode), title, number, publish date, description/show notes, optional
artwork. For the show: title, description, author, owner email, language, Apple category,
explicit flag, and cover art (square, ideally 3000×3000).

## Open decisions (answered by the content folder)

- Language of the show and site (Bulgarian, English, both)? Sets `<language>` and UI text.
- Expected length and cadence of episodes (drives the storage math above).
- Show metadata: title, description, author name, owner email for the feed, Apple category.
