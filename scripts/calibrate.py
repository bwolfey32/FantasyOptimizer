"""Check Benny's frozen pregame forecasts against what players scored, and save the result as calibration.json.

Usage: python3 scripts/calibrate.py [repo folder]        (run by .github/workflows/refresh-data.yml)
       python3 scripts/calibrate.py --selfcheck          (checks the metrics on simulated data; run by the self-test CI)

Reads forecasts/<season>-wNN.json (written by extract_snapshot.py; each player's forecast as it stood before his game:
[mean, sd, base, Sleeper projection, saved at]) for every week that is over, fetches that week's PPR scores from Sleeper,
and measures:
  coverage50  share of scores inside the likely range (the 25th-75th percentile band the site shows; the target is 50%)
  p20         reliability of "chance of 20+ points": predicted vs. observed rate, in bins
  pairs       reliability of "chance to outscore" for players at the same position in the same week, in bins, plus
              the Brier score
  mae         average miss of Benny's projection and of Sleeper's projection alone, on the same players
The site shows these in its "how sure is this?" notes once three weeks are covered (calibOK in index.html).
D/STs are left out: the site scores them itself, so Sleeper's weekly points don't match its forecasts.
"""
import json
import math
import os
import random
import sys
import urllib.request

POSITIONS = ["QB", "RB", "WR", "TE", "K"]
STATS_URL = "https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=regular&" + "&".join(
    "position[]=" + p for p in POSITIONS)
MIN_MEAN = 3.0       # players projected under this are rarely in a lineup; they'd only flatter the numbers
PAIR_MIN_MEAN = 5.0
P20_BINS = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.01)]
PAIR_BINS = [(0.5, 0.55), (0.55, 0.65), (0.65, 0.8), (0.8, 1.01)]   # the site's Toss-up / Slight / Clear / Strong lean


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def p_above(x, m, sd):
    return 1 - phi((x - m) / sd) if sd > 0 else (1.0 if m >= x else 0.0)


def evaluate(rows):
    """rows: dicts with week, pos, mean, sd, sleeper (or None) and actual. Returns the calibration summary."""
    rows = [r for r in rows if r["mean"] >= MIN_MEAN and r["sd"] and r["actual"] is not None]
    if not rows:
        return None
    inside = 0
    for r in rows:
        lo, hi = r["mean"] - 0.674 * r["sd"], r["mean"] + 0.674 * r["sd"]
        lo = max(0.0, lo)                                   # as the site shows it: no negative low end
        inside += lo <= r["actual"] <= hi
    p20 = []
    for lo, hi in P20_BINS:
        b = [(p_above(20, r["mean"], r["sd"]), r["actual"] >= 20) for r in rows]
        b = [(p, y) for p, y in b if lo <= p < hi]
        if b:
            p20.append({"lo": lo, "hi": min(hi, 1.0), "pred": sum(p for p, _ in b) / len(b), "obs": sum(y for _, y in b) / len(b), "n": len(b)})
    pairs, brier = {i: [] for i in range(len(PAIR_BINS))}, []
    groups = {}
    for r in rows:
        if r["mean"] >= PAIR_MIN_MEAN:
            groups.setdefault((r["week"], r["pos"]), []).append(r)
    for g in groups.values():
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                a, b = g[i], g[j]
                if a["actual"] == b["actual"]:
                    continue
                p = phi((a["mean"] - b["mean"]) / math.sqrt(a["sd"] ** 2 + b["sd"] ** 2))
                fav, won = (p, a["actual"] > b["actual"]) if p >= 0.5 else (1 - p, b["actual"] > a["actual"])
                brier.append((fav - won) ** 2)
                for k, (lo, hi) in enumerate(PAIR_BINS):
                    if lo <= fav < hi:
                        pairs[k].append((fav, won))
    pair_bins = [{"lo": lo, "hi": min(hi, 1.0), "pred": sum(p for p, _ in pairs[k]) / len(pairs[k]), "obs": sum(w for _, w in pairs[k]) / len(pairs[k]), "n": len(pairs[k])}
                 for k, (lo, hi) in enumerate(PAIR_BINS) if pairs[k]]
    both = [r for r in rows if r["sleeper"] is not None]
    mae = {"model": sum(abs(r["mean"] - r["actual"]) for r in both) / len(both) if both else None,
           "sleeper": sum(abs(r["sleeper"] - r["actual"]) for r in both) / len(both) if both else None, "n": len(both)}
    return {"n": len(rows), "coverage50": inside / len(rows), "p20": p20,
            "pairs": {"n": len(brier), "brier": sum(brier) / len(brier) if brier else None, "bins": pair_bins}, "mae": mae}


def fetch_scores(season, week):
    req = urllib.request.Request(STATS_URL.format(season=season, week=week), headers={"User-Agent": "bennys-picks-calibration"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    out = {}
    for row in data or []:
        st, pos = row.get("stats") or {}, (row.get("player") or {}).get("position")
        if (st.get("gp") or 0) > 0 and pos in POSITIONS:          # played; as the site reads weekly stats
            out[str(row.get("player_id"))] = (float(st.get("pts_ppr") or 0), pos)
    return out


def main(root):
    fdir = os.path.join(root, "forecasts")
    with open(os.path.join(root, "snapshot.json"), encoding="utf-8") as f:
        snap = json.load(f)
    season, current = snap["detSeason"], snap["detWeek"]
    rows, weeks = [], []
    for name in sorted(os.listdir(fdir)) if os.path.isdir(fdir) else []:
        if not name.endswith(".json"):
            continue
        with open(os.path.join(fdir, name), encoding="utf-8") as f:
            book = json.load(f)
        if book["season"] != season or book["week"] >= current:
            continue                                         # only weeks that are over, this season
        scores = fetch_scores(book["season"], book["week"])
        if not scores:
            continue
        n0 = len(rows)
        for pid, (mean, sd, _base, sleeper, _at) in book["players"].items():
            if pid in scores:   # played (gp > 0); forecasts for players who sat out aren't judged
                pts, pos = scores[pid]
                rows.append({"week": book["week"], "pos": pos, "mean": mean, "sd": sd, "sleeper": sleeper, "actual": pts})
        if len(rows) > n0:
            weeks.append(book["week"])
    result = evaluate(rows) or {"n": 0}
    result.update({"season": season, "weeks": weeks, "updated": snap.get("createdAt")})
    with open(os.path.join(root, "calibration.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, separators=(",", ":"))
    print(f"Calibration: {result['n']} player-weeks over weeks {weeks}; range coverage {result.get('coverage50')}")


def selfcheck():
    """Forecasts that are right on average and honest about their spread should land near the targets."""
    rng, rows = random.Random(7), []
    for week in range(1, 7):
        for i in range(150):
            mean = rng.uniform(4, 25)
            sd = mean * rng.uniform(0.25, 0.6)   # spreads like real ones, so few simulated scores fall below 0
            rows.append({"week": week, "pos": POSITIONS[i % 4], "mean": mean, "sd": sd, "sleeper": mean, "actual": rng.gauss(mean, sd)})
    for r in rows:   # the site clips the range at 0, so clip the simulated scores the same way
        r["actual"] = max(0.0, r["actual"])
    res = evaluate(rows)
    assert 0.44 <= res["coverage50"] <= 0.56, res["coverage50"]
    for b in res["pairs"]["bins"]:
        assert abs(b["pred"] - b["obs"]) < 0.06, b
    for b in res["p20"]:
        if b["n"] >= 100:
            assert abs(b["pred"] - b["obs"]) < 0.07, b
    biased = evaluate([dict(r, sd=r["sd"] / 2) for r in rows])   # overconfident spreads must show up as low coverage
    assert biased["coverage50"] < 0.4, biased["coverage50"]
    print("calibrate.py selfcheck passed:", json.dumps({"coverage50": round(res["coverage50"], 3), "brier": round(res["pairs"]["brier"], 3)}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selfcheck":
        selfcheck()
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
