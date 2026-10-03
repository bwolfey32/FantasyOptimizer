# Benny's Picks — Fantasy Optimizer

A free weekly lineup optimizer for ESPN fantasy football. It sets your best lineup, makes the close start/sit calls for you, and finds the waiver moves that add the most points, all from live data.

**Use it:** https://bwolfey32.github.io/FantasyOptimizer/

![Benny's Picks](assets/social-preview.jpg)

## What it does

- **This week at a glance:** one line at the top tells you what your optimal lineup projects for, how many close calls to review, and the best waiver move.
- **Lineup:** picks the starters that score the most for your lineup slots and benches anyone on bye, ruled out, or on IR. Each player gets a matchup grade (A–F), a projected score with a likely range, and the chance of beating his season average. Tap a player for the full breakdown.
- **Benny's Pick:** for any two players, the recommended start, the chance he outscores the other player, the projected edge, and the reasons why. It opens on your closest start/sit calls.
- **Waiver Optimizer:** add/drop moves ranked by the expected lineup points they add over the next few weeks, using each player's schedule. Injured players worth keeping are never suggested as drops, and bench depth counts as injury cover.
- **Safe and Boom modes:** favor steady floors when you're favored, or high ceilings when you're the underdog.
- **Matchup breakdowns:** points the opponent allows to the position, its secondary or run defense, pass rush against your line, the Vegas implied total and spread, offensive style and pace, and defensive roster changes. Each team's play-callers have a short profile explaining how their scheme tends to help or hurt your player.
- **Defense & special-teams changes:** signings, trades, injuries and returners that make a defense stronger or weaker than its stats. These feed into schedule difficulty and projections.
- **Multiple teams:** keep several leagues side by side, each with its own roster, scoring (PPR, half-PPR or standard), lineup slots and waiver settings.
- **Import / export:** move teams between devices or send one to a friend as a short code or a file.

## Getting started

1. Open the site. It starts with an example roster.
2. On ESPN, open **My Team**, copy the roster table, and paste it into the **Players** tab. A plain list of names, one per line, also works.
3. On the **Lineup** tab, set your league's **Scoring**. If your league doesn't use ESPN's default lineup, set the slots in **Settings**.
4. Open **Waiver Optimizer** for pickups. For exact suggestions, paste your league's free-agent list at the bottom of that tab.

Public ESPN leagues can also be imported with the league ID in **Settings**. Private leagues can't be read by a website, so paste the roster instead.

## Your data

Your teams and settings are saved only in your own browser. Nothing is sent to a server, and nobody else who uses the site can see them. Clearing your browser's site data erases them, so use **Import / export** to keep a backup.

## Data sources

Projections, stats, injuries and schedules come from [Sleeper](https://sleeper.com). Scores, records, Vegas lines, ownership and head coaches come from ESPN. Both are free, unofficial feeds, so if either one changes, part of the tool may stop working until the code is updated. Coordinator names and coaching profiles were compiled by hand as of October 2, 2026, and can be edited in **Settings → Coaching staffs**.

Projections are estimates, not guarantees. The weights the model uses are adjustable in **Settings**.

## How it's built

The whole app is one file, `index.html`, with no build step or server. It loads data straight from Sleeper and ESPN in the browser. `snapshot.json` is a saved copy of the data: the page shows it instantly, then swaps in live data, and keeps it if the live feeds can't be reached. A GitHub Action (`.github/workflows/refresh-data.yml`) refreshes it every three hours by opening `index.html#export` in headless Chrome; you can also run it from the **Actions** tab.

Built with [Claude Code](https://claude.com/claude-code).
