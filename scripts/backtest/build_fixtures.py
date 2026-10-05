"""Build historical replay fixtures for the backtest: one v1 data bundle per week, as index.html#export would have
written it before that week's first kickoff, plus each week's actual results kept apart from the fixture.

Usage: python3 scripts/backtest/build_fixtures.py [--weeks 2025:2-18,2026:1-4] [--out scripts/backtest/out]

Writes
  out/fixtures/<season>-wNN.json   the bundle ingest() reads (index.html?fixture=...#selftest), pregame information only
  out/actuals/<season>-wNN.json    that week's scores and usage, for scoring (never read by the page)
  out/rosters.json                 a synthetic 12-team league drafted from week-1 projections (replay.py uses them)

Every HTTP response is cached under scripts/backtest/cache/, so a rerun costs nothing. Sources, and what each fixture
field is built from (functions ported from index.html are named after their originals):
  proj      Sleeper weekly projections for the week. The row-level team and opponent are that week's; the nested `player`
            object is today's metadata (current team, current injury), so it is never used except for name and position.
  weeks     Sleeper weekly stats for weeks 1..N-1 of the season (compactWeek).
  priors    Sleeper season totals for the three prior seasons (deriveTotals), with last season's weekly QB rows.
  prevPPG   last season's per-game PPR, catches and team (playerPPG).
  sched     Sleeper's season schedule.
  games     ESPN's scoreboard for the week (ids, kickoff, home/away, neutral sites), every game set to 'pre'. The scoreboard
            drops odds once a game is played, so spread and total come from ESPN's odds feed: CLOSING lines.
  rec       team records built from the final scores of weeks 1..N-1 (the scoreboard's records include the week's game).
  wx        Open-Meteo's historical-forecast archive for the three hours from kickoff, at open-air stadiums (the archived
            short-range forecast, close to what fell; the live site reads a forecast hours or days ahead).
  idp       last season's defenders and returners (idpCompactPrev, returnersPrev) and this season's defenders through
            week N-1 from weekly stats, with their team that week from nflverse's weekly rosters (idpCompactNow).
  injuries  STUBS, see injury_of(): the official Friday injury report (nflverse) for Out/Doubtful/Questionable, nflverse
            weekly roster status RES as IR, and a player with past games but no projection counts Out only if he was
            inactive that week. Sleeper's own designations at the time can't be recovered.
  own       left empty: ESPN ownership by week can't be recovered. replay.py builds a free-agent pool instead.
  coaches, split   left out (display only).
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CACHE = os.path.join(HERE, "cache")

POS = ["QB", "RB", "WR", "TE", "K", "DEF"]
POSQ = "&".join("position[]=" + p for p in POS)
TEAMS = {"ARI": [22, "Cardinals"], "ATL": [1, "Falcons"], "BAL": [33, "Ravens"], "BUF": [2, "Bills"], "CAR": [29, "Panthers"],
         "CHI": [3, "Bears"], "CIN": [4, "Bengals"], "CLE": [5, "Browns"], "DAL": [6, "Cowboys"], "DEN": [7, "Broncos"],
         "DET": [8, "Lions"], "GB": [9, "Packers"], "HOU": [34, "Texans"], "IND": [11, "Colts"], "JAX": [30, "Jaguars"],
         "KC": [12, "Chiefs"], "LV": [13, "Raiders"], "LAC": [24, "Chargers"], "LAR": [14, "Rams"], "MIA": [15, "Dolphins"],
         "MIN": [16, "Vikings"], "NE": [17, "Patriots"], "NO": [18, "Saints"], "NYG": [19, "Giants"], "NYJ": [20, "Jets"],
         "PHI": [21, "Eagles"], "PIT": [23, "Steelers"], "SF": [25, "49ers"], "SEA": [26, "Seahawks"],
         "TB": [27, "Buccaneers"], "TEN": [10, "Titans"], "WAS": [28, "Commanders"]}
STADIUMS = {  # [lat, lon, roof] as in index.html
    "ARI": [33.5276, -112.2626, "retract"], "ATL": [33.7554, -84.4008, "retract"], "BAL": [39.2780, -76.6227, "open"],
    "BUF": [42.7738, -78.7870, "open"], "CAR": [35.2258, -80.8528, "open"], "CHI": [41.8623, -87.6167, "open"],
    "CIN": [39.0955, -84.5161, "open"], "CLE": [41.5061, -81.6995, "open"], "DAL": [32.7473, -97.0945, "retract"],
    "DEN": [39.7439, -105.0201, "open"], "DET": [42.3400, -83.0456, "dome"], "GB": [44.5013, -88.0622, "open"],
    "HOU": [29.6847, -95.4107, "retract"], "IND": [39.7601, -86.1639, "retract"], "JAX": [30.3239, -81.6373, "open"],
    "KC": [39.0489, -94.4839, "open"], "LV": [36.0908, -115.1833, "dome"], "LAC": [33.9535, -118.3392, "dome"],
    "LAR": [33.9535, -118.3392, "dome"], "MIA": [25.9580, -80.2389, "open"], "MIN": [44.9736, -93.2575, "dome"],
    "NE": [42.0909, -71.2643, "open"], "NO": [29.9511, -90.0812, "dome"], "NYG": [40.8135, -74.0745, "open"],
    "NYJ": [40.8135, -74.0745, "open"], "PHI": [39.9008, -75.1675, "open"], "PIT": [40.4468, -80.0158, "open"],
    "SF": [37.4030, -121.9700, "open"], "SEA": [47.5952, -122.3316, "open"], "TB": [27.9759, -82.5033, "open"],
    "TEN": [36.1665, -86.7713, "open"], "WAS": [38.9077, -76.8645, "open"]}

SLEEPER = {
    "proj": "https://api.sleeper.com/projections/nfl/{s}/{w}?season_type=regular&" + POSQ,
    "wk": "https://api.sleeper.com/stats/nfl/{s}/{w}?season_type=regular&" + POSQ,
    "tot": "https://api.sleeper.com/stats/nfl/{s}?season_type=regular&" + POSQ,
    "wkQB": "https://api.sleeper.com/stats/nfl/{s}/{w}?season_type=regular&position[]=QB",
    "sched": "https://api.sleeper.com/schedule/nfl/regular/{s}",
    "idp": "https://api.sleeper.com/stats/nfl/{s}?season_type=regular&position[]=DL&position[]=LB&position[]=DB",
    "idpwk": "https://api.sleeper.com/stats/nfl/{s}/{w}?season_type=regular&position[]=DL&position[]=LB&position[]=DB",
}
ESPN_SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={w}&seasontype=2&dates={s}"
ESPN_ODDS = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{e}/competitions/{e}/odds"
NFLVERSE = {
    "inj": "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{s}.csv",
    "ros": "https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{s}.csv",
}
WX_URL = ("https://historical-forecast-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
          "&hourly=temperature_2m,precipitation,precipitation_probability,snowfall,wind_speed_10m,wind_gusts_10m,weather_code,is_day"
          "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=UTC&start_date={d0}&end_date={d1}")
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search?count=1&name={q}"


# ---------- HTTP with an on-disk cache ----------
def fetch(url, kind="json", fresh=False):
    """GET url, cached forever under cache/ (keyed by a hash of the url). kind: 'json' or 'text'."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:20] + (".json" if kind == "json" else ".txt"))
    if os.path.exists(path) and not fresh:
        with open(path, encoding="utf-8") as f:
            return json.load(f) if kind == "json" else f.read()
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bennys-picks-backtest", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            text = body.decode("utf-8")
            data = json.loads(text) if kind == "json" else text
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(path + ".tmp", path)
            time.sleep(0.15)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except Exception as e:  # network hiccup: back off and retry
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


# ---------- ports of index.html's data shaping ----------
def fix_abbr(a):
    return {"WSH": "WAS", "JAC": "JAX", "LA": "LAR", "OAK": "LV", "SD": "LAC", "STL": "LAR"}.get(a, a) if a else None


def js_round(x, n=0):
    """Number(x.toFixed(n)) / Math.round, half away from zero (close enough to JS for these values)."""
    k = 10 ** n
    return math.floor(abs(x) * k + 0.5) / k * (1 if x >= 0 else -1)


def name_of(r):
    p = r.get("player") or {}
    if p.get("position") == "DEF":
        return (TEAMS.get(fix_abbr(r.get("player_id"))) or [0, r.get("player_id")])[1] + " D/ST"
    return " ".join(x for x in [p.get("first_name"), p.get("last_name")] if x) or r.get("player_id")


def num(s, k):
    v = s.get(k)
    return v if isinstance(v, (int, float)) and v == v else 0


def compact_week(rows):
    P, Dd = [], []
    for r in rows or []:
        s, pos = r.get("stats") or {}, (r.get("player") or {}).get("position")
        if not (num(s, "gp") > 0):
            continue
        if pos == "DEF":
            T = fix_abbr(r.get("team") or r.get("player_id"))
            if T not in TEAMS:
                continue
            Dd.append([T, fix_abbr(r.get("opponent")), num(s, "fan_pts_allow_qb"), num(s, "fan_pts_allow_rb"), num(s, "fan_pts_allow_wr"),
                       num(s, "fan_pts_allow_te"), num(s, "fan_pts_allow_k"), num(s, "fan_pts_allow_def"), num(s, "sack"),
                       num(s, "pts_allow"), num(s, "yds_allow"), js_round(num(s, "pts_ppr"), 2)])
            continue
        if pos not in POS:
            continue
        P.append([r.get("player_id"), pos, fix_abbr(r.get("team")), fix_abbr(r.get("opponent")), js_round(num(s, "pts_ppr"), 2),
                  num(s, "pass_att"), num(s, "pass_yd"), num(s, "pass_sack"), num(s, "rush_att"), num(s, "rush_yd"),
                  num(s, "rec_tgt"), num(s, "rec_yd"), name_of(r), num(s, "rec")])
    return {"P": P, "D": Dd}


def blank_agg():
    return {"g": 0, "passAtt": 0, "sacksTaken": 0, "rushAtt": 0, "rushYd": 0, "tgt": {"RB": 0, "WR": 0, "TE": 0},
            "fpa": {"QB": 0, "RB": 0, "WR": 0, "TE": 0, "K": 0, "DEF": 0}, "sacks": 0, "ptsA": 0, "ydsA": 0,
            "passYdA": None, "rushAttA": None, "rushYdA": None, "ptsFor": None}


def derive(a):
    g = a["g"]
    if not g:
        return None
    plays = a["passAtt"] + a["rushAtt"] + a["sacksTaken"]
    tt = (a["tgt"]["RB"] + a["tgt"]["WR"] + a["tgt"]["TE"]) or 1
    return {"g": g, "passRate": (a["passAtt"] + a["sacksTaken"]) / plays if plays else None, "plays": plays / g,
            "ypc": a["rushYd"] / a["rushAtt"] if a["rushAtt"] else None, "sacksTaken": a["sacksTaken"] / g,
            "tsRB": a["tgt"]["RB"] / tt, "tsWR": a["tgt"]["WR"] / tt, "tsTE": a["tgt"]["TE"] / tt,
            "fpaQB": a["fpa"]["QB"] / g, "fpaRB": a["fpa"]["RB"] / g, "fpaWR": a["fpa"]["WR"] / g, "fpaTE": a["fpa"]["TE"] / g,
            "fpaK": a["fpa"]["K"] / g, "fpaDEF": a["fpa"]["DEF"] / g, "sacks": a["sacks"] / g, "ptsA": a["ptsA"] / g,
            "ydsA": a["ydsA"] / g, "passYdA": a["passYdA"] / g if a["passYdA"] is not None else None,
            "ypcA": a["rushYdA"] / a["rushAttA"] if a["rushAttA"] else None,
            "ptsFor": a["ptsFor"] / g if a["ptsFor"] is not None else None}


def derive_totals(rows, qb_weeks=None):
    A = {}
    ga = lambda T: A.setdefault(T, blank_agg())
    use_wk = bool(qb_weeks) and len([w for w in qb_weeks if w]) >= 10
    for r in rows or []:
        s, pos = r.get("stats") or {}, (r.get("player") or {}).get("position")
        T = fix_abbr(r.get("team") or (r.get("player_id") if pos == "DEF" else None))
        if T not in TEAMS:
            continue
        a = ga(T)
        if pos == "DEF":
            a["g"] = num(s, "gp")
            a["fpa"] = {"QB": num(s, "fan_pts_allow_qb"), "RB": num(s, "fan_pts_allow_rb"), "WR": num(s, "fan_pts_allow_wr"),
                        "TE": num(s, "fan_pts_allow_te"), "K": num(s, "fan_pts_allow_k"), "DEF": num(s, "fan_pts_allow_def")}
            a["sacks"], a["ptsA"], a["ydsA"] = num(s, "sack"), num(s, "pts_allow"), num(s, "yds_allow")
        elif pos in ("QB", "RB", "WR", "TE"):
            if not (use_wk and pos == "QB"):
                a["passAtt"] += num(s, "pass_att"); a["sacksTaken"] += num(s, "pass_sack")
                a["rushAtt"] += num(s, "rush_att"); a["rushYd"] += num(s, "rush_yd")
            if pos != "QB":
                a["tgt"][pos] += num(s, "rec_tgt")
    if use_wk:
        for wk in qb_weeks:
            for r in wk or []:
                s, T = r.get("stats") or {}, fix_abbr(r.get("team"))
                if T not in TEAMS or not (num(s, "gp") > 0):
                    continue
                a = ga(T)
                a["passAtt"] += num(s, "pass_att"); a["sacksTaken"] += num(s, "pass_sack")
                a["rushAtt"] += num(s, "rush_att"); a["rushYd"] += num(s, "rush_yd")
    out = {}
    for T, a in A.items():
        d = derive(a)
        if d:
            out[T] = d
    return out


def player_ppg(rows):
    out = {}
    for r in rows or []:
        s, pos = r.get("stats") or {}, (r.get("player") or {}).get("position")
        if pos not in POS or not (num(s, "gp") >= 2):
            continue
        ppg = num(s, "pts_ppr") / s["gp"]
        pid = fix_abbr(r.get("player_id")) if pos == "DEF" else r.get("player_id")
        if ppg >= 4 or pos == "DEF":
            out[pid] = [js_round(ppg, 1), s["gp"], js_round(num(s, "rec") / s["gp"], 2), fix_abbr(r.get("team"))]
    return out


def idp_impact(s):
    return [js_round(4 * num(s, "idp_sack") + num(s, "idp_qb_hit") + 2 * num(s, "idp_ff"), 1),
            js_round(5 * num(s, "idp_int") + 1.5 * num(s, "idp_pass_def"), 1),
            js_round(num(s, "idp_tkl_loss") + 0.1 * num(s, "idp_tkl"), 1)]


def ret_yds(s):
    return num(s, "kr_yd") + num(s, "pr_yd")


def pname(r):
    p = r.get("player") or {}
    return " ".join(x for x in [p.get("first_name"), p.get("last_name")] if x)


def idp_compact_prev(rows):
    out = []
    for r in rows or []:
        s, T = r.get("stats") or {}, fix_abbr(r.get("team"))
        if not (num(s, "gp") > 0) or T not in TEAMS:
            continue
        a, b, c = idp_impact(s)
        if a + b + c < 2 and ret_yds(s) < 150:
            continue
        out.append([r.get("player_id"), pname(r), (r.get("player") or {}).get("position") or "", T, s["gp"], a, b, c, ret_yds(s), num(s, "st_td")])
    return out


def returners_prev(rows):
    out = []
    for r in rows or []:
        s, T = r.get("stats") or {}, fix_abbr(r.get("team"))
        if not (num(s, "gp") > 0) or T not in TEAMS or ret_yds(s) < 150:
            continue
        out.append([r.get("player_id"), pname(r), T, s["gp"], ret_yds(s), num(s, "st_td")])
    return out


# ---------- nflverse injuries and weekly rosters ----------
_nv = {}


def nflverse(season):
    """{week: {sleeper id: (team, status, report status)}} for the season, plus name/position for each id."""
    if season in _nv:
        return _nv[season]
    with open(os.path.join(ROOT, "player-ids.json"), encoding="utf-8") as f:
        ids = json.load(f)["ids"]
    gsis2sl = {v[1]: k for k, v in ids.items() if v and v[1]}
    ros = {}
    text = fetch(NFLVERSE["ros"].format(s=season), "text")
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("game_type") not in ("REG", ""):
            continue
        sid = row.get("sleeper_id") or gsis2sl.get(row.get("gsis_id"))
        if not sid:
            continue
        if row.get("gsis_id"):
            gsis2sl.setdefault(row["gsis_id"], sid)
        w = int(row["week"])
        ros.setdefault(w, {})[sid] = [fix_abbr(row["team"]), row["status"], None]
    # a team on bye has no rows that week: carry its roster from the latest earlier week it played
    last = {}
    for w in sorted(ros):
        teams = {v[0] for v in ros[w].values()}
        for T, members in last.items():
            if T not in teams:
                for sid, v in members.items():
                    ros[w].setdefault(sid, v)
        cur = {}
        for sid, v in ros[w].items():
            cur.setdefault(v[0], {})[sid] = v
        last.update(cur)
    inj = {}
    try:
        text = fetch(NFLVERSE["inj"].format(s=season), "text")
        for row in csv.DictReader(io.StringIO(text)):
            if row.get("game_type") != "REG":
                continue
            st = (row.get("report_status") or "").strip()
            if st not in ("Out", "Doubtful", "Questionable"):
                continue
            sid = gsis2sl.get(row.get("gsis_id"))
            if sid:
                inj.setdefault(int(row["week"]), {})[sid] = st
    except urllib.error.HTTPError:
        pass
    _nv[season] = (ros, inj)
    return _nv[season]


def inj_kind(s):
    s = (s or "").lower()
    return "long" if re.match(r"(ir|pup|sus|na)", s) else "short" if re.match(r"(out|doubtful)", s) else None


def injury_of(season, week, sid, projected, has_history):
    """The injury designation the fixture gives a player (a stub: see the module notes)."""
    ros, inj = nflverse(season)
    rep = inj.get(week, {}).get(sid)
    if rep:
        return rep
    r = ros.get(week, {}).get(sid)
    if r and r[1] == "RES":
        return "IR"
    if not projected and has_history and r and r[1] == "INA":
        return "Out"
    return None


def roster_team(season, week, sid):
    r = nflverse(season)[0].get(week, {}).get(sid)
    return r[0] if r and r[1] in ("ACT", "RES", "INA") and r[0] in TEAMS else None


# ---------- ESPN games, lines and records ----------
def espn_week(season, week):
    return fetch(ESPN_SB.format(s=season, w=week))


def closing_line(eid):
    """ESPN's odds for a played game: the first provider's details ('KC -3.5') and total. These are closing lines."""
    try:
        j = fetch(ESPN_ODDS.format(e=eid))
    except urllib.error.HTTPError:
        return None, 0, None
    items = sorted(j.get("items") or [], key=lambda it: (it.get("provider") or {}).get("priority", 99))
    for it in items:
        ou = it.get("overUnder")
        ou = float(ou) if isinstance(ou, (int, float)) and ou > 0 else None
        m = re.match(r"^([A-Z]{2,4})\s*-(\d+(?:\.\d+)?)", it.get("details") or "")
        if ou or m:
            return (fix_abbr(m.group(1)) if m else None), (float(m.group(2)) if m else 0), ou
    return None, 0, None


def games_of(season, week):
    j = espn_week(season, week)
    games = []
    for e in j.get("events") or []:
        c = (e.get("competitions") or [None])[0]
        if not c:
            continue
        teams = [{"abbr": fix_abbr((t.get("team") or {}).get("abbreviation")), "home": t.get("homeAway") == "home"} for t in c.get("competitors") or []]
        h = next((t for t in teams if t["home"]), None)
        a = next((t for t in teams if not t["home"]), None)
        if not h or not a:
            continue
        fav, line, ou = closing_line(e["id"])
        v = c.get("venue") or {}
        ad = v.get("address") or {}
        venue = None
        if c.get("neutralSite") and v:
            venue = {"name": v.get("fullName") or "", "city": ", ".join(x for x in [ad.get("city"), ad.get("state") or ad.get("country")] if x),
                     "q": ad.get("city") or "", "roof": "dome" if v.get("indoor") else "open", "neutral": True}
        games.append({"id": e["id"], "date": e["date"], "home": h["abbr"], "away": a["abbr"], "state": "pre", "short": "",
                      "fav": fav, "line": line, "ou": ou, "venue": venue, "espnWx": None})
    return games


def records_before(season, week):
    """Each team's W-L(-T) from the final scores of weeks 1..week-1."""
    W = {}
    for w in range(1, week):
        for e in espn_week(season, w).get("events") or []:
            c = (e.get("competitions") or [None])[0]
            if not c or not ((c.get("status") or {}).get("type") or {}).get("completed"):
                continue
            cs = c.get("competitors") or []
            if len(cs) != 2:
                continue
            sc = [float(x.get("score") or 0) for x in cs]
            for i, x in enumerate(cs):
                T = fix_abbr((x.get("team") or {}).get("abbreviation"))
                r = W.setdefault(T, [0, 0, 0])
                r[0 if sc[i] > sc[1 - i] else 1 if sc[i] < sc[1 - i] else 2] += 1
    return {T: f"{r[0]}-{r[1]}" + (f"-{r[2]}" if r[2] else "") for T, r in W.items()}


# ---------- weather (fetchWeather, on the historical-forecast archive) ----------
def mean(a):
    return sum(a) / len(a) if a else None


def weather_of(games):
    spots = []
    for g in games:
        s = g["venue"] or ({"lat": STADIUMS[g["home"]][0], "lon": STADIUMS[g["home"]][1], "roof": STADIUMS[g["home"]][2]} if g["home"] in STADIUMS else None)
        if not s or s["roof"] != "open":
            continue
        lat, lon = s.get("lat"), s.get("lon")
        if s.get("neutral"):
            if not s.get("q"):
                continue
            r = (fetch(GEO_URL.format(q=urllib.request.quote(s["q"]))).get("results") or [None])[0]
            if not r:
                continue
            lat, lon = js_round(r["latitude"], 3), js_round(r["longitude"], 3)
        spots.append((g, lat, lon))
    out = {}
    if not spots:
        return out
    ts = [datetime.strptime(g["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) for g, _, _ in spots]
    d0, d1 = min(ts).strftime("%Y-%m-%d"), (max(ts) + timedelta(days=1)).strftime("%Y-%m-%d")
    j = fetch(WX_URL.format(lat=",".join(str(x[1]) for x in spots), lon=",".join(str(x[2]) for x in spots), d0=d0, d1=d1))
    allj = j if isinstance(j, list) else [j]
    for i, (g, _, _) in enumerate(spots):
        h = (allj[i] if i < len(allj) else {}).get("hourly") or {}
        if not h.get("time"):
            continue
        t0 = ts[i].replace(minute=0).strftime("%Y-%m-%dT%H:%M")
        if t0 not in h["time"]:
            continue
        i0 = h["time"].index(t0)
        span = [k for k in (i0, i0 + 1, i0 + 2) if k < len(h["time"])]
        vals = lambda k: [h[k][x] for x in span if h.get(k) and h[k][x] is not None]
        hi = lambda k: max(vals(k)) if vals(k) else None
        r1 = lambda x: js_round(x, 1) if x is not None else None
        snow = sum(vals("snowfall"))
        tm = mean(vals("temperature_2m"))
        out[g["id"]] = {"t": js_round(tm) if tm is not None else None, "wind": r1(mean(vals("wind_speed_10m"))), "gust": r1(hi("wind_gusts_10m")),
                        "snow": r1(snow), "rain": js_round(max(0, sum(vals("precipitation")) - snow / 10) * 100) / 100,
                        "prob": hi("precipitation_probability"), "code": (h.get("weather_code") or [None] * (i0 + 1))[i0],
                        "day": (h.get("is_day") or [None] * (i0 + 1))[i0]}
    return out


# ---------- one week's fixture ----------
def weekly_stats(season, week):
    return fetch(SLEEPER["wk"].format(s=season, w=week))


def build_week(season, week, cache):
    proj_rows = fetch(SLEEPER["proj"].format(s=season, w=week))
    weeks_raw = [weekly_stats(season, w) for w in range(1, week)]
    weeks = [compact_week(r) for r in weeks_raw]
    tot1 = cache.tot(season - 1)
    prev_ppg = player_ppg(tot1)
    # this season's games so far, per player: latest team, for players Sleeper didn't project this week
    hist_team, hist_n, names = {}, {}, {}
    for wk in weeks:
        for p in wk["P"]:
            hist_team[p[0]] = p[2]; hist_n[p[0]] = hist_n.get(p[0], 0) + 1; names[p[0]] = (p[12], p[1])
    sched_rows = cache.sched(season)
    opp_of = {}
    for w, h, a in sched_rows:
        if w == week:
            opp_of[h], opp_of[a] = a, h
    proj, seen = [], set()
    for r in proj_rows or []:
        p = r.get("player") or {}
        pos = p.get("position")
        if pos not in POS:
            continue
        pid = r.get("player_id")
        st = r.get("stats") or {}
        pts = st.get("pts_ppr")
        projected = isinstance(pts, (int, float))
        has_hist = pid in hist_n or pid in prev_ppg
        if not projected and not has_hist:
            continue
        if projected:
            team = fix_abbr(r.get("team"))          # the row's team is that week's when there is a projection
            opp = fix_abbr(r.get("opponent"))
        else:
            # no projection: the row's team is today's, so take his team that week from nflverse's weekly rosters (none
            # when he was cut or on a practice squad), or his last game's team if nflverse has no rosters for the week
            if pos == "DEF":
                team = fix_abbr(pid)
            elif nflverse(season)[0].get(week):
                team = roster_team(season, week, pid)
            else:
                team = hist_team.get(pid)
            opp = opp_of.get(team)
        if pos == "DEF":
            inj = None
        else:
            inj = injury_of(season, week, pid, projected, has_hist)
        if not ((pts or 0) > 0 or pid in hist_n or pid in prev_ppg):
            continue                                # as the export trims proj
        seen.add(pid)
        proj.append([pid, name_of(r), pos, team, inj, pts if projected else None, opp, st.get("rec") or 0])
    # players with games this season whom Sleeper's file doesn't list at all this week
    for pid, (nm, pos) in names.items():
        if pid in seen:
            continue
        team = roster_team(season, week, pid) if nflverse(season)[0].get(week) else hist_team.get(pid)
        inj = injury_of(season, week, pid, False, True)
        proj.append([pid, nm, pos, team, inj, None, opp_of.get(team), 0])
    games = games_of(season, week)
    first_kick = min(datetime.strptime(g["date"], "%Y-%m-%dT%H:%MZ") for g in games)
    created = (first_kick - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:00.000Z")
    # injury log: the first week of the current run of the same kind of designation
    log = {}
    for row in proj:
        k = inj_kind(row[4])
        if not k:
            continue
        first = week
        for w in range(week - 1, 0, -1):
            prev = injury_of(season, w, row[0], True, True)
            if inj_kind(prev) == k:
                first = w
            else:
                break
        log[row[0]] = [row[4], season, first, created[:10]]
    fixture = {
        "v": 1, "createdAt": created, "fresh": None, "season": season, "week": week, "detSeason": season, "detWeek": week,
        "games": games, "rec": records_before(season, week), "proj": proj, "weeks": weeks, "actual": {"P": [], "D": []},
        "priors": [[season - k, cache.prior(season - k, k == 1)] for k in (1, 2, 3)], "sched": sched_rows, "own": [],
        "prevPPG": prev_ppg, "wx": weather_of(games), "idp": cache.idp(season, week), "injLog": log,
    }
    return fixture


def actuals_of(season, week):
    """That week's results, for scoring only: PPR points and usage per player who played, and D/ST points."""
    rows = weekly_stats(season, week)
    P, Dd = {}, {}
    for r in rows or []:
        s, pos = r.get("stats") or {}, (r.get("player") or {}).get("position")
        if not (num(s, "gp") > 0):
            continue
        if pos == "DEF":
            T = fix_abbr(r.get("team") or r.get("player_id"))
            if T in TEAMS:
                Dd[T] = js_round(num(s, "pts_ppr"), 2)
            continue
        if pos not in POS:
            continue
        P[r["player_id"]] = [js_round(num(s, "pts_ppr"), 2), pos, fix_abbr(r.get("team")), fix_abbr(r.get("opponent")),
                             num(s, "rec_tgt"), num(s, "rush_att"), num(s, "off_snp"), num(s, "tm_off_snp"), num(s, "rec"),
                             num(s, "pass_att"), num(s, "rush_yd"), num(s, "rec_yd"), num(s, "pass_yd"), num(s, "gp")]
    return {"season": season, "week": week, "P": P, "D": Dd,
            "cols": ["pts_ppr", "pos", "team", "opp", "tgt", "rush_att", "off_snp", "tm_off_snp", "rec", "pass_att", "rush_yd", "rec_yd", "pass_yd", "gp"]}


class Cache:
    """Season-level inputs, built once."""
    def __init__(self):
        self._tot, self._prior, self._sched, self._idpw = {}, {}, {}, {}

    def tot(self, s):
        if s not in self._tot:
            self._tot[s] = fetch(SLEEPER["tot"].format(s=s))
        return self._tot[s]

    def prior(self, s, with_qb):
        key = (s, with_qb)
        if key not in self._prior:
            qb = [fetch(SLEEPER["wkQB"].format(s=s, w=w)) for w in range(1, 19)] if with_qb else None
            self._prior[key] = derive_totals(self.tot(s), qb)
        return self._prior[key]

    def sched(self, s):
        if s not in self._sched:
            rows = fetch(SLEEPER["sched"].format(s=s))
            self._sched[s] = [[g["week"], fix_abbr(g["home"]), fix_abbr(g["away"])] for g in rows or [] if g.get("week") and g.get("home") and g.get("away")]
        return self._sched[s]

    def idp_week(self, s, w):
        if (s, w) not in self._idpw:
            self._idpw[(s, w)] = fetch(SLEEPER["idpwk"].format(s=s, w=w))
        return self._idpw[(s, w)]

    def idp(self, season, week):
        prev_rows = fetch(SLEEPER["idp"].format(s=season - 1))
        prev = idp_compact_prev(prev_rows)
        ret = returners_prev(self.tot(season - 1))
        known = {p[0] for p in prev}
        agg = {}
        for w in range(1, week):
            for r in self.idp_week(season, w) or []:
                s = r.get("stats") or {}
                if not (num(s, "gp") > 0):
                    continue
                a = agg.setdefault(r["player_id"], {"stats": {}, "name": pname(r), "pos": (r.get("player") or {}).get("position") or "", "team": None})
                for k in ("gp", "idp_sack", "idp_qb_hit", "idp_ff", "idp_int", "idp_pass_def", "idp_tkl_loss", "idp_tkl"):
                    a["stats"][k] = a["stats"].get(k, 0) + num(s, k)
                a["team"] = fix_abbr(r.get("team")) or a["team"]
        now = []
        prev_by = {p[0]: p for p in prev}
        for pid in set(agg) | known:
            a = agg.get(pid)
            team_now = roster_team(season, week, pid)
            if team_now is None and a and not nflverse(season)[0].get(week):
                team_now = a["team"]                  # no nflverse roster for the week: his latest game's team
            inj = injury_of(season, week, pid, True, True)
            s = a["stats"] if a else {}
            x, y, z = idp_impact(s)
            p = prev_by.get(pid)
            now.append([pid, a["name"] if a else p[1], a["pos"] if a else p[2], team_now if team_now in TEAMS else None, inj,
                        int(s.get("gp", 0)), x, y, z, a["team"] if a else None])
        now.sort(key=lambda r: r[0])
        return {"prev": prev, "now": now, "ret": ret}


# ---------- synthetic league: draft three rosters from week-1 projections ----------
DRAFT_CAPS = {"QB": 2, "RB": 6, "WR": 6, "TE": 2, "K": 1, "DEF": 1}
NEED = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}
REPL_RANK = {"QB": 13, "RB": 30, "WR": 36, "TE": 13, "K": 12, "DEF": 12}


def draft(season, teams=12, rounds=16):
    """A plain value-over-replacement snake draft on Sleeper's week-1 projections (pregame information) blended with
    last season's per-game scoring. Kickers and D/STs go in the last two rounds. Returns each team's list of ids."""
    rows = fetch(SLEEPER["proj"].format(s=season, w=1))
    prev = player_ppg(Cache().tot(season - 1))
    val = {}
    for r in rows:
        p, st = r.get("player") or {}, r.get("stats") or {}
        pos = p.get("position")
        if pos not in POS or not isinstance(st.get("pts_ppr"), (int, float)) or st["pts_ppr"] <= 0:
            continue
        pid = r["player_id"]
        v = st["pts_ppr"]
        if pid in prev and pos not in ("K", "DEF"):
            v = 0.6 * v + 0.4 * prev[pid][0]
        val[pid] = (pos, v, name_of(r))
    repl = {}
    for P in POS:
        vs = sorted((v for pos, v, _ in val.values() if pos == P), reverse=True)
        repl[P] = vs[min(REPL_RANK[P], len(vs)) - 1] if vs else 0
    avail = sorted(val, key=lambda i: -(val[i][1] - repl[val[i][0]]))
    rosters = [[] for _ in range(teams)]
    for rd in range(rounds):
        order = range(teams) if rd % 2 == 0 else reversed(range(teams))
        for t in order:
            have = {}
            for i in rosters[t]:
                have[val[i][0]] = have.get(val[i][0], 0) + 1
            left = rounds - rd
            missing = [P for P in NEED if have.get(P, 0) < NEED[P]]
            pick = None
            for i in avail:
                P = val[i][0]
                if have.get(P, 0) >= DRAFT_CAPS[P]:
                    continue
                if P in ("K", "DEF") and rd < rounds - 2:
                    continue
                if len(missing) >= left and P not in missing:
                    continue
                pick = i
                break
            avail.remove(pick)
            rosters[t].append(pick)
    return [[(i, val[i][0], val[i][2]) for i in r] for r in rosters]


def parse_weeks(spec):
    out = []
    for part in spec.split(","):
        s, rng = part.split(":")
        a, b = (rng.split("-") + [rng])[:2]
        out += [(int(s), w) for w in range(int(a), int(b) + 1)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--weeks", default="2025:2-18,2026:1-4")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    args = ap.parse_args()
    fdir, adir = os.path.join(args.out, "fixtures"), os.path.join(args.out, "actuals")
    os.makedirs(fdir, exist_ok=True); os.makedirs(adir, exist_ok=True)
    cache = Cache()
    todo = parse_weeks(args.weeks)
    seasons = sorted({s for s, _ in todo})
    rosters = {}
    for s in seasons:
        teams = draft(s)
        # every team of the 12-team draft, lettered B-M by draft slot (A is the reviewer's roster, in replay.py)
        rosters[str(s)] = {chr(ord("B") + i): t for i, t in enumerate(teams)}
    with open(os.path.join(args.out, "rosters.json"), "w", encoding="utf-8") as f:
        json.dump(rosters, f, indent=1)
    for s, w in todo:
        t0 = time.time()
        fx = build_week(s, w, cache)
        name = "%d-w%02d.json" % (s, w)
        with open(os.path.join(fdir, name), "w", encoding="utf-8") as f:
            json.dump(fx, f, separators=(",", ":"))
        # results for this week and the next four, so rest-of-season and waiver windows can be scored
        for w2 in range(w, min(18, w + 4) + 1):
            ap_ = os.path.join(adir, "%d-w%02d.json" % (s, w2))
            if os.path.exists(ap_):
                continue
            try:
                act = actuals_of(s, w2)
            except Exception as e:
                print(f"  no results for {s} week {w2}: {e}")
                continue
            if act["P"]:
                with open(ap_, "w", encoding="utf-8") as f:
                    json.dump(act, f, separators=(",", ":"))
        lines = sum(1 for g in fx["games"] if g["ou"])
        print(f"{name}: {len(fx['proj'])} players, {len(fx['games'])} games ({lines} with lines), {len(fx['wx'])} forecasts, "
              f"{sum(1 for p in fx['proj'] if p[4])} injury tags, {len(fx['idp']['now'])} defenders  [{time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
