# За Учителите — podcast.znam.be

Static site and RSS feed for the podcast „За Учителите“ by Знам.бе.

- Site + feed: Jekyll on GitHub Pages → https://podcast.znam.be (feed: `/feed.xml`)
- Audio: Cloudflare R2 → https://media.znam.be/episodes/
- Episodes: one file per episode in `_episodes/` (front matter = metadata, body = show notes)

See [PLAN.md](PLAN.md) for the architecture and migration notes.

```bash
bundle install
bundle exec jekyll serve
```
