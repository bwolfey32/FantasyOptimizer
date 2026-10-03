"""Pull the data snapshot out of a page rendered with index.html#export and save it as snapshot.json.

Usage: python3 scripts/extract_snapshot.py dom.html snapshot.json

The page writes the snapshot into <pre id="snapshot-out"> only when every live source answered, so a missing or
thin snapshot means the export failed; the script then exits with an error and the old snapshot.json is kept.
"""
import html
import json
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

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))
print(f"Saved snapshot for {snap['season']} week {snap['week']}: {len(snap['proj'])} players, created {snap['createdAt']}")
