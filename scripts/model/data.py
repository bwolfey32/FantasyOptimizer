"""The normalized tables the trained model is built from, filled from nflverse (history) and, for live predictions and
replays, from a v1 data bundle (snapshot.json or a backtest fixture).

Tables (pandas DataFrames, team codes as the site writes them: LAR, LV, LAC, WAS):
  logs    one row per player-game a QB/RB/WR/TE played (a stat line or an offensive snap): ppr (Sleeper's PPR, which
          counts an interception -1 where nflverse's counts -2), rec, tgt, car, patt
          (pass attempts), pyd, ryd, recyd, sk (sacks taken), snp (share of the team's offensive snaps, NaN before snap
          counts), tm_tgt and tm_car (his team's targets and carries that game)
  tg      one row per team-game: the offense's tgt, car, patt, sk, pyd, ryd, and the final score (pf, pa)
  games   one row per team per scheduled game, what was known before kickoff: opp, home (1, 0, 0.5 neutral), spread
          (points the team is favored by), total, dome, temp, wind, rest, coach
  status  one row per player-week on the injury report or a reserve list: inj = Out (reserve lists count as Out),
          Doubtful or Questionable
  people  one row per player: birth date, rookie year, draft pick, Sleeper id
  sproj   Sleeper's PPR projection per player-week (model B only)

Box scores come from nflverse in both modes, so training and live features share one code path; a bundle only
overrides what is known before kickoff (lines, forecast, injury tags, Sleeper's projection) and fills in weeks nflverse
hasn't published yet.
"""
import json
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

import nflverse as nv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backtest"))
from build_fixtures import STADIUMS  # noqa: E402  ([lat, lon, roof] per home team, as in index.html)

SKILL = ("QB", "RB", "WR", "TE")
TEAM_FIX = {"LA": "LAR", "STL": "LAR", "OAK": "LV", "SD": "LAC", "JAC": "JAX", "WSH": "WAS"}
OUT_ROSTER = {"RES", "SUS", "RSN", "RSR", "NWT"}   # reserve lists (IR, PUP, NFI, suspended...): out until activated
SLEEPER_PROJ = "https://api.sleeper.com/projections/nfl/{s}/{w}?season_type=regular&position[]=QB&position[]=RB&position[]=WR&position[]=TE"


def fix(x):
    return x.replace(TEAM_FIX) if isinstance(x, pd.Series) else TEAM_FIX.get(x, x)


def season_logs(season, max_age=None):
    """logs and tg for one season."""
    st = nv.frame("stats_{s}.csv", season, max_age)
    st = st[st.season_type == "REG"].copy()
    st["team"], st["opponent_team"] = fix(st.team), fix(st.opponent_team)
    f = lambda c: pd.to_numeric(st[c], errors="coerce").fillna(0)
    st = st.assign(tgt=f("targets"), car=f("carries"), patt=f("attempts"), pyd=f("passing_yards"), ryd=f("rushing_yards"),
                   recyd=f("receiving_yards"), sk=f("sacks_suffered"), rec=f("receptions"),
                   ppr=f("fantasy_points_ppr") + f("passing_interceptions"))
    tg = st.groupby(["week", "team"], as_index=False)[["tgt", "car", "patt", "sk", "pyd", "ryd"]].sum()
    st["pos"] = st.position.replace({"FB": "RB"})
    lg = st[st.pos.isin(SKILL)][["week", "player_id", "pos", "team", "opponent_team", "ppr", "rec", "tgt", "car", "patt",
                                 "pyd", "ryd", "recyd", "sk"]].rename(columns={"player_id": "pid", "opponent_team": "opp"})
    # snap counts (2013 on), keyed by PFR id: nflverse's player file gives the gsis id (the weekly rosters miss a
    # quarter of them before 2020)
    snp = pd.DataFrame(columns=["week", "pid", "snp", "spos", "team", "opp"])
    if season >= 2013:
        sn = nv.frame("snap_counts_{s}.csv", season, max_age)
        sn = sn[(sn.game_type == "REG") & (sn.offense_snaps > 0)]
        ids = nv.frame("players.csv", max_age=24 * 7)[["pfr_id", "gsis_id"]].dropna().drop_duplicates("pfr_id")
        sn = sn.merge(ids, left_on="pfr_player_id", right_on="pfr_id", how="inner")
        snp = pd.DataFrame({"week": sn.week, "pid": sn.gsis_id, "snp": sn.offense_pct, "spos": sn.position.replace({"FB": "RB"}),
                            "team": fix(sn.team), "opp": fix(sn.opponent)}).drop_duplicates(["week", "pid"])
    lg = lg.merge(snp[["week", "pid", "snp"]], on=["week", "pid"], how="left")
    # played with no stat line: an offensive snap and nothing else (a receiver with no target), a zero
    extra = snp[snp.spos.isin(SKILL)].merge(lg[["week", "pid"]], on=["week", "pid"], how="left", indicator=True)
    extra = extra[extra._merge == "left_only"].rename(columns={"spos": "pos"}).drop(columns="_merge")
    for c in ("ppr", "rec", "tgt", "car", "patt", "pyd", "ryd", "recyd", "sk"):
        extra[c] = 0.0
    lg = pd.concat([lg, extra[lg.columns]], ignore_index=True)
    lg = lg.merge(tg[["week", "team", "tgt", "car"]].rename(columns={"tgt": "tm_tgt", "car": "tm_car"}), on=["week", "team"], how="left")
    lg.insert(0, "season", season)
    tg.insert(0, "season", season)
    return lg, tg


def schedule(seasons):
    """games (pregame, one row per team) and the final scores for tg."""
    g = nv.frame("games.csv", max_age=12)
    g = g[(g.game_type == "REG") & g.season.isin(seasons)].copy()
    g["home_team"], g["away_team"] = fix(g.home_team), fix(g.away_team)
    neutral = (g.location == "Neutral").to_numpy()
    dome = g.roof.isin(["dome", "closed"]).astype(float).to_numpy()
    base = dict(season=g.season.to_numpy(), week=g.week.to_numpy(), total=g.total_line.to_numpy(), dome=dome,
                temp=g.temp.to_numpy(), wind=g.wind.to_numpy(), gameday=g.gameday.to_numpy())
    home = pd.DataFrame({**base, "team": g.home_team.to_numpy(), "opp": g.away_team.to_numpy(), "home": np.where(neutral, 0.5, 1.0),
                         "spread": g.spread_line.to_numpy(), "rest": g.home_rest.to_numpy(), "coach": g.home_coach.to_numpy(),
                         "pf": g.home_score.to_numpy(), "pa": g.away_score.to_numpy()})
    away = pd.DataFrame({**base, "team": g.away_team.to_numpy(), "opp": g.home_team.to_numpy(), "home": np.where(neutral, 0.5, 0.0),
                         "spread": -g.spread_line.to_numpy(), "rest": g.away_rest.to_numpy(), "coach": g.away_coach.to_numpy(),
                         "pf": g.away_score.to_numpy(), "pa": g.home_score.to_numpy()})
    out = pd.concat([home, away], ignore_index=True)
    # a covered stadium's temperature and wind are the building's, not the weather
    out.loc[out.dome == 1, ["temp", "wind"]] = np.nan
    return out


def season_status(season, max_age=None):
    """The Friday injury report (Out, Doubtful, Questionable) and the weekly reserve lists, as one tag per player-week."""
    inj = nv.frame("injuries_{s}.csv", season, max_age)
    typ = inj["season_type"] if "season_type" in inj else inj["game_type"]
    inj = inj[(typ == "REG") & inj.report_status.isin(["Out", "Doubtful", "Questionable"])]
    a = pd.DataFrame({"week": inj.week, "pid": inj.gsis_id, "inj": inj.report_status})
    ros = nv.frame("roster_weekly_{s}.csv", season, max_age)
    ros = ros[(ros.game_type == "REG") & ros.status.isin(OUT_ROSTER)]
    b = pd.DataFrame({"week": ros.week, "pid": ros.gsis_id, "inj": "Out"})
    rank = {"Out": 0, "Doubtful": 1, "Questionable": 2}
    s = pd.concat([a, b]).dropna(subset=["pid"])
    s = s.assign(r=s.inj.map(rank)).sort_values("r").drop_duplicates(["week", "pid"]).drop(columns="r")
    s.insert(0, "season", season)
    return s


def people(seasons):
    """Birth date, rookie year and draft pick (the latest weekly roster that has them), and the Sleeper id
    (DynastyProcess's crosswalk, which matched every fantasy-relevant player of 2025)."""
    rows = []
    for s in seasons:
        r = nv.frame("roster_weekly_{s}.csv", s)
        rows.append(r[["gsis_id", "birth_date", "rookie_year", "entry_year", "draft_number", "sleeper_id"]].dropna(subset=["gsis_id"]))
    p = pd.concat(rows).groupby("gsis_id").last()
    p["rookie_year"] = p.rookie_year.fillna(p.entry_year)
    dp = nv.frame("db_playerids.csv", max_age=24 * 7)[["gsis_id", "sleeper_id"]].dropna()
    dp = dp[dp.gsis_id.str.startswith("00-")].drop_duplicates("gsis_id").set_index("gsis_id")
    p["sleeper_id"] = dp.sleeper_id.reindex(p.index).fillna(p.sleeper_id)
    p["sleeper_id"] = p.sleeper_id.map(lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace(".0", "").isdigit() else (x if pd.notna(x) else None))
    p["birth_date"] = pd.to_datetime(p.birth_date, errors="coerce")
    return p[["birth_date", "rookie_year", "draft_number", "sleeper_id"]].rename_axis("pid")


def sleeper_proj(seasons, gsis_of, weeks=range(1, 19), live_season=None):
    """Sleeper's weekly PPR projections (2018 on carry PPR points), cached as one small CSV per season; the season being
    played is fetched again when its file is more than 6 hours old (its projections change until kickoff)."""
    rows = []
    for s in seasons:
        p = os.path.join(nv.CACHE, f"sleeper_proj_{s}.csv")
        stale = s == live_season and os.path.exists(p) and time.time() - os.path.getmtime(p) > 6 * 3600
        if not os.path.exists(p) or stale:
            got = []
            for w in weeks:
                req = urllib.request.Request(SLEEPER_PROJ.format(s=s, w=w), headers={"User-Agent": "bennys-picks-model"})
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        data = json.load(r)
                except Exception:
                    continue
                for x in data or []:
                    pts = (x.get("stats") or {}).get("pts_ppr")
                    if pts is not None:
                        got.append((w, str(x.get("player_id")), float(pts)))
            if not got:
                continue
            pd.DataFrame(got, columns=["week", "sid", "proj"]).to_csv(p, index=False)
        d = pd.read_csv(p, dtype={"sid": str})
        d.insert(0, "season", s)
        rows.append(d)
    if not rows:
        return pd.DataFrame(columns=["season", "week", "pid", "sproj"])
    d = pd.concat(rows)
    d["pid"] = d.sid.map(gsis_of)
    return d.dropna(subset=["pid"]).rename(columns={"proj": "sproj"})[["season", "week", "pid", "sproj"]].drop_duplicates(["season", "week", "pid"])


def context(seasons, with_sleeper=False, live_season=None):
    """Every table for these seasons (the season before the first is loaded too, for last season's numbers). The season
    being played (live_season) is re-downloaded when its cached files are more than 6 hours old."""
    seasons = sorted(set(seasons) | {min(seasons) - 1})
    age = lambda s: 6 if s == live_season else None
    L, T, S = [], [], []
    for s in seasons:
        lg, tg = season_logs(s, age(s))
        L.append(lg); T.append(tg); S.append(season_status(s, age(s)))
    games = schedule(seasons)
    tg = pd.concat(T, ignore_index=True).merge(games[["season", "week", "team", "pf", "pa"]], on=["season", "week", "team"], how="left")
    ppl = people(seasons)
    ctx = {"logs": pd.concat(L, ignore_index=True), "tg": tg, "games": games.drop(columns=["pf", "pa"]),
           "scores": games[["season", "week", "team", "pf", "pa"]], "status": pd.concat(S, ignore_index=True), "people": ppl, "sproj": None}
    if with_sleeper:
        ctx["sproj"] = sleeper_proj([s for s in seasons if s >= 2018], gsis_map(ppl), live_season=live_season)
    return ctx


def gsis_map(ppl):
    """Sleeper id -> gsis id."""
    return {sid: g for g, sid in ppl.sleeper_id.dropna().items()}


# ---------- the bundle adapter: snapshot.json or a backtest fixture ----------
SLEEPER_OUT = ("out", "ir", "pup", "sus", "na", "cov")   # index.html's evalPlayer: these tags mean he's out


def inj_of(tag):
    t = (tag or "").lower()
    if t.startswith("questionable"):
        return "Questionable"
    if t.startswith("doubtful"):
        return "Doubtful"
    return "Out" if t.startswith(SLEEPER_OUT) else None


def bundle_logs(bundle, weeks, gsis_of):
    """logs and tg rows from the bundle's weekly stats (compactWeek rows) for the given weeks."""
    S, L, T = bundle["season"], [], []
    for w in weeks:
        if w - 1 >= len(bundle["weeks"]):
            continue
        rows = bundle["weeks"][w - 1]["P"]
        d = pd.DataFrame([r[:16] + [None] * (16 - len(r)) for r in rows],
                         columns=["sid", "pos", "team", "opp", "ppr", "patt", "pyd", "sk", "car", "ryd", "tgt", "recyd", "name", "rec", "snp", "tsnp"])
        d["team"], d["opp"] = fix(d.team), fix(d.opp)
        tm = d.groupby("team", as_index=False)[["tgt", "car", "patt", "sk", "pyd", "ryd"]].sum()
        T.append(tm.assign(season=S, week=w))
        # played on offense, as nflverse counts it: some usage or an offensive snap (a special-teams-only game is not one)
        d = d[d.pos.isin(SKILL) & ((d.tgt + d.car + d.patt > 0) | (d.snp.fillna(0).astype(float) > 0))].copy()
        d["pid"] = d.sid.map(gsis_of)
        d = d.dropna(subset=["pid"])
        d["snp"] = np.where((d.tsnp.fillna(0) > 0) & d.snp.notna(), d.snp.astype(float) / d.tsnp.replace(0, np.nan).astype(float), np.nan)
        d = d.merge(tm[["team", "tgt", "car"]].rename(columns={"tgt": "tm_tgt", "car": "tm_car"}), on="team", how="left")
        L.append(d.assign(season=S, week=w)[["season", "week", "pid", "pos", "team", "opp", "ppr", "rec", "tgt", "car", "patt", "pyd",
                                             "ryd", "recyd", "sk", "snp", "tm_tgt", "tm_car"]])
    return (pd.concat(L, ignore_index=True) if L else None), (pd.concat(T, ignore_index=True) if T else None)


def apply_bundle(ctx, bundle):
    """The tables as they stood when the bundle was made: its week's line, total, weather, injury tags and Sleeper
    projections replace nflverse's (which are closing lines, game-day weather and the Friday report), and its weekly
    stats fill in the weeks of its season nflverse hasn't published."""
    S, W = bundle["season"], bundle["week"]
    gsis_of = gsis_map(ctx["people"])
    ctx = dict(ctx)
    # box scores nflverse doesn't have yet
    have = set(ctx["logs"].loc[ctx["logs"].season == S, "week"])
    missing = [w for w in range(1, W) if w not in have]
    lg, tg = bundle_logs(bundle, missing, gsis_of)
    if lg is not None:
        ctx["logs"] = pd.concat([ctx["logs"], lg], ignore_index=True)
        tg = tg.merge(ctx["scores"], on=["season", "week", "team"], how="left")
        ctx["tg"] = pd.concat([ctx["tg"], tg[ctx["tg"].columns]], ignore_index=True)
    # this week's games: lines, totals, weather and covered stadiums as the bundle has them. ESPN drops a game's odds
    # once it's played, so a game without a total keeps nflverse's (closing) line. A covered stadium is the site's
    # roof table's (a retractable roof counts as covered: the site reads weather only at open-air stadiums); an
    # open-air game without a forecast yet has unknown weather.
    G = ctx["games"].copy()
    wx = bundle.get("wx") or {}
    for g in bundle.get("games") or []:
        home, away = fix(g["home"]), fix(g["away"])
        fav, line, ou = fix(g.get("fav")) if g.get("fav") else None, g.get("line") or 0, g.get("ou")
        w, venue = wx.get(str(g.get("id"))), g.get("venue") or {}
        roof = venue.get("roof") or (STADIUMS.get(home) or [None, None, None])[2]
        for team, opp in ((home, away), (away, home)):
            m = (G.season == S) & (G.week == W) & (G.team == team)
            vals = {"opp": opp}
            if ou is not None:
                vals.update(spread=(line if fav == team else -line) if fav else 0.0, total=ou)
            if roof:
                covered = roof != "open"
                vals.update(dome=float(covered), temp=np.nan if covered else (w or {}).get("t", np.nan),
                            wind=np.nan if covered else (w or {}).get("wind", np.nan))
            if venue.get("neutral"):
                vals["home"] = 0.5
            if m.any():
                for k, v in vals.items():
                    G.loc[m, k] = v
    ctx["games"] = G
    # this week's injury tags: Sleeper's, in place of the Friday report and the reserve lists
    tags = []
    for sid, _, pos, team, inj, *_ in bundle.get("proj") or []:
        t, g = inj_of(inj), gsis_of.get(str(sid))
        if t and g:
            tags.append((S, W, g, t))
    st = ctx["status"]
    ctx["status"] = pd.concat([st[~((st.season == S) & (st.week == W))],
                               pd.DataFrame(tags, columns=["season", "week", "pid", "inj"])], ignore_index=True)
    # Sleeper's projection this week (PPR)
    sp = [(S, W, gsis_of.get(str(r[0])), r[5]) for r in bundle.get("proj") or [] if r[5] is not None]
    sp = pd.DataFrame(sp, columns=["season", "week", "pid", "sproj"]).dropna(subset=["pid"]).drop_duplicates(["season", "week", "pid"])
    old = ctx.get("sproj")
    ctx["sproj"] = pd.concat([old[~((old.season == S) & (old.week == W))], sp], ignore_index=True) if old is not None and len(old) else sp
    return ctx


def live_keys(ctx, bundle, horizons=(1, 2, 3, 4)):
    """What to predict from a bundle: every QB/RB/WR/TE in its projections with a team, for this week and the next three
    (weeks his team plays), with his Sleeper id for the output."""
    S, W = bundle["season"], bundle["week"]
    gsis_of = gsis_map(ctx["people"])
    G = ctx["games"]
    plays = set(zip(G.loc[G.season == S, "week"], G.loc[G.season == S, "team"]))
    seen, keys = set(), []
    for sid, _, pos, team, *_ in bundle.get("proj") or []:
        sid, team = str(sid), fix(team) if team else None
        g = gsis_of.get(sid)
        if pos not in SKILL or not team or not g or sid in seen:
            continue
        seen.add(sid)
        for h in horizons:
            T = W + h - 1
            if T <= 18 and (T, team) in plays:
                keys.append((g, sid, pos, S, T, h, team))
    return pd.DataFrame(keys, columns=["pid", "sid", "pos", "season", "week", "h", "team"])
