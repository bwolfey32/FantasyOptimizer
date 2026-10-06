"""Train the projection model: LightGBM, one model per position (QB, RB, WR, TE), on dataset.py's player-week history.

Usage: python scripts/model/train.py CONFIG [CONFIG ...] [--data scripts/model/out/player_weeks.parquet]
                                     [--oof scripts/model/out/backtest] [--out model]

Three models per position, written to model/<config>-<pos>-{mean,rec,spread}.txt with model/meta.json:
  mean    PPR points if he plays (L2), the projection
  rec     catches if he plays, so other scoring formats convert as index.html's fmtPts does
  spread  how far the score lands from the projection (the mean absolute miss), fitted on the backtest's out-of-season
          misses (--oof, which backtest.py writes); sd = a scale x its prediction, the scale set so the 25th-75th
          percentile range holds half of those scores
Variant A uses situation features only (features.FEATURES); B adds Sleeper's weekly projection (2018 on; earlier rows
have none and the trees learn both cases). Rows are weighted by season, halving every half_life seasons back, so older
seasons teach the broad patterns and recent ones lead. backtest.py chooses the variant, half-life and settings
(docs/model-report.md): B-hl3-bsl-md300-h1 for next week, A-hl5-md300-far for 2-4 weeks ahead.
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
import features as F  # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE")
PARAMS = {"objective": "regression", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 100, "feature_fraction": 0.8,
          "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "verbose": -1, "seed": 1, "deterministic": True,
          "force_row_wise": True}
SPREAD_PARAMS = dict(PARAMS, num_leaves=15, min_data_in_leaf=300, learning_rate=0.05)
SPREAD_ROUNDS = 300
MAX_ROUNDS, PATIENCE = 3000, 100
# more of these never lowers the projection (the trees may not learn a dip from noise)
MONOTONE = {"use_ew": 1, "use_cur": 1, "implied": 1, "sl_now": 1}
NORMAL_MAD = math.sqrt(math.pi / 2)   # a normal's sd over its mean absolute deviation
Z50 = 0.6745                          # half the 25th-75th percentile range, in sds


def config(name):
    """A config from its name, VARIANT-hlN[-tag...]: variant A, B or C (feature_list), the half-life in seasons (hlinf:
    none), and tags: bcl starts from Benny's current forecast; bsl / bsl1 / bsldb / bform from Sleeper's projection / the
    same a week ahead only / less its running bias / form; h1 / far train on next week / 2-4 weeks ahead only; nlN, mdN, lrN (thousandths), l2N set
    LightGBM's leaves, rows per leaf, learning rate, L2; lin linear trees; nomono no monotone constraints; rtN retrain
    during the season every N weeks on the weeks played so far; cwN weighs the current season's rows N times (with rtN);
    dsNAME labels a dataset variant (results cache apart)."""
    parts = name.split("-")
    cfg = {"variant": parts[0], "half_life": None if parts[1] == "hlinf" else float(parts[1][2:]), "params": {}, "monotone": True}
    for t in parts[2:]:
        if t == "nomono":
            cfg["monotone"] = False
        elif t.startswith("nl"):
            cfg["params"]["num_leaves"] = int(t[2:])
        elif t.startswith("md"):
            cfg["params"]["min_data_in_leaf"] = int(t[2:])
        elif t.startswith("l2"):
            cfg["params"]["lambda_l2"] = float(t[2:])
        elif t == "bform":
            cfg["base"] = "form"
        elif t == "bsl":
            cfg["base"] = "sleeper"
        elif t == "bcl":
            cfg["base"] = "classic"
        elif t == "bsldb":
            cfg["base"] = "sleeperdb"
        elif t == "bsl1":
            cfg["base"] = "sleeper1"
        elif t == "h1":
            cfg["horizons"] = [1]
        elif t == "far":
            cfg["horizons"] = [2, 3, 4]
        elif t == "lin":
            cfg["params"]["linear_tree"] = True
        elif t.startswith("lr"):
            cfg["params"]["learning_rate"] = float(t[2:]) / 1000
        elif t.startswith("rt"):
            cfg["retrain"] = int(t[2:])
        elif t.startswith("cw"):
            cfg["cur_w"] = float(t[2:])
        elif t.startswith("ds"):
            cfg["dataset"] = t[2:]   # a label for a dataset variant, so its results cache apart (no effect on training)
        else:
            raise ValueError(t)
    return cfg


def feature_list(variant):
    """A: situations only; B: and Sleeper's projection; C: and Benny's current forecast."""
    return F.FEATURES + (F.SLEEPER_FEATURES if variant in ("B", "C") else []) + (F.CLASSIC_FEATURES if variant == "C" else [])


def weights(seasons, ref, half_life):
    """Each row's weight: 1 for season ref, halving every half_life seasons back (None: all equal)."""
    s = np.asarray(seasons, dtype=float)
    return np.ones(len(s)) if not half_life else 0.5 ** ((ref - s) / half_life)


def form_base(df):
    """A starting point the trees correct, as index.html's formOf builds a player's form: this season's games (usage
    counted 3 to 1 over points, recent games heavier) blended with last season worth 4 games at week 1, easing to 1 by
    week 5. Zero with no games at all (the trees learn what a newcomer scores)."""
    c = (df.week - df.h + 1).to_numpy(dtype=float)
    cur = (0.75 * df.use_ew + 0.25 * df.ppr_ew).to_numpy(dtype=float)
    prev = (0.75 * df.use_prev + 0.25 * df.ppr_prev).to_numpy(dtype=float)
    g = df.g.to_numpy(dtype=float)
    k = np.where(np.isnan(prev), 0.0, np.where(c <= 5, 4 - 0.5 * (c - 1), 1.0))
    num = np.where(g > 0, g * np.nan_to_num(cur), 0) + k * np.nan_to_num(prev)
    den = np.where(g > 0, g, 0) + k
    return np.where(den > 0, num / np.where(den > 0, den, 1), 0.0)


def base_of(df, cfg):
    """The starting point the trees learn a correction to: none, form (form_base), or Sleeper's projection where there
    is one (form otherwise; sleeper1: a week ahead only)."""
    kind = cfg.get("base")
    if not kind:
        return np.zeros(len(df))
    f = form_base(df)
    if kind == "classic":   # Benny's current forecast (Waivers' value further ahead), else Sleeper's projection, else form
        cl = df.cl_now.to_numpy(dtype=float) if "cl_now" in df else np.full(len(df), np.nan)
        if "cl_fut" in df:
            fut = df.cl_fut.to_numpy(dtype=float)
            far = df.h.to_numpy() > 1
            cl = np.where(far, np.where(fut > 0, fut, np.nan), cl)
        sl = df.sl_now.to_numpy(dtype=float) if "sl_now" in df else np.full(len(df), np.nan)
        return np.where(~np.isnan(cl), cl, np.where(~np.isnan(sl), sl, f))
    if kind == "sleeperdb":   # Sleeper's projection less its running bias at the position (features.sl_bias)
        sl = df.sl_now.to_numpy(dtype=float) - df.sl_bias.fillna(0).to_numpy(dtype=float)
        return np.where(np.isnan(sl), f, sl)
    if kind in ("sleeper", "sleeper1"):
        sl = df.sl_now.to_numpy(dtype=float) if "sl_now" in df else np.full(len(df), np.nan)
        if kind == "sleeper1":   # this week's projection is about this week's game: a start only a week ahead
            sl = np.where(df.h.to_numpy() == 1, sl, np.nan)
        return np.where(np.isnan(sl), f, sl)
    return f


def params_for(feats, cfg):
    p = dict(PARAMS, **cfg.get("params", {}))
    if cfg.get("monotone", True) and not p.get("linear_tree"):
        p["monotone_constraints"] = [MONOTONE.get(f, 0) for f in feats]
        p["monotone_constraints_method"] = "advanced"
    return p


def _ds(df, feats, y, w, cfg):
    base = base_of(df, cfg) if y == "y_ppr" else None
    return lgb.Dataset(df[feats].astype(float), label=df[y].to_numpy(dtype=float), weight=w, init_score=base, free_raw_data=False)


def fit(train, feats, cfg, y="y_ppr", valid=None, rounds=None):
    """One LightGBM model. With valid, the number of rounds comes from early stopping on it."""
    p = params_for(feats, cfg)
    ref = cfg.get("ref", train.season.max())
    w = weights(train.season, ref, cfg.get("half_life"))
    if cfg.get("cur_w") and cfg.get("cur"):
        w = np.where(train.season.to_numpy() == cfg["cur"], w * cfg["cur_w"], w)
    dt = _ds(train, feats, y, w, cfg)
    if valid is not None:
        dv = _ds(valid, feats, y, None, cfg)
        b = lgb.train(p, dt, num_boost_round=MAX_ROUNDS, valid_sets=[dv], callbacks=[lgb.early_stopping(PATIENCE, verbose=False)])
        return b, b.best_iteration
    return lgb.train(p, dt, num_boost_round=rounds), rounds


def fit_season(rows, S, variant, cfg, y="y_ppr", upto=None, rounds=None):
    """Models for predicting season S, from seasons before it only: the rounds come from early stopping on season S-1
    (trained on the seasons before that), then the model is refit on every season before S with 10% more rounds.
    cfg["horizons"] limits the rows to those horizons (a near model for next week, a far one for Waivers' later weeks).
    upto: an in-season refit before week upto of S, adding S's games before it (target week < upto, all played by then),
    with the preseason models' rounds (out["rounds"])."""
    feats, out = feature_list(variant), {"rounds": {}}
    hs = cfg.get("horizons")
    for pos in POSITIONS:
        known = (rows.season < S) | ((rows.season == S) & (rows.week < upto)) if upto else (rows.season < S)
        d = rows[(rows.pos == pos) & known & (rows.h.isin(hs) if hs else True)]
        if rounds:
            n = rounds[pos]
        else:
            tr, va = d[d.season < S - 1], d[d.season == S - 1]
            _, best = fit(tr, feats, dict(cfg, ref=S - 2), y=y, valid=va)
            n = max(50, int(best * 1.1))
        ref = S if upto else S - 1
        out[pos], _ = fit(d, feats, dict(cfg, ref=ref, cur=S), y=y, rounds=n)
        out["rounds"][pos] = n
    out["cfg"] = cfg if y == "y_ppr" else dict(cfg, base=None)
    return out


def predict(models, df, variant):
    feats, pred = feature_list(variant), np.full(len(df), np.nan)
    base = base_of(df, models.get("cfg", {}))
    for pos in POSITIONS:
        k = (df.pos == pos).to_numpy()
        if pos in models and k.any():
            pred[k] = models[pos].predict(df.loc[k, feats].astype(float)) + base[k]
    return np.maximum(pred, 0.0)


def fit_spread(oof, variant, cfg):
    """Spread models from out-of-season predictions (oof: rows with pred and y_ppr): each position's model predicts the
    mean absolute miss from the features and the projection; k scales it to an sd that puts half of those scores inside
    the 25th-75th percentile range."""
    feats = feature_list(variant) + ["pred"]
    models, ks = {}, {}
    oof = oof.assign(absmiss=(oof.y_ppr - oof.pred).abs())
    for pos in POSITIONS:
        d = oof[oof.pos == pos]
        p = dict(SPREAD_PARAMS)
        dt = lgb.Dataset(d[feats].astype(float), label=d.absmiss.to_numpy(dtype=float),
                         weight=weights(d.season, d.season.max(), cfg.get("half_life")))
        m = lgb.train(p, dt, num_boost_round=SPREAD_ROUNDS)
        mad = np.maximum(m.predict(d[feats].astype(float)), 0.5)
        sel = (d.pred >= 3).to_numpy()
        ks[pos] = float(np.median(d.absmiss.to_numpy()[sel] / (Z50 * NORMAL_MAD * mad[sel])))
        models[pos] = m
    return models, ks


def predict_sd(models, ks, df, variant):
    feats, sd = feature_list(variant) + ["pred"], np.full(len(df), np.nan)
    for pos, m in models.items():
        k = (df.pos == pos).to_numpy()
        if k.any():
            sd[k] = ks[pos] * NORMAL_MAD * np.maximum(m.predict(df.loc[k, feats].astype(float)), 0.5)
    return sd


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("names", nargs="+", help="configs to train (see config()), e.g. B-hl3-bsl-md300-h1 A-hl5-md300-far")
    ap.add_argument("--data", default=os.path.join(HERE, "out", "player_weeks.parquet"))
    ap.add_argument("--oof", default=os.path.join(HERE, "out", "backtest"), help="the backtest's out-of-season predictions (spread models)")
    ap.add_argument("--out", default=os.path.join(ROOT, "model"))
    a = ap.parse_args()
    rows = pd.read_parquet(a.data)
    S = int(rows.season.max()) + 1          # every season there is, as if predicting the next
    os.makedirs(a.out, exist_ok=True)
    meta_path = os.path.join(a.out, "meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    for name in a.names:
        t, cfg = time.time(), config(name)
        v = cfg["variant"]
        mean = fit_season(rows, S, v, cfg)
        rec = fit_season(rows, S, v, cfg, y="y_rec")
        oof = pd.read_parquet(os.path.join(a.oof, name + ".parquet"))
        oof = oof.merge(rows[["pid", "season", "week", "h"] + [f for f in feature_list(v) if f not in oof.columns]], on=["pid", "season", "week", "h"])
        sp, ks = fit_spread(oof, v, cfg)
        for pos in POSITIONS:
            for kind, m in (("mean", mean[pos]), ("rec", rec[pos]), ("spread", sp[pos])):
                m.save_model(os.path.join(a.out, f"{name}-{pos}-{kind}.txt"))
        meta[name] = {"config": cfg, "features": feature_list(v), "spreadK": ks, "seasons": [int(rows.season.min()), int(rows.season.max())],
                      "trained": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        print(f"{name}: 12 models in {time.time() - t:.0f}s -> {a.out}")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)


if __name__ == "__main__":
    main()
