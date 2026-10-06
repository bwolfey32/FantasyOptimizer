# Trained model: does learning the weights beat setting them by hand?

*October 6, 2026. Chronological backtest of LightGBM projection models trained on 2013-2025 NFL data, scored against
what players scored, against Sleeper's projection, and against Benny's current hand-tuned model replayed on every week
from 2018 on.*

Benny's weekly number today is a hand-built blend: Sleeper's projection, the player's scoring form, and about 30 constants
set one at a time ([backtest-report.md](backtest-report.md)). This test asks whether models that *learn* those weights from
general NFL situations do better, judged only on seasons they never trained on.

## The short version

| Next week's projection | Trained | Benny today | Sleeper |
|---|---|---|---|
| **Average miss, 2019-24** (out of sample for both models) | **5.19** | 5.25 | 5.31 |
| Average miss, 2025 (Benny today was tuned on it) | 5.14 | **5.10** | 5.22 |
| Average miss, 2026 weeks 1-4 (held out) | 5.25 | 5.24 | 5.29 |
| Squared miss (RMSE), 2019-24 / 2025 / 2026 | **6.79 / 6.67** / 6.87 | 6.84 / 6.68 / **6.79** | 6.88 / 6.76 / 6.79 |
| Too high (+) or low (−) on average, 2019-24 | **−0.11** | +0.21 | +0.51 |
| **Chance-to-outscore score** (Brier, lower is better), 2019-24 / 2025 / 2026 | **0.2132 / 0.2107** / 0.2121 | 0.2154 / 0.2135 / **0.2114** | – |
| Scores inside the likely range (target 50%), 2019-24 / 2025 / 2026 | 53% / 53% / **52%** | 51% / 51% / 45% | – |

| Waivers' values, 2-4 weeks ahead | Trained | Benny today | Sleeper (this week's) |
|---|---|---|---|
| Average miss, 2019-24 / 2025 / 2026 | 5.45 / 5.42 / 5.33 | **5.39 / 5.35 / 5.25** | 5.53 / 5.52 / 5.30 |
| Squared miss, 2019-24 / 2025 / 2026 | **7.05 / 7.02** / 6.96 | 7.07 / 7.05 / **6.94** | 7.14 / 7.16 / 6.97 |
| Too high (+) or low (−), 2019-24 | **−0.00** | −0.13 | +0.48 |

In plain terms:

- **A week ahead, the trained model beats Benny today over 2019-24 by 1.1%** (5.19 vs. 5.25; 95% interval −0.08 to
  −0.03), and both of them beat Sleeper. The gain is concentrated in 2019-22. From 2023 on the two are about even:
  Benny today is 0.03-0.04 ahead in 2024 and 2025, and they tie in 2026.
- **Its chance to outscore**, which Start/Sit shows, is sharper in 2019-24 and 2025 and about even in 2026. **Its likely
  ranges hold half the scores without hand-set widening.**
- **For Waivers it is unbiased but trails on average miss.** Average miss rewards forecasting low, because most weeks land
  under a player's average. Squared miss judges expected points, which is what lineups and Waivers add up, and on that
  it leads in 2019-24 and 2025 and trails a little in 2026.
- **Nothing here is a big jump.** The two models' errors are 98% correlated: what's left is game-day noise. The trained
  model's case is that it learns every weight from data, adapts as habits change (see "Sleeper's quarterbacks"), and is
  at least as accurate.

## What the trained model is

Two models per position (QB, RB, WR, TE), retrained every two weeks during the season on everything played so far:

- **Next week** (`B-hl3-bsldb-md300-h1-rt2`) starts from Sleeper's projection, *corrected for how far Sleeper has been off
  at that position lately*, and learns how much to move it from:
  - **Usage**: target, carry and snap share; usage-weighted points (as `USAGE_PTS`), this season and last.
  - **Role**: depth chart, rank and share of the position group's usage, a rising or shrinking role, a new team, age,
    experience, draft pick.
  - **Team and opponent**: pace, pass rate, points, what the defense allows to the position.
  - **The game**: line, total, implied points, home or away, dome, temperature, wind, rest, a new head coach.
  - **Injuries**: his tag, the work of teammates newly out.
  - **Sleeper's read**: its projection, his share of his position group's projections, and its recent bias.

  No feature names a team, a player or a season.
- **2-4 weeks ahead** (`C-hl3-bcl-md300-far`) starts from Benny today's Waivers value for that week and learns a
  correction from the same features (`C` = Sleeper's and Benny today's numbers as inputs too).

A third LightGBM model per position predicts how far the score lands from the projection; that sets the likely range.

`tests/test_features.py` changes every box score, injury tag, line, weather report, depth chart and future Sleeper
projection from the prediction week on, and checks that not one feature moves.

## How it improved on the first version

The first version (this morning) tied Benny today a week ahead and lost on Waivers. Each change below was chosen on
2019-24 only:

| Change | Average miss a week ahead, 2019-24 |
|---|---|
| First version (start from Sleeper, one model for next week) | 5.229 |
| + weekly depth charts (nflverse; a player's depth after skipping teammates who are out) | 5.225 |
| + retrain every two weeks during the season | 5.205 |
| + track Sleeper's recent bias at each position, and start from Sleeper's projection less that bias | **5.194** |
| Benny today's own number as the starting point instead (model C) | 5.209 (no gain) |
| Retraining with extra weight on the current season | worse (5.219) |

Learning from Benny today's number added nothing a week ahead, which says the trained model already knows what the
hand-tuned rules know. Two to four weeks ahead it helped: starting from Benny today's Waivers values gave the lowest
squared miss.

### Sleeper's quarterbacks

Sleeper projected quarterbacks 1.8-4.1 points too high in every season 2018-25, and in 2026 it stopped (−0.1). The first
version had learned the old habit as a fixed discount and projected 2026 quarterbacks 2.75 points too low. The model now
reads Sleeper's bias as it goes (`sl_bias`: this season's misses so far, with last season's worth about two weeks), so the
discount fades as the evidence comes in:

| 2026 week | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| Sleeper's QB bias the model reads | +2.8 | +1.6 | +1.1 | +0.5 |
| Trained QB projection minus Sleeper's | −2.9 | −1.8 | −1.4 | −0.4 |
| Trained QBs too high (+) or low (−) | −2.9 | −1.7 | −2.9\* | +0.6 |

\* A low-scoring week for every quarterback: Sleeper was 1.6 too low, Benny today 1.9.

Week 1 can't know; by week 4 the trained model's QB bias is smaller than Sleeper's. This is most of what 2026 still costs it.

## Against Benny today, season by season (a week ahead)

| Season | Player-weeks | Trained | Benny today | Squared: trained | Squared: Benny today |
|---|---|---|---|---|---|
| 2019 | 3,380 | **5.39** | 5.41 | 7.05 | 7.06 |
| 2020 | 3,783 | **5.28** | 5.32 | 6.88 | 6.92 |
| 2021 | 3,990 | **5.17** | 5.35 | 6.72 | 6.85 |
| 2022 | 3,905 | **5.05** | 5.17 | 6.66 | 6.72 |
| 2023 | 3,788 | 5.07 | 5.07 | 6.66 | 6.66 |
| 2024 | 3,820 | 5.22 | **5.19** | 6.81 | 6.82 |
| 2025\* | 3,917 | 5.14 | **5.10** | 6.67 | 6.68 |
| 2026 wk 1-4 | 969 | 5.25 | 5.24 | 6.87 | **6.79** |

\* Benny today's constants were chosen on 2025.

Players Benny today has a number for (weeks 2 on), who played and whom Sleeper projected at 3+; for a tagged player, both
models' number if he plays. 2018, the first season with Sleeper data, is left out: the trained model had never seen
Sleeper's projection before it, so it isn't a fair test (5.70 vs. 5.58).

By position over 2019-24, the gain is mostly quarterbacks (5.91 vs. 6.12) and receivers (5.29 vs. 5.35); running backs
and tight ends are even.

## Against Sleeper

| Period | Trained | Sleeper | 95% interval of the change | 2-4 weeks: trained | Sleeper |
|---|---|---|---|---|---|
| 2019-24 | 5.19 | 5.31 | −0.14 to −0.09 | 5.45 | 5.52 |
| 2025 | 5.13 | 5.20 | −0.12 to −0.03 | 5.41 | 5.51 |
| 2026 wk 1-4 | 5.25 | 5.28 | −0.11 to +0.04 | 5.33 | 5.30 |

## Choosing between them

The plan's rule was to switch when the trained model beats Benny today on average miss in 2025 and 2026. It doesn't: it
trails by 0.04 in 2025 (the season Benny today was tuned on) and ties in 2026. Over the six seasons neither model was
tuned on, it wins by 1.1%, but most of that is 2019-22. The options:

1. **Use it where it is clearly better: Start/Sit's chances and the likely ranges.** Sharper chances in 2019-24 and 2025,
   honest ranges in every season, no hand-set spread.
2. **Use it for the weekly projection too**, with the 2026 caveat: early in a season where Sleeper's habits change, it
   needs about three weeks to catch up.
3. **Average the two** for the weekly number. Their errors are nearly the same, so the gain is small. Two to four weeks
   ahead, averaging gives up the trained model's unbiasedness for Benny today's better average miss.
4. **Wait for more 2026 weeks.** Both models are close enough that 4 held-out weeks can't separate them. By midseason
   there will be 10.

## Limitations

1. **Four held-out 2026 weeks**, all early season, the weeks the trained model is weakest. Rerun at midseason.
2. **Benny today was tuned on 2025.** The six seasons before it are the fair comparison, and Benny today's rules were
   designed with recent seasons in mind, which may be why the gap narrows after 2022.
3. **The replays rebuild what the site would have known**: closing lines (nflverse's for most of 2023, where ESPN's feed
   has none), archived weather, the Friday injury report. Both models see the same inputs.
4. **Kickers and D/STs are not modeled.**
5. **The 2-4 week comparison** leaves out weeks Benny today valued at 0 (a bye or an expected absence): the trained
   model's rows are games the player played.

## How to rerun

```
python scripts/model/dataset.py --sleeper --classic           # history; --classic needs the replay below first
python -m pytest tests/test_features.py                       # leakage and data checks
python scripts/backtest/build_fixtures.py --weeks 2018:2-17,2019:2-17,2020:2-17,2021:2-18,2022:2-18,2023:2-18,2024:2-18,2025:2-18,2026:1-4
python scripts/backtest/replay.py baseline                    # Benny today on every week (about 5 minutes)
python scripts/model/backtest.py tune B-hl3-bsldb-md300-h1-rt2              # any configs, scored on 2019-24
python scripts/model/backtest.py final B-hl3-bsldb-md300-h1-rt2 A-hl5-md300-h1 C-hl3-bcl-md300-far
python scripts/model/train.py B-hl3-bsldb-md300-h1-rt2 C-hl3-bcl-md300-far  # the models for live use
```

Config names read `VARIANT-hlN[-tags]` (`train.config()` lists the tags). Results go to `scripts/model/out/backtest/`
(`final.json`, and per-config out-of-season predictions that reruns reuse).
