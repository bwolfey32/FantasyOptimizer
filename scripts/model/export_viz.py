"""Everything model.html draws, in one file: model/viz.json, from the trained models, the backtest and this week's numbers.

Usage: python scripts/model/export_viz.py [--models scripts/model/models] [--backtest scripts/model/out/backtest]
                                          [--data scripts/model/out/player_weeks.parquet] [--out model/viz.json]

Blocks (the page hides one that is missing, so the script still runs where the gitignored backtest or dataset isn't there):
  meta         the models, when they were trained, the week the numbers are for
  importance   per model, position and kind (mean / spread): each feature's share of the gain and of the splits
  pd           partial dependence of the next-week mean models' correction on their top features
  accuracy     average miss, squared miss and bias by season, for the trained model, Benny's classic numbers and Sleeper
  calibration  predicted against actual by decile, how many scores land in the likely range, and the misses in sds
  week         this week's trained, classic and Sleeper numbers for every QB, RB, WR and TE
"""
import argparse
import json
import math
import os
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import predict as P  # noqa: E402
import train as T  # noqa: E402

POS = T.POSITIONS
Z50 = T.Z50
FAMILIES = [  # (family, test on the feature's name), first match wins
    ("Sleeper's read", lambda f: f.startswith("sl_")),
    ("Benny's number", lambda f: f.startswith("cl_")),
    ("Projection", lambda f: f == "pred"),
    ("Injuries", lambda f: f == "inj" or f.startswith("vac_") or f == "qb_out"),
    ("Game", lambda f: f in ("home", "spread", "total", "implied", "dome", "temp", "wind", "rest", "new_hc")),
    ("Team & opponent", lambda f: f.startswith(("t_", "o_"))),
    ("Role & career", lambda f: f in ("tm_change", "depth", "pos_share", "dc_depth", "dc_eff", "age", "exp", "draft")),
    ("Calendar", lambda f: f in ("week", "h")),
    ("Recent form", lambda f: f.startswith(("ppr_", "g_", "wk_", "miss")) or f == "g"),
]
SEASONS = range(2019, 2027)
PD_FEATURES, PD_POINTS, PD_ROWS = 6, 24, 2500


def family(f):
    return next((name for name, test in FAMILIES if test(f)), "Usage")


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def importance(mdir, meta):
    out = {}
    for tag, name in (("near", P.NEAR), ("far", P.FAR)):
        feats = meta[name]["features"]
        spread = feats + ["pred"]
        o = {"features": feats, "spreadFeatures": spread}
        for pos in POS:
            for kind in ("mean", "rec", "spread"):
                b = lgb.Booster(model_file=os.path.join(mdir, f"{name}-{pos}-{kind}.txt"))
                names = b.feature_name()
                assert names == (spread if kind == "spread" else feats), f"{name} {pos} {kind}: feature names differ from meta.json"
                row = {}
                for how in ("gain", "split"):
                    v = b.feature_importance(importance_type=how).astype(float)
                    row[how] = [r(x, 3) for x in 100 * v / max(v.sum(), 1e-9)]
                row["trees"] = b.num_trees()
                o.setdefault(pos, {})[kind] = row
        out[tag] = o
    out["families"] = {f: family(f) for f in sorted(set(sum((out[t]["features"] for t in ("near", "far")), []) + ["pred"]))}
    return out


def partial_dependence(mdir, meta, data_path, imp):
    """The mean model's correction to its base (Sleeper less its bias) as one feature moves, the rest as they were."""
    df = pd.read_parquet(data_path)
    df = df[(df.h == 1) & (df.season >= 2019)]
    feats = meta[P.NEAR]["features"]
    out = {}
    for pos in POS:
        b = lgb.Booster(model_file=os.path.join(mdir, f"{P.NEAR}-{pos}-mean.txt"))
        d = df[df.pos == pos]
        d = d.sample(min(PD_ROWS, len(d)), random_state=1)
        X = d[feats].astype(float).reset_index(drop=True)
        gain = np.array(imp["near"][pos]["mean"]["gain"])
        curves = []
        for i in np.argsort(-gain)[:PD_FEATURES]:
            f = feats[i]
            col = X[f].dropna()
            grid = np.unique(np.quantile(col, np.linspace(0.05, 0.95, PD_POINTS))) if col.nunique() > 2 else np.sort(col.unique())
            ys = []
            for g in grid:
                Xg = X.copy()
                Xg[f] = g
                ys.append(b.predict(Xg).mean())
            curves.append({"f": f, "gain": r(gain[i], 1), "x": [r(g, 3) for g in grid], "y": [r(y, 3) for y in ys],
                           "deciles": [r(q, 3) for q in np.quantile(col, np.linspace(0, 1, 11))]})
        out[pos] = curves
    return out


def comparable(bt):
    """The rows the report scores: next week, a classic number, Sleeper projecting 3+ (docs/model-report.md)."""
    return bt[(bt.h == 1) & bt.cl_now.notna() & (bt.sl_now >= 3) & bt.y_ppr.notna() & (bt.season >= 2019)].copy()


def score(d):
    out = {"n": int(len(d))}
    for key, col in (("trained", "pred"), ("classic", "cl_now"), ("sleeper", "sl_now")):
        e = d[col] - d.y_ppr
        out[key] = {"mae": r(e.abs().mean(), 3), "rmse": r(math.sqrt((e ** 2).mean()), 3), "bias": r(e.mean(), 3)}
    return out


def accuracy_and_calibration(bt_dir, final):
    bt = pd.read_parquet(os.path.join(bt_dir, "final-near.parquet"))
    d = comparable(bt)
    d["z"] = (d.y_ppr - d.pred) / d.sd
    d["inside"] = d.z.abs() <= Z50
    acc = {"seasons": {str(s): score(d[d.season == s]) for s in SEASONS if (d.season == s).any()},
           "pooled": {"2019-24": score(d[d.season <= 2024])},
           "byPos": {pos: score(d[(d.season <= 2024) & (d.pos == pos)]) for pos in POS}}
    if final:
        acc["far"] = {str(s): {h: v for h, v in final["seasons"][str(s)].get("far", {}).items()} for s in SEASONS if str(s) in final["seasons"]}
        acc["farPooled"] = {}
        for h in ("2", "3", "4"):
            ns = [(final["seasons"][str(s)]["B"]["n"], final["seasons"][str(s)]["far"][h]) for s in range(2019, 2025)]
            tot = sum(n for n, _ in ns)
            acc["farPooled"][h] = {k: r(sum(n * v[k] for n, v in ns) / tot, 3) for k in ("model", "sleeper")}
    cal = {"deciles": {}, "coverage": {}, "z": {}}
    for pos in POS + ("all",):
        s = d if pos == "all" else d[d.pos == pos]
        qs = pd.qcut(s.pred, 10, duplicates="drop")
        g = s.groupby(qs, observed=True)
        cal["deciles"][pos] = [[r(a, 2), r(b, 2), int(n)] for a, b, n in zip(g.pred.mean(), g.y_ppr.mean(), g.size())]
        cal["coverage"][pos] = {str(y): r(s[s.season == y].inside.mean(), 4) for y in SEASONS if (s.season == y).any()}
        cal["coverage"][pos]["2019-24"] = r(s[s.season <= 2024].inside.mean(), 4)
        edges = np.arange(-4, 4.01, 0.5)
        cal["z"][pos] = [int(c) for c in np.histogram(s.z.clip(-3.999, 3.999), bins=edges)[0]]
    cal["zEdges"] = [-4, 4, 0.5]
    return acc, cal


def this_week(proj_path, snap_path, classic_path):
    with open(proj_path, encoding="utf-8") as f:
        pj = json.load(f)
    with open(snap_path, encoding="utf-8") as f:
        snap = json.load(f)
    cl = {}
    if os.path.exists(classic_path):
        with open(classic_path, encoding="utf-8") as f:
            cl = json.load(f)
        if (cl.get("season"), cl.get("week")) != (pj["season"], pj["week"]):
            cl = {}
    fc = cl.get("fc") or {}
    fut = cl.get("fut") or {}
    rows = []
    for sid, name, pos, team, inj, sl, opp, rec in snap["proj"]:
        v = pj["ids"].get(str(sid))
        if pos not in POS or not v or v[0] is None:
            continue
        c = fc.get(str(sid)) or [None, None]
        rows.append([str(sid), name, pos, team, opp, inj, v[0], v[2], v[1], r(c[0]), r(c[1]), r(sl), v[3], v[5], v[7],
                     (fut.get(str(sid)) or [None] * 3)])
    rows.sort(key=lambda x: -x[6])
    return {"season": pj["season"], "week": pj["week"], "made": pj["made"], "snapshot": pj.get("snapshot"),
            "cols": ["id", "name", "pos", "team", "opp", "inj", "trained", "sd", "rec", "classic", "classicSd", "sleeper",
                     "t2", "t3", "t4", "classicFut"], "rows": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", default=os.path.join(HERE, "models"))
    ap.add_argument("--backtest", default=os.path.join(HERE, "out", "backtest"))
    ap.add_argument("--data", default=os.path.join(HERE, "out", "player_weeks.parquet"))
    ap.add_argument("--out", default=os.path.join(ROOT, "model", "viz.json"))
    a = ap.parse_args()
    with open(os.path.join(a.models, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    near, far = meta[P.NEAR], meta[P.FAR]
    out = {"meta": {"near": P.NEAR, "far": P.FAR, "trained": near.get("trained"), "throughSeason": near["through"][0],
                    "throughWeek": near["through"][1], "seasons": near["seasons"], "positions": list(POS),
                    "nearConfig": near["config"], "farConfig": far["config"], "spreadK": near["spreadK"]}}
    out["importance"] = importance(a.models, meta)
    print("importance: done")
    if os.path.exists(a.data):
        out["pd"] = partial_dependence(a.models, meta, a.data, out["importance"])
        print("pd: done")
    else:
        print(f"{a.data} not found: no partial dependence")
    if os.path.exists(os.path.join(a.backtest, "final-near.parquet")):
        final = None
        fp = os.path.join(a.backtest, "final.json")
        if os.path.exists(fp):
            with open(fp, encoding="utf-8") as f:
                final = json.load(f)
        out["accuracy"], out["calibration"] = accuracy_and_calibration(a.backtest, final)
        print("accuracy, calibration: done")
    else:
        print("no backtest: no accuracy or calibration")
    out["week"] = this_week(os.path.join(ROOT, "model", "proj.json"), os.path.join(ROOT, "snapshot.json"),
                            os.path.join(ROOT, "model", "classic.json"))
    print(f"week: {len(out['week']['rows'])} players")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"-> {a.out} ({os.path.getsize(a.out) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
