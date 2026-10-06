"""Fit the injury, handcuff and role-change constants in index.html from nflverse's public data alone (no Sleeper archive).

Usage: python3 scripts/backtest/fit_nflverse.py [--seasons 2023,2024,2025] [--out scripts/backtest/out/results/nflverse.json]

nflverse publishes the official injury report (report_status: Questionable, Doubtful, Out), snap counts and weekly stats
for every regular-season game. That is enough to measure, without any projection:
  P_PLAY    how often a player with each designation took an offensive snap (QB/RB/WR/TE), with a 95% interval
  PLAY_K    a player who played through a designation: his points that game over his average in his untagged games
  HC.pMiss  how often a regular (his team's snap leader at the position) has no offensive snap 1-4 weeks later
  HC.succ   what the next man up scores in a game the regular misses, over the regular's own average
  REDIST.k  of the targets and carries a missing regular averaged, the share his teammates at RB/WR/TE add that game
  RC        role-change flags (snap, carry and target share, last two games against the earlier ones): how often the
            change holds the next week, and how far toward the recent games the next week's form should move
            (formMax), judged on usage-weighted points without any projection, so an upper bound on what the
            projection blend can still gain
Downloads are cached under scripts/backtest/cache/nflverse/. Sleeper's projections already know some of this (a
player ruled out, a depth-chart change), which only a full replay (replay.py) can measure; this fit is what the public
data alone says.
"""
import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "model"))
from nflverse import BASE, load  # noqa: E402  (shared loader and cache, scripts/model/nflverse.py)

SKILL = ("QB", "RB", "WR", "TE")
# index.html's USAGE_PTS: PPR points a game's usage is worth [base, per target, per carry, per pass attempt]
USAGE_PTS = {"QB": [-0.191, 0, 1.053, 0.422], "RB": [-0.367, 1.242, 0.769, 0], "WR": [0.06, 1.737, 0.682, 0], "TE": [-0.002, 1.904, 0.572, 0]}
USAGE_W = 0.75
RC_W = {"RB": (0.4, 0.35, 0.25), "WR": (0.5, 0, 0.5), "TE": (0.5, 0, 0.5)}   # index.html's RC.w: snap, carry, target share


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def wilson(k, n, z=1.96):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def season_data(s, pfr_of):
    inj = load(f"injuries_{s}.csv", f"{BASE}/injuries/injuries_{s}.csv")
    snaps = load(f"snap_counts_{s}.csv", f"{BASE}/snap_counts/snap_counts_{s}.csv")
    stats = load(f"stats_{s}.csv", f"{BASE}/stats_player/stats_player_week_{s}.csv")
    snap = {}            # (pfr id, week) -> offense share
    plays = set()        # (team, week) with a game
    for r in snaps:
        if r["game_type"] != "REG":
            continue
        w = int(r["week"])
        plays.add((r["team"], w))
        if num(r["offense_snaps"]) > 0:
            snap[(r["pfr_player_id"], w)] = num(r["offense_pct"])
    g = {}               # (gsis, week) -> per-game row
    team_tot = defaultdict(lambda: [0.0, 0.0])   # (team, week) -> [targets, carries]
    for r in stats:
        if r["season_type"] != "REG" or r["position"] not in SKILL:
            continue
        w, t = int(r["week"]), r["team"]
        row = {"pos": r["position"], "team": t, "ppr": num(r["fantasy_points_ppr"]), "tgt": num(r["targets"]), "car": num(r["carries"]),
               "att": num(r["attempts"]), "rec": num(r["receptions"])}
        g[(r["player_id"], w)] = row
        team_tot[(t, w)][0] += row["tgt"]
        team_tot[(t, w)][1] += row["car"]
    for (gid, w), row in g.items():
        tt = team_tot[(row["team"], w)]
        row["snp"] = snap.get((pfr_of.get(gid), w))
        row["ts"] = row["tgt"] / tt[0] if tt[0] else 0
        row["cs"] = row["car"] / tt[1] if tt[1] else 0
        u = USAGE_PTS[row["pos"]]
        row["use"] = u[0] + u[1] * row["tgt"] + u[2] * row["car"] + u[3] * row["att"]
        row["form"] = USAGE_W * row["use"] + (1 - USAGE_W) * row["ppr"]
    played = lambda gid, w: (pfr_of.get(gid), w) in snap or ((gid, w) in g and (g[(gid, w)]["tgt"] + g[(gid, w)]["car"] + g[(gid, w)]["att"]) > 0)
    tags = {}
    for r in inj:
        if (r.get("season_type") or r.get("game_type")) == "REG" and r["position"] in SKILL and r["report_status"] in ("Questionable", "Doubtful", "Out"):
            tags[(r["gsis_id"], int(r["week"]))] = (r["report_status"], r["position"], r["team"])
    return {"g": g, "plays": plays, "played": played, "tags": tags, "snap": snap}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2023,2024,2025")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "results", "nflverse.json"))
    a = ap.parse_args()
    seasons = [int(x) for x in a.seasons.split(",")]
    pfr_of = {r["gsis_id"]: r["pfr_id"] for r in load("players.csv", f"{BASE}/players/players.csv") if r["gsis_id"] and r["pfr_id"]}
    tally = defaultdict(lambda: [0, 0])          # (status, pos) -> [played, n]
    playk = defaultdict(list)                    # status -> ratio of points to untagged average
    miss = defaultdict(lambda: [0, 0])           # pos -> [missed, n] for regulars 1-4 weeks later
    succ = defaultdict(list)                     # pos -> next man up's points over the regular's average
    redist = defaultdict(list)                   # pos of missing regular -> teammates' added work / his work
    redist_same = []                             # share of the added work that went to his own position
    rc = []                                      # role-change flags: (pos, dir, err at formMax 0..1, persists)
    for s in seasons:
        S = season_data(s, pfr_of)
        g, plays, played, tags = S["g"], S["plays"], S["played"], S["tags"]
        # ---- P(play) and PLAY_K ----
        by_player = defaultdict(list)
        for (gid, w), row in g.items():
            by_player[gid].append((w, row))
        for (gid, w), (st, pos, team) in tags.items():
            if (team, w) not in plays:
                continue
            # regulars only (2+ earlier games this season, 5+ points a game): a deep backup can be active and still
            # take no offensive snap, which isn't what the designation is about
            before = [r["ppr"] for ww, r in by_player[gid] if ww < w]
            if len(before) < 2 or statistics.mean(before) < 5:
                continue
            p = played(gid, w)
            tally[(st, pos)][0] += p
            tally[(st, pos)][1] += 1
            if p and st != "Out" and (gid, w) in g:
                clean = [r["ppr"] for ww, r in by_player[gid] if ww != w and (gid, ww) not in tags]
                if len(clean) >= 3 and statistics.mean(clean) >= 5:
                    playk[st].append(g[(gid, w)]["ppr"] / statistics.mean(clean))
        # ---- regulars: misses, the next man up, and where the work goes ----
        weeks = sorted({w for _, w in g})
        team_pos = defaultdict(list)             # (team, pos, week) -> [(gid, row)]
        for (gid, w), row in g.items():
            team_pos[(row["team"], row["pos"], w)].append((gid, row))
        for (team, pos, w), lst in list(team_pos.items()):
            lead = max(lst, key=lambda x: (x[1]["snp"] or 0, x[1]["tgt"] + x[1]["car"] + x[1]["att"]))
            gid, row = lead
            if pos != "QB" and (row["snp"] or 0) < 0.5:
                continue
            hist = [r for ww, r in by_player[gid] if ww <= w and r["team"] == team]
            avg = statistics.mean(r["ppr"] for r in hist)
            if avg < 8 or len(hist) < 2:
                continue
            others = sorted([x for x in lst if x[0] != gid], key=lambda x: -((x[1]["snp"] or 0) + 0.01 * (x[1]["car"] + x[1]["tgt"] + x[1]["att"])))
            for k in range(1, 5):
                w2 = w + k
                if (team, w2) not in plays:
                    continue
                m = not played(gid, w2)
                miss[pos][0] += m
                miss[pos][1] += 1
                if m and k == 1:
                    # the next man up: his teammate at the position with the most snaps this week, in the week he's missing
                    if others and (others[0][0], w2) in g and g[(others[0][0], w2)]["team"] == team:
                        succ[pos].append(g[(others[0][0], w2)]["ppr"] / avg)
                    if pos != "QB":
                        work = statistics.mean(r["tgt"] + r["car"] for r in hist)
                        if work >= 4:
                            add = add_same = 0.0
                            for P in ("RB", "WR", "TE"):
                                for og, orow in team_pos.get((team, P, w2), []):
                                    prev = [r for ww, r in by_player[og] if ww <= w and r["team"] == team]
                                    if len(prev) < 2:
                                        continue
                                    d = orow["tgt"] + orow["car"] - statistics.mean(r["tgt"] + r["car"] for r in prev)
                                    add += d
                                    add_same += d if P == pos else 0
                            redist[pos].append(add / work)
                            if add > 0:
                                redist_same.append(add_same / add)
        # ---- role changes ----
        for gid, lst in by_player.items():
            lst.sort(key=lambda x: x[0])
            for i in range(4, len(lst)):
                w_next, nxt = lst[i]
                prior = [r for _, r in lst[:i] if r["team"] == nxt["team"]]
                if len(prior) < 4 or nxt["pos"] not in RC_W or any(r["snp"] is None for r in prior[-4:]):
                    continue
                wt = RC_W[nxt["pos"]]
                o = [wt[0] * (r["snp"] or 0) + wt[1] * r["cs"] + wt[2] * r["ts"] for r in prior]
                score = statistics.mean(o[-2:]) - statistics.mean(o[:-2])
                if abs(score) < 0.12 or (score > 0 and statistics.mean((r["snp"] or 0) for r in prior[-2:]) < 0.4):
                    continue
                # an in-game injury, not a role: his latest snap share under half the one before
                if score < 0 and (prior[-1]["snp"] or 0) < 0.5 * (prior[-2]["snp"] or 1):
                    continue
                form_all = statistics.mean(r["form"] for r in prior)
                form_rec = statistics.mean(r["form"] for r in prior[-2:])
                errs = [abs(nxt["ppr"] - (form_all + f / 10 * (form_rec - form_all))) for f in range(11)]
                on = wt[0] * (nxt["snp"] or 0) + wt[1] * nxt["cs"] + wt[2] * nxt["ts"]
                persists = (on - statistics.mean(o[:-2])) * score > 0 and abs(on - statistics.mean(o[:-2])) >= 0.5 * abs(score)
                rc.append((nxt["pos"], "up" if score > 0 else "down", errs, persists, s))
    out = {"seasons": seasons, "pPlay": {}, "playK": {}, "pMiss": {}, "succ": {}, "redist": {}, "rc": {}}
    for st in ("Questionable", "Doubtful", "Out"):
        k = sum(tally[(st, p)][0] for p in SKILL)
        n = sum(tally[(st, p)][1] for p in SKILL)
        out["pPlay"][st] = {"all": [round(k / n, 3) if n else None, n, wilson(k, n)],
                            **{p: [round(tally[(st, p)][0] / tally[(st, p)][1], 3) if tally[(st, p)][1] else None, tally[(st, p)][1]] for p in SKILL}}
    for st, xs in playk.items():
        out["playK"][st] = {"median": round(statistics.median(xs), 3), "mean": round(statistics.mean(xs), 3), "n": len(xs)}
    for p, (k, n) in miss.items():
        out["pMiss"][p] = [round(k / n, 3), n, wilson(k, n)]
    for p, xs in succ.items():
        out["succ"][p] = {"median": round(statistics.median(xs), 3), "mean": round(statistics.mean(xs), 3), "n": len(xs)}
    for p, xs in redist.items():
        out["redist"][p] = {"mean": round(statistics.mean(xs), 3), "median": round(statistics.median(xs), 3), "n": len(xs)}
    out["redist"]["sameShare"] = round(statistics.mean(redist_same), 3) if redist_same else None
    for pos in ("RB", "WR", "TE"):
        for d in ("up", "down"):
            rows = [r for r in rc if r[0] == pos and r[1] == d]
            if not rows:
                continue
            mae = [statistics.mean(r[2][f] for r in rows) for f in range(11)]
            best = min(range(11), key=lambda f: mae[f])
            out["rc"][f"{pos} {d}"] = {"n": len(rows), "persists": round(sum(r[3] for r in rows) / len(rows), 3),
                                       "mae0": round(mae[0], 3), "bestFormMax": best / 10, "maeBest": round(mae[best], 3), "mae5": round(mae[5], 3)}
    allrows = rc
    mae = [statistics.mean(r[2][f] for r in allrows) for f in range(11)] if allrows else []
    if mae:
        out["rc"]["all"] = {"n": len(allrows), "bestFormMax": min(range(11), key=lambda f: mae[f]) / 10, "mae": [round(x, 3) for x in mae]}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
