# Backtest: how Benny's projections and Waivers advice held up

*October 5, 2026. Replays of 2025 weeks 2-18 and 2026 weeks 1-4, scored against what players actually scored.*

The live forecast record (`forecasts/`, `calibration.json`) only started in week 4 of 2026, so it can't say yet how good the
model is. This backtest answers that question another way. It rebuilds the data the site would have had before each past
week's first kickoff, runs the site's own `index.html` on it, and checks every forecast and every Waivers suggestion
against the results. Every number below comes from the model as it is on `main` (commit a4abf0b, which includes the
Jennings fixes), unless a row says "tuned".

## The short version

| | Shipped model | Tuned model (5 changes, below) | Sleeper's projection alone |
|---|---|---|---|
| **Average miss per player, per week** (all 5,434 player-weeks) | 5.06 pts | **5.00 pts** | 5.09 pts |
| Average miss, 2025 (the weeks used for tuning) | 5.03 | 4.97 | 5.08 |
| Average miss, **2026 weeks 1-4 (held out, never used for tuning)** | 5.18 (*worse than Sleeper*) | **5.10** (*better than Sleeper*) | 5.12 |
| Share of scores inside the "likely range" (should be 50%) | 43% | 50% | – |
| Chance to outscore: when Benny leans hard (80%+, about 85% on average), how often he's right | 82% | 85% | – |
| Chance-to-outscore score (Brier, lower is better), 2025 / 2026 | 0.2166 / 0.2151 | 0.2161 / 0.2159 | – |
| Average miss on Waivers' week-by-week values (next 1-4 weeks), 2025 / 2026 | 5.35 / 5.26 | 5.24 / 5.13 | – |
| **Waivers Best move: gain shown vs. gain that happened** (226 moves) | +7.0 shown, **+5.9** happened | +7.2 shown, **+7.1** happened | – |
| Best moves that actually helped | 56% | 61% | – |
| Jennings-type Best moves (big name, slow start): shown vs. happened | +4.2 vs. **+1.4** (25% helped) | +5.2 vs. +3.0 (53% helped) | – |

In plain terms:

- **As shipped, Benny's weekly projections are about as good as Sleeper's, no better.** Over 2025 Benny missed by 5.03
  points a player-week against Sleeper's 5.08. In the first four weeks of 2026 he missed by more than Sleeper (5.18 vs.
  5.12). Sleeper's projection does most of the work, and fantasy scores are mostly noise: even a perfect model would
  miss by several points a week.
- **The likely ranges are too narrow.** Only 43% of scores landed inside a range that should hold half of them, and
  misses on the low side (34%) outnumber misses on the high side (23%).
- **Waivers advice helps, but it promises a bit more than it delivers.** Across 226 Best moves the shown gain averaged
  +7.0 points over the window, and the lineup actually gained +5.9 (± 0.9). Kicker swaps, borrowed roles and
  Jennings-type pickups are where it overpromises most.
- **The five changes recommended below** make Benny about 2% more accurate than Sleeper overall, and they hold up on
  the four 2026 weeks that tuning never saw. They make the ranges honest (50%) and bring the Waivers promise in line
  with what happened (+7.2 shown, +7.1 realized). The tuned model beat the shipped one in 16 of 17 weeks of 2025 and
  in all 4 held-out weeks.
- **The slow-start rule from a4abf0b mostly misfires.** It mostly catches rookies growing into a role and backup
  quarterbacks taking over, and for those Sleeper's higher projection was right. Narrowing it to players who changed
  teams (the Jennings case) fixes that. In the replay of 2026, Jennings was never suggested on Waivers, before or after
  tuning.

## How the test works

1. **Historical data** (`scripts/backtest/build_fixtures.py`). For each week it writes a data bundle in the exact format
   the site's export uses. The bundle holds Sleeper's projections for that week, Sleeper's weekly stats for the earlier
   weeks of the season, last season's totals, ESPN's schedule and betting lines, kickoff weather, team records from
   earlier results, and defensive personnel. Nothing from the week's games goes in: results are kept in a separate file
   that the page never sees. A few things can't be recovered exactly and are approximated (see
   [Limitations](#limitations)).
2. **Replay** (`scripts/backtest/replay.py` + `driver.html`). It serves the repo, opens `index.html?fixture=…#selftest`
   in headless Chrome for each week, and collects every player's forecast, his Waivers values for the next four weeks,
   and the Waivers moves for 13 fantasy rosters:
   - the reviewer's 17-player roster from `tests/selftest.html`;
   - all 12 teams of a 12-team league drafted from week-1 projections, held fixed all season.

   `index.html` is not changed. To test other constant values, the harness rewrites the handful of functions that
   hold those constants inside the page. Each week it checks that, at the shipped values, the rewritten model gives
   exactly the same numbers as the original. It did, for all 21 weeks.
3. **Scoring** (`scripts/backtest/analyze.py`) reuses `scripts/calibrate.py`'s `evaluate()` (range coverage, chance of
   20+, chance to outscore, average miss vs. Sleeper), adds the checks below, and simulates each Waivers move with
   real scores.

**Fidelity check.** Week 4 of 2026 is the one week where the live site froze its own pregame forecasts. Against those:

- Sleeper's projection in the archive matched exactly for 33 of 48 players and within 1 point for the other 15.
- The replayed Benny forecast matched the live one within half a point for 47 of 48 (median difference 0.02 points).

"Average miss" below is the mean absolute error, in PPR points. Forecasts are scored only for players who played and
whom Benny projected at 3+ points, as `calibrate.py` does. D/STs are left out, because the site scores them itself.

## How accurate is the model today

### By position, week and projection size

| Group | Player-weeks | Benny's miss | Sleeper's miss | Benny too high by | Sleeper too high by | Inside range (target 50%) |
|---|---|---|---|---|---|---|
| All | 5,441 | 5.06 | 5.09 | 0.34 | 0.53 | 43.1% |
| QB | 640 | 6.22 | 6.44 | 1.30 | 2.29 | 45.6% |
| RB | 1,257 | 5.26 | 5.26 | 0.17 | 0.35 | 43.8% |
| WR | 2,010 | 5.14 | 5.15 | 0.42 | 0.48 | 42.1% |
| TE | 898 | 4.62 | 4.63 | -0.02 | 0.00 | 43.1% |
| K | 636 | 3.84 | 3.84 | 0.00 | -0.02 | 42.5% |
| Weeks 1-4 | 1,877 | 5.10 | 5.04 | 0.17 | 0.22 | 40.3% |
| Weeks 5-9 | 1,203 | 5.05 | 5.08 | 0.08 | 0.23 | 43.3% |
| Weeks 10-14 | 1,260 | 4.99 | 5.07 | 0.80 | 1.07 | 45.9% |
| Weeks 15-18 | 1,101 | 5.07 | 5.20 | 0.41 | 0.76 | 44.5% |
| Projected 3-8 | 2,196 | 3.91 | 3.94 | -0.13 | 0.15 | 39.2% |
| Projected 8-12 | 1,521 | 5.04 | 5.08 | 0.21 | 0.32 | 44.2% |
| Projected 12-16 | 866 | 6.21 | 6.26 | 0.71 | 1.02 | 46.9% |
| Projected 16+ | 858 | 6.87 | 6.88 | 1.44 | 1.35 | 47.4% |

Benny beats Sleeper from week 5 on, where his blend with each player's scoring form helps. He loses to Sleeper early in
the season, when that form is a game or two of noise. Both run high on quarterbacks: Sleeper by 2.3 points a game in
2025, Benny by 1.3. Both also run high on the biggest projections.

### Are the "chance" numbers honest?

| Benny said "chance of 20+" | Happened | n | | Benny said "chance to outscore" | Happened | pairs |
|---|---|---|---|---|---|---|
| 2% | 4% | 3,554 | | 52% | 52% | 19,693 |
| 19% | 17% | 989 | | 60% | 59% | 35,774 |
| 39% | 32% | 582 | | 72% | 70% | 39,899 |
| 57% | 47% | 281 | | 86% | 82% | 16,939 |
| 74% | 57% | 35 | | | | |

The chance to outscore is close to honest but a little overconfident at the strong end. The chance of a 20-point game
is too high for the top players, for the same reason the ranges are too narrow: the model allows too little room for a
dud (injury exits, game script).

### Is the likely range the right width?

| | Avg. spread the model assumed (sd) | Actual spread of misses | Inside 50% range | Inside 80% range | Below the range | Above the range |
|---|---|---|---|---|---|---|
| All | 5.79 | 6.58 | 43.1% | 74.4% | 33.9% | 23.0% |
| QB | 7.37 | 7.65 | 45.6% | 75.2% | 33.4% | 20.9% |
| RB | 6.04 | 6.92 | 43.9% | 75.1% | 33.1% | 23.0% |
| WR | 5.84 | 6.67 | 42.1% | 74.2% | 36.0% | 21.9% |
| TE | 5.25 | 6.07 | 43.1% | 74.6% | 33.4% | 23.5% |
| K | 4.31 | 4.77 | 42.5% | 72.2% | 29.7% | 27.8% |

Every position's range is about 15% too narrow (16% overall, 12-21% by position). In 2026 so far only 38% of scores
landed inside the range.

### Bias by game situation (positive = projected too high)

| Situation | Player-weeks | Benny | Sleeper |
|---|---|---|---|
| Home | 2,730 | +0.27 ± 0.13 | +0.40 |
| Away | 2,704 | +0.42 ± 0.13 | +0.65 |
| Dome or closed roof | 1,761 | +0.07 ± 0.16 | +0.21 |
| Outdoors, fair weather | 2,667 | +0.33 ± 0.12 | +0.46 |
| **Outdoors, rough weather** (wind, rain, snow or cold) | 1,006 | **+0.87 ± 0.21** | +1.26 |
| Favored by 7+ | 794 | +0.41 ± 0.24 | +0.10 |
| Favored by 0.5-6.5 | 1,953 | +0.47 ± 0.15 | +0.46 |
| Underdog by 0.5-6.5 | 1,922 | +0.13 ± 0.15 | +0.49 |
| **Underdog by 7+** | 765 | +0.50 ± 0.22 | **+1.22** |

Home and away don't differ beyond noise. **Bad weather is the clear gap:** both projections run high, and quarterbacks
run highest (+2.4 points in rough weather). Benny's weather factor recovers about a third of Sleeper's miss there. A
stronger weather weight helped a little in late 2025 (see [What we tested and left alone](#what-we-tested-and-left-alone)).
Benny already corrects most of Sleeper's over-projection of big underdogs.

### Waivers' week-by-week values

Waivers' values for the next 1-4 weeks were about right on average (0.07 points too low). They were off for these groups:

| Group | Value-weeks | Value minus what he scored |
|---|---|---|
| Flagged as a slow start (projDoubt) | 96 | **-4.3** (valued far too low) |
| Bigger role (expanded) | 394 | -2.0 |
| Smaller role (reduced) | 453 | -1.1 |
| Changed teams since last season | 2,441 | +0.9 (valued too high) |
| QBs | 1,518 | +0.9 |

The slow-start rule is the clearest miss. The rows it flagged were mostly:

- rookies growing into a role: Omarion Hampton, Tyler Shough, Colston Loveland, Kyle Williams;
- backups who had just become the starter: Jacoby Brissett, Mason Rudolph, and Philadelphia's resting starters in week 18.

For these players Sleeper's projection was right and their season average was stale. Hampton was flagged after two
games and then scored 24.9 and 27.5.

## Waivers audit

Each Best move is replayed with real scores over the window Waivers used (4 weeks, 3 for kickers and D/STs). In every
week, the lineup is set by that week's forecasts, with and without the move. The realized gain is the difference in
points that lineup actually scored. As in `computeWaivers`, an empty slot goes to a streamer (the third-best free agent)
from the next week on.

| Group | Best moves | Gain shown | Gain shown, lineup only | Gain that happened | ± | Helped |
|---|---|---|---|---|---|---|
| All | 226 | +7.0 | +6.0 | **+5.9** | 0.9 | 56% |
| 2025 | 185 | +7.9 | +6.8 | +7.1 | 1.0 | 63% |
| 2026 (held out; windows cut short) | 41 | +3.0 | +2.4 | +0.6 | 1.7 | 27% |
| Adding a QB | 71 | +9.6 | +8.1 | +8.6 | 1.4 | 65% |
| Adding a RB | 21 | +8.2 | +6.8 | +7.8 | 3.8 | 57% |
| Adding a WR | 29 | +6.6 | +5.6 | +7.8 | 2.9 | 55% |
| Adding a TE | 66 | +5.1 | +4.0 | +3.3 | 1.4 | 48% |
| **Swapping kickers** | 19 | +6.3 | +6.1 | **-0.6** | 2.6 | 42% |
| Adding a D/ST | 20 | +4.7 | +4.6 | +6.8 | 3.0 | 65% |
| Big name (10+ a game last season, or projected) | 129 | +7.6 | +6.4 | +5.3 | 1.0 | 53% |
| Slow start (flagged, or scoring under 60% of the projection) | 22 | +4.3 | +3.4 | +2.7 | 1.6 | 32% |
| Changed teams | 45 | +8.3 | +6.9 | +6.6 | 1.7 | 67% |
| **Borrowed role** (a teammate's injury) | 35 | +3.9 | +3.1 | **+1.4** | 1.9 | 26% |
| **Big name + slow start (Jennings type)** | 20 | +4.2 | +3.4 | **+1.4** | 1.5 | 25% |
| None of those flags | 83 | +6.1 | +5.2 | +6.9 | 1.7 | 59% |

"Gain shown, lineup only" leaves out the bench-insurance credit that `depthValue` adds to the shown gain. The realized
gain can't include that credit. The gap between shown and realized is mostly that credit (about 1 point a move) plus
kicker swaps.

How well the shown gain predicts the realized one: the correlation is 0.31, and a move shown at +10 delivers about +8
on average. That's useful, but noisy: the realized gain of a single move swings by about 13 points either way.

**The 15 worst Best moves** (shipped model; one row per roster and player, since a fixed roster gets the same advice
several weeks running):

| Week | Roster | Add (drop) | Shown | Happened | Flags | Reason Waivers gave |
|---|---|---|---|---|---|---|
| 2026 wk 2 | K | Jayden Reed, WR GB (Malachi Fields) | +9.5 | -20.1 | big name, borrowed role | Raises your usual lineup by +5.1 pts a week at WR, your weak spot; starts all 4 |
| 2025 wk 10 | C | Aaron Rodgers, QB PIT | +4.9 | -23.1 | big name, team change | Raises your usual lineup by +1.5 at QB, your weak spot; starts 3 of 4; soft schedule |
| 2025 wk 14 | H | AJ Barner, TE SEA | +7.4 | -19.7 | – | Raises your usual lineup by +2.0 at TE, your weak spot; starts all 4; soft schedule |
| 2025 wk 8 | G | Eddy Pineiro, K SF (Cam Little) | +11.2 | -14.0 | team change | Pineiro projects more than Little in 3 of 3 weeks, +5.1 a week |
| 2025 wk 7 | K | Brandon McManus, K GB (Evan McPherson) | +3.2 | -21.0 | – | McManus projects more than McPherson in 2 of 3 weeks, +1.5 a week |
| 2025 wk 9 | C | C.J. Stroud, QB HOU | +8.2 | -15.6 | big name | Raises your usual lineup by +2.3 at QB, your weak spot; starts 3 of 4 |
| 2026 wk 1 | F | Isaiah Likely, TE NYG (Denzel Boston) | +2.5 | -20.8 | big name, team change, borrowed role | Short-term cover: starts 3 of the next 4 weeks, for byes or injuries |
| 2025 wk 4 | J | Bryce Young, QB CAR | +10.7 | -12.5 | big name | Raises your usual lineup by +1.1 at QB, your weak spot; starts 3 of 4 |
| 2026 wk 2 | D | Jayden Reed, WR GB | +8.5 | -12.8 | big name, borrowed role | Raises your usual lineup by +4.3 at WR, your weak spot; starts all 4 |
| 2025 wk 9 | H | C.J. Stroud, QB HOU | +24.9 | +4.4 | big name | Raises your usual lineup by +2.3 at QB, your weak spot; starts 3 of 4 |
| 2025 wk 8 | F | Kendrick Bourne, WR SF | +8.9 | -11.3 | team change | Short-term cover: starts 2 of the next 4 weeks (WR/FLEX) |
| 2025 wk 17 | M | Evan McPherson, K CIN (Matt Gay) | +9.8 | -10.0 | – | McPherson projects more than Gay in 2 of 2 weeks, +8.8 a week |
| 2025 wk 12 | F | Broncos D/ST | +6.2 | -13.0 | big name | Raises your usual lineup by +2.4 at D/ST; starts 2 of 3; DEN defense improved |
| 2025 wk 2 | J | T.J. Hockenson, TE MIN (Ray-Ray McCloud) | +4.5 | -14.6 | big name | Short-term cover: starts 3 of the next 4 weeks, for byes or injuries |
| 2025 wk 2 | K | T.J. Hockenson, TE MIN | +7.8 | -11.2 | big name | Fills your weak TE spot; short-term cover: starts 3 of 4 |

The misses fall into four patterns:

1. **A pickup QB who starts over the roster's own QB and has a bad stretch** (Rodgers, Stroud, Young). The model starts
   whoever projects higher, so a small edge in the forecast becomes a full swap.
2. **Kicker swaps**, which are mostly noise. Of the 19 kicker Best moves, the realized gain averaged -0.6.
3. **Borrowed roles and big names on the way back.** Reed was coming back from injury and Likely was on a new team with
   an injured teammate's role. The Jennings type shows the same pattern.
4. **Short-term TE cover**: adds valued on their bye-week and injury coverage, which delivered less than shown.

**The Jennings case itself.** In the 2026 replay Jennings is flagged with a bigger role in week 4 (Jefferson out), and
his projection leads for that week (forecast 10.2, scored 1.8). With a4abf0b's `bumpOf`, his later weeks fall back to
his own scoring (4.4-5.5 a game), so **no roster in any 2026 week was offered Jennings on Waivers.** The fix works for
the case that was reported.

## Recommended changes, ranked

All five are on the `backtest/model-tweaks` branch. "Change in miss" is the change in average points missed per
player-week (negative is better). 2025 weeks 2-18 were used to choose the values. **2026 weeks 1-4 were never used for
choosing**, so that column is the honest test. RMSE weighs big misses more. It checks that a change improves the
projected *average*, not just the typical miss: a change that only shaded projections down could lower the average miss
while making the projection worse as an average.

| # | Change | Weekly miss, 2025 | Weekly miss, **2026 held out** | Waivers values miss, 2025 / **2026** | RMSE weekly, 2025 / **2026** (was 6.58 / 6.63) |
|---|---|---|---|---|---|
| 1 | Follow Sleeper when it projects a player *below* his form | -0.037 | **-0.073** | -0.054 / **-0.068** | 6.55 / **6.59** |
| 2 | Count usage (targets, carries) in each player's scoring form | -0.026 | **-0.027** | -0.031 / **-0.054** | 6.53 / **6.60** |
| 3 | Waivers: future matchups at half strength | 0 | 0 | -0.039 / **-0.043** | – |
| 4 | Widen the likely range by 15% | 0 | 0 | 0 | – (range coverage 44% to 51%) |
| 5 | Slow-start rule only for RB/WR/TE who changed teams | -0.006 | -0.003 | -0.004 / 0.000 | 6.57 / 6.62 |
| | **All five together** | **-0.057** | **-0.078** | **-0.115 / -0.130** | **6.51 / 6.58** |

All five together beat the shipped model in 16 of 17 weeks of 2025 and in 4 of 4 held-out weeks. Bootstrapping by
week, the 95% intervals for the weekly change are -0.079 to -0.036 (2025) and -0.104 to -0.061 (2026). For Waivers
values they are -0.133 to -0.100 (2025) and -0.282 to -0.040 (2026). The intervals clear zero, but the gains are small,
about 1-2% of the average miss: most of each week's score is luck no model can see.

### 1. Follow Sleeper when it projects a player below his form

Today the weekly projection is 60% Sleeper and 40% the player's scoring form, whichever way they disagree. The data
says the two directions behave differently:

- **When Sleeper projects a player *below* his scoring form**, the best weight on Sleeper was about 1.0 at every ratio.
  Sleeper is usually reacting to something the average can't see, such as a smaller role, an injury, a tough matchup or
  a hot streak about to cool.
- **When Sleeper projects him *above* his form**, about 0.4-0.5 was best.

The change: when the projection is under his form, the projection counts 90% (`PROJ_DOWN = 0.9`), both this week and in
Waivers' values. The "Smaller role" label still starts at half his average.

An alternative was to raise `ROLE_LO` from 0.5 to 0.8-0.9. That gave about the same accuracy, but it would label
hundreds of ordinary players "Smaller role". That's why the rule was built separately from the label.

### 2. Count usage in each player's scoring form

Recent usage predicts next week better than recent fantasy points. Over 2025 weeks 10-18 and 2026, predicting the next
game from each player's last three games:

| Position | Next-game miss from last-3 points | from last-3 usage | Correlation, points / usage |
|---|---|---|---|
| All | 4.43 | **4.26** | 0.62 / **0.65** |
| QB | 6.86 | 6.83 | 0.33 / 0.33 |
| RB | 4.60 | **4.36** | 0.63 / **0.66** |
| WR | 4.42 | **4.33** | 0.56 / **0.58** |
| TE | 3.35 | **3.22** | 0.59 / **0.63** |

Usage means each game re-scored from its volume. The rates were fitted on 2025 weeks 1-9 and are rounded in the code:

- QB: -0.19 + 1.05 per carry + 0.42 per pass attempt
- RB: -0.37 + 1.24 per target + 0.77 per carry
- WR: 0.06 + 1.74 per target + 0.68 per carry
- TE: 0.00 + 1.90 per target + 0.57 per carry

Snap share helped a little more on its own, but the page's weekly rows don't carry snaps. Adding usage directly on top
of Benny's final forecast gained nothing, because Sleeper's projection already reflects usage. Where it helps is
`formOf`: each game counts 75% usage-based points and 25% actual points (`USAGE_W = 0.75`). TD luck then counts less in
the scoring form. Usage is converted to the user's scoring format the same way the points are.

### 3. Waivers: future matchups at half strength

Waivers scales each future week by that opponent's points allowed. In both 2025 and 2026 those future-week adjustments
worked best at a third to a half of their current strength (none at all was better than full strength too): a matchup
weeks away is much less certain than this week's. The change is `MATCHUP_FUT = 0.5` in `matchupMult`, the conservative
end of that range. This week's projection doesn't use `matchupMult`, so only Waivers values change, along with the
schedule shading and the "soft/tough upcoming schedule" notes, which now need a bigger difference to appear.

### 4. Widen the likely range by 15%

`sd × 1.15` (`SD_SCALE`) brings range coverage from 44% to 51% (2025) and from 38% to 45% (2026 so far, where early-season
noise is larger). It also makes "chance to outscore" honest at the strong end (85% predicted, 85% happened) and
improves the 20+ chance at the top. The chance-to-outscore score is unchanged within noise (0.2166 to 0.2161 in 2025,
0.2151 to 0.2159 in 2026).

### 5. Narrow the slow-start rule to players who changed teams

The rule now fires only for running backs, receivers and tight ends who changed teams since last season (the Jennings
pattern). It no longer fires for rookies, players without a last season, or quarterbacks: for those, a projection well
above their early games usually means a real new role. This rule touched only about 22 player-weeks, and those got about
1.2 points closer on average. With so few cases, `DOUBT_K` and the rule's thresholds can't be tuned reliably, so they
stay as shipped.

### How the five changes affect Waivers

| | Best moves | Gain shown | Gain that happened | Helped | Shown vs. happened, correlation |
|---|---|---|---|---|---|
| Shipped | 226 | +7.0 | +5.9 ± 0.9 | 56% | 0.31 |
| Tuned | 218 | +7.2 | **+7.1 ± 1.0** | 61% | 0.30 |
| Shipped, 2026 held out | 41 | +3.0 | +0.6 ± 1.7 | 27% | 0.03 |
| Tuned, 2026 held out | 32 | +2.9 | +5.1 ± 2.4 | 44% | 0.32 |
| Shipped, Jennings type | 20 | +4.2 | +1.4 | 25% | |
| Tuned, Jennings type | 15 | +5.2 | +3.0 | 53% | |
| Shipped, borrowed role | 35 | +3.9 | +1.4 | 26% | |
| Tuned, borrowed role | 21 | +7.7 | +9.6 | 71% | |

The 2026 Waivers samples are small, and their windows are cut short because only weeks 2-4 have results. Treat them as
a direction, not a measurement.

## What we tested and left alone

| Constant | Tested | Finding |
|---|---|---|
| `blend` 0.6 (weekly projection weight) | 0.3-0.9 | 0.6 was best over 2025 (0.5 and 0.7 within 0.01). Early weeks prefer more projection weight and late weeks less, and change #1 captures most of that. Keep 0.6. |
| Early-season schedule (0.9 at week 1, easing to 0.6) | several | Helped on its own (2026 -0.044), but not on top of #1 (average miss worse, RMSE about the same). Left out. |
| `ROS_PROJ` 0.75 | 0.5-1.2 | 0.6-0.75 is best for 2025. Higher helps only in early 2026. Keep. |
| `RECENT_W` [1.5, 1.25, 1.1] | flat to [3, 2, 1.5] | All within ±0.003. Keep. |
| `priorGames` 4 → 2 → 1, cap 1.5 after a move | 2-8 games, cap 0.5-4 | All within ±0.003 in 2025. 2026 prefers a little more last-season weight (-0.014), which isn't consistent. Keep. |
| `DOUBT_K` 0.4 and the slow-start thresholds | 0-0.8, ratio 1.5-2.5, gap 2-6 | As shipped, every softening helped. After #5 too few cases remain to tune. Keep. |
| `roleOf` 0.5 / 1.6, `ROLE_LEAD` 0.9 | 0.3-0.9 / 1.3-off / 0.6-1.0 | The low side is handled by #1. The high side and `ROLE_LEAD` are mixed across halves of 2025. Keep. |
| `bumpOf` (borrowed role lasts until the teammate's return) | on/off | Off is slightly better in early 2025 (-0.007) and clearly worse in late 2025 (+0.024) for Waivers values. Keep. |
| QB discount (×0.94) | 0.9-0.97 | Sleeper ran 2.3-3.2 points high on QBs all of 2025, and a discount lowers the average miss. But it worsens held-out RMSE and leaves 2026 QBs projected too low. Not recommended. Check again at season's end. |
| Weather weight (Settings) | ×1.5, ×2.5 | ×2.5 helps late 2025 (-0.011) and barely 2026 (-0.002). Worth another look after a winter of 2026 data. |
| Matchup strength (Settings) | 0.2-0.8 | Its effect on Waivers is what #3 captures. For this week's projection it's mixed. Keep. |

## Limitations

The results are worth reading with these in mind. The first three matter most.

1. **Only four held-out weeks, all early season.** The 2026 check covers 1,073 player-weeks but only 4 weeks. Its
   Waivers windows are cut short (results exist only through week 4), so the 2026 Waivers figures cover 32-41 moves. To
   guard against tuning on noise, each change also had to help in both halves of 2025 (weeks 2-10 and 11-18), which all
   five do. Rerun the backtest at the end of 2026.
2. **Waivers runs on stand-ins for real leagues.** ESPN ownership by week can't be recovered. The free-agent pool is
   everyone outside the top 20 QBs, 50 RBs, 60 WRs, 18 TEs, 14 kickers and 16 D/STs, ranked by a mix of this week's
   projection, this season's average and last season's. The rosters are synthetic: one 12-team draft from week-1
   projections, held fixed all season, plus the reviewer's 17 names reused for 2025. The realized gain sets lineups by
   the model's own forecasts and ignores the bench-insurance credit. Read the Waivers numbers as indicative.
3. **Injury designations are rebuilt, not recovered.** Sleeper's own injury tags at the time are gone (its player file
   only has today's). Every injury stub:
   - the official Friday injury report (via nflverse) for Out, Doubtful and Questionable;
   - nflverse weekly roster status RES counted as IR (so PUP, NFI and suspensions all count as IR);
   - a player with past games but no Sleeper projection counted Out only if he was inactive that week;
   - the week an injury started, rebuilt from the same reports;
   - mid-week changes after Friday not seen.

   The slow-start rule, `mateOut`, `bumpOf` and return weeks all read these tags, so findings about them carry this
   uncertainty.
4. **Betting lines are closing lines** (ESPN's odds feed). The live site reads whatever line is posted when it
   refreshes, usually a few points different.
5. **Weather is Open-Meteo's archived short-range forecast**, close to what actually fell. The site uses a forecast from
   hours or days before, and the archive has no rain probability, so rain counts as certain.
6. **Sleeper's projection archive is stamped 1-4 days after each game.** That looks like when the archive was written,
   not edits after kickoff. The archive matched the site's frozen pregame record in 2026 week 4 (33 identical, 15
   within 1 point), and Sleeper's 2025 errors look like ordinary pregame errors (2.3 points too high on QBs, for
   instance). Benny and Sleeper see the same projection either way, so the comparison between them is fair.
7. **2025 coaching staffs.** The site's staff table is 2026's. For 2025 the replay sets "new play-caller" flags from a
   best-effort list of 2025 hires and skips previous-team blending. The flags only widen ranges by 10% and shorten how
   much last season's team stats count.
8. **Defensive personnel.** Each defender's team comes from nflverse's weekly rosters, and a team on bye carries its
   previous week's roster. About 60 defenders a week with games this season have no current team (released players,
   practice squads).
9. **Smaller gaps.**
   - 2025 week 1 isn't replayed (there are no earlier weeks to build from).
   - 2026 week 4's Monday night game hadn't been played on October 5, so its players are left out.
   - Scoring is PPR only, and D/STs are left out of forecast scoring, as in `calibrate.py`.
   - Last season's indoor/outdoor splits and ESPN coach records aren't built: both are display only.

## Injuries, teammates, role changes, handcuffs and win chance (October 2026)

Five additions to the model, fitted from nflverse's public injury reports, snap counts and weekly stats for 2023-25
(`scripts/backtest/fit_nflverse.py`, results in `out/results/nflverse.json`). **They have not been through the replay
above**: the session that built them couldn't reach Sleeper's or ESPN's archives, so their effect on projection error,
Waivers and lineups is unmeasured. They ship at the fitted values (or, where nothing could be fitted, the proposed ones);
the replay is the next step, with the configs in [How to rerun](#how-to-rerun).

| What | Fit (2023-25, regular season, QB/RB/WR/TE) | Shipped |
|---|---|---|
| Chance a player listed **questionable** plays (regulars: 2+ games, 5+ points a game) | 69% of 634 (95% interval 66-73%); QB 40% of 78, RB 73%, WR 72%, TE 80% | `P_PLAY.Questionable` QB 0.45, RB 0.73, WR 0.72, TE 0.78 (shrunk toward 69%) |
| Chance a player listed **doubtful** plays | 1% of 83 | `P_PLAY.Doubtful` 0.02 |
| Still questionable once inactives are out (90 minutes before kickoff) | not in the data | `P_PLAY.late` 0.97 |
| What a questionable player scores when he plays, over his untagged games | 0.98 on average (median 0.83), 416 games | `PLAY_K.Questionable` 0.97 |
| Of a missing regular's targets and carries, the share his RB/WR/TE teammates add that game | RB 0.95, TE 1.06, WR 1.55 (noisy); 89% of it at his own position | `REDIST.k` 0.9, `REDIST.same` 0.85 |
| Chance a regular (his team's snap leader) has no offensive snap 1-4 weeks later | RB 8.3%, WR 8.6%, TE 8.3%, QB 13% (benchings count) | `HC.pMiss` |
| Next man up's points in the game the regular misses, over the regular's average | RB 0.82 mean, 0.61 median (35 games); QB 0.80 / 0.72 | `HC.succ` RB 0.7, QB 0.75 |
| Role-change flags (snap/carry/target share, last 2 games vs. earlier): change holds the next week | rises 62-72%, drops 55-68% (1,363 flags) | shown; flagged on Waivers |
| How far toward the last 2 games the next week's form should move (usage-weighted points, no projection) | rises: 0 for RB and WR, 0.2 TE (moving toward a rise made it worse); drops: 0.6-0.9 | `RC.formMax` up 0, down 0.6 |

What each one does:

- **Chance to play.** A questionable or doubtful player's number is his chance to play × what he scores if he plays,
  and his range is the mixture of the two (a zero when he sits). Doubtful now counts the same on Lineup and Waivers
  (before, Lineup counted him in full and Waivers as a zero). The forecast record keeps the if-he-plays numbers, so
  calibration still scores players who played.
- **Teammates.** A questionable or doubtful regular's targets and carries are passed to his teammates at the chance he
  sits. A player ruled out is left to Sleeper's projections, which already reflect it.
- **Backups.** A backup running back or quarterback behind a regular who may sit is valued as the starter at the chance
  he starts.
- **Role changes.** Off until the data includes snap counts (rows saved from October 2026 on).
- **Handcuffs.** On Waivers, the next running back behind a healthy regular (or quarterback, with a superflex spot) is
  worth `HC.pMiss` × what he'd score starting over what the lineup would have instead. Never worth a player you'd start.
- **Win chance.** Pro, Sleeper teams: the lineup with the best chance to beat this week's opponent, with the
  correlations `pairCorr` assumes, never below the Projected lineup's chance, and charging 0.1 points of win chance per
  projected point given up.

What the replay should measure first:
- Whether Sleeper already shades a questionable player's projection, which would make `PLAY_K` and the chance to play
  count twice. Compare projection over form for tagged and untagged players.
- `REDIST.k` from 0 up.
- `RC.formMax.down` against the projection blend.
- Handcuff moves' realized value.
- The win rate of Win chance vs. Projected lineups, with the drafted teams paired into weekly matchups.

## How to rerun

```
python3 scripts/backtest/build_fixtures.py          # about 120 MB of downloads the first time, cached in scripts/backtest/cache/
python3 scripts/backtest/replay.py baseline         # the model as it is in index.html (about 30 s)
python3 scripts/backtest/analyze.py all             # every table in this report except the tuned comparisons
python3 scripts/backtest/replay.py sweep5           # one change at a time and all five together (forecasts only)
python3 scripts/backtest/analyze.py sweep:sweep5
python3 scripts/backtest/replay.py compare          # shipped vs. tuned, with Waivers
python3 scripts/backtest/analyze.py compare:compare
```

`replay.py sweep`, `sweep2`, `sweep3` and `sweep4` are the earlier exploration rounds summarized in
[What we tested and left alone](#what-we-tested-and-left-alone). To add weeks, pass for example `--weeks 2026:5-8` to
`build_fixtures.py` (results for a week are fetched once it has been played).

`driver.html`'s `PATCHES` match the current code (parity is exact on the frozen week), and a patch that no longer
finds its text now stops the run instead of being skipped. The constants added in October 2026 live in plain objects
(`P_PLAY`, `PLAY_K`, `REDIST`, `RC`, `HC`, `WIN`), so a config sets them by dotted name with no source edit, for example
`{"name": "no redistribution", "params": {"REDIST.k": 0}, "full": true}` or `{"params": {"RC.formMax.down": 0.3}}`.
The earlier sweep modes still name some retired experiments (`XFP`, `DOWN_BLEND`); those parameters now do nothing.

```
python3 scripts/backtest/fit_nflverse.py            # the injury, handcuff and role-change fits below (nflverse only)
```
