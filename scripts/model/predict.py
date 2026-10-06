"""This week's trained projections for the site: model/proj.json, from snapshot.json and the trained models.

Usage: python scripts/model/predict.py [--snapshot snapshot.json] [--classic model/classic.json]
                                       [--models scripts/model/models] [--out model/proj.json]

Run by .github/workflows/refresh-data.yml after each snapshot. The snapshot gives what's known now (this week's lines,
forecast, injury tags and Sleeper's projections, and the weekly stats nflverse hasn't published yet); nflverse gives the
box scores, snap counts and depth charts (data.py); model/classic.json gives Benny's current hand-tuned numbers, which the
two-to-four-week model starts from (extract_snapshot.py writes it).

model/proj.json: {"season", "week", "made", "models": {"near", "far"}, "ids": {sleeperId: [ppr, rec, sd, ppr2, rec2,
ppr3, rec3, ppr4, rec4]}}: next week's PPR points and catches if he plays, the sd of his score, and the same points
and catches 2, 3 and 4 weeks ahead (null for a week his team doesn't play). index.html reads it (loadTrained).
"""
import argparse
import json
import math
import os
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import data  # noqa: E402
import features as F  # noqa: E402
import train as T  # noqa: E402

NEAR, FAR = "B-hl3-bsldb-md300-h1-rt2", "C-hl3-bcl-md300-far"


def load_models(mdir, name, meta):
    """{pos: booster} for the mean, catches and spread models of one config, with the config for predict()."""
    cfg = meta[name]["config"]
    out = {}
    for kind in ("mean", "rec", "spread"):
        m = {pos: lgb.Booster(model_file=os.path.join(mdir, f"{name}-{pos}-{kind}.txt")) for pos in T.POSITIONS}
        m["cfg"] = cfg if kind == "mean" else dict(cfg, base=None)
        out[kind] = m
    return out, cfg, meta[name]["spreadK"]


def classic_table(cl, season, week, gsis_of):
    """Benny's current numbers this week (cproj, as data.classic_proj builds from the replays)."""
    rows = []
    fut = cl.get("fut") or {}
    for sid, row in (cl.get("fc") or {}).items():
        g = gsis_of.get(str(sid))
        if not g:
            continue
        f = (fut.get(sid) or []) + [None] * 3
        rows.append((season, week, g, row[0], row[1], f[0], f[1], f[2]))
    return pd.DataFrame(rows, columns=["season", "week", "pid", "cproj", "csd", "cfut2", "cfut3", "cfut4"])


def r2(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=os.path.join(ROOT, "snapshot.json"))
    ap.add_argument("--classic", default=os.path.join(ROOT, "model", "classic.json"))
    ap.add_argument("--models", default=os.path.join(HERE, "models"))
    ap.add_argument("--out", default=os.path.join(ROOT, "model", "proj.json"))
    a = ap.parse_args()
    t = time.time()
    with open(a.snapshot, encoding="utf-8") as f:
        snap = json.load(f)
    S, W = snap["season"], snap["week"]
    with open(os.path.join(a.models, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    near, cfg_n, k_n = load_models(a.models, NEAR, meta)
    far, cfg_f, _ = load_models(a.models, FAR, meta)

    ctx = data.context([S], with_sleeper=True, live_season=S)
    ctx = data.apply_bundle(ctx, snap)
    gsis_of = data.gsis_map(ctx["people"])
    cl = {}
    if os.path.exists(a.classic):
        with open(a.classic, encoding="utf-8") as f:
            cl = json.load(f)
        if cl.get("season") != S or cl.get("week") != W:
            print(f"model/classic.json is for {cl.get('season')} week {cl.get('week')}, not {S} week {W}: the far model starts from Sleeper")
            cl = {}
    ctx["cproj"] = classic_table(cl, S, W, gsis_of)
    keys = data.live_keys(ctx, snap)
    rows = F.Builder(ctx).rows(keys)

    out = {}
    nr = rows[rows.h == 1].copy()
    nr["pred"] = T.predict(near["mean"], nr, cfg_n["variant"])
    nr["rec"] = np.clip(T.predict(near["rec"], nr, cfg_n["variant"]), 0, nr.pred)   # never more catches than points
    nr["sd"] = T.predict_sd({p: near["spread"][p] for p in T.POSITIONS}, k_n, nr, cfg_n["variant"])
    for sid, p, rc, sd in zip(nr.sid, nr.pred, nr.rec, nr.sd):
        out[sid] = [r2(p), r2(rc), r2(sd)] + [None] * 6
    fr = rows[rows.h > 1].copy()
    if len(fr):
        fr["pred"] = T.predict(far["mean"], fr, cfg_f["variant"])
        fr["rec"] = np.clip(T.predict(far["rec"], fr, cfg_f["variant"]), 0, fr.pred)
        for sid, h, p, rc in zip(fr.sid, fr.h, fr.pred, fr.rec):
            row = out.setdefault(sid, [None] * 9)
            row[3 + 2 * (h - 2)], row[4 + 2 * (h - 2)] = r2(p), r2(rc)
    res = {"season": S, "week": W, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "snapshot": snap.get("createdAt"),
           "models": {"near": NEAR, "far": FAR, "trained": meta[NEAR].get("trained")}, "ids": out}
    n1 = sum(1 for v in out.values() if v[0] is not None)
    if n1 < 300:
        sys.exit(f"Only {n1} players predicted; keeping the last model/proj.json.")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, separators=(",", ":"))
    print(f"{S} week {W}: {n1} players next week, {len(fr)} later-week values, in {time.time() - t:.0f}s -> {a.out}")


if __name__ == "__main__":
    main()
