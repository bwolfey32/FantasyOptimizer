# Share link previews

When someone shares their **Best move** from Waivers, the link points here (`share.bennyspicks.us/w?…`). Chat apps and social sites (iMessage, Discord, Slack, X, Facebook…) read this page's preview tags and show a picture of the Best move card:

- **`/w`** is the link itself. Its preview tags point at the card. People who open it go straight on to `bennyspicks.us/#waivers`, which shows the shared move as before.
- **`/card`** draws the card (1200×630 PNG) with [satori](https://github.com/vercel/satori) and resvg. Players are looked up by id in the site's `share-players.json`, built daily by `scripts/player_ids.py`, so a link can't put a made-up name on the card. Only the points, the ownership and the one-line reason come from the link.

It runs on Netlify because GitHub Pages can't make a page per link, and Supabase's functions serve HTML only as plain text. Netlify's free plan allows commercial sites. Each card is drawn once, then served from Netlify's cache.

## Setting it up (about 15 minutes, once)

1. Sign up at [netlify.com](https://www.netlify.com) with your GitHub account.
2. **Add new project → Import an existing project → GitHub**, and pick this repository.
3. On the build settings page, set:
   - **Base directory:** `share`
   - **Build command:** leave empty
   - **Publish directory:** `share/public`
   - **Functions directory:** `share/netlify/functions`

   Then **Deploy**. Netlify only rebuilds when something in `share/` changes. The data refresh's commits every three hours are skipped, so they don't use up the free plan.
4. Check it works on the address Netlify gave you (`https://<name>.netlify.app`):
   - `https://<name>.netlify.app/card?add=7049&drop=11304&wk=5&g=6.0&h=4&o=8` shows a card (Jauan Jennings for E.J. Jenkins).
   - `https://<name>.netlify.app/w?add=7049&drop=11304&wk=5&g=6.0&h=4&o=8` opens Benny's Picks on Waivers.
5. **Domain management → Add a domain** → `share.bennyspicks.us`. Netlify asks you to add a DNS record. In **GoDaddy → DNS**, add:

   | Type | Name | Value |
   |---|---|---|
   | CNAME | `share` | `<name>.netlify.app` |

   Netlify turns on HTTPS by itself once the record is live, usually within an hour.
6. In `index.html`, set `const SHARE_URL = 'https://share.bennyspicks.us/w';`, then commit and push. Until then, the Share button keeps sharing plain `bennyspicks.us` links.
7. Paste a shared link into [opengraph.xyz](https://www.opengraph.xyz) (or a Discord or Slack message to yourself) to see the preview.

## Notes

- `satori` and `@resvg/resvg-wasm` are pinned in `package.json`. The resvg engine loads from jsDelivr at the same version (`RESVG_WASM` in `lib/move.mjs`), so change both together.
- Fonts (Saira Condensed, IBM Plex Sans) come from Google Fonts. Player headshots and team logos come from ESPN's image server, as on the site.
- Apps cache a link's preview, often for days. A change to the card shows up only on links shared after it.
