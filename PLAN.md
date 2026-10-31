# Podcast hosting plan — „За Учителите“

Goal: move the podcast off SoundCloud to a static setup we control:

1. audio files and episode artwork in storage we own,
2. a homepage at **https://podcast.znam.be** to browse and play episodes,
3. an RSS feed at **https://podcast.znam.be/feed.xml** that any podcast app can subscribe to.

## Architecture

| Piece | Where | URL |
|---|---|---|
| Website, RSS feed, artwork | Cloudflare Pages, built from this repo (Jekyll) | `https://podcast.znam.be/` |
| Audio (MP3) | Cloudflare R2 bucket `znambe-podcast` | `https://media.znam.be/episodes/<slug>.mp3` |

Notes on these choices:

- **Why not R2 for the site too:** R2 is a plain file store. It doesn't serve `index.html` for `/` or `/episodes/x/`, and it has no build step, previews or redirects. Pages does all of that.
- **Why audio isn't on Pages:** Pages caps files at 25 MiB, and many episodes are around 100 MB.
- **Why audio lives on our own subdomain:** published audio URLs stay valid even if storage changes later.
- **Why GitHub Pages was rejected:** 1 GB site limit, 100 GB/month bandwidth, 100 MB per file, and it can't do 301 redirects.

### Deploy flow

- Cloudflare Pages is connected to this GitHub repo. Production branch: `main`.
- Every push to another branch gets a preview URL. The working branch is `claude/determined-ramanujan-njeyay`.
- Going live = merging into `main`. The repo owner decides when.
- Pages build settings:
  - Framework preset: Jekyll
  - Build command: `bundle exec jekyll build`
  - Output directory: `_site`

### Caching

- `feed.xml`: short `Cache-Control` (~10 min, via `_headers`) so new episodes reach apps quickly.
- Audio: never changes once published (a re-edit gets a new filename), so it is cached for a long time.

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
type: "full"                                      # full | bonus | trailer
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

## What's needed from Cloudflare (owner does these once)

1. **R2 bucket** named `znambe-podcast`.
   - Bucket → Settings → Custom Domains → add `media.znam.be`.
   - Leave the `r2.dev` URL disabled.
2. **API token** for uploading audio.
   - My Profile → API Tokens → Create Custom Token.
   - Permission: Account → Workers R2 Storage → Edit. Scope: the znam.be account.
3. **Put credentials in the Claude cloud environment, never in chat or the repo.**
   - Session title bar → environment → Edit → Network secrets (or environment variables).
   - Add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
   - Only sessions started after this change see them.
4. **Cloudflare Pages project.**
   - Workers & Pages → Create → Pages → Connect to Git → `angel-georgiev/znam.be-podcast`.
   - Production branch `main`; build settings as above.
   - Custom domain `podcast.znam.be`.
   - This can be done before or after the site code exists. If done before, the first build will just fail harmlessly.

Claude does not need a Cloudflare dashboard login. Pages builds from GitHub; audio uploads use the token from step 2 via `wrangler` (`api.cloudflare.com` is reachable from the session).

## Phases

1. **Data:** restructure `_episodes/` into the 85 + 4 + 1 model above, nesting the Практика clips. Create the 1400×1400 feed cover.
2. **Site:** Jekyll layouts, homepage, episode pages, `feed.xml`, `_headers`, Gemfile.
3. **CI:** a GitHub Actions workflow that builds the site, validates the feed and checks audio URLs.
4. **Audio copy:** `scripts/copy_audio_to_r2` streams each MP3 from SoundCloud to R2, one file at a time.
   - It skips files already uploaded with the right size, so it can resume after interruptions.
   - It verifies sizes after uploading.
5. **Preview:** check the Pages preview URL and run the feed through a validator (e.g. Podbase / Cast Feed Validator).
6. **Go live:** merge to `main`.
   - Point the old SoundCloud feed at the new one: SoundCloud redirect setting if available, otherwise update the feed URL in Apple Podcasts Connect and Spotify for Creators. Then add `<itunes:new-feed-url>`.
   - Submit to Podcast Index.
   - Keep the SoundCloud tracks online until the directories show the new feed.
7. **Later (optional):** download stats via OP3, transcripts, adding new episodes with `scripts/add-episode`.

## Unverified assumptions

- The Cloudflare Pages build image runs Jekyll from a Gemfile without extra config.
- Cloudflare Pages reports build status back to GitHub commits, so preview results are visible without dashboard access.
- SoundCloud still offers a feed-redirect setting.
