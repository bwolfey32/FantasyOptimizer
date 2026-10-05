"""Replay the site's model on historical fixtures in headless Chrome and save what it said each week.

Usage: python3 scripts/backtest/replay.py baseline            the model as shipped: full rows + Waivers for 13 rosters
       python3 scripts/backtest/replay.py sweep               one-at-a-time constant sweeps (forecasts only)
       python3 scripts/backtest/replay.py sweep2              round two: narrower rules and structural variants
       python3 scripts/backtest/replay.py configs FILE.json   any list of configs, e.g. [{"name": "x", "params": {...},
                                                              "settings": {"blend": 0.5}, "full": true, "waivers": true}]
Options: --fixtures 2025-w0* (glob on fixture names), --out NAME (default: the mode), --port 8765

Fixtures come from build_fixtures.py (scripts/backtest/out/fixtures). This script serves the repo folder, opens
scripts/backtest/driver.html in headless Chrome, hands it the job, and appends each fixture's results to
scripts/backtest/out/replay/<name>.jsonl. index.html is served as it is in the repo: the driver turns the constants
being tuned into parameters inside the page (see PATCHES in driver.html) and checks that, at the shipped values, the
patched model matches the original exactly. Needs Chrome or Chromium (set CHROME to its path if it isn't found).

Waivers are run for thirteen fantasy rosters: A, the reviewer's 17-player roster from tests/selftest.html (same names in
every week), and B-M, the twelve teams of a league drafted from week-1 projections (build_fixtures.py, rosters.json),
held fixed all season (each week's advice is judged on its own). ESPN ownership by week
can't be recovered, so the free-agent pool is a stand-in: everyone except the top QB20/RB50/WR60/TE18/K14/DEF16 by a mix
of this week's projection, this season's scoring average and last season's, and except the roster itself.
"""
import argparse
import fnmatch
import glob
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "out")

OWNED_TOP = {"QB": 20, "RB": 50, "WR": 60, "TE": 18, "K": 14, "DEF": 16}

# 2025 play-caller changes (offense / defense new to the team that season), best effort from the 2025 offseason. The site's
# STAFF_BASE is 2026's, so 2025 fixtures get these flags through state.staffEdits; staff only widens the range (x1.1) and
# shortens how much last season's team stats count. No previous-team blending is applied for 2025.
NEW_2025 = {"off": {"CHI", "DAL", "JAX", "LV", "NE", "NO", "NYJ", "DET", "PHI", "TB", "SEA", "HOU"},
            "def": {"ATL", "CHI", "DAL", "DET", "IND", "JAX", "NE", "NO", "NYJ", "SF", "CIN"},
            "hc": {"CHI", "DAL", "JAX", "LV", "NE", "NO", "NYJ"}}
ALL_TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC", "LV", "LAC",
             "LAR", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS"]


def staff_edits(season):
    if season != 2025:
        return {}
    return {T: {"hcNew": T in NEW_2025["hc"], "offNew": T in NEW_2025["off"], "defNew": T in NEW_2025["def"], "offPrev": "", "defPrev": ""}
            for T in ALL_TEAMS}


def reviewer_roster():
    with open(os.path.join(ROOT, "tests", "selftest.html"), encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"const ROSTER = \[(.*?)\];", src, re.S)
    return re.findall(r"'([^']+)'", m.group(1))


def owned_proxy(fx):
    """Players treated as rostered in other leagues (not on waivers) for this fixture: see the module notes."""
    cur = {}
    for wk in fx["weeks"]:
        for p in wk["P"]:
            cur.setdefault(p[0], []).append(p[4])
        for d in wk["D"]:
            cur.setdefault(d[0], []).append(d[11])
    by_pos = {}
    for pid, name, pos, team, inj, pts, opp, rec in fx["proj"]:
        vals = []
        if pts and pts > 0:
            vals.append(pts)
        if pid in cur:
            vals.append(sum(cur[pid]) / len(cur[pid]))
        if pid in fx["prevPPG"]:
            vals.append(fx["prevPPG"][pid][0])
        if vals and team:
            by_pos.setdefault(pos, []).append((sum(vals) / len(vals), pid))
    owned = []
    for pos, lst in by_pos.items():
        lst.sort(reverse=True)
        owned += [pid for _, pid in lst[:OWNED_TOP.get(pos, 0)]]
    return owned


def build_job(mode, configs, pattern):
    files = sorted(glob.glob(os.path.join(OUT, "fixtures", "*.json")))
    files = [f for f in files if fnmatch.fnmatch(os.path.basename(f)[:-5], pattern)]
    if not files:
        sys.exit("No fixtures: run build_fixtures.py first.")
    with open(os.path.join(OUT, "rosters.json"), encoding="utf-8") as f:
        drafted = json.load(f)
    names = reviewer_roster()
    fixtures = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            fx = json.load(f)
        key = os.path.basename(path)[:-5]
        rosters = {"A": {"names": names}}
        for k, team in drafted.get(str(fx["season"]), {}).items():
            rosters[k] = {"ids": [p[0] for p in team]}
        fixtures.append({"key": key, "path": "/" + os.path.relpath(path, ROOT).replace(os.sep, "/"), "season": fx["season"], "week": fx["week"],
                         "staffEdits": staff_edits(fx["season"]), "rosters": rosters, "owned": owned_proxy(fx)})
    return {"fixtures": fixtures, "configs": configs}


# ---------- the constants swept, one at a time around the shipped values (forecasts only) ----------
def sweep_configs():
    cfg = [{"name": "base", "params": {}}]
    add = lambda name, params=None, settings=None: cfg.append({"name": name, "params": params or {}, "settings": settings or {}})
    for b in (0.3, 0.4, 0.5, 0.7, 0.8, 0.9):
        add(f"blend={b}", settings={"blend": b})
    for rp in (0.5, 0.6, 0.9, 1.0, 1.2):
        add(f"ROS_PROJ={rp}", {"ROS_PROJ": rp})
    for name, rw in (("flat", [1, 1, 1]), ("mild", [1.25, 1.1, 1.05]), ("strong", [2, 1.5, 1.25]), ("vstrong", [3, 2, 1.5])):
        add(f"RECENT_W={name}", {"RECENT_W": rw})
    for k0, kend, kl in ((2, 1, 0.5), (3, 1.5, 1), (6, 3, 1.5), (8, 4, 2), (4, 2, 2), (4, 2, 0.5), (4, 2, 0)):
        add(f"prior={k0}/{kend}/{kl}", {"PRIOR_K0": k0, "PRIOR_KEND": kend, "PRIOR_KLATE": kl})
    for mc in (0.5, 1, 2.5, 4):
        add(f"MOVED_CAP={mc}", {"MOVED_CAP": mc})
    add("DOUBT_ON=false", {"DOUBT_ON": False})
    for dk in (0, 0.2, 0.6, 0.8):
        add(f"DOUBT_K={dk}", {"DOUBT_K": dk})
    for r in (1.5, 1.75, 2.5):
        add(f"DOUBT_RATIO={r}", {"DOUBT_RATIO": r})
    for g in (2, 3, 6):
        add(f"DOUBT_GAP={g}", {"DOUBT_GAP": g})
    for l in (0.6, 1.0, 10):
        add(f"DOUBT_LAST={l}", {"DOUBT_LAST": l})
    add("DOUBT_NMIN=2", {"DOUBT_NMIN": 2})
    add("DOUBT_NMIN=4", {"DOUBT_NMIN": 4, "DOUBT_NMIN_NEW": 3})
    for lo in (0.3, 0.4, 0.6):
        add(f"ROLE_LO={lo}", {"ROLE_LO": lo})
    for hi in (1.3, 1.45, 1.8, 2.2, 99):
        add(f"ROLE_HI={hi}", {"ROLE_HI": hi})
    for rl in (0.6, 0.7, 0.8, 1.0):
        add(f"ROLE_LEAD={rl}", {"ROLE_LEAD": rl})
    add("BUMP=false", {"BUMP": False})
    for sk in (0.8, 0.9, 1.1, 1.2):
        add(f"SD_K={sk}", {"SD_K": sk})
    return cfg


def sweep2_configs():
    """Round two: the changes round one pointed to, and structural variants (see driver.html DEFAULTS)."""
    cfg = [{"name": "base", "params": {}}]
    add = lambda name, params=None, settings=None: cfg.append({"name": name, "params": params or {}, "settings": settings or {}})
    # slow starts: narrower rules
    add("doubt: veterans only", {"DOUBT_NEW": False})
    add("doubt: team changes only", {"DOUBT_MOVED_ONLY": True})
    add("doubt: not QBs", {"DOUBT_POS": ["RB", "WR", "TE"]})
    add("doubt: veterans, not QBs", {"DOUBT_NEW": False, "DOUBT_POS": ["RB", "WR", "TE"]})
    add("doubt: team changes, not QBs", {"DOUBT_MOVED_ONLY": True, "DOUBT_POS": ["RB", "WR", "TE"]})
    add("doubt: team changes, not QBs, K=0.6", {"DOUBT_MOVED_ONLY": True, "DOUBT_POS": ["RB", "WR", "TE"], "DOUBT_K": 0.6})
    add("doubt: off", {"DOUBT_ON": False})
    # roles
    for lo in (0.6, 0.7):
        add(f"ROLE_LO={lo}", {"ROLE_LO": lo})
    # projection weight that starts high and eases to the setting
    for b1, wn in ((0.8, 6), (0.85, 8), (0.9, 8), (0.9, 10), (0.85, 12)):
        add(f"blend {b1} at wk1 -> 0.6 by wk{wn}", {"BLEND_W1": b1, "BLEND_WN": wn})
    for b1, wn in ((0.85, 8), (0.9, 10)):
        add(f"blend {b1} at wk1 -> 0.5 by wk{wn}", {"BLEND_W1": b1, "BLEND_WN": wn}, {"blend": 0.5})
    # usage in the scoring form
    try:
        with open(os.path.join(OUT, "results", "usage.json"), encoding="utf-8") as f:
            xfp = json.load(f)["coef4"]
        for uw in (0.25, 0.5, 0.75):
            add(f"usage form {uw}", {"USAGE_W": uw, "XFP": xfp})
    except (OSError, KeyError):
        print("No usage coefficients yet (run analyze.py usage): skipping usage configs.")
    # range width, QBs, weather
    add("SD_K=1.15", {"SD_K": 1.15})
    for qk in (0.94, 0.97):
        add(f"QB_K={qk}", {"QB_K": qk})
    W = {"dvp": 1, "cover": 1, "protect": 1, "script": 1, "style": 1, "pers": 1, "wx": 1}
    for wx in (1.5, 2.5):
        add(f"weather weight {wx}", settings={"w": dict(W, wx=wx)})
    add("intensity 0.8", settings={"intensity": 0.8})
    add("intensity 0.4", settings={"intensity": 0.4})
    return cfg


def sweep3_configs():
    """Round three: where the round-two winners peak, and how they combine."""
    with open(os.path.join(OUT, "results", "usage.json"), encoding="utf-8") as f:
        xfp = json.load(f)["coef4"]
    cfg = [{"name": "base", "params": {}}]
    add = lambda name, params=None, settings=None: cfg.append({"name": name, "params": params or {}, "settings": settings or {}})
    for lo in (0.7, 0.8, 0.9):
        add(f"ROLE_LO={lo}", {"ROLE_LO": lo})
    for lo, lead in ((0.7, 0.8), (0.8, 0.8), (0.8, 1.0)):
        add(f"ROLE_LO={lo}, ROLE_LEAD={lead}", {"ROLE_LO": lo, "ROLE_LEAD": lead})
    for uw in (0.75, 1.0):
        add(f"usage form {uw}", {"USAGE_W": uw, "XFP": xfp})
    for mk in (0, 0.33, 0.5, 0.67):
        add(f"Waivers matchup x{mk}", {"MM_K": mk})
    for i in (0.2, 0.3):
        add(f"intensity {i}", settings={"intensity": i})
    for qk in (0.9, 0.92):
        add(f"QB_K={qk}", {"QB_K": qk})
    add("blend 0.9 at wk1 -> 0.6 by wk10", {"BLEND_W1": 0.9, "BLEND_WN": 10})
    add("blend 1.0 at wk1 -> 0.6 by wk10", {"BLEND_W1": 1.0, "BLEND_WN": 10})
    doubt = {"DOUBT_MOVED_ONLY": True, "DOUBT_POS": ["RB", "WR", "TE"]}
    combo = dict(doubt, ROLE_LO=0.8, USAGE_W=0.75, XFP=xfp, BLEND_W1=0.9, BLEND_WN=10, MM_K=0.5, SD_K=1.15)
    add("combo", combo)
    add("combo + QB_K=0.94", dict(combo, QB_K=0.94))
    add("combo, usage 1.0", dict(combo, USAGE_W=1.0))
    add("combo, ROLE_LO=0.7", dict(combo, ROLE_LO=0.7))
    add("combo, doubt off", dict(combo, DOUBT_ON=False))
    add("combo, no blend schedule", {k: v for k, v in combo.items() if not k.startswith("BLEND")})
    return cfg


TUNED_DOUBT = {"DOUBT_MOVED_ONLY": True, "DOUBT_POS": ["RB", "WR", "TE"]}


def tuned_params(xfp):
    """The recommended set (docs/backtest-report.md), as driver parameters."""
    return dict(TUNED_DOUBT, DOWN_BLEND=0.9, DOWN_ROS=0.9, USAGE_W=0.75, XFP=xfp, MM_K=0.5, SD_K=1.15)


def sweep5_configs():
    """Round five: the final set, and each piece left out once (its contribution on held-out weeks)."""
    with open(os.path.join(OUT, "results", "usage.json"), encoding="utf-8") as f:
        xfp = json.load(f)["coef4"]
    t = tuned_params(xfp)
    cfg = [{"name": "base", "params": {}}, {"name": "tuned", "params": t}]
    add = lambda name, params: cfg.append({"name": name, "params": params, "settings": {}})
    add("tuned + QB x0.94 this week", dict(t, QB_K=0.94))
    add("tuned + QB x0.94 this week and later", dict(t, QB_K=0.94, QB_ROS_K=0.94))
    add("tuned, no usage", {k: v for k, v in t.items() if k not in ("USAGE_W", "XFP")})
    add("tuned, no down rule", {k: v for k, v in t.items() if not k.startswith("DOWN")})
    add("tuned, matchup x1", dict(t, MM_K=1))
    add("tuned, sd x1", dict(t, SD_K=1))
    add("tuned, doubt as shipped", {k: v for k, v in t.items() if not k.startswith("DOUBT")})
    add("tuned, early-season schedule", dict(t, BLEND_W1=0.9, BLEND_WN=10, BLEND_ROS=False))
    # one change at a time on top of the shipped model
    add("only: down rule", {"DOWN_BLEND": 0.9, "DOWN_ROS": 0.9})
    add("only: usage form", {"USAGE_W": 0.75, "XFP": xfp})
    add("only: Waivers matchup x0.5", {"MM_K": 0.5})
    add("only: QB discount", {"QB_K": 0.94, "QB_ROS_K": 0.94})
    add("only: wider range", {"SD_K": 1.15})
    add("only: narrower slow-start rule", dict(TUNED_DOUBT))
    return cfg


def sweep4_configs():
    """Round four: 'follow a lower projection' without a role label, and the final combinations."""
    with open(os.path.join(OUT, "results", "usage.json"), encoding="utf-8") as f:
        xfp = json.load(f)["coef4"]
    cfg = [{"name": "base", "params": {}}]
    add = lambda name, params=None, settings=None: cfg.append({"name": name, "params": params or {}, "settings": settings or {}})
    for d in (0.8, 0.9, 1.0):
        add(f"DOWN_BLEND={d}", {"DOWN_BLEND": d})
    for d in (0.6, 0.75, 0.9):
        add(f"DOWN_BLEND=0.9, DOWN_ROS={d}", {"DOWN_BLEND": 0.9, "DOWN_ROS": d})
    add("DOWN_BLEND=0.9, DOWN_ROS=0.9, blend 0.5", {"DOWN_BLEND": 0.9, "DOWN_ROS": 0.9}, {"blend": 0.5})
    add("blend schedule, weekly only", {"BLEND_W1": 0.9, "BLEND_WN": 10, "BLEND_ROS": False})
    # the candidate set as it stood in round four (round five dropped the schedule and settled the rest)
    t = dict(TUNED_DOUBT, DOWN_BLEND=0.9, DOWN_ROS=0.9, BLEND_W1=0.9, BLEND_WN=10, BLEND_ROS=False, USAGE_W=0.75, XFP=xfp, MM_K=0.5, SD_K=1.15)
    add("tuned", t)
    add("tuned + QB_K=0.94", dict(t, QB_K=0.94))
    add("tuned, ROLE_LO=0.8", dict(t, ROLE_LO=0.8))
    add("tuned, usage 1.0", dict(t, USAGE_W=1.0))
    add("tuned, no usage", {k: v for k, v in t.items() if k not in ("USAGE_W", "XFP")})
    add("tuned, no down rule", {k: v for k, v in t.items() if not k.startswith("DOWN")})
    add("tuned, no schedule", {k: v for k, v in t.items() if not k.startswith("BLEND")})
    add("tuned, matchup x1", dict(t, MM_K=1))
    add("tuned, doubt as shipped", {k: v for k, v in t.items() if not k.startswith("DOUBT")})
    add("tuned, doubt off", dict(t, DOUBT_ON=False))
    add("tuned, blend 0.5", t, {"blend": 0.5})
    return cfg


# ---------- serve the repo, run Chrome, collect results ----------
def find_chrome():
    cands = [os.environ.get("CHROME"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    cands += [shutil.which(x) for x in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    sys.exit("Chrome not found: set CHROME to its path.")


def run(job, name, port, timeout):
    os.makedirs(os.path.join(OUT, "replay"), exist_ok=True)
    out_path = os.path.join(OUT, "replay", name + ".jsonl")
    open(out_path, "w").close()
    done = threading.Event()
    lock = threading.Lock()
    state = {"n": 0, "errors": 0}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=ROOT, **k)

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path == "/__job":
                body = json.dumps(job).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
                return
            super().do_GET()

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
            if self.path == "/__result":
                with lock:
                    with open(out_path, "ab") as f:
                        f.write(body.replace(b"\n", b" ") + b"\n")
                    state["n"] += 1
                    if b'"error"' in body[:200]:
                        state["errors"] += 1
            elif self.path == "/__log":
                print("  [page]", body.decode("utf-8", "replace")[:2000], flush=True)
            elif self.path == "/__done":
                done.set()
            self.send_response(204); self.end_headers()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    prof = tempfile.mkdtemp(prefix="bp-backtest-")
    args = [find_chrome(), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={prof}",
            "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
            "--disable-extensions", f"http://127.0.0.1:{port}/scripts/backtest/driver.html"]
    if sys.platform.startswith("linux"):
        args.insert(1, "--no-sandbox")
    t0 = time.time()
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while not done.wait(2):
            if time.time() - t0 > timeout:
                print("Timed out.")
                break
            if proc.poll() is not None:
                print("Chrome exited early.")
                break
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        srv.shutdown()
        shutil.rmtree(prof, ignore_errors=True)
    print(f"{name}: {state['n']} fixtures saved ({state['errors']} errors) to {os.path.relpath(out_path, ROOT)} in {time.time() - t0:.0f}s")
    return state["errors"] == 0 and state["n"] == len(job["fixtures"])


def load(name):
    """{fixture key: result} from a replay run."""
    out = {}
    with open(os.path.join(OUT, "replay", name + ".jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out[r["key"]] = r
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["baseline", "sweep", "sweep2", "sweep3", "sweep4", "sweep5", "compare", "configs"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--fixtures", default="*")
    ap.add_argument("--out")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--timeout", type=int, default=6 * 3600)
    a = ap.parse_args()
    if a.mode == "baseline":
        configs = [{"name": "base", "params": {}, "full": True, "waivers": True}]
    elif a.mode == "sweep":
        configs = sweep_configs()
    elif a.mode == "sweep2":
        configs = sweep2_configs()
    elif a.mode == "sweep3":
        configs = sweep3_configs()
    elif a.mode == "sweep5":
        configs = sweep5_configs()
    elif a.mode == "sweep4":
        configs = sweep4_configs()
    elif a.mode == "compare":
        with open(os.path.join(OUT, "results", "usage.json"), encoding="utf-8") as f:
            xfp = json.load(f)["coef4"]
        configs = [{"name": "base", "params": {}, "full": True, "waivers": True},
                   {"name": "tuned", "params": tuned_params(xfp), "full": True, "waivers": True}]
    else:
        with open(a.file, encoding="utf-8") as f:
            configs = json.load(f)
    ok = run(build_job(a.mode, configs, a.fixtures), a.out or a.mode, a.port, a.timeout)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
