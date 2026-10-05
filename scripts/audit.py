"""Run tests/audit.html in headless Chrome: draft whole leagues from a data bundle, run every engine for every team, and
print the advice a fantasy player would call wrong on sight.

Usage: python3 scripts/audit.py [--fixture snapshot.json] [--leagues 2] [--out report.txt] [--summary FILE] [--report-only]

--fixture   the data bundle, relative to the repo folder (default snapshot.json, the live data; tests/fixture-2026w4.json
            is the frozen week the self-test uses)
--summary   also append the report to FILE as Markdown (GitHub's $GITHUB_STEP_SUMMARY)
Exits 1 when the report has an ERROR line (a broken rule) or never finishes, unless --report-only. WARN lines are worth a
look but don't fail. Needs Chrome or Chromium (set CHROME to its path if it isn't found).
"""
import argparse
import functools
import html
import http.server
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def find_chrome():
    cands = [os.environ.get("CHROME"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    cands += [shutil.which(x) for x in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    sys.exit("Chrome not found: set CHROME to its path.")


def serve():
    handler = functools.partial(type("Quiet", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory=ROOT)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", default="snapshot.json")
    ap.add_argument("--leagues", type=int, default=2)
    ap.add_argument("--out")
    ap.add_argument("--summary")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    srv = serve()
    url = f"http://127.0.0.1:{srv.server_address[1]}/tests/audit.html?fixture={a.fixture}&leagues={a.leagues}"
    with tempfile.TemporaryDirectory() as prof:
        dom = subprocess.run([find_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", f"--user-data-dir={prof}",
                              "--virtual-time-budget=600000", "--dump-dom", url], capture_output=True, text=True, timeout=900).stdout
    srv.shutdown()
    m = re.search(r'<pre id="audit-out">(.*?)</pre>', dom, re.S)
    text = html.unescape(m.group(1)) if m else "ERROR no results in the page"
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    done = re.search(r"(?m)^DONE", text)
    errors = re.search(r"(?m)^ERROR", text)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            head = text.split("\nDETAILS")[0]
            f.write(f"### Advice audit ({a.fixture})\n\n```\n{head}\n```\n")
            if errors or re.search(r"(?m)^WARN", text):
                f.write("\n<details><summary>Details</summary>\n\n```\n" + text + "\n```\n</details>\n")
    if a.report_only:
        return 0
    return 1 if errors or not done else 0


if __name__ == "__main__":
    sys.exit(main())
