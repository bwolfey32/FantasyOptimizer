"""Every QB/RB/WR/TE's game log and season totals since 2013, one small JSON file per player, for the player pages
(index.html's #player/<id> and the static /players/<slug>/ pages that scripts/player_pages.py writes).

Usage: python scripts/model/player_history.py [--out players/data] [--since 2013] [--force]

Box scores come from nflverse (data.season_logs, plus the touchdowns, interceptions, completions and fumbles it leaves
out), so the points are Sleeper's PPR (an interception counts -1). The browser re-scores them for other formats from the
catches, as it does this season's (fmtPts). Run by .github/workflows/refresh-data.yml; rebuilt at most once every 20
hours (players/data/index.json keeps the time), and a file is only rewritten when its numbers changed.

players/data/<sleeperId>.json:
  {"v": 1, "id", "gsis", "name", "pos",
   "scols": [...], "seasons": [[season, team, gp, ppr, rec, tgt, car, patt, cmp, pyd, ptd, int, ryd, rtd, recyd, rectd,
                                fum, snp, tsh, csh, rank], ...],
   "gcols": [...], "games": {"2025": [[week, team, opp, ppr, rec, tgt, car, patt, cmp, pyd, ptd, int, ryd, rtd, recyd,
                                       rectd, fum, snp], ...]}}
  team: his teams that season in order ("NYJ/PIT"); snp: average share of his team's offensive snaps in the games he
  played (null before snap counts); tsh, csh: his share of his team's targets and carries in those games; rank: his
  finish at the position by total PPR points among everyone who played it that season.
players/data/index.json: {"updated", "seasons": [first, last], "n": files}
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import data  # noqa: E402
import nflverse as nv  # noqa: E402

ROOT = nv.ROOT
MAX_AGE_HOURS = 20
SCOLS = ["season", "team", "gp", "ppr", "rec", "tgt", "car", "patt", "cmp", "pyd", "ptd", "int", "ryd", "rtd", "recyd",
         "rectd", "fum", "snp", "tsh", "csh", "rank"]
GCOLS = ["week", "team", "opp", "ppr", "rec", "tgt", "car", "patt", "cmp", "pyd", "ptd", "int", "ryd", "rtd", "recyd",
         "rectd", "fum", "snp"]
COUNTS = ["ppr", "rec", "tgt", "car", "patt", "cmp", "pyd", "ptd", "int", "ryd", "rtd", "recyd", "rectd", "fum"]


def extras(season, max_age):
    """The box-score columns season_logs drops, per player-week."""
    st = nv.frame("stats_{s}.csv", season, max_age)
    st = st[st.season_type == "REG"]
    f = lambda c: pd.to_numeric(st[c], errors="coerce").fillna(0) if c in st else 0
    return pd.DataFrame({"week": st.week, "pid": st.player_id, "cmp": f("completions"), "ptd": f("passing_tds"),
                         "int": f("passing_interceptions"), "rtd": f("rushing_tds"), "rectd": f("receiving_tds"),
                         "fum": f("rushing_fumbles_lost") + f("receiving_fumbles_lost") + f("sack_fumbles_lost"),
                         "name": st.player_display_name}).drop_duplicates(["week", "pid"])


def season_frame(season, max_age):
    """One row per player-game with every GCOLS column, and his name."""
    lg, _ = data.season_logs(season, max_age)
    lg = lg.merge(extras(season, max_age), on=["week", "pid"], how="left")
    for c in ("cmp", "ptd", "int", "rtd", "rectd", "fum"):
        lg[c] = lg[c].fillna(0)
    return lg


def r(x, d=1):
    """A JSON number: rounded, whole numbers as ints, NaN as null."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    x = round(float(x), d)
    return int(x) if x == int(x) else x


def seasons_of(g):
    """A player's season rows from his games (all seasons), ranks attached later."""
    out = []
    for s, gs in g.groupby("season", sort=True):
        gs = gs.sort_values("week")
        teams = list(dict.fromkeys(gs.team.dropna()))
        tot = gs[COUNTS].sum()
        tm_t, tm_c = gs.tm_tgt.sum(), gs.tm_car.sum()
        snp = gs.snp.dropna()
        out.append({"season": int(s), "team": "/".join(teams), "gp": len(gs), **{c: tot[c] for c in COUNTS},
                    "snp": snp.mean() if len(snp) else None, "tsh": tot["tgt"] / tm_t if tm_t else None,
                    "csh": tot["car"] / tm_c if tm_c else None})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "players", "data"))
    ap.add_argument("--since", type=int, default=2013)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    idx_path = os.path.join(a.out, "index.json")
    if not a.force and os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            old = json.load(f)
        age = time.time() - datetime.fromisoformat(old["updated"].replace("Z", "+00:00")).timestamp()
        if age < MAX_AGE_HOURS * 3600:
            print(f"Player history is {age / 3600:.1f} hours old; kept (--force rebuilds it)")
            return

    with open(os.path.join(ROOT, "snapshot.json"), encoding="utf-8") as f:
        snap = json.load(f)
    with open(os.path.join(ROOT, "share-players.json"), encoding="utf-8") as f:
        share = json.load(f)["p"]
    with open(os.path.join(ROOT, "player-ids.json"), encoding="utf-8") as f:
        pids = json.load(f)["ids"]
    last = int(snap["season"])

    # every season's games; a season nflverse hasn't started publishing yet is skipped
    frames = []
    for s in range(a.since, last + 1):
        try:
            frames.append(season_frame(s, 24 if s == last else None))
        except Exception as e:  # noqa: BLE001
            print(f"{s}: no box scores ({e.__class__.__name__}); skipped")
    g = pd.concat(frames, ignore_index=True)
    first_season, last_season = int(g.season.min()), int(g.season.max())

    # Sleeper id <-> gsis id: DynastyProcess's crosswalk (data.people), then player-ids.json for the rest
    ppl = data.people(range(max(a.since, last - 4), last_season + 1))
    sid_of = {gid: sid for gid, sid in ppl.sleeper_id.dropna().items()}
    for sid, (_, gid) in pids.items():
        if gid and gid not in sid_of:
            sid_of[gid] = sid
    gsis_of = {sid: gid for gid, sid in sid_of.items()}

    # his position: the one he played most; finish rank by season among everyone at that position
    pos_of = g.groupby("pid").pos.agg(lambda p: p.value_counts().index[0])
    tot = g.groupby(["season", "pid"], as_index=False).ppr.sum()
    tot["pos"] = tot.pid.map(pos_of)
    tot["rank"] = tot.groupby(["season", "pos"]).ppr.rank(ascending=False, method="min").astype(int)
    rank = {(s, p): k for s, p, k in zip(tot.season, tot.pid, tot["rank"])}
    name_of = g.dropna(subset=["name"]).groupby("pid").name.last()

    want = {sid for sid, v in share.items() if v[1] in data.SKILL}
    want |= {row[0] for row in snap["proj"] if row[2] in data.SKILL}
    by_pid = dict(tuple(g.groupby("pid")))
    os.makedirs(a.out, exist_ok=True)
    wrote = n = 0
    for sid in sorted(want):
        gid = gsis_of.get(sid)
        gp = by_pid.get(gid) if gid else None
        if gp is None or gp.empty:
            continue
        info = share.get(sid) or []
        srows = seasons_of(gp)
        seasons = [[r(x["season"]), x["team"], x["gp"], *[r(x[c]) for c in COUNTS], r(x["snp"], 3), r(x["tsh"], 3),
                    r(x["csh"], 3), rank.get((x["season"], gid))] for x in srows]
        games = {}
        for s, gs in gp.sort_values(["season", "week"]).groupby("season", sort=True):
            games[str(int(s))] = [[int(w.week), w.team, w.opp, *[r(getattr(w, c)) for c in COUNTS], r(w.snp, 3)]
                                  for w in gs.itertuples()]
        out = {"v": 1, "id": sid, "gsis": gid, "name": info[0] if info else name_of.get(gid, ""),
               "pos": info[1] if info and info[1] in data.SKILL else pos_of[gid],
               "scols": SCOLS, "seasons": seasons, "gcols": GCOLS, "games": games}
        text = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
        p = os.path.join(a.out, f"{sid}.json")
        old = None
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                old = f.read()
        if old != text:
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            wrote += 1
        n += 1
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(idx_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"updated": updated, "seasons": [first_season, last_season], "n": n}, f, separators=(",", ":"))
    print(f"Player history: {n} players, {wrote} files written, seasons {first_season}-{last_season}")


if __name__ == "__main__":
    main()
