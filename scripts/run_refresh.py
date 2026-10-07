"""Start the site's data refresh (.github/workflows/refresh-data.yml) now, the same as Run workflow on the Actions tab,
and optionally wait for it to finish. Also shows how the last runs went.

Usage: python scripts/run_refresh.py [--wait] [--status]

  (no flag)  start a run on main; needs GH_DISPATCH_TOKEN (or GH_TOKEN / GITHUB_TOKEN) in the environment: a GitHub
             token for this repository with Actions: read and write (the same kind share/'s scheduled refresh uses)
  --wait     after starting it, check every 20 seconds until it finishes; exits 1 if it failed or took over 30 minutes
  --status   only list the last few runs (no token needed: the repository is public)

The token is read from the environment only, never written anywhere.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

REPO, WORKFLOW = "bwolfey32/FantasyOptimizer", "refresh-data.yml"
API = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}"
POLL, MAX_WAIT = 20, 30 * 60


def call(url, token=None, body=None):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "bennys-picks"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET"), timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def runs(token=None, n=5, event=None):
    q = f"?per_page={n}" + (f"&event={event}" if event else "")
    return call(f"{API}/runs{q}", token)["workflow_runs"]


def line(r):
    return f"{r['created_at']}  {r['event']:<17} {r['status']:<11} {r['conclusion'] or '':<9} {r['html_url']}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        for r in runs():
            print(line(r))
        return 0
    token = os.environ.get("GH_DISPATCH_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Set GH_DISPATCH_TOKEN to a GitHub token with Actions: read and write on this repository.", file=sys.stderr)
        return 2
    started = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        call(f"{API}/dispatches", token, {"ref": "main"})
    except urllib.error.HTTPError as e:
        print(f"Starting the refresh failed: {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    print("Refresh started.")
    # the dispatch call doesn't name the run it made: it's the first on-demand run created from now on
    run = None
    for _ in range(15):
        time.sleep(4)
        run = next((r for r in runs(token, 5, "workflow_dispatch")
                    if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= started.replace(second=0)), None)
        if run:
            break
    if not run:
        print("The run hasn't shown up yet; see the Actions tab.")
        return 0 if not a.wait else 1
    print(line(run))
    if not a.wait:
        return 0
    t0 = time.time()
    while run["status"] != "completed":
        if time.time() - t0 > MAX_WAIT:
            print("Still running after 30 minutes.", file=sys.stderr)
            return 1
        time.sleep(POLL)
        run = call(run["url"], token)
    print(line(run))
    return 0 if run["conclusion"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
