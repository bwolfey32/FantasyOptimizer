"""Build player-ids.json: each Sleeper player's ESPN and NFL GSIS ids, which the site uses for player headshots.
Also builds share-players.json next to it, for share.bennyspicks.us (share/ in this repo), which draws a shared move's
card from player ids alone.

Usage: python3 scripts/player_ids.py [player-ids.json] [--force]      (run by .github/workflows/refresh-data.yml)

Sleeper's player file (about 15 MB) carries an ESPN id for most players but not all; recent draft classes are often
missing one. Those are filled from ESPN's own player list, matched on name and position, and on team when two players
share a name. Sleeper asks that its player file be fetched at most once a day, so a map less than 20 hours old is kept.

Output: {"updated": ISO time, "ids": {sleeper id: [espn id or null, gsis id or null]}}, and share-players.json:
{"updated": ISO time, "p": {sleeper id: [name, position, team or null, espn id or null]}}. D/STs aren't listed in either:
both show team logos for them.
"""
import gzip
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone

SLEEPER_URL = "https://api.sleeper.app/v1/players/nfl"
ESPN_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/players?view=players_wl"
ESPN_FILTER = json.dumps({"players": {"limit": 20000}})
POSITIONS = {"QB", "RB", "WR", "TE", "K"}
ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K"}
# ESPN team ids, as in TEAMS in index.html
ESPN_TEAM = {22: "ARI", 1: "ATL", 33: "BAL", 2: "BUF", 29: "CAR", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
             8: "DET", 9: "GB", 34: "HOU", 11: "IND", 30: "JAX", 12: "KC", 13: "LV", 24: "LAC", 14: "LAR", 15: "MIA",
             16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 23: "PIT", 25: "SF", 26: "SEA", 27: "TB",
             10: "TEN", 28: "WAS"}
FIX_ABBR = {"WSH": "WAS", "JAC": "JAX", "LA": "LAR", "OAK": "LV", "SD": "LAC", "STL": "LAR"}   # fixAbbr in index.html
MAX_AGE_HOURS = 20


def norm(name):
    """Same as norm in index.html: lowercase, no accents, punctuation or suffixes."""
    s = unicodedata.normalize("NFD", str(name or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[.'’,-]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_json(url, headers=None, timeout=120):
    req = urllib.request.Request(url, headers=dict({"Accept-Encoding": "gzip", "User-Agent": "bennyspicks.us"}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return json.loads(body)


def build(sleeper, espn):
    # ESPN's players by normalized name and position: [(espn id, team)]
    by_name, name_of = {}, {}
    for p in espn:
        pos = ESPN_POS.get(p.get("defaultPositionId"))
        if pos and p.get("id") and p.get("fullName"):
            by_name.setdefault((norm(p["fullName"]), pos), []).append((int(p["id"]), ESPN_TEAM.get(p.get("proTeamId"))))
            name_of[int(p["id"])] = norm(p["fullName"])
    players = [p for p in sleeper.values() if p.get("position") in POSITIONS and (p.get("team") or p.get("active"))]
    full = lambda p: norm(p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}")
    sleeper_espn = lambda p: int(p["espn_id"]) if str(p.get("espn_id") or "").isdigit() else None

    def by_exact_name(p, taken):
        """The one ESPN player with this name and position (on the same team, if several), or None."""
        team = FIX_ABBR.get(p.get("team"), p.get("team"))
        cands = [c for c in by_name.get((full(p), p["position"]), []) if c[0] not in taken]
        same_team = [c for c in cands if team and c[1] == team]
        pick = same_team if len(same_team) == 1 else cands if len(cands) == 1 else []
        return pick[0][0] if pick else None

    # Sleeper's ESPN id first. Where a player on a team has one naming a different ESPN player (Sleeper has had two
    # players' ids swapped) and ESPN has exactly one player with his name, that one wins; a nickname ("Hollywood"
    # Brown) has no such match.
    resolved, matched = {}, 0
    for p in players:
        s = sleeper_espn(p)
        if p.get("team") and s is not None and s in name_of and name_of[s] != full(p):
            exact = by_exact_name(p, set())
            if exact is not None:
                s, matched = exact, matched + 1
        resolved[p["player_id"]] = s
    # then players Sleeper has no ESPN id for, by name, skipping ESPN ids another player already has
    claimed = {v for v in resolved.values() if v is not None}
    for p in players:
        if resolved[p["player_id"]] is None:
            exact = by_exact_name(p, claimed)
            if exact is not None:
                resolved[p["player_id"]] = exact
                claimed.add(exact)
                matched += 1
    ids, share = {}, {}
    for p in players:
        espn_id, gsis = resolved[p["player_id"]], (p.get("gsis_id") or "").strip() or None
        if espn_id or gsis:
            ids[str(p["player_id"])] = [espn_id, gsis]
        name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        if name:
            share[str(p["player_id"])] = [name, p["position"], FIX_ABBR.get(p.get("team"), p.get("team")) or None, espn_id]
    return ids, share, matched, len(players)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out_path = args[0] if args else "player-ids.json"
    share_path = os.path.join(os.path.dirname(out_path), "share-players.json")
    try:
        with open(out_path, encoding="utf-8") as f:
            old = json.load(f)
        age = time.time() - datetime.fromisoformat(old["updated"].replace("Z", "+00:00")).timestamp()
        if "--force" not in sys.argv and age < MAX_AGE_HOURS * 3600 and os.path.exists(share_path):
            print(f"Player ids are {age / 3600:.1f} hours old; keeping them (Sleeper asks for one players fetch a day).")
            return
    except (OSError, ValueError, KeyError):
        pass
    sleeper = fetch_json(SLEEPER_URL)
    if len(sleeper) < 5000:
        sys.exit(f"Sleeper's player file looks incomplete ({len(sleeper)} players); keeping the old map.")
    season = datetime.now(timezone.utc).year if datetime.now(timezone.utc).month >= 3 else datetime.now(timezone.utc).year - 1
    try:
        espn = fetch_json(ESPN_URL.format(season=season), {"x-fantasy-filter": ESPN_FILTER})
    except Exception as e:   # Sleeper's own ESPN ids still cover most players
        print(f"Warning: ESPN's player list didn't load ({e}); using Sleeper's ESPN ids only.")
        espn = []
    ids, share, matched, n = build(sleeper, espn)
    with_espn = sum(1 for v in ids.values() if v[0])
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"updated": updated, "ids": dict(sorted(ids.items()))}, f, separators=(",", ":"))
    with open(share_path, "w", encoding="utf-8") as f:
        json.dump({"updated": updated, "p": dict(sorted(share.items()))}, f, separators=(",", ":"), ensure_ascii=False)
    print(f"Saved {len(ids)} players to {os.path.basename(out_path)}: {with_espn} of {n} with an ESPN id "
          f"({matched} matched by name from ESPN's list).")


if __name__ == "__main__":
    main()
