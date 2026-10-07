"""Check that the data refresh's quiet fallbacks didn't hide a failure, so nobody has to watch the runs.

Usage: python3 scripts/health.py [--warnings FILE] [--summary FILE]

The refresh keeps last run's files whenever a step fails (`|| echo ... kept from the last run`), so the site keeps
working, but a step that fails every run would go unnoticed. This runs last in .github/workflows/refresh-data.yml and
exits 1 when something has gone stale, which fails the run, and GitHub emails the repository's owner:
  - model/proj.json isn't for the snapshot's week: the trained projections didn't update, and the site has fallen back
    to the classic model
  - players/data/index.json is over 48 hours old: the player history has failed to rebuild twice (it runs daily)
  - there are fewer than 500 player pages
Warnings (printed as annotations, the run still passes): an nflverse file served from an old cached copy because none
of its addresses answered (lines starting "WARNING" in --warnings, the earlier steps' stderr).
Everything found goes to --summary (the run's summary page) too.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def load(rel):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def hours_since(iso):
    return (time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) / 3600


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--warnings")
    ap.add_argument("--summary")
    a = ap.parse_args()
    errors, warns = [], []

    snap, proj = load("snapshot.json"), load("model/proj.json")
    if not snap:
        errors.append("snapshot.json is missing or unreadable.")
    elif not proj:
        errors.append("model/proj.json is missing: the site shows the classic model.")
    elif (proj.get("season"), proj.get("week")) != (snap.get("season"), snap.get("week")):
        errors.append(f"Trained projections are for {proj.get('season')} week {proj.get('week')}, the snapshot for {snap['season']} week {snap['week']}: "
                      "scripts/model/predict.py is failing, and the site has fallen back to the classic model.")

    idx = load("players/data/index.json")
    if not idx:
        errors.append("players/data/index.json is missing: the player history has never been built.")
    elif hours_since(idx["updated"]) > 48:
        errors.append(f"Player history is {hours_since(idx['updated']):.0f} hours old: scripts/model/player_history.py has failed to rebuild it twice.")

    slugs = (load("players/slugs.json") or {}).get("s", {})
    pages = sum(os.path.exists(os.path.join(ROOT, "players", s, "index.html")) for s in set(slugs.values()))
    if pages < 500:
        errors.append(f"Only {pages} player pages: scripts/player_pages.py may be failing.")

    if a.warnings and os.path.exists(a.warnings):
        with open(a.warnings, encoding="utf-8", errors="replace") as f:
            warns += sorted({line.strip() for line in f if line.startswith("WARNING")})

    for w in warns:
        print(f"::warning::{w}")
    for e in errors:
        print(f"::error::{e}")
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write("## Data health\n\n" + ("".join(f"- ❌ {e}\n" for e in errors) + "".join(f"- ⚠️ {w}\n" for w in warns) or
                                           f"- ✅ Trained projections, player history and {pages} player pages are current.\n") + "\n")
    print(f"Health: {len(errors)} problem(s), {len(warns)} warning(s); {pages} player pages.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
