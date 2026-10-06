"""Pull the data snapshot out of a page rendered with index.html#export and save it as snapshot.json.

Usage: python3 scripts/extract_snapshot.py dom.html snapshot.json

The page writes the snapshot into <pre id="snapshot-out"> only when every live source answered, so a missing or
thin snapshot means the export failed; the script then exits with an error and the old snapshot.json is kept.
"""
import html
import json
import os
import re
import sys

dom_path, out_path = sys.argv[1], sys.argv[2]
with open(dom_path, encoding="utf-8", errors="replace") as f:
    dom = f.read()

match = re.search(r'<pre id="snapshot-out"[^>]*>(.*?)</pre>', dom, re.S)
if not match:
    sys.exit("No snapshot in the rendered page: live data didn't load.")

snap = json.loads(html.unescape(match.group(1)))
checks = {
    "projections": len(snap.get("proj", [])) >= 300,
    "schedule": len(snap.get("sched", [])) >= 200,
    "defensive players": len((snap.get("idp") or {}).get("now", [])) >= 300,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    sys.exit("Snapshot looks incomplete (" + ", ".join(failed) + "); keeping the old one.")

if len(snap.get("own", [])) < 100:
    print("Warning: ESPN ownership didn't load; waiver suggestions on the saved copy will treat everyone as available.")
if not snap.get("wx"):
    print("Warning: no weather forecasts in the snapshot (none due yet, or Open-Meteo didn't answer).")
if not any(len(row) >= 16 and row[14] is not None for wk in snap.get("weeks", []) for row in wk.get("P", [])):
    print("Warning: no snap counts in this season's weekly stats; role changes (roleChgOf) stay off until they load.")
if not snap.get("split"):
    print("Warning: last season's indoor/outdoor splits didn't build; the weather factor will skip personal splits.")


def injury_kind(status):
    """Same groups as injKind in index.html: long (IR, PUP, suspended, NFI) or short (Out, Doubtful)."""
    s = (status or "").lower()
    if re.match(r"(ir|pup|sus|na)", s):
        return "long"
    if re.match(r"(out|doubtful)", s):
        return "short"
    return None


# Injury log: the week each injured player was first listed with his current kind of injury, carried over from the
# previous snapshot so an expected return counts from when he got hurt (returnWeek in index.html). Sleeper's
# injury_start_date is empty, so this log is the only record of it. Players who are healthy again drop out.
try:
    with open(out_path, encoding="utf-8") as f:
        old = json.load(f)
    prev_log = (old.get("injLog") or {}) if old.get("season") == snap["season"] else {}
except (OSError, ValueError):
    prev_log = {}
log = {}
for row in snap.get("proj", []):
    pid, status = row[0], row[4]
    kind = injury_kind(status)
    if not kind or pid in log:
        continue
    seen = prev_log.get(pid)
    if seen and seen[1] == snap["season"] and injury_kind(seen[0]) == kind:
        log[pid] = [status, seen[1], seen[2], seen[3]]
    else:
        log[pid] = [status, snap["season"], snap["detWeek"], snap["createdAt"][:10]]
snap["injLog"] = log

# Frozen forecasts, for scripts/calibrate.py: forecasts/<season>-wNN.json keeps each player's forecast as it stood before
# his game. A player's entry is written only while his game hasn't started, so the record never picks up news or scores
# from after kickoff. Rows: [mean, sd, base, Sleeper projection, saved at, chance he plays]: mean and sd are what he
# scores if he plays (calibrate.py scores players who played), the last field the chance he does (1 when untagged).
# Not kept in snapshot.json itself.
fc = snap.pop("fc", None) or {}
if fc:
    fdir = os.path.join(os.path.dirname(os.path.abspath(out_path)), "forecasts")
    os.makedirs(fdir, exist_ok=True)
    fpath = os.path.join(fdir, "%d-w%02d.json" % (snap["season"], snap["week"]))
    try:
        with open(fpath, encoding="utf-8") as f:
            book = json.load(f)
    except (OSError, ValueError):
        book = {"season": snap["season"], "week": snap["week"], "players": {}}
    frozen = 0
    for pid, row in fc.items():
        if row[4] == "pre":
            book["players"][pid] = row[:4] + [snap["createdAt"]] + row[5:6]
            frozen += 1
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(book, f, separators=(",", ":"), sort_keys=True)
    print(f"Forecasts: {frozen} pregame entries updated in {os.path.basename(fpath)} ({len(book['players'])} players)")

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))
print(f"Saved snapshot for {snap['season']} week {snap['week']}: {len(snap['proj'])} players, created {snap['createdAt']}")
