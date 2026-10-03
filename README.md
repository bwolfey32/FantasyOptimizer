# Benny's Picks — Fantasy Optimizer

A free weekly lineup optimizer for ESPN fantasy football. It sets your best lineup, makes the close start/sit calls for you, and finds the waiver moves that add the most points, all from live data.

**Use it:** https://bwolfey32.github.io/FantasyOptimizer/

![Benny's Picks](assets/social-preview.jpg)

## What it does

The site has five sections, plus Settings in the header:

- **Lineup:** who should I start this week? Benny picks the starters that score the most for your lineup slots and benches anyone on bye, ruled out, or on IR. Each player gets a matchup grade (A–F), a projected score with a likely range, and the chance of beating his season average. Tap a player for the three biggest reasons, with the full breakdown and coaching profiles one tap further. **Past weeks** shows Benny's lineup from each earlier week, what it projected and what it scored.
- **Start / Sit:** which of these two players should I choose? **Benny's Pick** names the start, the chance he outscores the other player, the projected edge, and the reasons why. It opens on your closest calls.
- **Waivers:** which available players improve my team? Add/drop moves ranked by the expected lineup points they add over the window you choose, using each player's schedule. Injured players worth keeping are never suggested as drops, and bench depth counts as injury cover.
- **Roster:** who's on my team, and how do I change it? Search every player as you type, add or remove (with Undo), filter by position, and set projection overrides under Advanced.
- **Research:** every defense, plus each team's schemes and play-callers, including signings, trades and injuries that make a defense stronger or weaker than its stats.

A team bar on every page shows the selected team, week, scoring and where the roster comes from, with **+ Add team**, **Team settings**, **Import / replace** and **Share / back up**. Each team keeps its own roster, scoring (PPR, half-PPR or standard, with optional TE premium), lineup slots and league size.

## Getting started

1. Open the site. It starts with the **Demo team**.
2. Press **Import your team** and pick a method:
   - **Connect Sleeper:** enter your username or league ID and pick your team. It re-syncs every time you open the site, flags lineup differences from Sleeper, and the Waivers section uses your league's exact free agents.
   - **Import ESPN:** load a public league by its ID, or, for any league, copy the roster table from **My Team** and paste it.
   - **Build manually:** search for each player, or paste a list of names.
   - **Restore saved team:** paste a team code or open a file from **Share / back up**.
3. Review what was found (players, any names that didn't match, scoring and lineup slots), choose whether to create a new team or replace the selected one, and save. Benny opens your lineup.
4. Use **Waivers** for pickups. For exact suggestions in an ESPN league, use **Use my league's free agents** at the top of that section.
5. Optional: press **Sign in** (next to Settings) to use your teams on your phone and computer. Enter your email and type in the code it sends, or use Google. There's no password. The first time you sign in on a browser that already has its own teams, Benny asks whether to keep both sets or one.

Each section has its own address (for example `#start-sit` or `#roster`), so the browser's Back button, refreshing, and shared links all land where you expect.

## Your data

Without an account, your teams, settings and saved lineups stay only in your own browser. Nothing is sent to a server, and clearing your browser's site data erases them, so use **Share / back up** to keep a copy.

If you sign in, the site also keeps a copy in its database so every device you sign in on sees the same teams:
- your email address;
- your teams (rosters, scoring, lineup slots and league links);
- your overrides and settings;
- Benny's weekly lineups.

Only you can read them. **Sign out** removes them from that browser but keeps them in your account. **Delete account** erases everything.

## Data sources

Projections, stats, injuries, schedules and synced Sleeper leagues come from [Sleeper](https://sleeper.com). Scores, records, Vegas lines, ownership and head coaches come from ESPN. Both are free, unofficial feeds, so if either one changes, part of the tool may stop working until the code is updated. Coordinator names and coaching profiles were compiled by hand as of October 2, 2026, and can be edited in **Settings → Coaching staffs**.

Projections are estimates, not guarantees. The weights the model uses are adjustable in **Settings**.

## How it's built

The whole app is one file, `index.html`, with no build step or server. It loads data straight from Sleeper and ESPN in the browser. `snapshot.json` is a saved copy of the data: the page shows it instantly, then swaps in live data, and keeps it if the live feeds can't be reached. A GitHub Action (`.github/workflows/refresh-data.yml`) refreshes it every three hours by opening `index.html#export` in headless Chrome; you can also run it from the **Actions** tab.

Accounts use [Supabase](https://supabase.com): sign-in, plus one row per person and one per saved lineup, private to that person through row-level security. The browser's own copy is always the one the app works from; when you're signed in, it pulls the account's copy when the page opens or comes back into view, and pushes a moment after each change. When two devices change things at the same time, teams merge by most recent edit. The Supabase library loads only for people who sign in. [`supabase/README.md`](supabase/README.md) covers the one-time setup, and [`supabase/schema.sql`](supabase/schema.sql) holds the database tables.

Built with [Claude Code](https://claude.com/claude-code).
