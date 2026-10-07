"""Player news for the player pages' News tab and Research → News: what changed for each player since the last run,
written by Benny from its own data, plus ESPN headlines that name a player (headline and link only, never the story).

Usage: python scripts/news.py [--snapshot snapshot.json] [--out news] [--offline]

Run by .github/workflows/refresh-data.yml every 3 hours, after snapshot.json and player-ids.json are built. Sources:
  injury   a status change on Sleeper's projection rows (snapshot.json proj, index 4): "listed Out", "off the report"
  team     a team change in share-players.json (player_ids.py, refreshed about daily): signed, released, joined
  depth    a skill player moving onto or off the top of his team's depth chart (nflverse's daily depth charts)
  trend    Sleeper's most-added players in the last 24 hours (a list in the feed, and an item when one enters the top 10)
  article  ESPN's NFL news, kept when it tags a player Benny knows: headline, time and link
Every source compares with the last run (news/state.json). A source's first run only records what it sees, so the feed
starts empty instead of announcing every injury already on the report. Slow sources (depth charts, trending) run at most
every 20 hours.

news/feed.json: {"v": 1, "updated", "items": [...14 days, newest first, at most 400], "trend": {"add": [[id, count]],
  "drop": [...], "at"}}
news/players/<sleeperId>.json: {"v": 1, "id", "items": [...his last 50, any age]}
An item: {"id", "t", "k", "ids", "names", "title", "sub", "src", "url", "note"}. id is stable (an item is never written
twice); k is injury | team | depth | trend | article; note is left null for a later "what it means" line.
"""
import argparse
import gzip
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ESPN_NEWS = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=50"
TRENDING = "https://api.sleeper.app/v1/players/nfl/trending/{kind}?lookback_hours=24&limit=25"
SLOW_HOURS = 20          # depth charts and trending: Sleeper asks for gentle use, and charts change about daily
FEED_DAYS, FEED_MAX, PLAYER_MAX, SEEN_MAX = 14, 400, 50, 4000
REL = 2.0                # a player matters once he's projected (or scored last season) this many points a game
SKILL = {"QB", "RB", "WR", "TE"}
STARTER = {"QB": 1, "RB": 1, "TE": 1, "WR": 3}   # the depth-chart spots that count as a starter
INJ_LABEL = {"IR": "on injured reserve", "PUP": "on the PUP list", "NA": "inactive", "Sus": "suspended",
             "COV": "on the COVID list", "DNR": "not reporting"}
SRC = "Benny's Picks"


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def item(k, iid, t, players, title, sub=None, src=SRC, url=None):
    """One feed item; players is [(sleeper id, name)]."""
    return {"id": iid, "t": t, "k": k, "ids": [p[0] for p in players], "names": [p[1] for p in players],
            "title": title, "sub": sub, "src": src, "url": url, "note": None}


def inj_text(s):
    return INJ_LABEL.get(s, s)


def relevance(st, rows, prev_ppg):
    """How much each player matters: the most he has been projected, or scored a game last season, as remembered."""
    rel = dict(st.get("rel", {}))
    for sid, v in (prev_ppg or {}).items():
        if v and isinstance(v[0], (int, float)):
            rel[sid] = max(rel.get(sid, 0), float(v[0]))
    for r in rows:
        if isinstance(r[5], (int, float)):
            rel[r[0]] = max(rel.get(r[0], 0), float(r[5]))
    return {k: round(v, 1) for k, v in rel.items() if v >= 1}


def injury_events(st, rows, rel, now):
    """A status change for a player on this week's projections. Players who drop off the projections keep their last
    status, so a waived player isn't reported healthy. The state keeps only tagged players (inj) and everyone seen
    (inj_seen), so a healthy player newly tagged is news but a player seen for the first time isn't."""
    t, day, out = iso(now), now.strftime("%Y-%m-%d"), []
    seed = "inj" not in st
    prev, known = st.get("inj", {}), set(st.get("inj_seen", []))
    for r in rows:
        sid, name, s = r[0], r[1], r[4] or None
        was = prev.get(sid)
        if seed or sid not in known or was == s or rel.get(sid, 0) < REL:
            continue
        if s is None:
            out.append(item("injury", f"inj-{sid}-ok-{day}", t, [(sid, name)], f"{name} off the injury report", f"was {inj_text(was)}"))
        else:
            out.append(item("injury", f"inj-{sid}-{s}-{day}", t, [(sid, name)], f"{name} {'listed' if s in ('Questionable', 'Doubtful', 'Out') else 'now'} {inj_text(s)}",
                            f"was {inj_text(was)}" if was else "new on the injury report"))
    cur = dict(prev)
    for r in rows:
        cur[r[0]] = r[4] or None
    st["inj"] = {k: v for k, v in cur.items() if v}
    st["inj_seen"] = sorted(known | {r[0] for r in rows})
    return out


def team_events(st, share, rel, now):
    """A team change in Sleeper's player file for anyone who matters."""
    t, day, out = iso(now), now.strftime("%Y-%m-%d"), []
    seed = "team" not in st
    prev = st.get("team", {})
    cur = {}
    for sid, v in share.items():
        if v[1] not in SKILL and v[1] != "K":
            continue
        cur[sid] = v[2]
        if seed or sid not in prev or prev[sid] == v[2] or rel.get(sid, 0) < REL:
            continue
        a, b, name = prev[sid], v[2], v[0]
        if a and b:
            title, sub = f"{name} joins {b}", f"from {a}"
        elif b:
            title, sub = f"{name} signs with {b}", "was a free agent"
        else:
            title, sub = f"{name} is a free agent", f"no longer on {a}'s roster"
        out.append(item("team", f"team-{sid}-{b or 'FA'}-{day}", t, [(sid, name)], title, sub))
    st["team"] = cur
    return out


def depth_chart(frame, gsis2sid, espn2sid=None):
    """The newest daily chart: {sleeper id: [team, pos, rank]} for QBs, RBs, WRs and TEs (his best rank if he's listed
    in several formations). Players are matched on the chart's ESPN id, then its gsis id."""
    d = frame[frame.pos_abb.isin(list(SKILL))].dropna(subset=["gsis_id"])
    if d.empty:
        return {}
    d = d[d.dt == d.dt.max()]
    out = {}
    espn = d.espn_id if "espn_id" in d else [None] * len(d)
    for e, g, team, pos, rk in zip(espn, d.gsis_id, d.team, d.pos_abb, d.pos_rank):
        sid = (espn2sid or {}).get(str(int(e)) if isinstance(e, (int, float)) and e == e else str(e or "")) or gsis2sid.get(g)
        if not sid:
            continue
        rk = int(rk)
        if sid not in out or rk < out[sid][2]:
            out[sid] = [team, pos, rk]
    return out


def depth_events(st, chart, names, rel, now):
    """A move onto or off his team's starting spots (QB1, RB1, TE1, the top three WRs). A team change is the team
    source's news, so it only updates the record here."""
    t, day, out = iso(now), now.strftime("%Y-%m-%d"), []
    seed = "depth" not in st
    prev = st.get("depth", {})
    for sid, (team, pos, rk) in chart.items():
        p = prev.get(sid)
        if seed or not p or p[0] != team or p[1] != pos or rel.get(sid, 0) < REL and rk > STARTER[pos]:
            continue
        was_s, now_s = p[2] <= STARTER[pos], rk <= STARTER[pos]
        if was_s == now_s:
            continue
        name = names.get(sid, sid)
        title = f"{name} moves up to {pos}{rk} on {team}'s depth chart" if now_s else f"{name} drops to {pos}{rk} on {team}'s depth chart"
        out.append(item("depth", f"depth-{sid}-{pos}{rk}-{day}", t, [(sid, name)], title, f"was {pos}{p[2]}"))
    st["depth"] = {**prev, **chart}
    return out


def trend_events(st, adds, names, now):
    """A player entering the top 10 of Sleeper's adds."""
    t, day = iso(now), now.strftime("%Y-%m-%d")
    top = [a[0] for a in adds[:10]]
    seed = "trend_top" not in st
    prev = set(st.get("trend_top", []))
    st["trend_top"] = top
    if seed:
        return []
    out = []
    for sid, n in adds[:10]:
        if sid in prev:
            continue
        name = names.get(sid, sid)
        out.append(item("trend", f"trend-{sid}-{day}", t, [(sid, name)], f"{name} is one of the most-added players",
                        f"added in {n:,} Sleeper leagues in the last 24 hours"))
    return out


ROUNDUP = 4   # an article tagging more players than this is a roundup: it goes to the players its headline names


def named(headline, name):
    """Whether a headline names him: his last name (or full name) as a word."""
    h = f" {headline.lower()} ".replace("'s ", " ").replace("’s ", " ")
    parts = [x for x in name.lower().replace(".", "").split() if x not in ("jr", "sr", "ii", "iii", "iv")]
    return bool(parts) and (f" {' '.join(parts)} " in h or f" {parts[-1]} " in h)


def article_items(articles, espn2sid, names):
    """ESPN headlines that tag a player Benny knows: headline, time and link; the story stays on ESPN. A roundup that
    tags many players is kept for the players its headline names, or for none (it still shows in the feed)."""
    out = []
    for a in articles:
        ids = []
        for c in a.get("categories") or []:
            if c.get("type") != "athlete":
                continue
            sid = espn2sid.get(str(c.get("athleteId") or (c.get("athlete") or {}).get("id") or ""))
            if sid and sid not in ids:
                ids.append(sid)
        url = ((a.get("links") or {}).get("web") or {}).get("href")
        if not ids or not a.get("headline") or not url or a.get("premium"):
            continue
        if len(ids) > ROUNDUP:
            ids = [s for s in ids if named(a["headline"], names.get(s, ""))]
        t = a.get("published") or a.get("lastModified")
        try:
            t = iso(datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc))
        except (AttributeError, ValueError):
            continue
        out.append(item("article", f"espn-{a.get('id')}", t, [(s, names.get(s, s)) for s in ids], a["headline"].strip(), None, "ESPN", url))
    return out


def merge(old, new, now, days=FEED_DAYS, cap=FEED_MAX):
    """The feed: new items added once (by id), the last `days`, newest first, at most `cap`."""
    have = {i["id"] for i in old}
    items = old + [i for i in new if i["id"] not in have]
    cut = iso(now - timedelta(days=days))
    items = [i for i in items if i["t"] >= cut]
    items.sort(key=lambda i: (i["t"], i["id"]), reverse=True)
    return items[:cap]


def player_items(old, new, cap=PLAYER_MAX):
    have = {i["id"] for i in old}
    items = old + [i for i in new if i["id"] not in have]
    items.sort(key=lambda i: (i["t"], i["id"]), reverse=True)
    return items[:cap]


def fresh(new, seen):
    """Drop items already written in an earlier run (an id can come back after it leaves the 14-day feed)."""
    out, s = [], set(seen)
    for i in new:
        if i["id"] not in s:
            out.append(i)
            s.add(i["id"])
    return out


def slow_due(st, key, now):
    at = st.get("slow", {}).get(key)
    if not at:
        return True
    return (now - datetime.fromisoformat(at.replace("Z", "+00:00"))).total_seconds() >= SLOW_HOURS * 3600


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "bennyspicks.us"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return json.loads(body)


def read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write(path, obj):
    """Write JSON only when it changed; returns whether it did."""
    text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def warn(msg):
    print(f"WARNING news: {msg}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=os.path.join(ROOT, "snapshot.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "news"))
    ap.add_argument("--offline", action="store_true", help="skip ESPN, Sleeper and nflverse (snapshot and team changes only)")
    a = ap.parse_args()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    snap = read(a.snapshot)
    if not snap or not snap.get("proj"):
        sys.exit("news: no snapshot to read")
    share = (read(os.path.join(ROOT, "share-players.json"), {}) or {}).get("p", {})
    pids = (read(os.path.join(ROOT, "player-ids.json"), {}) or {}).get("ids", {})
    st_path = os.path.join(a.out, "state.json")
    st = read(st_path, {}) or {}
    feed = read(os.path.join(a.out, "feed.json"), {}) or {}

    names = {sid: v[0] for sid, v in share.items()}
    names.update({r[0]: r[1] for r in snap["proj"]})
    rel = relevance(st, snap["proj"], snap.get("prevPPG"))
    st["rel"] = rel

    new = injury_events(st, snap["proj"], rel, now)
    if share:
        new += team_events(st, share, rel, now)
    trend = feed.get("trend")
    espn2sid = {str(v[0]): sid for sid, v in pids.items() if v[0]}
    if not a.offline:
        st.setdefault("slow", {})
        if slow_due(st, "depth", now):
            try:
                sys.path.insert(0, os.path.join(ROOT, "scripts", "model"))
                import nflverse as nv
                gsis2sid = {v[1]: sid for sid, v in pids.items() if v[1]}
                chart = depth_chart(nv.frame("depth_charts_{s}.csv", int(snap["season"]), 12), gsis2sid, espn2sid)
                if chart:
                    new += depth_events(st, chart, names, rel, now)
                    st["slow"]["depth"] = iso(now)
            except Exception as e:  # noqa: BLE001 (a moved or reshaped file: skip this source this run)
                warn(f"depth charts skipped ({e.__class__.__name__}: {e})")
        if slow_due(st, "trend", now):
            try:
                adds = [(x["player_id"], int(x["count"])) for x in fetch_json(TRENDING.format(kind="add"))]
                drops = [(x["player_id"], int(x["count"])) for x in fetch_json(TRENDING.format(kind="drop"))]
                new += trend_events(st, adds, names, now)
                trend = {"add": [list(x) for x in adds], "drop": [list(x) for x in drops], "at": iso(now)}
                st["slow"]["trend"] = iso(now)
            except Exception as e:  # noqa: BLE001
                warn(f"Sleeper trending skipped ({e.__class__.__name__}: {e})")
        try:
            arts = article_items(fetch_json(ESPN_NEWS).get("articles", []), espn2sid, names)
            # the first run takes the headlines as they are (they're news either way); later runs add the new ones
            new += arts
        except Exception as e:  # noqa: BLE001
            warn(f"ESPN headlines skipped ({e.__class__.__name__}: {e})")

    new = fresh(new, st.get("seen", []))
    st["seen"] = (st.get("seen", []) + [i["id"] for i in new])[-SEEN_MAX:]
    items = merge(feed.get("items", []), new, now)
    changed = write(os.path.join(a.out, "feed.json"), {"v": 1, "updated": iso(now), "items": items, "trend": trend or {"add": [], "drop": [], "at": None}})

    by_player = {}
    for i in new:
        for sid in i["ids"]:
            by_player.setdefault(sid, []).append(i)
    for sid, its in by_player.items():
        p = os.path.join(a.out, "players", f"{sid}.json")
        old = (read(p, {}) or {}).get("items", [])
        write(p, {"v": 1, "id": sid, "items": player_items(old, its)})
    write(st_path, st)
    kinds = {}
    for i in new:
        kinds[i["k"]] = kinds.get(i["k"], 0) + 1
    print(f"news: {len(new)} new item(s) {kinds or ''}; feed {len(items)} item(s), {len(by_player)} player file(s) updated{'' if changed else ' (feed unchanged)'}")


if __name__ == "__main__":
    main()
