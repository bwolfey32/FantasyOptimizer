"""Checks on the trained model's features (scripts/model/features.py), on real 2025 data (cached nflverse files; the
first run downloads them).

Run: python -m pytest tests/test_features.py
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "model"))
import data  # noqa: E402
import features as F  # noqa: E402

SEASON = 2025


@pytest.fixture(scope="module")
def ctx():
    return data.context([SEASON], with_sleeper=True)


def keys_at(ctx, c):
    """Every training key whose prediction is made before week c of SEASON (target week - h + 1 == c)."""
    keys = F.training_keys(ctx, [SEASON])
    return keys[keys.week - keys.h + 1 == c]


def rows_at(ctx, c, keys=None):
    """Their feature rows. The keys (who played, for which team, in the target week) come from the real tables, so a
    scrambled copy is asked about the same players."""
    keys = keys_at(ctx, c) if keys is None else keys
    return F.Builder(ctx).rows(keys).sort_values(["pid", "h"]).reset_index(drop=True)


def scrambled(ctx, c, seed=7):
    """The same tables with everything that isn't known before week c changed: box scores and final scores from week c
    on, injury tags of every other week, lines, totals, weather and depth charts of every week but c, and Sleeper's
    projections for the weeks after c."""
    rng = np.random.default_rng(seed)
    x = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in ctx.items()}
    L = x["logs"]
    m = (L.season == SEASON) & (L.week >= c)
    for col in ("ppr", "rec", "tgt", "car", "patt", "pyd", "ryd", "recyd", "sk", "snp", "tm_tgt", "tm_car"):
        L[col] = L[col].astype(float)
        L.loc[m, col] = L.loc[m, col] * rng.uniform(0.2, 3.0, m.sum()) + rng.uniform(0, 5, m.sum())
    L.loc[m, "team"] = rng.permutation(L.loc[m, "team"].to_numpy())
    T = x["tg"]
    mt = (T.season == SEASON) & (T.week >= c)
    for col in ("tgt", "car", "patt", "sk", "pyd", "ryd", "pf", "pa"):
        T[col] = T[col].astype(float)
        T.loc[mt, col] = T.loc[mt, col] * rng.uniform(0.2, 3.0, mt.sum())
    S = x["status"]
    x["status"] = pd.concat([S[(S.season != SEASON) | (S.week <= c)],
                             S[(S.season == SEASON) & (S.week > c)].assign(inj="Out")])
    G = x["games"]
    mg = (G.season == SEASON) & (G.week != c)
    for col in ("spread", "total", "temp", "wind"):
        G[col] = G[col].astype(float)
        G.loc[mg, col] = rng.uniform(-20, 60, mg.sum())
    D = x["depth"]
    md = (D.season == SEASON) & (D.week != c)
    D["depth"] = D["depth"].astype(float)
    D.loc[md, "depth"] = rng.integers(1, 6, md.sum())
    P = x["sproj"]
    mp = (P.season == SEASON) & (P.week > c)   # past weeks' projections are known (sl_bias reads them)
    P.loc[mp, "sproj"] = rng.uniform(0, 30, mp.sum())
    return x


@pytest.mark.parametrize("c", [1, 2, 6, 12])
def test_no_leakage(ctx, c):
    keys = keys_at(ctx, c)
    before = rows_at(ctx, c, keys)
    after = rows_at(scrambled(ctx, c), c, keys)
    assert len(before) > 300 and len(before) == len(after)
    assert before.sl_now.notna().mean() > 0.5
    for col in F.FEATURES + F.SLEEPER_FEATURES:
        a, b = before[col].to_numpy(dtype=float), after[col].to_numpy(dtype=float)
        assert np.allclose(a, b, equal_nan=True), f"{col} changed when week {c}+ results changed"


def test_scrambling_reaches_the_features(ctx):
    """The scramble is strong enough to matter: rows predicted a week later do change."""
    keys = keys_at(ctx, 7)
    before = rows_at(ctx, 7, keys)
    after = rows_at(scrambled(ctx, 6), 7, keys)
    assert not np.allclose(before.ppr_cur.to_numpy(dtype=float), after.ppr_cur.to_numpy(dtype=float), equal_nan=True)


def test_far_games_have_no_line_or_weather(ctx):
    r = rows_at(ctx, 6)
    far = r[r.h > 1]
    assert len(far) and far[["spread", "total", "implied", "temp", "wind"]].isna().all().all()
    near = r[r.h == 1]
    assert near.spread.notna().mean() > 0.95


def test_no_identity_features():
    for name in F.FEATURES + F.SLEEPER_FEATURES:
        assert name not in {"pid", "team", "opp", "season", "coach", "name"}, name


# ---------- the bundle adapter against nflverse, on the committed snapshot ----------
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


@pytest.fixture(scope="module")
def snap():
    import json
    with open(os.path.join(ROOT, "snapshot.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def live_ctx(snap):
    return data.context([snap["season"]], with_sleeper=False)


def played_weeks(ctx, snap):
    have = set(ctx["logs"].loc[ctx["logs"].season == snap["season"], "week"])
    return [w for w in range(1, snap["week"]) if w in have and w - 1 < len(snap["weeks"])]


def test_bundle_box_scores_match_nflverse(live_ctx, snap):
    weeks = played_weeks(live_ctx, snap)
    if not weeks:
        pytest.skip("nflverse has none of the snapshot's weeks yet")
    lg, _ = data.bundle_logs(snap, weeks, data.gsis_map(live_ctx["people"]))
    nv = live_ctx["logs"]
    nv = nv[(nv.season == snap["season"]) & nv.week.isin(weeks) & ((nv.tgt + nv.car + nv.patt) > 0)]
    m = nv.merge(lg, on=["week", "pid"], suffixes=("", "_b"))
    assert len(m) / len(nv) > 0.95, f"only {len(m)} of {len(nv)} nflverse player-games found in the bundle"
    for col, tol in (("ppr", 0.5), ("tgt", 0), ("car", 0), ("patt", 0), ("rec", 0)):
        share = ((m[col] - m[col + "_b"]).abs() <= tol).mean()
        assert share > 0.97, f"{col}: only {share:.1%} agree"


def test_bundle_lines_close_to_nflverse(live_ctx, snap):
    """The bundle's lines for its week (as posted when it was made) are close to nflverse's (closing or current)."""
    priced = {data.fix(t) for g in snap["games"] if g.get("ou") is not None for t in (g["home"], g["away"])}
    if len(priced) < 8:
        pytest.skip(f"only {len(priced)} teams still have odds in this snapshot (ESPN drops them once a game is played)")
    nv = live_ctx["games"].set_index(["season", "week", "team"])
    b = data.apply_bundle(live_ctx, snap)["games"].set_index(["season", "week", "team"])
    k = [i for i in nv.index if i[0] == snap["season"] and i[1] == snap["week"] and i[2] in priced]
    d = (nv.loc[k, "spread"] - b.loc[k, "spread"]).abs().dropna()
    t = (nv.loc[k, "total"] - b.loc[k, "total"]).abs().dropna()
    assert len(d) >= 8 and (d <= 3).mean() > 0.9, d.describe()
    assert (t <= 3).mean() > 0.9, t.describe()


def test_bundle_keeps_lines_and_weather_it_lacks(live_ctx, snap):
    """A game the bundle has no odds for keeps nflverse's line, and covered stadiums carry no weather."""
    b = data.apply_bundle(live_ctx, snap)["games"]
    nv = live_ctx["games"]
    wk = (b.season == snap["season"]) & (b.week == snap["week"])
    unpriced = {data.fix(t) for g in snap["games"] if g.get("ou") is None for t in (g["home"], g["away"])}
    m = wk & b.team.isin(unpriced)
    assert np.allclose(b.loc[m, "total"].to_numpy(dtype=float), nv.loc[m, "total"].to_numpy(dtype=float), equal_nan=True)
    assert b.loc[wk & (b.dome == 1), ["temp", "wind"]].isna().all().all()


def test_bundle_features_match_nflverse(live_ctx, snap):
    """The features for the snapshot's week, built from nflverse's box scores and from the bundle's own, agree. Rows
    saved before October 2026 carry no snap counts, so the bundle can't see a game a player was on the field for
    without a touch: then nflverse's side keeps only games with a touch too, so like is compared with like."""
    weeks = played_weeks(live_ctx, snap)
    if not weeks:
        pytest.skip("nflverse has none of the snapshot's weeks yet")
    S = snap["season"]
    keys = data.live_keys(live_ctx, snap, horizons=(1,))
    has_snaps = any(len(r) >= 16 and r[14] is not None for w in weeks for r in snap["weeks"][w - 1]["P"])
    full = live_ctx
    if not has_snaps:
        L = live_ctx["logs"]
        blind = (L.season == S) & L.week.isin(weeks) & ((L.tgt + L.car + L.patt) == 0)
        full = dict(live_ctx, logs=L[~blind])
    a = F.Builder(data.apply_bundle(full, snap)).rows(keys).set_index("pid")
    stripped = dict(live_ctx, logs=live_ctx["logs"][~((live_ctx["logs"].season == S) & live_ctx["logs"].week.isin(weeks))],
                    tg=live_ctx["tg"][~((live_ctx["tg"].season == S) & live_ctx["tg"].week.isin(weeks))])
    b = F.Builder(data.apply_bundle(stripped, snap)).rows(keys).set_index("pid")
    assert len(a) > 300 and len(b) == len(a)
    b = b.reindex(a.index)
    for col, tol in (("g", 0), ("ppr_cur", 0.5), ("use_ew", 0.5), ("tsh_cur", 0.02), ("csh_cur", 0.02), ("o_fpa", 1.0), ("t_plays", 1.0)):
        x, y = a[col].astype(float), b[col].astype(float)
        both = x.notna() & y.notna()
        share = ((x[both] - y[both]).abs() <= tol).mean()
        assert share > 0.95, f"{col}: only {share:.1%} within {tol}"
