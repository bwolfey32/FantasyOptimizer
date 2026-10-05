"""Score the replayed forecasts and Waivers moves against what happened, and print the tables for the report.

Usage: python3 scripts/backtest/analyze.py [section ...]
Sections: forecast (default), context, spread, ros, waivers, sweep, usage, compare (base vs tuned), all
Reads scripts/backtest/out/{replay,actuals,fixtures}; writes scripts/backtest/out/results/<section>.json and prints
Markdown tables.

Splits: 2025 weeks 2-18 tune the constants; 2026 weeks 1-4 are held out. Within 2025, weeks 2-10 vs 11-18 is a second
check that a change helps both halves rather than one.
"""
import glob
import json
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import calibrate  # noqa: E402  (scripts/calibrate.py)
import replay     # noqa: E402

OUT = os.path.join(HERE, "out")
RES = os.path.join(OUT, "results")
POSITIONS = ["QB", "RB", "WR", "TE", "K"]


def key_sw(key):
    s, w = key.split("-w")
    return int(s), int(w)


_act = {}


def actuals(s, w):
    if (s, w) not in _act:
        p = os.path.join(OUT, "actuals", "%d-w%02d.json" % (s, w))
        _act[(s, w)] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
    return _act[(s, w)]


def pts_of(s, w, pid):
    """PPR points scored, None if he didn't play (or the week has no results yet)."""
    a = actuals(s, w)
    if not a:
        return None
    if pid in a["D"]:
        return a["D"][pid]
    x = a["P"].get(pid)
    return x[0] if x else None


def split_of(s, w):
    return "2026 (held out)" if s == 2026 else "2025"


def mean(a):
    return sum(a) / len(a) if a else None


def se(a):
    return statistics.stdev(a) / math.sqrt(len(a)) if len(a) > 1 else None


def f(x, d=2):
    return "–" if x is None else f"{x:.{d}f}"


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def save(name, obj):
    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)


# ---------- the scored player-weeks ----------
_base = None


def base():
    global _base
    if _base is None:
        _base = replay.load("baseline")
    return _base


def scored(rep=None, cfg="base"):
    """Player-weeks with a forecast and a result (he played), as dicts; D/STs left out as in calibrate.py."""
    rep = rep or base()
    out = []
    for key, r in sorted(rep.items()):
        if "error" in r:
            continue
        s, w = key_sw(key)
        for pid, x in r["configs"][cfg]["rows"].items():
            if x["pos"] == "DEF":
                continue
            a = pts_of(s, w, pid)
            if a is None:
                continue
            out.append(dict(x, pid=pid, season=s, week=w, actual=a, sleeper=x["proj"]))
    return out


def evaluate(rows):
    return calibrate.evaluate([{"week": (r["season"], r["week"]), "pos": r["pos"], "mean": r["mean"], "sd": r["sd"],
                                "sleeper": r["sleeper"], "actual": r["actual"]} for r in rows])


def summary_line(label, rows):
    e = evaluate(rows)
    if not e:
        return [label, 0, "–", "–", "–", "–", "–", "–"]
    both = [r for r in rows if r["mean"] >= calibrate.MIN_MEAN and r["sleeper"] is not None]
    bias_m = mean([r["mean"] - r["actual"] for r in both])
    bias_s = mean([r["sleeper"] - r["actual"] for r in both])
    return [label, e["n"], f(e["mae"]["model"]), f(e["mae"]["sleeper"]), f(bias_m), f(bias_s), f(e["coverage50"] * 100, 1) + "%",
            f(e["pairs"]["brier"], 3)]


HEAD = ["Group", "Player-weeks", "MAE Benny", "MAE Sleeper", "Bias Benny", "Bias Sleeper", "Inside range (target 50%)", "Brier"]


def sec_forecast():
    rows = scored()
    lines, res = [], {}
    groups = [("All", rows)] + [(p, [r for r in rows if r["pos"] == p]) for p in POSITIONS]
    groups += [("2025 wk 2-18", [r for r in rows if r["season"] == 2025]), ("2026 wk 1-4", [r for r in rows if r["season"] == 2026])]
    groups += [("Weeks 1-4", [r for r in rows if r["week"] <= 4]), ("Weeks 5-9", [r for r in rows if 5 <= r["week"] <= 9]),
               ("Weeks 10-14", [r for r in rows if 10 <= r["week"] <= 14]), ("Weeks 15-18", [r for r in rows if r["week"] >= 15])]
    for lo, hi in ((3, 8), (8, 12), (12, 16), (16, 99)):
        groups.append((f"Benny projects {lo}-{hi if hi < 99 else '+'}", [r for r in rows if lo <= r["mean"] < hi]))
    table_rows = [summary_line(*g) for g in groups]
    print("### Forecast accuracy (baseline model)\n")
    print(table(HEAD, table_rows))
    e = evaluate(rows)
    print("\nChance of 20+ points, predicted vs. observed:")
    print(table(["Predicted bin", "Predicted", "Observed", "n"], [[f"{b['lo']:.1f}-{b['hi']:.1f}", f(b["pred"]), f(b["obs"]), b["n"]] for b in e["p20"]]))
    print("\nChance to outscore (same position, same week), predicted vs. observed:")
    print(table(["Lean", "Predicted", "Observed", "pairs"], [[f"{b['lo']:.2f}-{b['hi']:.2f}", f(b["pred"]), f(b["obs"]), b["n"]] for b in e["pairs"]["bins"]]))
    res["overall"] = e
    res["groups"] = {g[0]: evaluate(g[1]) for g in groups}
    save("forecast", res)


def sec_context():
    rows = [r for r in scored() if r["mean"] >= calibrate.MIN_MEAN and r["sleeper"] is not None]
    groups = [("Home", [r for r in rows if r["home"]]), ("Away", [r for r in rows if not r["home"]]),
              ("Dome / closed roof", [r for r in rows if r["covered"]]),
              ("Outdoors, fair weather", [r for r in rows if not r["covered"] and (r["wx"] or 0) < 0.3]),
              ("Outdoors, rough weather (wind/rain/snow/cold)", [r for r in rows if not r["covered"] and (r["wx"] or 0) >= 0.3]),
              ("Favored by 7+", [r for r in rows if r["line"] is not None and r["line"] >= 7]),
              ("Favored by 0.5-6.5", [r for r in rows if r["line"] is not None and 0 < r["line"] < 7]),
              ("Underdog by 0.5-6.5", [r for r in rows if r["line"] is not None and -7 < r["line"] < 0]),
              ("Underdog by 7+", [r for r in rows if r["line"] is not None and r["line"] <= -7]),
              ("Team total 26+", [r for r in rows if (r["implied"] or 0) >= 26]),
              ("Team total under 20", [r for r in rows if r["implied"] is not None and r["implied"] < 20])]
    head = ["Group", "n", "Benny bias (proj - actual)", "±", "Sleeper bias", "±", "MAE Benny", "MAE Sleeper"]
    out, res = [], {}
    for name, g in groups:
        bm, bs = [r["mean"] - r["actual"] for r in g], [r["sleeper"] - r["actual"] for r in g]
        out.append([name, len(g), f(mean(bm)), f(se(bm)), f(mean(bs)), f(se(bs)), f(mean([abs(x) for x in bm])), f(mean([abs(x) for x in bs]))])
        res[name] = {"n": len(g), "bias_model": mean(bm), "se_model": se(bm), "bias_sleeper": mean(bs), "se_sleeper": se(bs)}
    print("### Bias by game context (positive = projected too high)\n")
    print(table(head, out))
    # by position within each context, for the model
    print("\nBenny's bias by position and context:")
    head2 = ["Group"] + POSITIONS
    out2 = []
    for name, g in groups:
        out2.append([name] + [f(mean([r["mean"] - r["actual"] for r in g if r["pos"] == p])) for p in POSITIONS])
    print(table(head2, out2))
    save("context", res)


def sec_spread():
    rows = [r for r in scored() if r["mean"] >= calibrate.MIN_MEAN and r["sd"]]
    print("### Is the likely range the right width?\n")
    out, res = [], {}
    for name, g in [("All", rows)] + [(p, [r for r in rows if r["pos"] == p]) for p in POSITIONS]:
        z = [(r["actual"] - r["mean"]) / r["sd"] for r in g]
        az = sorted(abs(x) for x in z)
        med = az[len(az) // 2]
        cover = {k: mean([1 if abs(x) <= q else 0 for x in z]) for k, q in (("50", 0.674), ("80", 1.2816), ("90", 1.645))}
        sd_pred = mean([r["sd"] for r in g])
        sd_obs = statistics.pstdev([r["actual"] - r["mean"] for r in g])
        below = mean([1 if r["actual"] < r["mean"] - 0.674 * r["sd"] else 0 for r in g])
        above = mean([1 if r["actual"] > r["mean"] + 0.674 * r["sd"] else 0 for r in g])
        out.append([name, len(g), f(sd_pred), f(sd_obs), f(cover["50"] * 100, 1) + "%", f(cover["80"] * 100, 1) + "%", f(cover["90"] * 100, 1) + "%",
                    f(below * 100, 1) + "%", f(above * 100, 1) + "%", f(med / 0.674)])
        res[name] = {"n": len(g), "sd_pred": sd_pred, "sd_obs": sd_obs, "cover": cover, "below": below, "above": above, "scale": med / 0.674}
    print(table(["Group", "n", "Avg predicted sd", "Observed sd of misses", "Inside 50% range", "Inside 80%", "Inside 90%",
                 "Below range", "Above range", "sd scale for 50%"], out))
    print("\n(The 'sd scale' is how much wider the range would need to be for half of scores to land inside it. "
          "Ranges are clipped at 0 here, unlike calibrate.py's coverage50 which also clips the low end at 0.)")
    save("spread", res)


# ---------- rest-of-season values (what Waivers uses) ----------
def ros_pairs(rep=None, cfg="base", lite=False):
    """(row, k, predicted, actual) for each future week k=1..4 with a positive value and a result."""
    rep = rep or base()
    b = base()
    out = []
    for key, r in sorted(rep.items()):
        if "error" in r:
            continue
        s, w = key_sw(key)
        rows = r["configs"][cfg]["rows"]
        brows = b[key]["configs"]["base"]["rows"]
        for pid, x in rows.items():
            bx = brows.get(pid)
            if not bx or bx["pos"] == "DEF":
                continue
            fut = x[3:] if lite else x["fut"]
            for k, v in enumerate(fut, start=1):
                if v is None or v <= 0 or (bx["fut"][k - 1] or 0) <= 0:
                    continue
                a = pts_of(s, w + k, pid)
                if a is None:
                    continue
                out.append((bx, k, v, a, s, w))
    return out


def sec_ros():
    pr = ros_pairs()
    print("### Rest-of-season values (Waivers) vs. what the player scored in each of the next four weeks\n")
    head = ["Group", "n", "MAE", "Bias (value - actual)", "±"]
    groups = [("All", pr)] + [(p, [x for x in pr if x[0]["pos"] == p]) for p in POSITIONS]
    groups += [(f"{k} week{'s' if k > 1 else ''} ahead", [x for x in pr if x[1] == k]) for k in (1, 2, 3, 4)]
    groups += [("Slow start flagged (projDoubt)", [x for x in pr if x[0]["doubt"]]),
               ("Bigger role (expanded)", [x for x in pr if x[0]["role"] == "expanded"]),
               ("Smaller role (reduced)", [x for x in pr if x[0]["role"] == "reduced"]),
               ("Changed teams since last season", [x for x in pr if x[0]["moved"]]),
               ("Projection 1.6x+ his form, no flag", [x for x in pr if not x[0]["role"] and not x[0]["doubt"] and x[0]["proj"] and x[0]["form"] and x[0]["proj"] > 1.6 * x[0]["form"]]),
               ("Projection under half his form, no flag", [x for x in pr if not x[0]["role"] and x[0]["proj"] and x[0]["form"] and x[0]["proj"] < 0.5 * x[0]["form"]])]
    out, res = [], {}
    for name, g in groups:
        d = [v - a for _, _, v, a, _, _ in g]
        out.append([name, len(g), f(mean([abs(x) for x in d])), f(mean(d)), f(se(d))])
        res[name] = {"n": len(g), "mae": mean([abs(x) for x in d]), "bias": mean(d)}
    print(table(head, out))
    save("ros", res)


# ---------- waiver audit: predicted window gain vs. realized lineup gain ----------
SLOTS = [("QB", {"QB"}), ("RB", {"RB"}), ("RB", {"RB"}), ("WR", {"WR"}), ("WR", {"WR"}), ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}),
         ("D/ST", {"DEF"}), ("K", {"K"})]
_fx, _owned = {}, {}


def fixture(s, w):
    k = (s, w)
    if k not in _fx:
        p = os.path.join(OUT, "fixtures", "%d-w%02d.json" % (s, w))
        _fx[k] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
        _owned[k] = set(replay.owned_proxy(_fx[k])) if _fx[k] else set()
    return _fx[k]


def lineup_points(ids, s, w, rep=None, cfg="base", stream=True):
    """Points the lineup scores in week w when set by that week's forecasts (the fixture's replay): the best forecast
    at each slot, flex last; a slot nobody on the roster can fill goes to the streamer (third-best free agent by
    forecast at the position, as computeWaivers assumes from next week on; stream=False leaves it empty, as
    computeWaivers does for the week the move is made). None when that week wasn't replayed or has no results."""
    rep = rep or base()
    key = "%d-w%02d" % (s, w)
    if key not in rep or "error" in rep[key] or not actuals(s, w):
        return None
    rows = rep[key]["configs"][cfg]["rows"]
    fixture(s, w)
    owned = _owned[(s, w)]
    cand = sorted((x["mean"], pid) for pid, x in rows.items() if pid in ids)
    cand.reverse()
    used, total = set(), 0.0
    order = [i for i, sl in enumerate(SLOTS) if sl[0] != "FLEX"] + [i for i, sl in enumerate(SLOTS) if sl[0] == "FLEX"]
    for i in order:
        elig = SLOTS[i][1]
        pick = next((pid for m, pid in cand if pid not in used and rows[pid]["pos"] in elig), None)
        if pick is None:
            if not stream:
                continue
            pool = sorted(((x["mean"], pid) for pid, x in rows.items() if x["pos"] in elig and pid not in owned and pid not in ids), reverse=True)
            if pool:
                total += pts_of(s, w, pool[min(2, len(pool) - 1)][1]) or 0
            continue
        used.add(pick)
        total += pts_of(s, w, pick) or 0
    return total


def audit_moves(rep=None, cfg="base", only_best=True):
    rep = rep or base()
    out = []
    for key, r in sorted(rep.items()):
        if "error" in r or "waivers" not in r["configs"][cfg]:
            continue
        s, w = key_sw(key)
        for rk, W in r["configs"][cfg]["waivers"].items():
            idx = [W["best"]] if only_best else [i for i, m in enumerate(W["moves"]) if not m["marginal"]]
            for i in idx:
                if i is None or i < 0:
                    continue
                m = W["moves"][i]
                before = set(W["roster"])
                after = (before - {m["d"]}) | {m["f"]}
                pred, predL, real, weeks = 0.0, 0.0, 0.0, []
                for j, wk in enumerate(m["weeks"]):
                    st = wk != w   # the week of the move itself has no streamer, as in computeWaivers
                    a, b = lineup_points(after, s, wk, rep, cfg, st), lineup_points(before, s, wk, rep, cfg, st)
                    if a is None or b is None:
                        continue
                    pred += m["per"][j]; predL += m["perL"][j]; real += a - b; weeks.append(wk)
                if not weeks:
                    continue
                fl = m["flags"]
                big = (fl["prev"] or 0) >= 10 or (fl["proj"] or 0) >= 10
                slow = bool(fl["doubt"]) or (fl["n"] >= 2 and fl["proj"] and fl["cur"] is not None and fl["cur"] < 0.6 * fl["proj"])
                borrowed = bool(fl["bump"]) or fl["role"] == "expanded" or bool(fl["fill"])
                out.append({"key": key, "season": s, "week": w, "roster": rk, "add": m["name"], "pos": m["pos"], "team": m["team"], "drop": m["dname"],
                            "pred": pred, "predL": predL, "real": real, "nweeks": len(weeks), "H": m["H"], "hz": m["hz"], "why": m["why"], "flags": fl,
                            "big": big, "slow": slow, "moved": fl["moved"], "borrowed": borrowed, "f": m["f"]})
    return out


def corr(x, y):
    if len(x) < 3:
        return None
    mx, my = mean(x), mean(y)
    sx, sy = math.sqrt(sum((a - mx) ** 2 for a in x)), math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else None


def slope(x, y):
    mx, my = mean(x), mean(y)
    v = sum((a - mx) ** 2 for a in x)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / v if v else None


def audit_summary(moves):
    if not moves:
        return {"n": 0}
    p, q, rl = [m["pred"] for m in moves], [m["predL"] for m in moves], [m["real"] for m in moves]
    return {"n": len(moves), "pred": mean(p), "predL": mean(q), "real": mean(rl), "real_se": se(rl), "hit": mean([1 if x > 0 else 0 for x in rl]),
            "corr": corr(p, rl), "slope": slope(p, rl), "per_week_pred": sum(p) / sum(m["nweeks"] for m in moves),
            "per_week_real": sum(rl) / sum(m["nweeks"] for m in moves)}


def sec_waivers(rep=None, cfg="base", label="baseline", quiet=False):
    best = audit_moves(rep, cfg, True)
    allm = audit_moves(rep, cfg, False)
    res = {"best": audit_summary(best), "all": audit_summary(allm)}
    groups = [("Best moves, all", best), ("Best moves, 2025", [m for m in best if m["season"] == 2025]),
              ("Best moves, 2026 (held out)", [m for m in best if m["season"] == 2026])]
    groups += [("Best moves, reviewer's roster (A)", [m for m in best if m["roster"] == "A"]),
               ("Best moves, drafted rosters (B-M)", [m for m in best if m["roster"] != "A"])]
    groups += [(f"Best moves adding a {p}", [m for m in best if m["pos"] == p]) for p in ["QB", "RB", "WR", "TE", "K", "DEF"]]
    groups += [("Big name (10+ pts/g last season or projected)", [m for m in best if m["big"]]),
               ("Slow start (flagged, or under 60% of projection)", [m for m in best if m["slow"]]),
               ("Changed teams", [m for m in best if m["moved"]]),
               ("Borrowed role (injured teammate)", [m for m in best if m["borrowed"]]),
               ("Big name + slow start", [m for m in best if m["big"] and m["slow"]]),
               ("None of those", [m for m in best if not (m["big"] or m["slow"] or m["moved"] or m["borrowed"])]),
               ("Every non-marginal move listed", allm)]
    res["groups"] = {g: audit_summary(x) for g, x in groups}
    if quiet:
        return res, best
    print(f"### Waivers: predicted gain vs. realized lineup gain ({label})\n")
    print(table(["Group", "Moves", "Predicted (shown)", "Predicted, lineup only", "Realized", "±", "Realized > 0", "Correlation", "Slope"],
                [[g, s_["n"], f(s_.get("pred"), 1), f(s_.get("predL"), 1), f(s_.get("real"), 1), f(s_.get("real_se"), 1),
                  f((s_.get("hit") or 0) * 100, 0) + "%", f(s_.get("corr")), f(s_.get("slope"))] for g, s_ in [(g, audit_summary(x)) for g, x in groups]]))
    # the 15 worst misses: one per roster and player (a fixed roster gets the same advice for several weeks)
    seen, worst = set(), []
    for m in sorted(best, key=lambda m: m["real"] - m["pred"]):
        k = (m["roster"], m["f"], m["season"])
        if k in seen:
            continue
        seen.add(k)
        worst.append(m)
        if len(worst) == 15:
            break
    print("\nThe 15 worst misses among Best moves (one per roster and player):\n")
    print(table(["Week", "Roster", "Add", "Drop", "Predicted", "Realized", "Flags", "Reason the model gave"],
                [[m["key"], m["roster"], f"{m['add']} ({m['pos']}, {m['team']})", m["drop"] or "–", f(m["pred"], 1), f(m["real"], 1),
                  ", ".join(x for x, on in (("big name", m["big"]), ("slow start", m["slow"]), ("team change", m["moved"]), ("borrowed role", m["borrowed"])) if on) or "–",
                  m["why"].replace("|", "/")[:220]] for m in worst]))
    res["worst"] = worst
    save("waivers" if label == "baseline" else "waivers-" + label, res)
    return res, best


# ---------- constant sweeps ----------
def sweep_metrics(rep, cfg):
    """Weekly MAE and rest-of-season MAE for a config, on the baseline's scored set, by split."""
    b = base()
    out = {}
    for key, r in rep.items():
        if "error" in r or key not in b:
            continue
        s, w = key_sw(key)
        brows = b[key]["configs"]["base"]["rows"]
        rows = r["configs"][cfg]["rows"]
        half = "2026" if s == 2026 else ("2025a" if w <= 10 else "2025b")
        for pid, x in rows.items():
            bx = brows.get(pid)
            if not bx or bx["pos"] == "DEF" or bx["mean"] < calibrate.MIN_MEAN:
                continue
            a = pts_of(s, w, pid)
            if a is not None:
                o = out.setdefault(half, {"wk": [], "wkA": [], "ros": [], "z": []})
                o["wk"].append(abs(x[0] - a))
                if abs(x[0] - bx["mean"]) > 0.05:
                    o["wkA"].append((abs(x[0] - a), abs(bx["mean"] - a)))
                if x[1]:
                    o["z"].append((x[0], x[1], a, bx["pos"], (s, w)))
            for k, v in enumerate(x[3:], start=1):
                if v is None or v <= 0 or (bx["fut"][k - 1] or 0) <= 0:
                    continue
                a2 = pts_of(s, w + k, pid)
                if a2 is not None:
                    out.setdefault(half, {"wk": [], "wkA": [], "ros": [], "z": []})["ros"].append(abs(v - a2))
    return out


def sec_sweep(name="sweep"):
    rep = replay.load(name)
    cfgs = list(next(iter(rep.values()))["configs"].keys())
    rows, res = [], {}
    basem = sweep_metrics(rep, "base")
    for c in cfgs:
        m = sweep_metrics(rep, c)
        def mae(h, k):
            return mean(m.get(h, {}).get(k, [])) if h != "2025" else mean(m.get("2025a", {}).get(k, []) + m.get("2025b", {}).get(k, []))
        def d(h, k):
            a, b_ = mae(h, k), (mean(basem.get(h, {}).get(k, [])) if h != "2025" else mean(basem.get("2025a", {}).get(k, []) + basem.get("2025b", {}).get(k, [])))
            return a - b_ if a is not None and b_ is not None else None
        aff = m.get("2025a", {}).get("wkA", []) + m.get("2025b", {}).get("wkA", [])
        cov = {}
        for h in ("2025", "2026"):
            z = m.get("2025a", {}).get("z", []) + m.get("2025b", {}).get("z", []) if h == "2025" else m.get("2026", {}).get("z", [])
            e = calibrate.evaluate([{"week": wk, "pos": p, "mean": mu, "sd": sd, "sleeper": None, "actual": a} for mu, sd, a, p, wk in z])
            cov[h] = e
        res[c] = {"wk": {h: mae(h, "wk") for h in ("2025", "2025a", "2025b", "2026")}, "ros": {h: mae(h, "ros") for h in ("2025", "2025a", "2025b", "2026")},
                  "affected": len(aff), "affected_gain": mean([b_ - a for a, b_ in aff]) if aff else None,
                  "cov": {h: cov[h]["coverage50"] if cov[h] else None for h in cov}, "brier": {h: cov[h]["pairs"]["brier"] if cov[h] else None for h in cov}}
        rows.append([c, f(d("2025", "wk"), 3), f(d("2025a", "wk"), 3), f(d("2025b", "wk"), 3), f(d("2026", "wk"), 3),
                     f(d("2025", "ros"), 3), f(d("2025a", "ros"), 3), f(d("2025b", "ros"), 3), f(d("2026", "ros"), 3), len(aff),
                     f(res[c]["affected_gain"], 2), f((cov["2025"] or {}).get("coverage50", 0) * 100, 1), f((cov["2025"] or {}).get("pairs", {}).get("brier"), 4)])
    print(f"### Constant sweeps ({name}): change in MAE vs. the shipped model (negative = better)\n")
    print("Baseline MAE: weekly 2025 " + f(res["base"]["wk"]["2025"], 3) + ", 2026 " + f(res["base"]["wk"]["2026"], 3) +
          "; rest of season 2025 " + f(res["base"]["ros"]["2025"], 3) + ", 2026 " + f(res["base"]["ros"]["2026"], 3) + "\n")
    print(table(["Config", "Weekly 2025", "2025 wk2-10", "2025 wk11-18", "Weekly 2026 (held out)", "ROS 2025", "ROS wk2-10", "ROS wk11-18",
                 "ROS 2026 (held out)", "Player-weeks changed", "Avg gain where changed", "Coverage 2025 %", "Brier 2025"], rows))
    save(name, res)


# ---------- does recent usage predict next week better than recent points? ----------
def sec_usage():
    """Per player-week (3+ earlier games this season): last-3-game average of PPR points vs. of usage-implied points
    (targets, carries, pass attempts, snap share, fitted per position on 2025 weeks 1-9), predicting the next game."""
    seasons = {2025: range(1, 19), 2026: range(1, 5)}
    games = {}
    for s, wks in seasons.items():
        for w in wks:
            a = actuals(s, w)
            if not a:
                continue
            for pid, x in a["P"].items():
                pts, pos, tm, opp, tgt, ra, snp, tsnp, rec, patt = x[:10]
                games.setdefault((s, pid), []).append({"w": w, "pos": pos, "pts": pts, "tgt": tgt, "ra": ra, "pa": patt, "snap": (snp / tsnp) if tsnp else None})
    feats = lambda g: [1.0, g["tgt"], g["ra"], g["pa"], g["snap"] or 0.0]
    # fit expected points per game from same-game usage, per position (least squares), on 2025 weeks 1-9
    coef = {}
    for p in ("QB", "RB", "WR", "TE"):
        X, y = [], []
        for (s, pid), gl in games.items():
            for g in gl:
                if s == 2025 and g["w"] <= 9 and g["pos"] == p:
                    X.append(feats(g)); y.append(g["pts"])
        coef[p] = lstsq(X, y)
    xfp = lambda g: sum(c * v for c, v in zip(coef[g["pos"]], feats(g))) if g["pos"] in coef else None
    # base model forecasts for the same player-weeks, to see whether usage adds anything to Benny's own number
    b = base()
    model = {}
    for key, r in b.items():
        if "error" in r:
            continue
        s, w = key_sw(key)
        for pid, x in r["configs"]["base"]["rows"].items():
            model[(s, w, pid)] = (x["mean"], x["proj"], x["form"])
    recs = []
    for (s, pid), gl in games.items():
        gl.sort(key=lambda g: g["w"])
        for i in range(3, len(gl)):
            g, prev = gl[i], gl[i - 3:i]
            if g["pos"] not in coef:
                continue
            fp = mean([x["pts"] for x in prev])
            xu = mean([xfp(x) for x in prev])
            mm = model.get((s, g["w"], pid))
            recs.append({"s": s, "w": g["w"], "pos": g["pos"], "y": g["pts"], "fp": fp, "xu": xu, "model": mm[0] if mm else None,
                         "proj": mm[1] if mm else None})
    test = lambda r: r["s"] == 2026 or r["w"] >= 10
    out, res = [], {}
    for p in ("All", "QB", "RB", "WR", "TE"):
        g = [r for r in recs if test(r) and (p == "All" or r["pos"] == p)]
        if not g:
            continue
        # best single-variable linear fit of next-game points on each predictor, fitted on the training weeks
        tr = [r for r in recs if not test(r) and (p == "All" or r["pos"] == p)]
        res_p = {}
        for k in ("fp", "xu"):
            c = lstsq([[1.0, r[k]] for r in tr], [r["y"] for r in tr])
            pred = [c[0] + c[1] * r[k] for r in g]
            res_p[k] = (mean([abs(a - r["y"]) for a, r in zip(pred, g)]), corr([r[k] for r in g], [r["y"] for r in g]))
        c = lstsq([[1.0, r["fp"], r["xu"]] for r in tr], [r["y"] for r in tr])
        both = mean([abs(c[0] + c[1] * r["fp"] + c[2] * r["xu"] - r["y"]) for r in g])
        # added to Benny's forecast: residual on (usage - points) gap
        gm = [r for r in g if r["model"] is not None]
        trm = [r for r in tr if r["model"] is not None]
        cm = lstsq([[1.0, r["model"], r["xu"] - r["fp"]] for r in trm], [r["y"] for r in trm]) if trm else None
        mae_model = mean([abs(r["model"] - r["y"]) for r in gm])
        mae_mu = mean([abs(cm[0] + cm[1] * r["model"] + cm[2] * (r["xu"] - r["fp"]) - r["y"]) for r in gm]) if cm else None
        cm0 = lstsq([[1.0, r["model"]] for r in trm], [r["y"] for r in trm]) if trm else None
        mae_m0 = mean([abs(cm0[0] + cm0[1] * r["model"] - r["y"]) for r in gm]) if cm0 else None
        out.append([p, len(g), f(res_p["fp"][0]), f(res_p["fp"][1]), f(res_p["xu"][0]), f(res_p["xu"][1]), f(both), f(mae_model), f(mae_m0), f(mae_mu),
                    f(cm[2], 3) if cm else "–"])
        res[p] = {"n": len(g), "mae_points": res_p["fp"][0], "corr_points": res_p["fp"][1], "mae_usage": res_p["xu"][0], "corr_usage": res_p["xu"][1],
                  "mae_both": both, "mae_model": mae_model, "mae_model_refit": mae_m0, "mae_model_plus_usage": mae_mu, "usage_gap_coef": cm[2] if cm else None}
    print("### Recent usage vs. recent points as a predictor of the next game (test: 2025 wk 10-18 + 2026)\n")
    print(table(["Position", "n", "MAE last-3 points", "Corr", "MAE last-3 usage", "Corr", "MAE both", "MAE Benny", "MAE Benny (refit)",
                 "MAE Benny + usage gap", "Usage-gap coefficient"], out))
    print("\nUsage coefficients (pts per game = a + b·targets + c·carries + d·pass attempts + e·snap share), fitted on 2025 wk 1-9:")
    print(table(["Pos", "a", "targets", "carries", "pass att", "snap share"], [[p] + [f(x, 3) for x in coef[p]] for p in coef]))
    res["coef"] = coef
    # the same fit without snap share, which the page's weekly rows don't carry: what an in-model test can use (formOf).
    # QBs on carries and pass attempts, everyone else on targets and carries (a QB's rare catch or a back's rare pass
    # only adds noise). Stored as [a, per target, per carry, per pass attempt].
    coef4 = {}
    for p in ("QB", "RB", "WR", "TE"):
        X, y = [], []
        for (s, pid), gl in games.items():
            for g in gl:
                if s == 2025 and g["w"] <= 9 and g["pos"] == p:
                    X.append([1.0, g["ra"], g["pa"]] if p == "QB" else [1.0, g["tgt"], g["ra"]]); y.append(g["pts"])
        c = [round(x, 3) for x in lstsq(X, y)]
        coef4[p] = [c[0], 0.0, c[1], c[2]] if p == "QB" else [c[0], c[1], c[2], 0.0]
    res["coef4"] = coef4
    print("\nWithout snap share (used for the in-model test, USAGE_W in driver.html):")
    print(table(["Pos", "a", "targets", "carries", "pass att"], [[p] + [f(x, 3) for x in coef4[p]] for p in coef4]))
    save("usage", res)


def lstsq(X, y):
    """Ordinary least squares by normal equations (small k)."""
    k = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) for j in range(k)] for i in range(k)]
    b = [sum(r[i] * t for r, t in zip(X, y)) for i in range(k)]
    for i in range(k):
        A[i][i] += 1e-9
    # Gaussian elimination
    for i in range(k):
        piv = max(range(i, k), key=lambda r: abs(A[r][i]))
        A[i], A[piv] = A[piv], A[i]; b[i], b[piv] = b[piv], b[i]
        for r in range(i + 1, k):
            fct = A[r][i] / A[i][i]
            for c in range(i, k):
                A[r][c] -= fct * A[i][c]
            b[r] -= fct * b[i]
    x = [0.0] * k
    for i in reversed(range(k)):
        x[i] = (b[i] - sum(A[i][c] * x[c] for c in range(i + 1, k))) / A[i][i]
    return x


# ---------- base vs. tuned, on held-out weeks ----------
def sec_compare(name="compare"):
    rep = replay.load(name)
    cfgs = list(next(iter(rep.values()))["configs"].keys())
    print(f"### Shipped vs. tuned ({name})\n")
    head = ["Config", "Split", "Player-weeks", "MAE Benny", "MAE Sleeper", "Bias", "Inside range", "Brier", "ROS MAE", "ROS bias"]
    out, res = [], {}
    for c in cfgs:
        rows = scored(rep, c)
        pr = ros_pairs(rep, c)
        for label, sel, selr in (("2025 (tuned on)", lambda r: r["season"] == 2025, lambda x: x[4] == 2025),
                                 ("2026 wk 1-4 (held out)", lambda r: r["season"] == 2026, lambda x: x[4] == 2026)):
            g = [r for r in rows if sel(r)]
            e = evaluate(g)
            d = [v - a for _, _, v, a, s, w in pr if selr((None, None, None, None, s, w))]
            both = [r for r in g if r["mean"] >= calibrate.MIN_MEAN and r["sleeper"] is not None]
            out.append([c, label, e["n"], f(e["mae"]["model"], 3), f(e["mae"]["sleeper"], 3), f(mean([r["mean"] - r["actual"] for r in both])),
                        f(e["coverage50"] * 100, 1) + "%", f(e["pairs"]["brier"], 4), f(mean([abs(x) for x in d]), 3), f(mean(d))])
            res.setdefault(c, {})[label] = {"eval": e, "ros_mae": mean([abs(x) for x in d]), "ros_bias": mean(d), "ros_n": len(d)}
    print(table(head, out))
    if all("waivers" in next(iter(rep.values()))["configs"][c] for c in cfgs):
        for c in cfgs:
            r_, _ = sec_waivers(rep, c, c, quiet=True)
            res[c]["waivers"] = r_
        print("\nWaivers, best moves, predicted vs. realized:")
        print(table(["Config", "Group", "Moves", "Predicted (shown)", "Realized", "±", "Realized > 0", "Correlation", "Slope"],
                    [[c, g, s_["n"], f(s_.get("pred"), 1), f(s_.get("real"), 1), f(s_.get("real_se"), 1), f((s_.get("hit") or 0) * 100, 0) + "%", f(s_.get("corr")), f(s_.get("slope"))]
                     for c in cfgs for g, s_ in res[c]["waivers"]["groups"].items()
                     if g in ("Best moves, all", "Best moves, 2025", "Best moves, 2026 (held out)", "Big name + slow start", "Slow start (flagged, or under 60% of projection)",
                              "Borrowed role (injured teammate)", "Changed teams")]))
    save(name, res)


def main():
    secs = sys.argv[1:] or ["forecast"]
    if "all" in secs:
        secs = ["forecast", "context", "spread", "ros", "waivers", "sweep", "usage"]
    for s in secs:
        name = None
        if ":" in s:
            s, name = s.split(":", 1)
        fn = {"forecast": sec_forecast, "context": sec_context, "spread": sec_spread, "ros": sec_ros, "waivers": sec_waivers,
              "sweep": sec_sweep, "usage": sec_usage, "compare": sec_compare}[s]
        fn(name) if name else fn()
        print()


if __name__ == "__main__":
    main()
