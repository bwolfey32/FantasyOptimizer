# Benny's Picks — Fantasy Optimizer

A free weekly lineup optimizer for Sleeper and ESPN fantasy football. It sets your best lineup, makes the close start/sit calls for you, and finds the waiver moves that add the most points, all from live data.

**Use it:** https://bennyspicks.us/

![Benny's Picks](assets/social-preview.jpg)

## What it does

The site has three sections, **My Team** (Lineup, Start / Sit, Waivers and Roster), **Players** and **Research**, plus Settings. Every player's name and picture, wherever it appears, opens his player page.

- **Lineup:** who should I start this week? At the top:
  - **Benny Grade** scores your roster out of 100, with its strongest and weakest positions. For a Sleeper team, **See your league’s power rankings** grades every roster in the league the same way, best first, with each team’s record. **Share with your league** sends the rankings to the league chat as a link: everyone in the league sees the rankings computed live, picks their own team from the list and is one tap from setting it up.
  - **Benny's Moves** lists the most useful things to do: lineup changes against the lineup set in Sleeper or ESPN, pickups and drops, and your weakest spot, ranked by points gained.

  Below that, Benny picks the starters that score the most for your lineup slots and benches anyone on bye, ruled out, or on IR. A player listed questionable or doubtful counts at his chance to play (how often players with that tag played in 2023-25: about 7 in 10 questionable, almost no doubtful), with a range that includes the zero if he sits, and the teammates who'd get his work gain it at that chance; a backup running back or quarterback behind a starter who may sit is valued as the starter at the chance he starts. Snap counts flag a rising or shrinking role (share of snaps, carries and targets the last two games against the earlier ones): a shrinking role moves his number toward his recent games, a rising one is shown and flagged on Waivers, since a bigger role often doesn't last. Each player gets a matchup grade (A–F), a projected score with a likely range, and the chance of beating his season average. Tap a player for the three biggest reasons, with the full breakdown and coaching profiles one tap further. **Past weeks** shows Benny's lineup from each earlier week, what it projected and what it scored. With Pro, a team in a Sleeper league can pick **Win chance**: Benny loads this week's opponent from the league, and picks the lineup with the best chance to beat his (more range when you're projected to lose, steadier when you're projected to win, stacks counted), shows the chance, and says where and why it differs from the projected lineup.
- **Start / Sit:** which of these two players should I choose? **Benny's Pick** names the start, the chance he outscores the other player, the projected edge, and the reasons why. It opens on your closest calls (with no team yet, on an example close call). **Share** sends the pick as a link with a card of the call; it opens Start / Sit on the same two players, for anyone.
- **Waivers:** which available players improve my team? Add/drop moves ranked by the expected lineup points they add over the window you choose, plus how much they raise your usual lineup. An upgrade at a weak position outranks a pickup who only covers a bye or an injury. Values lean on season scoring averages, recent games a little more, with each game counted mostly for its usage (targets, carries and passes) rather than its touchdowns. Last season counts less as this season goes on, and less again for a player who changed teams. When Sleeper projects a player below his average, the projection leads. A player on a new team whose games fall well short of his projection is valued more on his games, and a bigger role that comes from an injured teammate lasts only until that teammate is expected back. Each week is projected against that week's opponent (at half strength, since a matchup weeks away is less certain), with byes and injuries counted. A bye is a short absence, not part of a player's value: in the ranking a week touched by one counts about a third of its gain and the rest as if everyone played his usual week, so a pickup is never sold on bye-week cover (except in the week you set a lineup for next, when you need a fill-in now), and a free agent's own bye doesn't sink him. Injured players worth keeping are never suggested as drops, and bench depth counts as injury cover. A player most leagues roster is never dropped for a bye or matchup patch, and when a move drops one for an upgrade, the reason says why he's expendable. A kicker's average counts for little (kicker scores are mostly weekly noise), so a kicker swap needs a real head-to-head edge, not a bye week. A move must add at least a point in its window, and a pickup who's injured now says so first. A handcuff (the next running back behind a healthy regular, or quarterback with a superflex spot) is a pickup for what he'd score when the regular misses (about 1 week in 12), counted at that chance over what your lineup would have instead; it's never worth a player you'd start. A rising role from snap counts puts a player on the list before his points show it. Once nearly all of the week's games have kicked off (Sunday night and Monday), the window starts with next week.
- **Roster:** who's on my team, and how do I change it? Search every player as you type, add or remove (with Undo), filter by position, and set projection overrides under Advanced.
- **Players:** search any player, or rank a position on this week's projections or rest-of-season value. **Player pages** (`#player/<id>`) have four tabs. **Overview** has this week's projection, Benny's rank at the position, the matchup, the three models side by side, the reasons behind his number, and **Benny's call** for your team: where he plays in your lineup, the waiver move he's part of, or whether he's available. **Game log** lists every game this season and in past seasons. **History** has his season totals and his finish at the position each year since 2013. **Stats** has snap, target and carry shares and efficiency by season, and his last three games against his season.
- **Research:** every defense, plus each team's schemes and play-callers, including signings, trades and injuries that make a defense stronger or weaker than its stats. **Weather** lists every game's stadium, whether it has a dome or roof, the kickoff forecast at open-air stadiums, and how the conditions move your players.

**Weather and stadiums.** Every projection includes a weather & stadium factor:
- Domes and closed retractable roofs give passers and kickers a small lift.
- Outdoors, the forecast for the three hours from kickoff matters. Wind over 10 mph hurts deep passing and kickers most, rain and snow shift work to running backs, and freezing cold costs kickers and passers a little.
- How much a player feels it depends on his role: a deep threat more than a slot receiver, a running quarterback less than a pocket passer.
- His own scores indoors vs. outdoors, this season and last, count a little.

The betting total already reflects bad weather, so this factor moves points between positions rather than cutting everyone again. Its weight is adjustable in **Settings**.

A team bar on every page shows the selected team, week, scoring and where the roster comes from, with **+ Add team**, **Team settings**, **Import / replace** and **Share / back up**. Each team keeps its own roster, scoring (PPR, half-PPR or standard, with optional TE premium), lineup slots and league size.

## Getting started

1. Open the site. Lineup, Waivers and Roster ask how you'd like to add your team. You can look around first: **Start / Sit** works for any two players (it opens on an example close call), and **Research** and **Settings** need no team either. A bar at the top of those pages adds your team right there. Already have an account? Press **Sign in** at the top and your teams come straight back.
2. Pick one of four ways:
   - **Sleeper:** enter your username or league ID and pick your team. It re-syncs every time you open the site, flags lineup differences from Sleeper, and the Waivers section uses your league's exact free agents.
   - **ESPN Fantasy:** load a public league by its ID, or, for any league, copy the roster table from **My Team** and paste it.
   - **Yahoo Fantasy:** copy the roster table from **My Team** and paste it. Benny reads Yahoo's "Team - Pos" tags, so players who share a name and every D/ST come in right. Set your scoring and lineup slots on the next step, since Yahoo doesn't share them.
   - **Find your players:** search for each player and pick them from the suggestions, or paste a roster.

   To bring back a team saved from Benny's Picks, use **Restore a saved team** below the cards: paste a team code or open a file from **Share / back up**.
3. Review what was found (players, any names that didn't match, scoring and lineup slots) and save. Benny opens your lineup.
4. **Save your team across devices** (optional): a banner on your lineup offers sign-in with your email, typing in the code it sends, or with Google. There's no password. Until then your team is saved in this browser.
5. Use **+ Add team** for more leagues, and **Waivers** for pickups. For exact suggestions in an ESPN or Yahoo league, use **Use my league's free agents** at the top of that section and paste the league's free-agent list.

Each section has its own address (for example `#start-sit` or `#roster`), so the browser's Back button, refreshing, and shared links all land where you expect.

## Your data

Without an account, your teams, settings and saved lineups stay only in your own browser. Nothing is sent to a server, and clearing your browser's site data erases them, so use **Share / back up** to keep a copy.

If you sign in, the site also keeps a copy in its database so every device you sign in on sees the same teams:
- your email address;
- your teams (rosters, scoring, lineup slots and league links);
- your overrides and settings;
- Benny's weekly lineups.

Only you and the site's owner can read them. **Sign out** removes them from that browser but keeps them in your account. **Delete account** erases everything.

Comments are the exception: each player's discussion is public, and a comment shows the username you choose when you sign in (or before your first post, if you skip it then), never your email; each username has a page (`#u/username`) listing their comments, and it can be changed once every 30 days. Deleting your account deletes your comments and reactions (a comment others replied to stays as “[deleted]”, with no text or name).

If you buy Pro, Stripe handles the payment; Benny's Picks never sees your card and stores only your plan and its end date. Free users see ads: Benny's own promotions, and Google ads once AdSense is set up. The details are in the [privacy policy](privacy.html) and [terms](terms.html).

## Free and Pro

Benny's Picks is free, with ads. **Pro** ($4.99/month, or $14.99 for the whole season) does more of the work for you. Pro is tied to your account, so you sign in first, and it works on every device you sign in on.

| | Free | Pro |
|---|---|---|
| Player research, projections, matchups, weather | ✓ | ✓ |
| Your optimized lineup, Team Grade, Benny's Pick for any two players | ✓ | ✓ |
| Benny's Moves (lineup changes, pickups and drops, best first) | top 2 | all |
| Waiver moves for your roster | best 2 | all |
| This week's close start/sit calls | first 1 | all |
| Win chance lineups (Sleeper leagues), Safe and Boom lineups, every matchup factor and the math | | ✓ |
| Teams | 1 | unlimited |
| Ads | yes | none |

The Pro checks run in your browser, like the rest of the app. Payments go only through Stripe, and Pro is granted only by Stripe's confirmation. [`supabase/README.md`](supabase/README.md) covers setting up Stripe and AdSense.

## Data sources

Projections, stats, injuries, schedules and synced Sleeper leagues come from [Sleeper](https://sleeper.com). Scores, records, Vegas lines, ownership, head coaches, neutral-site venues, player headshots and team logos come from ESPN. Weather forecasts come from [Open-Meteo](https://open-meteo.com), and stadium locations and roof types were compiled by hand as of October 2026. All three are free. Sleeper's and ESPN's are unofficial, so if either one changes, part of the tool may stop working until the code is updated. Coordinator names and coaching profiles were compiled by hand as of October 2, 2026, and can be edited in **Settings → Coaching staffs**.

**Trained projections.** By default, each quarterback's, running back's, receiver's and tight end's weekly number and likely range come from models trained on every NFL game since 2013 (public box scores, snap counts, injury reports and depth charts from [nflverse](https://github.com/nflverse/nflverse-data)). They start from Sleeper's projection, take out how far Sleeper has run high or low at the position lately, and correct it from usage, role and depth chart, the betting line, the opponent, the weather and injuries; they're retrained every week of the season. Lineup, Start/Sit, Benny's Moves, Benny Grade and Win chance use them. Waivers stays on the classic model: replayed on past seasons, the trained numbers set better lineups but made worse waiver picks. Kickers and D/STs always use the classic model, and **Settings → Projections → Classic** switches everything back. [`docs/model-report.md`](docs/model-report.md) has how they were built and tested.

Projections are estimates, not guarantees. The weights the classic model uses are adjustable in **Settings**.

## How it's built

The whole app is one file, `index.html`, with no build step or server. It loads data straight from Sleeper and ESPN in the browser. `snapshot.json` is a saved copy of the data: the page shows it instantly, then swaps in live data, and keeps it if the live feeds can't be reached. A GitHub Action (`.github/workflows/refresh-data.yml`) refreshes it every three hours by opening `index.html#export` in headless Chrome; you can also run it from the **Actions** tab. The same Action keeps `player-ids.json` (each Sleeper player's ESPN and NFL GSIS ids, for headshots) up to date with `scripts/player_ids.py`, at most once a day; the page keeps a copy in the browser for a day.

**Installed app.** Added to a phone's home screen (Share > Add to Home Screen on iPhone, Install app on Android), the site runs full screen like a native app: launch screens in brand green, no browser bars, bounce or zoom on tap, and the notch and home indicator kept clear. `sw.js` (the service worker) keeps the app and the last data on the device: the page and its images answer from the device and refresh in the background, while live data (Sleeper, ESPN, weather, `snapshot.json`) always tries the network first and falls back to the last copy after 5 seconds or offline. A page that was never saved shows `offline.html`. When a new version is out, a bar offers "Update available · tap to refresh". **Bump `VERSION` in `sw.js` whenever that file changes**; a new `index.html` needs no bump. The browser's storage keys are `bp:v1:` plus a name, with a schema version and a migration step in `makeStore` (index.html), and fall back to memory when storage is full or blocked. `scripts/make_app_images.py` rebuilds the maskable icon and launch screens from `assets/icon-512.png`.

**Weekly pages.** The app draws itself with JavaScript, so search engines see little of it. `weekly/` holds plain pages they can read, with the same addresses every week: [waiver wire](https://bennyspicks.us/weekly/waiver-wire/) (the best free agents at each position over the next four weeks), [rankings](https://bennyspicks.us/weekly/rankings/) (this week's projections by position, PPR), [defense rankings](https://bennyspicks.us/weekly/defense-rankings/) (D/STs to start, and the fantasy points each defense allows by position) and the [NFL weather report](https://bennyspicks.us/weekly/weather/). `scripts/weekly_pages.py` writes them and `sitemap.xml` after every data refresh: it opens `scripts/weekly-pages.html` in headless Chrome, which loads the site on the new snapshot and takes the numbers from its own model. `robots.txt` points search engines at the sitemap. To rebuild them by hand: `python3 scripts/weekly_pages.py`.

**Player pages.** `scripts/model/player_history.py` writes `players/data/<sleeperId>.json`: every QB, RB, WR and TE's game log and season totals since 2013, from nflverse box scores, with his finish at the position each season. The app's player pages load a player's file the first time it's needed; this season's games come from the snapshot. `scripts/player_pages.py` turns the same files into static pages search engines can read, one per player on a team (`players/<slug>/`, listed in `players/index.html` and `sitemap.xml`), with the week's projection filled in from `model/proj.json`. A player's slug is kept in `players/slugs.json` once given, so his address never changes. The data refresh runs both at most once a day; a file is only rewritten when it changed. By hand: `python scripts/model/player_history.py --force`, then `python scripts/player_pages.py` and `python scripts/weekly_pages.py`.

**News.** `scripts/news.py` writes `news/feed.json` (the last two weeks of player news) and `news/players/<sleeperId>.json` (each player's last 50 items) after every data refresh. Most items are Benny's own, found by comparing with the last run (`news/state.json`): an injury tag that changed on Sleeper's projections, a team change in Sleeper's player file, a move onto or off a starting spot on nflverse's daily depth charts, and a player entering Sleeper's top 10 adds. ESPN headlines that tag a player are kept as a headline and a link to ESPN, never the story. A source's first run only records what it sees, and a source that fails is skipped with a warning. The app shows it on each player's **News** tab and Overview, in **Research → News** (by kind, position or your team, with Sleeper's most added and dropped), and on the static player pages. Tests: `python -m pytest tests/test_news.py`.

**Discussion.** Every player has a public discussion: on his page (**Discussion**, and the newest two comments on the Overview), on his expanded lineup card, and as a 💬 count beside his name elsewhere. Reading needs no account; posting, replying and reacting need one and a username. The tables, and every rule about who may write what and how much, are in [`supabase/community.sql`](supabase/community.sql); the page only chooses which buttons to show, and hides the discussion entirely until that file has been run. Reports go to moderators at `#mod`, which can also ban accounts and keeps a log of every moderator action. Deleting a comment others replied to leaves “[deleted]” so their replies stay; web addresses in comments become links (marked nofollow), and the static player pages show a comment count that links into the app. `tests/test_community_sql.py` runs the SQL against a real Postgres in CI. Start / Sit has a poll under Benny's Pick, “Who would you start?”: one vote per account per pair and week, changeable until a game starts; you see the split after you vote (anyone sees it from 5 votes), and who voted for what is never public. Players can be watched from their page (**☆ Watch**, synced with your account); the bell in the header lists news about your team and the players you watch, and, once you're signed in, replies in threads you've posted in, comments that @mention you (write `@username` in a comment) and reactions to your comments, since you last opened it.

`tests/selftest.html` checks the model's rules on a frozen week of data. `tests/audit.html` drafts whole 12-team leagues from a data bundle (ESPN roster percentages as the draft board), runs Lineup, Start/Sit, Waivers, Benny's Moves and Benny Grade for every team under several league setups, and flags advice a fantasy player would call wrong on sight: a pick who won't play, an injured pickup the reason doesn't mention, a widely rostered player dropped for a one-week patch, a gain that's really one bye week, one kicker pushed on most of a league. Run it with `python3 scripts/audit.py` (current data) or `--fixture tests/fixture-2026w4.json`; any ERROR line fails it. Both run on every push, and the data refresh posts an audit of the fresh data to its run summary.

**The trained model** lives in `scripts/model/`. `dataset.py` builds the history (one row per game a QB/RB/WR/TE played, 2013 on, with only what was known before kickoff), `backtest.py` predicts each season from earlier ones only, `train.py` fits the models in `scripts/model/models/`, and `predict.py` writes `model/proj.json` after every data refresh, from the snapshot, nflverse and the classic numbers the export saves in `model/classic.json`. The page reads `model/proj.json` and falls back to the classic model when it isn't for the current week. `.github/workflows/retrain-model.yml` retrains next week's model every Tuesday, after `tests/test_features.py` checks that no feature can see the game it predicts. Python 3.12 with `pip install -r scripts/model/requirements.txt`.

`scripts/backtest/` replays the model on past weeks (2025 weeks 2-18 and 2026 so far) and scores it against what happened; [`docs/backtest-report.md`](docs/backtest-report.md) has the results. To rerun it (Python 3 and Chrome; the first run downloads about 120 MB into `scripts/backtest/cache/`, and reruns use that copy): `python3 scripts/backtest/build_fixtures.py`, then `python3 scripts/backtest/replay.py baseline` (and `sweep`/`compare` for the constant tests), then `python3 scripts/backtest/analyze.py all`.

Accounts use [Supabase](https://supabase.com): sign-in, plus one row per person and one per saved lineup, private to that person through row-level security. The browser's own copy is always the one the app works from; when you're signed in, it pulls the account's copy when the page opens or comes back into view, and pushes a moment after each change. When two devices change things at the same time, teams merge by most recent edit. The Supabase library loads only for people who sign in. [`supabase/README.md`](supabase/README.md) covers the one-time setup, and [`supabase/schema.sql`](supabase/schema.sql) holds the database tables.

Built with [Claude Code](https://claude.com/claude-code).
