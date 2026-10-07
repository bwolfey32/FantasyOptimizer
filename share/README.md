# Share link previews

When someone shares from Benny's Picks, the link points here. Chat apps and social sites (iMessage, Discord, Slack, X, Facebook…) read the link page's preview tags and show a picture of what was shared. Each kind of link has a page and a card (1200×630 PNG, drawn with [satori](https://github.com/vercel/satori) and resvg):

| Shared from | Link | Card | Opens on the site |
|---|---|---|---|
| **Best move** (Waivers) | `/w?add=&drop=&wk=&g=&h=&o=&why=` | `/card` | `#waivers`, showing the shared move |
| **Benny's Pick** (Start / Sit) | `/s?start=&sit=&wk=&e=&p=&f=&why=` | `/scard` | `#start-sit`, on the same two players |
| **Who would you start?** (Share on the poll under Benny's Pick) | `/v?start=&sit=&wk=` | `/vcard` | `#start-sit`, on the same two players, poll in view (no call or split in the link) |
| **Power rankings** (a Sleeper team's grade card) | `/l?id=&wk=&r=` | `/lcard` | `#lineup`, ranking the league live; a visitor picks their own team from it to set up |
| **A player's page** (Share on his page; also the preview picture of his static page) | `/p?id=&t=` | `/pcard` | his page, on the tab that was shared (`#player/<id>/<tab>`) |
| **A comment** (Share under a comment) | `/c?id=&p=` | `/ccard` | the comment in his discussion (`#player/<id>/talk/<comment id>`) |

A link can't put a made-up name on a card:

- Players are looked up by id in the site's `share-players.json`, built daily by `scripts/player_ids.py`. Only the numbers (points, ownership, the edge and the chance to outscore), the scoring and the one-line reason come from a move's or a pick's link.
- A league's name and team names come from Sleeper's public API (by league id). Only each team's grade (roster id and score) comes from the link.
- A comment's words, its author's username and its reactions are read from the site's community database (Supabase), as an anonymous visitor with the site's public key (`lib/sb.mjs`, the same as `CLOUD` in `index.html`). A link carries only ids. A hidden or deleted comment can't be read, so it isn't drawn. A player card on the Discussion tab reads his comment count and newest comment the same way.

`lib/card.mjs` holds what every card and link page share (fonts, emoji, the resvg engine, the panel and header, the link page itself). `lib/move.mjs`, `lib/call.mjs`, `lib/poll.mjs`, `lib/league.mjs`, `lib/player.mjs` and `lib/comment.mjs` read their links and draw their cards.

It runs on Netlify because GitHub Pages can't make a page per link, and Supabase's functions serve HTML only as plain text. Netlify's free plan allows commercial sites. Each card is drawn once, then served from Netlify's cache: for good for a move, a call or a league, a day for a player, and an hour for anything showing comments (a moderator can hide one).

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

## Starting the data refresh on time

`netlify/functions/refresh.mjs` is a scheduled function, not a link: every 3 hours (at :17) it starts the site's data refresh, `.github/workflows/refresh-data.yml`, through GitHub's API. GitHub runs that workflow's own schedule late or skips it when GitHub is busy, so it ran about every 7 hours, and the player pages' News waited with it. GitHub's schedule stays on as a backup. A run that finds nothing new commits nothing.

It needs a GitHub token, set up once:

1. On GitHub: **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**. Name it "Benny's Picks refresh", pick **Only select repositories** → this repository, and under **Repository permissions** set **Actions: Read and write**. Choose an expiry (a year at most), and put a reminder in your calendar for it.
2. In Netlify: **Project configuration → Environment variables → Add a variable**: key `GH_DISPATCH_TOKEN`, the token as the value. Leave the scope on **All scopes** (limiting it to Functions needs a paid plan, and the function reads the variable at runtime either way).
3. Deploy, so the function picks the variable up. A push that changes something in `share/` deploys. Otherwise use **Deploys → Trigger deploy**.
4. Check **Logs → Functions → refresh** after the next :17 past a multiple of 3 hours (UTC). It says "data refresh started", and a run started by `workflow_dispatch` shows on GitHub's Actions tab.

When the token expires, the function logs a 401 and only GitHub's own schedule runs, until you make a new token and replace the variable.

To start a refresh yourself (or from a script), use **Actions → Refresh data → Run workflow**, or `python scripts/run_refresh.py --wait` with the same kind of token in `GH_DISPATCH_TOKEN`. `python scripts/run_refresh.py --status` lists the last runs and needs no token.

## Notes

- `satori` and `@resvg/resvg-wasm` are pinned in `package.json`. The resvg engine loads from jsDelivr at the same version (`RESVG_WASM` in `lib/card.mjs`), so change both together.
- Emoji (in comments and reaction counts) are Twemoji pictures from jsDelivr, at the version in `TWEMOJI` in `lib/card.mjs`.
- Fonts (Saira Condensed, IBM Plex Sans) come from Google Fonts. Player headshots and team logos come from ESPN's image server, as on the site.
- Apps cache a link's preview, often for days. A change to the card shows up only on links shared after it.
- To try a card on your computer: `npm install` here, then import a function from `netlify/functions/` in Node and call it with a `Request` for its address. It returns the PNG or the page. (`node_modules/` and `package-lock.json` stay out of the repo.)
