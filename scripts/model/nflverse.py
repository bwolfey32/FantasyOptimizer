"""Download and cache nflverse's public data (and DynastyProcess's player id crosswalk), shared by scripts/model/ and
scripts/backtest/fit_nflverse.py.

Every file is downloaded once into scripts/backtest/cache/nflverse/ and read from there afterwards. A season still being
played changes every week, so its files are refreshed when they are older than `max_age` hours (the past seasons never
change).
"""
import csv
import os
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE = os.path.join(ROOT, "scripts", "backtest", "cache", "nflverse")
BASE = "https://github.com/nflverse/nflverse-data/releases/download"
DP_IDS = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"

# name in the cache -> url; {s} is the season
FILES = {
    "stats_{s}.csv": BASE + "/stats_player/stats_player_week_{s}.csv",
    "snap_counts_{s}.csv": BASE + "/snap_counts/snap_counts_{s}.csv",
    "injuries_{s}.csv": BASE + "/injuries/injuries_{s}.csv",
    "roster_weekly_{s}.csv": BASE + "/weekly_rosters/roster_weekly_{s}.csv",
    "depth_charts_{s}.csv": BASE + "/depth_charts/depth_charts_{s}.csv",
    "games.csv": BASE + "/schedules/games.csv",
    "players.csv": BASE + "/players/players.csv",
    "db_playerids.csv": DP_IDS,
}


# other addresses for a file, tried in order when its FILES address fails: nflverse moves release files now and then
# (the schedule's release copy went missing in October 2026; nfldata keeps the same file)
MIRRORS = {
    "games.csv": ["https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"],
}


def path(name, url, max_age=None):
    """The cached file's path, downloading it first if it's missing (or older than max_age hours). Each address is
    tried in turn (url, then MIRRORS); when none answers, an older cached copy is kept, with a warning on stderr, and
    only a file never downloaded raises."""
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, name)
    stale = max_age is not None and os.path.exists(p) and time.time() - os.path.getmtime(p) > max_age * 3600
    if not os.path.exists(p) or stale:
        tmp, err = p + ".part", None
        for u in [url, *MIRRORS.get(name, [])]:
            try:
                urllib.request.urlretrieve(u, tmp)
                os.replace(tmp, p)
                return p
            except Exception as e:  # noqa: BLE001 (a moved file, a network error: try the next address)
                err = e
                print(f"nflverse: {name} from {u} failed ({e})", file=sys.stderr)
        if not os.path.exists(p):
            raise err
        age = (time.time() - os.path.getmtime(p)) / 3600
        print(f"WARNING nflverse: no address answered for {name}; using the cached copy from {age:.0f} hours ago", file=sys.stderr)
    return p


def load(name, url, max_age=None):
    """A cached CSV as a list of dicts (fit_nflverse.py's original loader)."""
    with open(path(name, url, max_age), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def frame(kind, season=None, max_age=None):
    """A cached file as a pandas DataFrame: kind is a key of FILES with {s} filled from season."""
    import pandas as pd
    name, url = kind.format(s=season), FILES[kind].format(s=season)
    return pd.read_csv(path(name, url, max_age), low_memory=False)
