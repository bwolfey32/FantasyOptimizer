"""Chronological backtest of the trained model: for each season S, train only on the seasons before it, then predict
every game of S at horizons 1-4 and compare with what happened and with Sleeper's projection.

Usage: python scripts/model/backtest.py tune [CONFIG ...]   configs scored on 2019-2024 only (names: see train.config())
       python scripts/model/backtest.py final NEAR NEAR_A FAR  the chosen near model (next week), the situations-only near
                                                              model and the far model (2-4 weeks) on every season
                                                              2016-2026: 2025 confirms the choice, 2026 is the held-out
                                                              test, and the replays give the current model's numbers;
                                                              writes out/backtest/final.json (docs/model-report.md)
       python scripts/model/backtest.py fixtures              replay fixtures carrying the final run's predictions, for
                                                              replay.py --dir fixtures-ml (the page on the trained model)
Options: --data scripts/model/out/player_weeks.parquet

Out-of-season predictions are saved per config in scripts/model/out/backtest/<name>.parquet (reruns reuse them); a
config's spread model is fitted on its own earlier seasons' misses (train.fit_spread), so its ranges are out of season too.

The common yardstick, "average miss", is the mean absolute error in PPR points on games the player played, a week ahead,
for players Sleeper projected at 3+ points (so every model is scored on the same player-weeks).
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import train as T  # noqa: E402
from calibrate import evaluate  # noqa: E402

OUT = os.path.join(HERE, "out", "backtest")
TUNE = list(range(2019, 2025))          # choices are made on these seasons only
CONFIRM, HELDOUT = 2025, 2026
FIRST = 2016                            # earliest season predicted (2016-2018 feed the spread models)


def oof(rows, name, seasons):
    """Out-of-season predictions for config name over these seasons, cached."""
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".parquet")
    have = pd.read_parquet(path) if os.path.exists(path) else None
    done = set(have.season.unique()) if have is not None else set()
    cfg, parts = T.config(name), [have] if have is not None else []
    for S in seasons:
        if S in done or S not in set(rows.season):
            continue
        t = time.time()
        m = T.fit_season(rows, S, cfg["variant"], cfg)
        te = rows[(rows.season == S) & (rows.h.isin(cfg["horizons"]) if cfg.get("horizons") else True)]
        pred = T.predict(m, te, cfg["variant"])
        R = cfg.get("retrain")
        if R:
            # in season: every R weeks, refit on the games played so far and predict the next R weeks' cutoffs
            c = (te.week - te.h + 1).to_numpy()
            for k in range(1 + R, 19, R):
                sel = (c >= k) & (c < k + R)
                if sel.any():
                    mk = T.fit_season(rows, S, cfg["variant"], cfg, upto=k, rounds=m["rounds"])
                    pred[sel] = T.predict(mk, te[sel], cfg["variant"])
        parts.append(te[["pid", "pos", "season", "week", "h", "team", "y_ppr", "y_rec", "sl_now"]].assign(pred=pred))
        print(f"  {name} {S}: {time.time() - t:.0f}s", flush=True)
        pd.concat(parts, ignore_index=True).to_parquet(path, index=False)
    out = pd.concat(parts, ignore_index=True)
    return out[out.season.isin(seasons)]


def miss(d, col):
    e = d.y_ppr - d[col]
    return {"mae": float(e.abs().mean()), "rmse": float(np.sqrt((e ** 2).mean())), "bias": float(-e.mean()), "n": int(len(d))}


def common(d, h=1):
    return d[(d.h == h) & (d.sl_now >= 3)]


# ---------- tune ----------
def tune(rows, names):
    res = {}
    for n in names:
        o = oof(rows, n, TUNE)
        near = (o.h == 1).any()
        by = {S: miss(common(o[o.season == S]), "pred")["mae"] if near else float("nan") for S in TUNE}
        far = np.mean([miss(common(o, h), "pred")["mae"] for h in (2, 3, 4)]) if (o.h > 1).any() else float("nan")
        res[n] = {"mae": float(np.mean(list(by.values()))), "far": float(far), "by": by}
    sl = {S: miss(common(rows[rows.season == S]), "sl_now")["mae"] for S in TUNE}
    slfar = np.mean([miss(common(rows[rows.season.isin(TUNE)], h), "sl_now")["mae"] for h in (2, 3, 4)])
    print(f"\n{'config':28} {'avg miss':>8} {'2-4 wk':>7}  " + " ".join(f"{S:>6}" for S in TUNE))
    print(f"{'Sleeper':28} {np.mean(list(sl.values())):8.3f} {slfar:7.3f}  " + " ".join(f"{sl[S]:6.3f}" for S in TUNE))
    for n, r in sorted(res.items(), key=lambda x: x[1]["mae"]):
        print(f"{n:28} {r['mae']:8.3f} {r['far']:7.3f}  " + " ".join(f"{r['by'][S]:6.3f}" for S in TUNE))
    return res


# ---------- final ----------
def with_spread(rows, o, name):
    """sd for every season from FIRST+3 on, from a spread model fitted on the config's earlier seasons' misses."""
    cfg = T.config(name)
    feats = T.feature_list(cfg["variant"])
    o = o.merge(rows[["pid", "season", "week", "h"] + [f for f in feats if f not in o.columns]], on=["pid", "season", "week", "h"], how="left")
    o["sd"] = np.nan
    for S in sorted(o.season.unique()):
        past = o[(o.season < S) & (o.season >= FIRST)]
        if past.season.nunique() < 3:
            continue
        models, ks = T.fit_spread(past, cfg["variant"], cfg)
        k = o.season == S
        o.loc[k, "sd"] = T.predict_sd(models, ks, o[k], cfg["variant"])
    return o


def calib(d, col="pred"):
    """calibrate.py's checks (range coverage, chance of 20+, chance to outscore) on these rows' projection col and sd."""
    d = d[d.sd.notna()]
    return evaluate([{"week": (s, w), "pos": p, "mean": float(m), "sd": float(sd), "sleeper": None if sl != sl else float(sl), "actual": float(y)}
                     for s, w, p, m, sd, sl, y in zip(d.season, d.week, d.pos, d[col], d.sd, d.sl_now, d.y_ppr)])


def band_rows(d, cols):
    out = []
    groups = [("All", d)] + [(p, d[d.pos == p]) for p in T.POSITIONS] + [
        ("Weeks 1-4", d[d.week <= 4]), ("Weeks 5-9", d[(d.week >= 5) & (d.week <= 9)]), ("Weeks 10-14", d[(d.week >= 10) & (d.week <= 14)]),
        ("Weeks 15-18", d[d.week >= 15]), ("Sleeper 3-8", d[d.sl_now < 8]), ("Sleeper 8-12", d[(d.sl_now >= 8) & (d.sl_now < 12)]),
        ("Sleeper 12-16", d[(d.sl_now >= 12) & (d.sl_now < 16)]), ("Sleeper 16+", d[d.sl_now >= 16])]
    for g, x in groups:
        if len(x):
            out.append({"group": g, "n": int(len(x)), **{c: miss(x, c) for c in cols}})
    return out


def boot(d, a, b, n=1000, seed=3, sq=False):
    """95% interval of the change in average miss (a minus b; sq: in mean squared miss), resampling whole weeks."""
    rng = np.random.default_rng(seed)
    loss = (lambda x: x ** 2) if sq else np.abs
    g = d.assign(da=loss(d.y_ppr - d[a]), db=loss(d.y_ppr - d[b])).groupby(["season", "week"])[["da", "db"]].agg(["sum", "count"])
    sa, sb, c = g[("da", "sum")].to_numpy(), g[("db", "sum")].to_numpy(), g[("da", "count")].to_numpy()
    k = len(c)
    xs = []
    for _ in range(n):
        i = rng.integers(0, k, k)
        xs.append(sa[i].sum() / c[i].sum() - sb[i].sum() / c[i].sum())
    return [float(np.percentile(xs, 2.5)), float(np.percentile(xs, 97.5))]


def vs_classic(N, Fr, ss):
    """Against Benny's current hand-tuned model (its replayed forecasts, dataset columns cl_now, cl_sd and cl_fut), on
    the player-weeks it has a number for: next week (his number if he plays) and Waivers' values 2-4 weeks ahead (a
    value of 0, a bye or an absence it expects, is left out: these rows are games he played). Average miss rewards
    forecasting below the average (scores are skewed: most weeks land under it), so the squared miss and the bias are
    reported too; lineups and Waivers add up expected points, which the squared miss judges."""
    d = common(N[N.season.isin(ss)])
    d = d[d.cl_now.notna()]
    f = Fr[Fr.season.isin(ss) & (Fr.sl_now >= 3) & (Fr.cl_fut > 0)]
    out = {}
    for label, x, col in (("near", d, "cl_now"), ("far", f, "cl_fut")):
        if not len(x):
            continue
        out[label] = {"n": int(len(x)), "model": miss(x, "pred"), "classic": miss(x, col), "sleeper": miss(x, "sl_now"),
                      "boot": boot(x, "pred", col), "bootSq": boot(x, "pred", col, sq=True),
                      "byPos": {p: {"model": miss(y, "pred"), "classic": miss(y, col)} for p, y in x.groupby("pos")}}
        if label == "near":
            out[label]["A"] = miss(x, "predA")
            out[label]["calibModel"], out[label]["calibClassic"] = calib(x), calib(x.assign(sd=x.cl_sd), "cl_now")
        else:
            out[label]["byH"] = {int(h): {"model": miss(y, "pred"), "classic": miss(y, col)} for h, y in x.groupby("h")}
            out[label]["blend"] = miss(x.assign(b=(x.pred + x[col]) / 2), "b")
    return out


def final(rows, near, near_a, far):
    """The chosen near model (next week), the situations-only near model for comparison, and the far model (2-4 weeks
    ahead, Waivers), on every season: tables by season, and for the tuning seasons, 2025 and 2026."""
    seasons = list(range(FIRST, HELDOUT + 1))
    key = ["pid", "season", "week", "h"]
    fr = {n: with_spread(rows, oof(rows, n, seasons), n) for n in (near, near_a, far)}
    cl = rows[key + ["cl_now", "cl_sd", "cl_fut"]] if "cl_now" in rows else rows[key].assign(cl_now=np.nan, cl_sd=np.nan, cl_fut=np.nan)
    N = fr[near][key + ["pos", "y_ppr", "sl_now", "pred", "sd"]].merge(
        fr[near_a][key + ["pred", "sd"]].rename(columns={"pred": "predA", "sd": "sdA"}), on=key).merge(cl, on=key, how="left")
    Fr = fr[far][key + ["pos", "y_ppr", "sl_now", "pred", "sd"]].merge(cl, on=key, how="left")
    N.to_parquet(os.path.join(OUT, "final-near.parquet"), index=False)
    Fr.to_parquet(os.path.join(OUT, "final-far.parquet"), index=False)
    res = {"names": {"near": near, "nearA": near_a, "far": far}, "seasons": {}}
    for S in seasons:
        d = common(N[N.season == S])
        if not len(d):
            continue
        res["seasons"][S] = {"B": miss(d, "pred"), "A": miss(d, "predA"), "sleeper": miss(d, "sl_now"), "bootB": boot(d, "pred", "sl_now"),
                             "far": {h: {"model": miss(common(Fr[Fr.season == S], h), "pred")["mae"],
                                         "sleeper": miss(common(Fr[Fr.season == S], h), "sl_now")["mae"]} for h in (2, 3, 4)}}
    for label, ss in (("tune", TUNE), ("confirm", [CONFIRM]), ("heldout", [HELDOUT])):
        d = common(N[N.season.isin(ss)])
        f = Fr[Fr.season.isin(ss) & (Fr.sl_now >= 3)]
        res[label] = {"B": miss(d, "pred"), "A": miss(d, "predA"), "sleeper": miss(d, "sl_now"),
                      "bands": band_rows(d, ["pred", "predA", "sl_now"]),
                      "bootB": boot(d, "pred", "sl_now"), "bootA": boot(d, "predA", "sl_now"), "bootBA": boot(d, "pred", "predA"),
                      "calibB": calib(d), "calibA": calib(d.assign(sd=d.sdA), "predA"),
                      "far": {"model": miss(f, "pred"), "sleeper": miss(f, "sl_now"), "boot": boot(f, "pred", "sl_now"),
                              "byH": {int(h): {"model": miss(x, "pred")["mae"], "sleeper": miss(x, "sl_now")["mae"], "n": int(len(x))} for h, x in f.groupby("h")},
                              "calib": calib(f)}}
    res["classic"] = {label: vs_classic(N, Fr, ss) for label, ss in (("tune", TUNE), ("confirm", [CONFIRM]), ("heldout", [HELDOUT]))}
    res["classic"].update({int(S): vs_classic(N, Fr, [S]) for S in seasons if S >= 2018})
    with open(os.path.join(OUT, "final.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x))
    for label in ("tune", "confirm", "heldout"):
        r = res[label]
        print(f"{label:8} next week: B {r['B']['mae']:.3f}  A {r['A']['mae']:.3f}  Sleeper {r['sleeper']['mae']:.3f}  (n {r['B']['n']:,}, "
              f"B-Sleeper 95% {r['bootB'][0]:+.3f}..{r['bootB'][1]:+.3f})  |  2-4 weeks: {r['far']['model']['mae']:.3f} vs Sleeper "
              f"{r['far']['sleeper']['mae']:.3f}  |  B range coverage {r['calibB']['coverage50']:.1%}")
    for label in ("tune", "confirm", "heldout"):
        for part in ("near", "far"):
            r = res["classic"][label].get(part)
            if r:
                m, c = r["model"], r["classic"]
                print(f"vs current Benny, {label:8} {part}: average miss {m['mae']:.3f} vs {c['mae']:.3f} (95% {r['boot'][0]:+.3f}..{r['boot'][1]:+.3f})"
                      f"  RMSE {m['rmse']:.3f} vs {c['rmse']:.3f}  bias {m['bias']:+.2f} vs {c['bias']:+.2f}  (n {r['n']:,})")
    return res


def fixtures_ml():
    """Copies of the replay fixtures (scripts/backtest/out/fixtures) with the trained model's out-of-season predictions
    from the final run as their ml field, the way model/proj.json gives them to the page, in fixtures-ml/: replay.py
    --dir fixtures-ml then runs the page on the trained model (Settings: Trained) and on the classic one. The predictions
    exist for games players played (the backtest's rows), so a player who didn't play keeps the classic number in both;
    catches aren't predicted here, which only matters outside PPR (the replay is PPR)."""
    import glob
    import data
    near = pd.read_parquet(os.path.join(OUT, "final-near.parquet"))
    far = pd.read_parquet(os.path.join(OUT, "final-far.parquet"))
    sid = {g: s for s, g in data.gsis_map(data.people(list(range(2018, HELDOUT + 1)))).items()}
    src = os.path.join(ROOT, "scripts", "backtest", "out", "fixtures")
    dst = os.path.join(ROOT, "scripts", "backtest", "out", "fixtures-ml")
    os.makedirs(dst, exist_ok=True)
    far = far.assign(c=far.week - far.h + 1)
    n = 0
    for path in sorted(glob.glob(os.path.join(src, "*.json"))):
        with open(path, encoding="utf-8") as f:
            fx = json.load(f)
        S, W = fx["season"], fx["week"]
        if S < 2019:
            continue
        ids = {}
        for g, p_, sd in near[(near.season == S) & (near.week == W) & (near.h == 1)][["pid", "pred", "sd"]].itertuples(index=False):
            if sid.get(g) and p_ == p_:
                ids[sid[g]] = [round(p_, 2), 0, round(sd, 2) if sd == sd else None] + [None] * 6
        for g, h, p_ in far[(far.season == S) & (far.c == W)][["pid", "h", "pred"]].itertuples(index=False):
            if sid.get(g) and sid[g] in ids and p_ == p_:
                ids[sid[g]][2 * h - 1], ids[sid[g]][2 * h] = round(p_, 2), 0
        fx["ml"] = {"season": S, "week": W, "made": "backtest", "ids": ids}
        with open(os.path.join(dst, os.path.basename(path)), "w", encoding="utf-8") as f:
            json.dump(fx, f, separators=(",", ":"))
        n += 1
    print(f"{n} fixtures with trained predictions -> {os.path.relpath(dst, ROOT)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["tune", "final", "fixtures"])
    ap.add_argument("names", nargs="*", help="tune: configs; final: NEAR NEAR_A FAR")
    ap.add_argument("--data", default=os.path.join(HERE, "out", "player_weeks.parquet"))
    a = ap.parse_args()
    rows = pd.read_parquet(a.data)
    if a.mode == "fixtures":
        return fixtures_ml()
    if a.mode == "tune":
        names = a.names or [f"{v}-hl{h}" for v in "AB" for h in ("1", "2", "3", "5", "inf")]
        tune(rows, names)
    else:
        final(rows, *a.names)


if __name__ == "__main__":
    main()
