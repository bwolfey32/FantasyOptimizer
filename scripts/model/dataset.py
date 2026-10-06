"""Build the trained model's history: one row per player-game a QB/RB/WR/TE played, at horizons 1-4, with the features
known before it (features.py) and what he scored.

Usage: python scripts/model/dataset.py [--seasons 2013-2026] [--sleeper] [--out scripts/model/out/player_weeks.parquet]

--sleeper adds Sleeper's weekly projection (sl_now, sl_ratio; 2018 on) for model B. The first run downloads about
250 MB of nflverse files into scripts/backtest/cache/nflverse/ (and, with --sleeper, Sleeper's projections, kept there
as one small CSV per season); later runs read the cache.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import data  # noqa: E402
import features as F  # noqa: E402


def seasons_of(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2013-2026")
    ap.add_argument("--sleeper", action="store_true")
    ap.add_argument("--classic", action="store_true", help="add Benny's current forecast from the replays (model C)")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "player_weeks.parquet"))
    a = ap.parse_args()
    seasons = seasons_of(a.seasons)
    t = time.time()
    ctx = data.context(seasons, with_sleeper=a.sleeper, live_season=max(seasons), with_classic=a.classic)
    print(f"tables loaded in {time.time() - t:.0f}s: {len(ctx['logs']):,} player-games")
    B = F.Builder(ctx)
    keys = F.training_keys(B.ctx, seasons)
    rows = B.rows(keys)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    rows.to_parquet(a.out, index=False)
    print(f"{len(rows):,} rows ({rows.pid.nunique():,} players, seasons {min(seasons)}-{max(seasons)}) in {time.time() - t:.0f}s -> {a.out}")
    print(rows.groupby("season").size().to_string())


if __name__ == "__main__":
    main()
