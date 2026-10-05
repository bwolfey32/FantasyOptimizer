# Benny's Picks — Fantasy Optimizer

A free weekly lineup optimizer for ESPN fantasy football. It sets your best lineup, makes the close start/sit calls for you, and finds the waiver moves that add the most points, all from live data.

**Use it:** https://bennyspicks.us/

![Benny's Picks](assets/social-preview.jpg)

## What it does

The site has five sections, plus Settings in the header:

- **Lineup:** who should I start this week? At the top:
  - **Benny Grade** scores your roster out of 100, with its strongest and weakest positions.
  - **Benny's Moves** lists the most useful things to do: lineup changes against the lineup set in Sleeper or ESPN, pickups and drops, and your weakest spot, ranked by points gained.

  Below that, Benny picks the starters that score the most for your lineup slots and benches anyone on bye, ruled out, or on IR. Each player gets a matchup grade (A–F), a projected score with a likely range, and the chance of beating his season average. Tap a player for the three biggest reasons, with the full breakdown and coaching profiles one tap further. **Past weeks** shows Benny's lineup from each earlier week, what it projected and what it scored.
- **Start / Sit:** which of these two players should I choose? **Benny's Pick** names the start, the chance he outscores the other player, the projected edge, and the reasons why. It opens on your closest calls.
- **Waivers:** which available players improve my team? Add/drop moves ranked by the expected lineup points they add over the window you choose, plus how much they raise your usual lineup. An upgrade at a weak position outranks a pickup who only covers a bye or an injury. Values lean on season scoring averages (last season counts too), and each week is projected against that week's opponent, with byes and injuries counted. Injured players worth keeping are never suggested as drops, and bench depth counts as injury cover. Once nearly all of the week's games have kicked off (Sunday night and Monday), the window starts with next week.
- **Roster:** who's on my team, and how do I change it? Search every player as you type, add or remove (with Undo), filter by position, and set projection overrides under Advanced.
- **Research:** every defense, plus each team's schemes and play-callers, including signings, trades and injuries that make a defense stronger or weaker than its stats. **Weather** lists every game's stadium, whether it has a dome or roof, the kickoff forecast at open-air stadiums, and how the conditions move your players.

**Weather and stadiums.** Every projection includes a weather & stadium factor:
- Domes and closed retractable roofs give passers and kickers a small lift.
- Outdoors, the forecast for the three hours from kickoff matters. Wind over 10 mph hurts deep passing and kickers most, rain and snow shift work to running backs, and freezing cold costs kickers and passers a little.
- How much a player feels it depends on his role: a deep threat more than a slot receiver, a running quarterback less than a pocket passer.
- His own scores indoors vs. outdoors, this season and last, count a little.

The betting total already reflects bad weather, so this factor moves points between positions rather than cutting everyone again. Its weight is adjustable in **Settings**.

A team bar on every page shows the selected team, week, scoring and where the roster comes from, with **+ Add team**, **Team settings**, **Import / replace** and **Share / back up**. Each team keeps its own roster, scoring (PPR, half-PPR or standard, with optional TE premium), lineup slots and league size.

## Getting started

1. Open the site. The first visit asks how you'd like to add your team. Already have an account? Press **Sign in** at the top and your teams come straight back.
2. Pick one of three ways:
   - **Sleeper:** enter your username or league ID and pick your team. It re-syncs every time you open the site, flags lineup differences from Sleeper, and the Waivers section uses your league's exact free agents.
   - **ESPN Fantasy:** load a public league by its ID, or, for any league, copy the roster table from **My Team** and paste it.
   - **Find your players:** search for each player and pick them from the suggestions, or paste a roster.

   To bring back a team saved from Benny's Picks, use **Restore a saved team** below the cards: paste a team code or open a file from **Share / back up**.
3. Review what was found (players, any names that didn't match, scoring and lineup slots) and save. Benny opens your lineup.
4. **Save your team across devices** (optional): a banner on your lineup offers sign-in with your email, typing in the code it sends, or with Google. There's no password. Until then your team is saved in this browser.
5. Use **+ Add team** for more leagues, and **Waivers** for pickups. For exact suggestions in an ESPN league, use **Use my league's free agents** at the top of that section.

Each section has its own address (for example `#start-sit` or `#roster`), so the browser's Back button, refreshing, and shared links all land where you expect.

## Your data

Without an account, your teams, settings and saved lineups stay only in your own browser. Nothing is sent to a server, and clearing your browser's site data erases them, so use **Share / back up** to keep a copy.

If you sign in, the site also keeps a copy in its database so every device you sign in on sees the same teams:
- your email address;
- your teams (rosters, scoring, lineup slots and league links);
- your overrides and settings;
- Benny's weekly lineups.

Only you and the site's owner can read them. **Sign out** removes them from that browser but keeps them in your account. **Delete account** erases everything.

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
| Safe and Boom lineups, every matchup factor and the math | | ✓ |
| Teams | 1 | unlimited |
| Ads | yes | none |

The Pro checks run in your browser, like the rest of the app. Payments go only through Stripe, and Pro is granted only by Stripe's confirmation. [`supabase/README.md`](supabase/README.md) covers setting up Stripe and AdSense.

## Data sources

Projections, stats, injuries, schedules and synced Sleeper leagues come from [Sleeper](https://sleeper.com). Scores, records, Vegas lines, ownership, head coaches, neutral-site venues, player headshots and team logos come from ESPN. Weather forecasts come from [Open-Meteo](https://open-meteo.com), and stadium locations and roof types were compiled by hand as of October 2026. All three are free. Sleeper's and ESPN's are unofficial, so if either one changes, part of the tool may stop working until the code is updated. Coordinator names and coaching profiles were compiled by hand as of October 2, 2026, and can be edited in **Settings → Coaching staffs**.

Projections are estimates, not guarantees. The weights the model uses are adjustable in **Settings**.

## How it's built

The whole app is one file, `index.html`, with no build step or server. It loads data straight from Sleeper and ESPN in the browser. `snapshot.json` is a saved copy of the data: the page shows it instantly, then swaps in live data, and keeps it if the live feeds can't be reached. A GitHub Action (`.github/workflows/refresh-data.yml`) refreshes it every three hours by opening `index.html#export` in headless Chrome; you can also run it from the **Actions** tab. The same Action keeps `player-ids.json` (each Sleeper player's ESPN and NFL GSIS ids, for headshots) up to date with `scripts/player_ids.py`, at most once a day; the page keeps a copy in the browser for a day.

Accounts use [Supabase](https://supabase.com): sign-in, plus one row per person and one per saved lineup, private to that person through row-level security. The browser's own copy is always the one the app works from; when you're signed in, it pulls the account's copy when the page opens or comes back into view, and pushes a moment after each change. When two devices change things at the same time, teams merge by most recent edit. The Supabase library loads only for people who sign in. [`supabase/README.md`](supabase/README.md) covers the one-time setup, and [`supabase/schema.sql`](supabase/schema.sql) holds the database tables.

Built with [Claude Code](https://claude.com/claude-code).
