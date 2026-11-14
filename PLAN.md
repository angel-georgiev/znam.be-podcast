# „За Учителите“ — podcast hosting

Status (2026-11-14): **live** at https://podcast.znam.be, feed at https://podcast.znam.be/feed.xml.
All 160 SoundCloud recordings have been migrated. The podcast is paused. When it restarts,
Claude publishes new episodes following [Publishing a new episode](#publishing-a-new-episode).

## Architecture

| Piece | Where | URL |
|---|---|---|
| Website, RSS feed, artwork | GitHub Pages, built by GitHub from `main` (Jekyll, `github-pages` gem) | `https://podcast.znam.be/` |
| Audio (MP3) | Cloudflare R2 bucket `znambe-podcast`, folder `episodes/` | `https://media.znam.be/episodes/<file>.mp3` |

- **GitHub Pages:**
  - Classic "deploy from branch": `main`, root.
  - `CNAME` file = `podcast.znam.be`. Don't delete it, or the custom domain is dropped.
  - *Enforce HTTPS* is on.
  - Builds take ~1 min after a merge. Pages sends `Cache-Control: max-age=600`, so apps see changes within ~10 min.
- **Cloudflare DNS** for `znam.be`:
  - `podcast` CNAME → `angel-georgiev.github.io`, **DNS only** (grey cloud). Proxying it would break GitHub's certificate renewal.
  - `media` is the R2 bucket's custom domain. The bucket's `r2.dev` URL is disabled.
- **Bot protection:** Cloudflare's default bot protection on `media.znam.be` returns 403 to generic library user agents (e.g. `Python-urllib`). Real podcast apps, browsers and `curl` get 200. Scripts must send their own `User-Agent`.
- **Why this split:** audio is 9.4 GB with files up to ~140 MB, too big for Pages. The site itself is ~55 MB.
- **Local preview:**

  ```bash
  bundle install && LANG=C.UTF-8 bundle exec jekyll serve
  ```

## Repository layout

```
_config.yml              site URL, media_base, podcast:guid, cover paths
_data/show.json          show metadata (title, description, owner, category, language)
_episodes/<slug>.html    one file per feed item; front matter = metadata, body = show notes (HTML)
_layouts/, _includes/    page templates
index.html               homepage
feed.xml                 RSS feed template
assets/cover.jpg         show cover (1000×1000, used on the site)
assets/cover-1400.jpg    same cover upscaled to 1400×1400 (Apple minimum), used in the feed
assets/episodes/         episode artwork, 3000×3000 JPEG
assets/style.css
scripts/                 import_soundcloud.py, copy_audio_to_r2.py (migration, kept for reference)
sources/                 archived copy of the original SoundCloud feed
```

## Content model

Feed items are of three types: 85 numbered episodes (`full`), 4 English specials (`bonus`), 1 trailer.
Short "Практика" clips are not separate feed items. They are nested in their episode and shown as a second player on its page.

```yaml
title: "Епизод #85 Как да не ставаме англичани с Моника Стефанова"   # full title, feed <title>
short_title: "Как да не ставаме англичани с Моника Стефанова"         # itunes:title, page heading
date: "2022-07-14T06:12:28+00:00"
guid: "tag:soundcloud,2010:tracks/1304918038"   # NEVER change once published
episode_type: "full"                              # full | bonus | trailer
number: 85                                        # full episodes only
audio_file: "epizod-85-....mp3"                   # object episodes/<audio_file> in R2
audio_bytes: 98992953                             # exact size; must match R2
duration: "00:41:16"
duration_label: "41 мин"
image: "/assets/episodes/epizod-85-....jpg"
description: "plain-text show notes"
practice: { title, short_title, audio_file, audio_bytes, duration, duration_label, image, description, description_html }   # optional
---
<p>Show notes as HTML (body)</p>
```

Front matter values are written as JSON scalars and objects, which are valid YAML and avoid quoting problems.

## Publishing a new episode

Claude does this end to end. The owner provides the content and merges the pull request.

### What the owner provides

- **Audio:** MP3 (or WAV), plus the Практика clip if there is one.
- **Text:** title (guest name at the end, as before) and show notes.
- **Artwork:** square JPEG, ideally 3000×3000, following the existing template.
- **Publish date:** optional; defaults to the merge day.

Files can be attached in the session or put in a shared folder.

### What Claude needs in the session

- `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` (`953a61161c8fb16cac3c355fe1603983`), set as environment variables / network secrets in the Claude cloud environment, not pasted in chat.
  - The token needs R2 edit on `znambe-podcast`. The owner keeps the existing token for this.
- `ffprobe`/`ffmpeg` (preinstalled in the cloud image) for duration, and for encoding if the source is WAV.

### Steps

1. **Number and slug.** Number = highest existing `number` + 1. Slug follows the existing pattern: transliterated title, e.g. `epizod-86-<topic>`, `praktika-86-<topic>`.
2. **Audio.**
   - If the source is WAV, encode to MP3 mono. The bitrate is an open decision (see below).
   - Read the exact byte size and the duration (`ffprobe`).
3. **Upload** the audio to R2 at `episodes/<slug>.mp3` with `Content-Type: audio/mpeg`.
   - Verify via `https://media.znam.be/episodes/<slug>.mp3` that a HEAD request returns the same size, and that a range request returns 206.
   - Never overwrite an already-published file. A re-edit gets a new filename.
4. **Artwork** → `assets/episodes/<slug>.jpg`. Check it is square, at least 1400 px, RGB JPEG.
5. **Episode file** `_episodes/<slug>.html`:
   - All fields of the content model, with `practice` nested if there is one.
   - The `guid` for new episodes is `https://podcast.znam.be/episodes/<slug>/`. It is fixed at creation and never changed, even if the slug later changes.
6. **Build and check locally** with `jekyll build`:
   - the feed parses;
   - the item count went up by one;
   - the new item's enclosure URL, length and type are correct;
   - the page renders, with screenshots for the owner.
7. **Pull request** to `main`, with screenshots and the feed diff. **The owner merges = the episode goes live.**
8. **After merge:** confirm that https://podcast.znam.be/feed.xml contains the new item. Apple, Spotify and the others pick it up on their own next poll; no resubmission is needed.

### To build when publishing restarts

- `scripts/add_episode.py` automates steps 1–6. It should reuse `to_html`, `short_title` and `duration_label` from `import_soundcloud.py`, and the R2 upload code from `copy_audio_to_r2.py`.
- Optional: a GitHub Actions check on pull requests that builds the site, validates `feed.xml`, and checks each enclosure's size against R2.

### Open decisions for new episodes

- **Encoding for WAV sources.** The old episodes are 320 kbps mono MP3. 128 kbps mono would cut sizes by ~60% with no audible difference for speech (not tested here). Default if not decided: match the old episodes at 320 kbps.

## Migration from SoundCloud (done)

- **Source:** https://soundcloud.com/znambe. The feed is archived in `sources/soundcloud-feed.xml`.
- **Audio:** all 160 SoundCloud recordings (85 episodes, 70 Практика, 4 bonus, 1 trailer) were copied to R2 unchanged (320 kbps mono, 9.38 GB) and verified by size. Each feed episode keeps its original SoundCloud `guid`, so apps don't see the 90 feed items as new.
- **Artwork:** the original images were kept. The show cover is upscaled to 1400×1400 for the feed only.
- **Subscriber redirect:** as of 2026-11-14, the old SoundCloud feed is **not** redirected. It still serves its own items with no `itunes:new-feed-url`.
  - Either set SoundCloud's feed redirect to `https://podcast.znam.be/feed.xml`, if the setting exists, or change the feed URL in Apple Podcasts Connect and Spotify for Creators.
  - Keep the SoundCloud tracks online until directories show the new feed.
  - Submit the new feed to Podcast Index.

## Cloudflare resources

| Resource | Status |
|---|---|
| R2 bucket `znambe-podcast` (160 objects in `episodes/`) | keep |
| `media.znam.be` custom domain on the bucket | keep |
| DNS `podcast` CNAME → `angel-georgiev.github.io` (DNS only) | keep |
| API token with R2 edit | keep. Roll it (it was pasted in chat) and limit it to R2 on this bucket. |
| Workers project `znam-be-podcast` (Workers Builds, from the first setup attempt) | delete. It fails on every push to `main`. |
| Cloudflare GitHub app access to this repo | remove, unless used elsewhere |
