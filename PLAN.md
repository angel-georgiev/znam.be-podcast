# Podcast hosting plan — „За Учителите“

Goal: move the podcast off SoundCloud to a static setup we control:

1. audio files and episode artwork in storage we own,
2. a homepage at **https://podcast.znam.be** to browse and play episodes,
3. an RSS feed at **https://podcast.znam.be/feed.xml** that any podcast app can subscribe to.

## Architecture

| Piece | Where | URL |
|---|---|---|
| Website, RSS feed, artwork | GitHub Pages, built by GitHub from `main` (Jekyll, `github-pages` gem) | `https://podcast.znam.be/` |
| Audio (MP3) | Cloudflare R2 bucket `znambe-podcast` | `https://media.znam.be/episodes/<file>.mp3` |

- **Site and feed: GitHub Pages.** Classic "deploy from branch" (`main`, root), with `CNAME` = `podcast.znam.be`. The site is ~55 MB, far inside Pages limits.
- **Audio: R2.** It is too big for Pages: 9.38 GB, files up to ~140 MB, and every subscriber's app downloads every episode.
- **DNS in Cloudflare:**
  - `podcast` CNAME → `angel-georgiev.github.io`, set to **DNS only** (grey cloud) so GitHub can issue the HTTPS certificate.
  - `media` is attached to the R2 bucket.
- **Redirects:** if the feed ever has to move, Cloudflare Redirect Rules can 301 it (requires proxying `podcast`).
- **Caching:** GitHub Pages sends `Cache-Control: max-age=600`, so feed updates reach apps within ~10 min.
- **Local preview:** `bundle install && bundle exec jekyll serve`. Set `LANG=C.UTF-8` if Sass complains about encoding.

## Content (migrated from SoundCloud)

Source: https://soundcloud.com/znambe, feed
`https://feeds.soundcloud.com/users/soundcloud:users:772017865/sounds.rss`
(archived copy in `sources/soundcloud-feed.xml`, imported by `scripts/import_soundcloud.py`).

The old feed has 160 items. They map onto the new site like this:

| Old items | Count | New home | In RSS feed? |
|---|---|---|---|
| Епизод #1–#85 (#1–#14 titled just "#N …") | 85 | One page per episode | Yes, `episodeType: full`, `itunes:episode` = number |
| Практика #15–#85 (none for #1–#14 and #31) | 70 | Second player on the matching episode's page, matched by number. All 70 also match by guest name. | No |
| #I–#IV English episodes (Jul–Aug 2020) | 4 | "Специални" section on the site | Yes, `episodeType: bonus` |
| Представяне на подкаст „За Учителите“ (trailer) | 1 | Top of the homepage | Yes, `episodeType: trailer` |

So apps see 85 numbered episodes, plus 4 bonus episodes and 1 trailer.

### Data model

One file per episode in `_episodes/`. The matching Практика clip is nested inside it:

```yaml
title: "Епизод #85 Как да не ставаме англичани с Моника Стефанова"
date: "2022-07-14T06:12:38+00:00"
guid: "tag:soundcloud,2010:tracks/1304918038"   # kept from SoundCloud — never change
episode_type: "full"                              # full | bonus | trailer
number: 85
audio_file: "epizod-85-....mp3"
audio_bytes: 98992953
duration: "00:41:16"
image: "/assets/episodes/epizod-85-....jpg"
description: "..."
practice:                                         # optional
  title: "Практика #85 ..."
  audio_file: "praktika-85-....mp3"
  audio_bytes: 9747657
  duration: "00:04:03"
  image: "/assets/episodes/praktika-85-....jpg"
  description: "..."
```

Show-level metadata is in `_data/show.json`: title, description, language `bg`, category Education, owner `angel@znam.be`.

### Decisions taken

- **Audio quality:** keep the SoundCloud files as-is (320 kbps mono MP3). That's 9.38 GB total, about $0.015/GB-month beyond R2's 10 GB free tier.
- **Artwork:** keep the current images. Episode art is 3000×3000.
  - The show cover is 1000×1000, below Apple's 1400×1400 minimum. The site will use the original.
  - The feed's `itunes:image` points to the same picture upscaled to 1400×1400, so it looks identical and passes validation.
- **Subscriber migration:** done after the new site is live (see phase 6).

## Site

- **Homepage:** show cover and description, subscribe links, trailer, episode list (newest first), "Специални" section.
- **Episode page:** artwork, `<audio controls preload="none">` player, show notes (links auto-linked), and a "Практика" block with its own player when there is one.
- **Language of the UI:** Bulgarian.
- No JavaScript framework is needed; the player is the browser's native one.

## RSS feed

- RSS 2.0 with the `itunes` and `podcast` namespaces.
- Channel fields: title, link, description, `language` bg, `itunes:author`, `itunes:owner` (angel@znam.be), `itunes:image`, `itunes:category` Education, `itunes:explicit` false, `podcast:guid`, `podcast:locked`.
- Per item: original `guid`, `pubDate`, `enclosure` (url/length/type), `itunes:duration`, `itunes:episode`, `itunes:episodeType`, description, `itunes:image`.
- CI validates the feed XML and checks that every enclosure URL returns 200 with the declared byte size.

## Setup checklist (owner)

- [x] R2 bucket `znambe-podcast` with custom domain `media.znam.be` (verified: range requests return 206).
- [x] Cloudflare API token with R2 edit. **Roll it after the migration**, since it was shared in chat.
- [ ] GitHub repo → Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
- [ ] Cloudflare DNS: `podcast` CNAME `angel-georgiev.github.io`, DNS only.
- [ ] GitHub → Settings → Pages: custom domain `podcast.znam.be` (read from `CNAME`), then tick *Enforce HTTPS* once the certificate exists.
- [ ] Optional: delete the unused Cloudflare Pages project / GitHub app connection.

## Phases

1. **Data:** restructure `_episodes/` into the 85 + 4 + 1 model above, nesting the Практика clips. Create the 1400×1400 feed cover.
2. **Site:** Jekyll layouts, homepage, episode pages, `feed.xml`, Gemfile.
3. **CI:** a GitHub Actions workflow that builds the site, validates the feed and checks audio URLs.
4. **Audio copy:** `scripts/copy_audio_to_r2` streams each MP3 from SoundCloud to R2, one file at a time.
   - It skips files already uploaded with the right size, so it can resume after interruptions.
   - It verifies sizes after uploading.
5. **Preview:** check locally / on GitHub Pages and run the feed through a validator (e.g. Podbase / Cast Feed Validator).
6. **Go live:** merge to `main`.
   - Point the old SoundCloud feed at the new one: SoundCloud redirect setting if available, otherwise update the feed URL in Apple Podcasts Connect and Spotify for Creators. Then add `<itunes:new-feed-url>`.
   - Submit to Podcast Index.
   - Keep the SoundCloud tracks online until the directories show the new feed.
7. **Later (optional):** download stats via OP3, transcripts, adding new episodes with `scripts/add-episode`.

## Unverified assumptions

- SoundCloud still offers a feed-redirect setting.
