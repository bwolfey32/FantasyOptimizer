"""The trained model's features: one row per (player, season, target week, horizon), from data.py's tables.

A row with horizon h predicts the target week T as of the moment before week c = T - h + 1 kicks off: box scores of
weeks before c only, plus what was known then about the target game (opponent, home or away, stadium, rest, coach;
the line, total and weather only when h is 1, since a game weeks away has none yet), the injury report and reserve
lists of week c, and Sleeper's projection for week c (model B). tests/test_features.py checks that changing any box
score from week c on leaves the row unchanged.

No feature names a team, a player or a season: the model learns from situations (usage, role, pace, line, opponent
strength, weather, injuries), so what it learns carries over to teams and seasons it hasn't seen.
"""
import numpy as np
import pandas as pd

# index.html's USAGE_PTS: PPR points a game's usage is worth [base, per target, per carry, per pass attempt]
USAGE_PTS = {"QB": [-0.191, 0, 1.053, 0.422], "RB": [-0.367, 1.242, 0.769, 0], "WR": [0.06, 1.737, 0.682, 0], "TE": [-0.002, 1.904, 0.572, 0]}
EW_HALF = 2          # games: the exponentially weighted averages halve a game's weight every two games back
POS_CODE = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}

FEATURES = [
    # this season, before week c
    "g", "wk_since", "miss", "ppr_cur", "ppr_ew", "ppr_l3", "ppr_sd", "use_cur", "use_ew", "use_l3", "tsh_cur", "tsh_ew",
    "csh_cur", "csh_ew", "snp_cur", "snp_ew", "patt_cur", "rec_cur", "tgt_cur", "car_cur", "bonus_cur", "ypt_cur", "catch_cur",
    "ypa_cur", "d_use", "d_snp",
    # last season
    "g_prev", "ppr_prev", "use_prev", "tsh_prev", "csh_prev", "snp_prev", "patt_prev", "bonus_prev",
    # role and career
    "tm_change", "depth", "pos_share", "dc_depth", "dc_eff", "age", "exp", "draft",
    # his team's offense and the opponent's defense (this season before c, and last season)
    "t_g", "t_plays", "t_prate", "t_pf", "t_plays_prev", "t_prate_prev", "t_pf_prev",
    "o_g", "o_fpa", "o_ypc", "o_pyd", "o_sk", "o_pa", "o_fpa_prev", "o_ypc_prev", "o_pyd_prev", "o_pa_prev",
    # the target game
    "home", "spread", "total", "implied", "dome", "temp", "wind", "rest", "new_hc",
    # injuries at week c
    "inj", "vac_tgt", "vac_car", "vac_pos", "qb_out",
    # calendar
    "week", "h",
]
SLEEPER_FEATURES = ["sl_now", "sl_ratio", "sl_share", "sl_rank", "sl_bias"]
SL_BIAS_PRIOR = 40    # player-weeks: last season's bias counts as this many of this season's (under two weeks of QBs)
CLASSIC_FEATURES = ["cl_now", "cl_sd", "cl_fut"]   # Benny's current forecast for week c, and Waivers' value for the target week (model C)
TARGETS = ["y_ppr", "y_rec"]


def _usage(L):
    u = np.zeros(len(L))
    for p, (b, t, c, a) in USAGE_PTS.items():
        m = (L.pos == p).to_numpy()
        u[m] = b + t * L.tgt.to_numpy()[m] + c * L.car.to_numpy()[m] + a * L.patt.to_numpy()[m]
    return u


def prepare(ctx):
    """Per-game columns every cutoff reuses: usage points, shares, and the points beyond yards and catches (touchdowns,
    mostly: the luck the usage numbers leave out)."""
    L = ctx["logs"].copy()
    L["use"] = _usage(L)
    L["tsh"] = np.where(L.tm_tgt > 0, L.tgt / L.tm_tgt.where(L.tm_tgt > 0), 0.0)
    L["csh"] = np.where(L.tm_car > 0, L.car / L.tm_car.where(L.tm_car > 0), 0.0)
    L["bonus"] = L.ppr - 0.04 * L.pyd - 0.1 * (L.ryd + L.recyd) - L.rec
    L["touch"] = L.car + L.rec
    L["yds"] = L.ryd + L.recyd
    ctx = dict(ctx, logs=L.sort_values(["season", "week"], kind="stable").reset_index(drop=True))
    # each defense's points allowed to each position, and what the offense it faced did, per game
    tg, lg = ctx["tg"], ctx["logs"]
    fpa = lg.groupby(["season", "week", "opp", "pos"]).ppr.sum().unstack("pos").reindex(columns=list(USAGE_PTS)).fillna(0)
    fpa.columns = ["fpa_" + c for c in fpa.columns]
    dg = tg.rename(columns={"team": "opp"}).set_index(["season", "week", "opp"])[["car", "ryd", "pyd", "sk", "pf"]]
    dg = dg.rename(columns={"car": "car_a", "ryd": "ryd_a", "pyd": "pyd_a", "sk": "sk_d", "pf": "pa"}).join(fpa, how="left").reset_index()
    dg = dg.rename(columns={"opp": "team"})   # the defending team, one row per game it played
    ctx["dg"] = dg
    return ctx


def _player(L, recent=True):
    """A player's numbers over the games in L (newest weighted most in the _ew columns)."""
    if L.empty:
        return pd.DataFrame()
    L = L.sort_values(["pid", "season", "week"], kind="stable")
    k = L.groupby("pid").cumcount(ascending=False).to_numpy()   # 0 = his latest game
    w = 0.5 ** (k / EW_HALF)
    l3 = (k < 3).astype(float)
    last2, early = (k < 2).astype(float), (k >= 2).astype(float)
    d = pd.DataFrame({"pid": L.pid.to_numpy(), "n": 1.0, "w": w, "l3": l3, "last2": last2, "early": early})
    for c in ("ppr", "use", "tsh", "csh", "patt", "rec", "tgt", "car", "bonus", "touch", "yds", "pyd"):
        v = L[c].to_numpy()
        d[c] = v; d[c + "_w"] = v * w; d[c + "_l3"] = v * l3
    sn = L.snp.to_numpy(dtype=float)
    has = ~np.isnan(sn)
    d["sn"] = np.where(has, sn, 0); d["sn_n"] = has.astype(float); d["sn_w"] = np.where(has, sn * w, 0); d["sn_ww"] = np.where(has, w, 0)
    d["use_last2"], d["use_early"] = d.use * last2, d.use * early
    d["sn_last2"], d["sn_early"] = d.sn * last2, d.sn * early
    d["sn_n2"], d["sn_ne"] = has * last2, has * early
    d["ppr2"] = d.ppr ** 2
    s = d.groupby("pid").sum()
    n = s.n
    out = pd.DataFrame(index=s.index)
    out["g"] = n
    for c, name in (("ppr", "ppr"), ("use", "use"), ("tsh", "tsh"), ("csh", "csh"), ("patt", "patt"), ("rec", "rec"),
                    ("tgt", "tgt"), ("car", "car"), ("bonus", "bonus")):
        out[name + "_cur"] = s[c] / n
        if recent:
            out[name + "_ew"] = s[c + "_w"] / s.w
            out[name + "_l3"] = s[c + "_l3"] / s.l3
    out["snp_cur"] = (s.sn / s.sn_n).where(s.sn_n > 0)
    if recent:
        out["snp_ew"] = (s.sn_w / s.sn_ww).where(s.sn_ww > 0)
        out["ppr_sd"] = np.sqrt(np.maximum(s.ppr2 / n - (s.ppr / n) ** 2, 0) * n / (n - 1)).where(n > 1)
        out["ypt_cur"] = (s.yds / s.touch).where(s.touch > 0)
        out["catch_cur"] = (s.rec / s.tgt).where(s.tgt > 0)
        out["ypa_cur"] = (s.pyd / s.patt).where(s.patt > 0)
        ok4 = n >= 4
        out["d_use"] = (s.use_last2 / s.last2 - s.use_early / s.early).where(ok4)
        out["d_snp"] = (s.sn_last2 / s.sn_n2 - s.sn_early / s.sn_ne).where(ok4 & (s.sn_n2 > 0) & (s.sn_ne > 0))
    last = L.groupby("pid").last()
    out["team_last"], out["wk_last"], out["pos"] = last.team, last.week, last.pos
    return out


def _team(tg, dg, games):
    """Team offense (plays, pass rate, points a game) and defense (what it allows) over the games given."""
    o = tg.assign(plays=tg.patt + tg.car + tg.sk, pas=tg.patt + tg.sk).groupby("team").agg(
        t_g=("plays", "size"), plays=("plays", "sum"), pas=("pas", "sum"), pf=("pf", "mean"))
    off = pd.DataFrame({"t_g": o.t_g, "t_plays": o.plays / o.t_g, "t_prate": o.pas / o.plays.where(o.plays > 0), "t_pf": o.pf})
    d = dg.groupby("team").agg(o_g=("pa", "size"), car=("car_a", "sum"), ryd=("ryd_a", "sum"), pyd=("pyd_a", "mean"),
                               sk=("sk_d", "mean"), pa=("pa", "mean"), **{p: ("fpa_" + p, "mean") for p in USAGE_PTS})
    de = pd.DataFrame({"o_g": d.o_g, "o_ypc": d.ryd / d.car.where(d.car > 0), "o_pyd": d.pyd, "o_sk": d.sk, "o_pa": d.pa})
    for p in USAGE_PTS:
        de["fpa_" + p] = d[p]
    return off, de


class Builder:
    """Builds feature rows; the season-level numbers (last season, career) are computed once per season."""

    def __init__(self, ctx):
        self.ctx = prepare(ctx)
        self._prev = {}
        self._slerr = {}

    def sl_errors(self, S):
        """Sleeper's misses in season S: projection minus what he scored, per player-week (projected 3+, played)."""
        if S not in self._slerr:
            sp, L = self.ctx.get("sproj"), self.ctx["logs"]
            if sp is None or not len(sp):
                self._slerr[S] = pd.DataFrame(columns=["week", "pos", "err"])
            else:
                m = sp[(sp.season == S) & (sp.sproj >= 3)].merge(L[L.season == S][["week", "pid", "pos", "ppr"]], on=["week", "pid"])
                self._slerr[S] = pd.DataFrame({"week": m.week, "pos": m.pos, "err": m.sproj - m.ppr})
        return self._slerr[S]

    def sl_bias(self, S, c):
        """How far Sleeper has run over (+) or under what players scored at each position: this season's weeks before c,
        with last season's bias worth SL_BIAS_PRIOR player-weeks. Sleeper's habits change (it ran 2-4 points high on
        quarterbacks every year 2018-25 and stopped in 2026), so the model reads them instead of memorizing them."""
        cur, prev = self.sl_errors(S), self.sl_errors(S - 1)
        cur = cur[cur.week < c]
        out = {}
        for pos in USAGE_PTS:
            a, b = cur[cur.pos == pos].err, prev[prev.pos == pos].err
            k = SL_BIAS_PRIOR if len(b) else 0
            n = len(a) + k
            out[pos] = (a.sum() + (k * b.mean() if k else 0.0)) / n if n else np.nan
        return out

    def prev(self, S):
        if S not in self._prev:
            c = self.ctx
            L = c["logs"][c["logs"].season == S - 1]
            P = _player(L, recent=False)
            off, de = _team(c["tg"][c["tg"].season == S - 1], c["dg"][c["dg"].season == S - 1], None)
            g = c["games"][c["games"].season == S - 1].sort_values("week")
            coach = g.groupby("team").coach.last()
            self._prev[S] = (P, off, de, coach)
        return self._prev[S]

    def rows(self, keys):
        """keys: DataFrame with pid, pos, season, week (the target week), h, team (his team in the target week)."""
        keys = keys.assign(c=keys.week - keys.h + 1)
        keys = keys[keys.c >= 1]
        parts = [self._at(S, c, k) for (S, c), k in keys.groupby(["season", "c"], sort=True)]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(keys.columns) + FEATURES)

    def _at(self, S, c, k):
        C = self.ctx
        L = C["logs"]
        cur = L[(L.season == S) & (L.week < c)]
        P = _player(cur)
        Pp, offp, dep, coach_prev = self.prev(S)
        tg = C["tg"][(C["tg"].season == S) & (C["tg"].week < c)]
        dg = C["dg"][(C["dg"].season == S) & (C["dg"].week < c)]
        off, de = _team(tg, dg, None)
        st = C["status"]
        st = st[(st.season == S) & (st.week == c)].set_index("pid").inj
        out_now = set(st[st == "Out"].index)

        r = k.reset_index(drop=True).copy()
        pid = r.pid
        get = lambda df, col: df[col].reindex(pid).to_numpy() if col in df else np.full(len(r), np.nan)
        for col in ("g", "ppr_cur", "ppr_ew", "ppr_l3", "ppr_sd", "use_cur", "use_ew", "use_l3", "tsh_cur", "tsh_ew", "csh_cur",
                    "csh_ew", "snp_cur", "snp_ew", "patt_cur", "rec_cur", "tgt_cur", "car_cur", "bonus_cur", "ypt_cur",
                    "catch_cur", "ypa_cur", "d_use", "d_snp"):
            r[col] = get(P, col)
        r["g"] = r.g.fillna(0)
        r["wk_since"] = c - get(P, "wk_last")
        for col in ("g", "ppr", "use", "tsh", "csh", "snp", "patt", "bonus"):
            r[col + "_prev"] = get(Pp, col if col == "g" else col + "_cur")
        r["g_prev"] = r.g_prev.fillna(0)
        # a new team: his latest game this season was for another team, or (no games yet) last season's was
        tl, tlp = pd.Series(get(P, "team_last")), pd.Series(get(Pp, "team_last"))
        known = tl.where(tl.notna(), tlp)
        r["tm_change"] = np.where(known.isna(), np.nan, (known != r.team).astype(float))

        # the target game
        G = C["games"].set_index(["season", "week", "team"])
        gi = pd.MultiIndex.from_arrays([r.season, r.week, r.team])
        for col in ("opp", "home", "spread", "total", "dome", "temp", "wind", "rest", "coach"):
            r[col] = G[col].reindex(gi).to_numpy()
        far = r.h > 1
        r.loc[far, ["spread", "total", "temp", "wind"]] = np.nan
        r["implied"] = r.total / 2 + r.spread / 2
        cp = coach_prev.reindex(r.team).to_numpy()
        r["new_hc"] = np.where(pd.isna(cp) | r.coach.isna(), np.nan, (cp != r.coach.to_numpy()).astype(float))
        # his team's offense and the opponent's defense
        for col in ("t_g", "t_plays", "t_prate", "t_pf"):
            r[col] = off[col].reindex(r.team).to_numpy() if col in off else np.nan
        r["t_g"] = r.t_g.fillna(0)
        for col in ("t_plays", "t_prate", "t_pf"):
            r[col + "_prev"] = offp[col].reindex(r.team).to_numpy() if col in offp else np.nan
        opp = r.opp
        for col in ("o_g", "o_ypc", "o_pyd", "o_sk", "o_pa"):
            r[col] = de[col].reindex(opp).to_numpy() if col in de else np.nan
        r["o_g"] = r.o_g.fillna(0)
        for col in ("o_ypc", "o_pyd", "o_pa"):
            r[col + "_prev"] = dep[col].reindex(opp).to_numpy() if col in dep else np.nan
        fpa = np.full(len(r), np.nan); fpap = np.full(len(r), np.nan)
        for p in USAGE_PTS:
            m = (r.pos == p).to_numpy()
            if "fpa_" + p in de:
                fpa[m] = de["fpa_" + p].reindex(opp[m]).to_numpy()
            if "fpa_" + p in dep:
                fpap[m] = dep["fpa_" + p].reindex(opp[m]).to_numpy()
        r["o_fpa"], r["o_fpa_prev"] = fpa, fpap

        # injuries at week c: his own tag, and the work of teammates who are out
        r["inj"] = st.reindex(pid).map({"Questionable": 1, "Doubtful": 2, "Out": 3}).fillna(0).to_numpy()
        self._c = c
        self._chart(r, S, c, out_now)
        sp = C.get("sproj")
        self._sl = sp[(sp.season == S) & (sp.week == c)].set_index("pid").sproj if sp is not None and len(sp) else None
        self._roles(r, P, Pp, out_now)

        # career
        pe = C["people"]
        bd = pe.birth_date.reindex(pid)
        r["age"] = ((pd.Timestamp(year=S, month=9, day=1) - bd).dt.days / 365.25).to_numpy()
        r["exp"] = S - pe.rookie_year.reindex(pid).to_numpy()
        r["draft"] = pe.draft_number.reindex(pid).to_numpy()
        r["miss"] = np.maximum(r.t_g - r.g, 0)

        # Sleeper's projection for week c (model B)
        if self._sl is not None:
            r["sl_now"] = self._sl.reindex(pid).to_numpy()
            base = r.ppr_cur.where(r.g > 0, r.ppr_prev)
            r["sl_ratio"] = r.sl_now / base.where(base > 1)
            r["sl_bias"] = r.pos.map(self.sl_bias(S, c)).astype(float)
        # Benny's current forecast for week c (model C)
        cp = C.get("cproj")
        if cp is not None and len(cp):
            x = cp[(cp.season == S) & (cp.week == c)].set_index("pid")
            r["cl_now"], r["cl_sd"] = x.cproj.reindex(pid).to_numpy(), x.csd.reindex(pid).to_numpy()
            fut = np.full(len(r), np.nan)
            for h in (2, 3, 4):
                m = (r.h == h).to_numpy()
                if m.any():
                    fut[m] = x["cfut%d" % h].reindex(pid[m]).to_numpy(dtype=float)
            r["cl_fut"] = fut
        r["pos_code"] = r.pos.map(POS_CODE)
        return r.drop(columns=["coach"])

    def _chart(self, r, S, c, out_now):
        """dc_depth: his depth on week c's chart (1 = a starter; his best slot if he's listed at several; 5 when his
        team has a chart he isn't on); dc_eff: the same after skipping teammates ahead of him who are out."""
        ch = self.ctx.get("depth")
        if ch is None or not len(ch):
            r["dc_depth"] = r["dc_eff"] = np.nan
            return
        ch = ch[(ch.season == S) & (ch.week == c)]
        q = ch.assign(up=~ch.pid.isin(out_now)).sort_values(["team", "slot", "depth"], kind="stable")
        q["eff"] = q.groupby(["team", "slot"]).up.cumsum() - q.up + 1
        best, eff = q.groupby("pid").depth.min(), q.groupby("pid").eff.min()
        charted = r.team.isin(set(ch.team)).to_numpy()
        r["dc_depth"] = np.where(charted, best.reindex(r.pid).fillna(5).to_numpy(), np.nan)
        r["dc_eff"] = np.where(charted, eff.reindex(r.pid).fillna(5).to_numpy(), np.nan)

    def _roles(self, r, P, Pp, out_now):
        """depth: his rank at his position on his team by recent usage (1 = the lead), and pos_share his share of that
        group's usage, among teammates not out; vac_*: the share of the team's targets and carries (this season, or last
        season's on the same team before he has played) belonging to teammates out this week; qb_out: the team's lead
        quarterback is out."""
        # every player's current team and usage: this season's games, else last season's
        cols = ["team", "pos", "use", "tsh", "csh", "patt"]
        a = pd.DataFrame({"team": P.get("team_last"), "pos": P.get("pos"), "use": P.get("use_ew"), "tsh": P.get("tsh_cur"),
                          "csh": P.get("csh_cur"), "patt": P.get("patt_cur")}) if len(P) else pd.DataFrame(columns=cols)
        b = pd.DataFrame({"team": Pp.get("team_last"), "pos": Pp.get("pos"), "use": Pp.get("use_cur"), "tsh": Pp.get("tsh_cur"),
                          "csh": Pp.get("csh_cur"), "patt": Pp.get("patt_cur")}) if len(Pp) else pd.DataFrame(columns=cols)
        pool = pd.concat([x for x in (a, b[~b.index.isin(a.index)]) if len(x)]) if len(a) or len(b) else pd.DataFrame(columns=cols)
        # the keyed players sit on their target-week team, whatever their last game says
        keyed = r.drop_duplicates("pid").set_index("pid")
        both = pool.index.intersection(keyed.index)
        pool.loc[both, "team"] = keyed.team.reindex(both)
        pool.loc[both, "pos"] = keyed.pos.reindex(both)
        missing = keyed.index.difference(pool.index)
        if len(missing):
            pool = pd.concat([pool, pd.DataFrame({"team": keyed.team.reindex(missing), "pos": keyed.pos.reindex(missing)}, index=missing)])
        pool = pool.fillna({"use": 0.0, "tsh": 0.0, "csh": 0.0, "patt": 0.0})
        pool["use"] = pool.use.clip(lower=0)
        pool["out"] = pool.index.isin(out_now)
        # a fresh absence: he played in the last three weeks (or, before he has played this season, it's week 1 or 2);
        # a team has long since adjusted to a player who's been on a reserve list for months
        wl = P["wk_last"].reindex(pool.index) if len(P) else pd.Series(np.nan, index=pool.index)
        pool["fresh"] = np.where(wl.notna(), wl.fillna(-99).to_numpy() >= self._c - 3, self._c <= 2)
        live = pool[~pool.out]
        live = live.assign(rank=live.groupby(["team", "pos"]).use.rank(ascending=False, method="first"),
                           tot=live.groupby(["team", "pos"]).use.transform("sum"))
        r["depth"] = live["rank"].reindex(r.pid).to_numpy()
        tot = live.tot.reindex(r.pid).to_numpy()
        r["pos_share"] = np.where(tot > 0, live.use.reindex(r.pid).to_numpy() / np.where(tot > 0, tot, 1), np.nan)
        gone = pool[pool.out & pool.fresh & pool.pos.isin(["RB", "WR", "TE"])]
        vt, vc = gone.groupby("team").tsh.sum(), gone.groupby("team").csh.sum()
        r["vac_tgt"] = vt.reindex(r.team).fillna(0).clip(upper=1).to_numpy()
        r["vac_car"] = vc.reindex(r.team).fillna(0).clip(upper=1).to_numpy()
        gpos = pool[pool.out & pool.fresh].groupby(["team", "pos"]).use.sum()
        allpos = pool[~pool.out | pool.fresh].groupby(["team", "pos"]).use.sum()
        idx = pd.MultiIndex.from_arrays([r.team, r.pos])
        num, den = gpos.reindex(idx).fillna(0).to_numpy(), allpos.reindex(idx).fillna(0).to_numpy()
        r["vac_pos"] = np.where(den > 0, num / np.where(den > 0, den, 1), 0)
        # Sleeper's read of the depth chart (model B): his share of his position group's projections, and his rank in it
        if self._sl is not None:
            sl = live.assign(sl=self._sl.reindex(live.index).fillna(0).to_numpy())
            sl = sl.assign(rk=sl.groupby(["team", "pos"]).sl.rank(ascending=False, method="first"),
                           tot=sl.groupby(["team", "pos"]).sl.transform("sum"))
            t = sl.tot.reindex(r.pid).to_numpy()
            r["sl_share"] = np.where(t > 0, sl.sl.reindex(r.pid).to_numpy() / np.where(t > 0, t, 1), np.nan)
            r["sl_rank"] = np.where(t > 0, sl.rk.reindex(r.pid).to_numpy(), np.nan)
        qbs = pool[pool.pos == "QB"].sort_values("patt", ascending=False).groupby("team").head(1)
        qb_out = qbs.groupby("team").out.first().astype(float)
        r["qb_out"] = qb_out.reindex(r.team).fillna(0).to_numpy()


def training_keys(ctx, seasons, horizons=(1, 2, 3, 4)):
    """Every game a QB/RB/WR/TE played in these seasons, at each horizon, with what he scored (the targets)."""
    L = ctx["logs"]
    g = L[L.season.isin(seasons)][["pid", "pos", "season", "week", "team", "ppr", "rec"]].rename(columns={"ppr": "y_ppr", "rec": "y_rec"})
    return pd.concat([g.assign(h=h) for h in horizons], ignore_index=True)
