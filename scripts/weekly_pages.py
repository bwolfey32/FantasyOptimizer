"""Write the weekly pages (plain HTML that search engines can read) and sitemap.xml from a data bundle.

Usage: python3 scripts/weekly_pages.py [--fixture snapshot.json] [--out .]

Runs scripts/weekly-pages.html in headless Chrome, which loads the site on the bundle and collects the numbers from the
site's own model, then writes:
  weekly/index.html                   this week's pages
  weekly/waiver-wire/index.html       the best free agents over the next four weeks, by position
  weekly/rankings/index.html          this week's projections by position (PPR)
  weekly/defense-rankings/index.html  D/STs to play, and fantasy points each defense allows by position
  weekly/weather/index.html           every game's stadium and kickoff forecast, and the players it moves
  sitemap.xml
The addresses stay the same every week; the week in the titles changes. The data refresh runs this after each new
snapshot (.github/workflows/refresh-data.yml). Exits 1 when the page's data doesn't come back; the old pages are kept.
Needs Chrome or Chromium (set CHROME to its path if it isn't found).
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

sys.dont_write_bytecode = True   # no __pycache__ from importing audit.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit import ROOT, find_chrome, serve  # noqa: E402

SITE = "https://bennyspicks.us"
POS_NAME = {"QB": "Quarterbacks", "RB": "Running backs", "WR": "Wide receivers", "TE": "Tight ends", "K": "Kickers", "DEF": "Defenses (D/ST)"}
POS_LABEL = {"DEF": "D/ST"}
PAGES = [("waiver-wire", "Waiver wire"), ("rankings", "Rankings"), ("defense-rankings", "Defenses"), ("weather", "Weather")]
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # no time zone data: kickoffs in UTC
    ET = timezone.utc

esc = html.escape
lab = lambda p: POS_LABEL.get(p, p)
cap = lambda t: t[:1].upper() + t[1:]   # unlike str.capitalize, leaves names as they are


def collect(fixture):
    srv = serve()
    url = f"http://127.0.0.1:{srv.server_address[1]}/scripts/weekly-pages.html?fixture={fixture}"
    # kept well inside the data refresh's 15 minutes, so a stuck browser can't hold up publishing the new snapshot
    try:
        with tempfile.TemporaryDirectory() as prof:
            dom = subprocess.run([find_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", f"--user-data-dir={prof}",
                                  "--virtual-time-budget=120000", "--dump-dom", url], capture_output=True, text=True, timeout=300).stdout
    except subprocess.TimeoutExpired:
        sys.exit("Chrome didn't finish the weekly pages in 5 minutes; keeping the old pages.")
    finally:
        srv.shutdown()
    m = re.search(r'<pre id="pages-out">(.*?)</pre>', dom, re.S)
    text = html.unescape(m.group(1)) if m else "ERROR no results in the page"
    if not text.startswith("{"):
        sys.exit(text[:2000])
    return json.loads(text)


def when(iso):
    if not iso:
        return ""
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET)
    return f"{t:%a %b} {t.day}, {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'} {'ET' if ET is not timezone.utc else 'UTC'}"


def opp_txt(p):
    return "Bye" if not p.get("opp") else f"{'vs' if p.get('home') else '@'} {p['opp']}"


def page(slug, d, title, desc, h1, intro, body, cta):
    """One weekly page: the site's look (light and dark), header, the page's sections, a link into the app, footer."""
    path = f"/weekly/{slug}/" if slug else "/weekly/"
    updated = when(d["createdAt"])
    nav = "".join(f'<a href="/weekly/{s}/"{" aria-current=page" if s == slug else ""}>{n}</a>' for s, n in PAGES)
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": h1, "description": desc, "url": SITE + path,
          "dateModified": d["createdAt"], "isPartOf": {"@type": "WebSite", "name": "Benny’s Picks", "url": SITE + "/"}}
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}{path}">
<meta name="theme-color" content="#075b37">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Benny’s Picks">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{SITE}{path}">
<meta property="og:image" content="{SITE}/assets/social-preview.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png?v=2">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=Saira+Condensed:wght@600;700&display=swap">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>
:root {{ --bg: #eef2ee; --surface: #fff; --surface-2: #e3e9e4; --ink: #13201a; --muted: #4a5850; --line: #cfd8d1; --accent: #075b37; --good: #1b7a4b; --bad: #b23a30; --warn: #a8670f; --gold: #8a6510; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #0e1512; --surface: #151e1a; --surface-2: #1c2722; --ink: #e4ebe6; --muted: #a9b7af; --line: #29352f; --accent: #4fc38e; --good: #4fc38e; --bad: #f07a6e; --warn: #e3b052; --gold: #e2bb52; color-scheme: dark; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.55 "IBM Plex Sans", system-ui, sans-serif; }}
.wrap {{ max-width: 980px; margin: 0 auto; padding: 18px 16px 48px; display: flex; flex-direction: column; gap: 16px; }}
a {{ color: var(--accent); }}
h1, h2 {{ font-family: "Saira Condensed", "Arial Narrow", sans-serif; font-weight: 700; text-transform: uppercase; line-height: 1.1; margin: 0; letter-spacing: .01em; }}
h1 {{ font-size: 34px; }} h2 {{ font-size: 23px; margin-top: 10px; }}
.top {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }}
.brand {{ display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--ink); font-family: "Saira Condensed", sans-serif; font-weight: 700; font-size: 24px; text-transform: uppercase; }}
.brand img {{ width: 44px; height: 44px; }}
.app {{ background: var(--accent); color: #fff; padding: 8px 14px; border-radius: 8px; text-decoration: none; font-weight: 600; }}
@media (prefers-color-scheme: dark) {{ .app {{ color: #07130d; }} }}
nav {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 6px; border-radius: 12px; background: linear-gradient(160deg, #0a6b41, #054a2c); }}
nav a {{ color: rgba(255,255,255,.85); text-decoration: none; padding: 7px 14px; border-radius: 8px; font-family: "Saira Condensed", sans-serif; font-weight: 600; font-size: 17px; text-transform: uppercase; }}
nav a[aria-current] {{ color: #fff; background: rgba(255,255,255,.17); box-shadow: inset 0 0 0 2px rgba(255,255,255,.7); }}
.intro {{ margin: 0; font-size: 16px; max-width: 70ch; }}
.muted {{ color: var(--muted); }} .small {{ font-size: 13.5px; }}
.jump {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.jump a {{ padding: 4px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface); text-decoration: none; }}
.tscroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 7px 10px; text-align: right; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }}
th.l, td.l {{ text-align: left; }} tr:last-child td {{ border-bottom: 0; }}
td.n {{ font-family: "Saira Condensed", sans-serif; font-weight: 700; font-size: 17px; color: var(--accent); }}
.pill {{ display: inline-block; padding: 0 7px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid var(--line); color: var(--muted); }}
.pill.q {{ color: var(--warn); border-color: currentColor; }} .pill.o {{ color: var(--bad); border-color: currentColor; }}
.g {{ display: inline-block; min-width: 24px; text-align: center; border-radius: 6px; font-family: "Saira Condensed", sans-serif; font-weight: 700; }}
.g-A, .g-B {{ color: var(--good); }} .g-D {{ color: var(--warn); }} .g-F {{ color: var(--bad); }} .g-C {{ color: var(--muted); }}
.wk {{ display: inline-block; margin: 0 3px 3px 0; padding: 0 6px; border-radius: 5px; font-size: 12.5px; background: var(--surface-2); white-space: nowrap; }}
.wk.up {{ background: color-mix(in srgb, var(--good) 22%, transparent); }} .wk.down {{ background: color-mix(in srgb, var(--bad) 18%, transparent); }}
.cta {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; padding: 14px 16px; border: 1.8px solid var(--accent); border-radius: 10px; background: var(--surface); }}
.cta span {{ flex: 1 1 300px; }}
.games {{ display: grid; gap: 10px; }}
.game {{ padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); display: grid; gap: 3px; }}
.game strong {{ font-size: 16px; }}
footer {{ display: flex; flex-wrap: wrap; gap: 6px 16px; padding-top: 10px; border-top: 1px solid var(--line); }}
footer a {{ color: var(--muted); }}
@media (max-width: 600px) {{ h1 {{ font-size: 28px; }} th, td {{ padding: 6px 7px; }} .hide-s {{ display: none; }} }}
</style>
<div class="wrap">
<header class="top"><a class="brand" href="/"><img src="/assets/icon-192.png" width="44" height="44" alt="">Benny’s Picks</a><a class="app" href="/{cta[1]}">{esc(cta[2])}</a></header>
<nav aria-label="This week">{nav}</nav>
<main style="display:flex;flex-direction:column;gap:14px">
<h1>{esc(h1)}</h1>
<p class="intro">{intro}</p>
<p class="small muted" style="margin:0">Updated {esc(updated)}. Projections refresh every few hours from Sleeper, ESPN and Open-Meteo.</p>
{body}
<div class="cta"><span>{cta[0]}</span><a class="app" href="/{cta[1]}">{esc(cta[2])}</a></div>
</main>
<footer class="small"><span>© {datetime.now(timezone.utc).year} Benny’s Picks</span><a href="/">Lineup optimizer</a><a href="/weekly/">This week</a><a href="/privacy.html">Privacy</a><a href="/terms.html">Terms</a></footer>
</div>
</html>
"""


def rankings_page(d):
    wk, body = d["week"], []
    body.append('<div class="jump">' + "".join(f'<a href="#{p.lower()}">{lab(p)}</a>' for p in d["rankings"]) + "</div>")
    for p, rows in d["rankings"].items():
        trs = "".join(
            f'<tr><td class="n">{i + 1}</td><td class="l"><strong>{esc(r["name"])}</strong> <span class="muted small">{esc(r["team"]) if p != "DEF" else ""}</span>'
            f'{" " + " ".join(pill(r)) if pill(r) else ""}</td>'
            f'<td class="l">{esc(opp_txt(r))}</td><td><span class="g g-{r["grade"][0]}">{esc(r["grade"])}</span></td>'
            f'<td><strong>{r["proj"]:.1f}</strong></td><td class="hide-s muted">{r["lo"]:.1f}–{r["hi"]:.1f}</td></tr>'
            for i, r in enumerate(rows))
        body.append(f'<h2 id="{p.lower()}">{POS_NAME[p]}</h2><div class="tscroll"><table><thead><tr><th>#</th><th class="l">Player</th><th class="l">Opponent</th>'
                    f'<th title="How favorable the matchup is, A to F">Matchup</th><th>Proj</th><th class="hide-s">Likely range</th></tr></thead><tbody>{trs}</tbody></table></div>')
    top = ", ".join(f'{d["rankings"][p][0]["name"]} ({lab(p)})' for p in ("QB", "RB", "WR", "TE") if d["rankings"].get(p))
    return page("rankings", d,
                f"Week {wk} Fantasy Football Rankings: QB, RB, WR, TE, K, D/ST (PPR) | Benny’s Picks",
                f"Week {wk} {d['season']} fantasy football rankings in PPR: every position ranked by projected points, with matchup grades and likely ranges. Top: {top}.",
                f"Week {wk} fantasy football rankings (PPR)",
                f"Every player who’ll play in week {wk}, ranked by the points Benny projects in PPR scoring: Sleeper’s projection blended with each player’s "
                "scoring form, then adjusted for the matchup, the betting lines, pace and the weather. The matchup grade rates how favorable the matchup is (A to F), "
                "not the player. The likely range is the middle half of outcomes.",
                "\n".join(body),
                ("Stuck between two players? Get Benny’s Pick for any two, with the chance each outscores the other and why.", "#start-sit", "Start / Sit any two players"))


def pill(r):
    out = []
    if r.get("played"):
        out.append('<span class="pill">Played</span>')
    inj = r.get("inj") or ""
    if inj:
        cls = "o" if re.match(r"(out|ir|pup|sus|na|doubtful)", inj, re.I) else "q"
        out.append(f'<span class="pill {cls}">{esc("Q" if inj == "Questionable" else inj)}</span>')
    if r.get("note"):
        out.append(f'<span class="pill">{esc(r["note"])}</span>')
    return out


def waiver_page(d):
    w0, w1 = d["waiverWeeks"]
    span = f"week {w0}" if w0 == w1 else f"weeks {w0}–{w1}"
    body = ['<div class="jump">' + "".join(f'<a href="#{p.lower()}">{lab(p)}</a>' for p in d["waivers"]) + "</div>"]
    for p, rows in d["waivers"].items():
        if not rows:
            continue
        def sched(r):
            return "".join(f'<span class="wk">{s["w"]} BYE</span>' if s["bye"] else
                           f'<span class="wk{" up" if (s["m"] or 0) >= 4 else " down" if (s["m"] or 0) <= -4 else ""}" title="Matchup {"+" if s["m"] >= 0 else "−"}{abs(s["m"]):.0f}%">{s["w"]} {"" if s["home"] else "@"}{esc(s["opp"] or "")}</span>'
                           if s["m"] is not None else f'<span class="wk">{s["w"]}</span>' for s in r["sched"])
        trs = "".join(
            f'<tr><td class="n">{i + 1}</td><td class="l"><strong>{esc(r["name"])}</strong> <span class="muted small">{esc(r["team"]) if p != "DEF" else ""}</span>'
            f'{("<div class=small>" + esc(cap("; ".join(r["notes"]))) + "</div>") if r["notes"] else ""}</td>'
            f'<td>{"&lt;1" if r["own"] < 1 else round(r["own"])}%</td><td>{r["ppg"]:.1f}</td><td><strong>{r["next"]:.1f}</strong></td><td class="l hide-s">{sched(r)}</td></tr>'
            for i, r in enumerate(rows))
        body.append(f'<h2 id="{p.lower()}">{POS_NAME[p]}</h2><div class="tscroll"><table><thead><tr><th>#</th><th class="l">Player</th><th title="Share of ESPN leagues that roster him">Rostered</th>'
                    f'<th title="Projected points a game, rest of season">Pts/g</th><th title="Projected points over {span}, byes and injuries counted">Next {w1 - w0 + 1}</th><th class="l hide-s">Schedule</th></tr></thead><tbody>{trs}</tbody></table></div>')
    top = ", ".join(f'{rows[0]["name"]} ({lab(p)})' for p, rows in d["waivers"].items() if rows and p in ("QB", "RB", "WR", "TE"))
    return page("waiver-wire", d,
                f"Week {w0} Waiver Wire Pickups: Best Fantasy Football Adds | Benny’s Picks",
                f"The best week {w0} fantasy football waiver pickups at every position, ranked by projected points over {span} (PPR), from players rostered in under {d['ownMax']}% of leagues. Top adds: {top}.",
                f"Week {w0} waiver wire pickups",
                f"The best free agents at each position for {span}, ranked by the points Benny projects over those weeks in PPR scoring, byes and injuries "
                f"counted. Only players rostered in under {d['ownMax']}% of ESPN leagues are listed, so most should be on your waiver wire. Schedule chips are green "
                "for a soft matchup and red for a tough one. The best pickup for <em>your</em> team depends on your roster: Benny ranks every add and drop by "
                "how many points it adds to your lineup.",
                "\n".join(body),
                ("Which of these fits your roster, and who should you drop? Benny ranks every add/drop by the points it adds to your lineup, free. With Sleeper it uses your league’s real free agents.", "#waivers", "Find your best pickup"))


def defense_page(d):
    wk = d["week"]
    trs = "".join(
        f'<tr><td class="n">{i + 1}</td><td class="l"><strong>{esc(r["name"])}</strong>{" " + " ".join(pill(r)) if pill(r) else ""}</td><td class="l">{esc(opp_txt(r))}</td>'
        f'<td><span class="g g-{r["grade"][0]}">{esc(r["grade"])}</span></td><td><strong>{r["proj"]:.1f}</strong></td><td class="hide-s muted">{r["lo"]:.1f}–{r["hi"]:.1f}</td></tr>'
        for i, r in enumerate(d["dst"]))
    rows = sorted(d["allowed"], key=lambda r: sum(r["rank"][k] or 16 for k in ("QB", "RB", "WR", "TE")))
    cell = lambda r, k: f'{r[k]:.1f} <span class="muted small">{r["rank"][k]}</span>' if r[k] is not None else "—"
    trs2 = "".join(
        f'<tr><td class="l"><strong>{esc(r["team"])}</strong> <span class="muted small">{esc(r["nick"])} {esc(r["rec"])}</span></td><td class="l hide-s">{esc("Bye" if not r["opp"] else ("vs " if r["home"] else "@ ") + r["opp"])}</td>'
        + "".join(f"<td>{cell(r, k)}</td>" for k in ("QB", "RB", "WR", "TE", "K")) + "</tr>"
        for r in rows)
    body = (f'<h2 id="dst">D/ST rankings, week {wk}</h2><div class="tscroll"><table><thead><tr><th>#</th><th class="l">D/ST</th><th class="l">Opponent</th><th>Matchup</th><th>Proj</th><th class="hide-s">Likely range</th></tr></thead><tbody>{trs}</tbody></table></div>'
            f'<h2 id="allowed">Fantasy points allowed by position</h2><p class="small muted" style="margin:0">Per game, this season blended with last by how much each staff carried over. '
            "The small number is the rank: 1 allows the most, the softest matchup. Softest defenses overall first.</p>"
            f'<div class="tscroll"><table><thead><tr><th class="l">Defense</th><th class="l hide-s">Week {wk}</th><th>vs QB</th><th>vs RB</th><th>vs WR</th><th>vs TE</th><th>vs K</th></tr></thead><tbody>{trs2}</tbody></table></div>')
    top = ", ".join(r["name"] for r in d["dst"][:3])
    return page("defense-rankings", d,
                f"Week {wk} Fantasy Defense Rankings (D/ST) & Matchups | Benny’s Picks",
                f"Week {wk} {d['season']} fantasy D/ST rankings by projected points, and the fantasy points every NFL defense allows to QBs, RBs, WRs and TEs. Top D/STs: {top}.",
                f"Week {wk} defense rankings",
                f"Which D/STs to start in week {wk}, ranked by projected points, and how many fantasy points each defense gives up to every position: "
                "the matchups to chase and the ones to avoid. Benny also counts each defense’s signings, trades and injuries that its stats don’t show yet.",
                body,
                ("See every defense’s play-caller and scheme, and how each matchup moves your players.", "#research", "Open Research"))


def weather_page(d):
    wk, cards = d["week"], []
    for g in d["games"]:
        cond = ("Indoors, no weather" if g["roof"] == "dome" else "Retractable roof, closed in bad weather") if g["covered"] else (g["forecast"] or "Forecast not out yet (about two weeks before kickoff)")
        moved = ", ".join(f'{esc(m["name"])} {"+" if m["pct"] >= 0 else "−"}{abs(m["pct"])}%' for m in g["moved"])
        state = ' <span class="pill">Final</span>' if g["state"] == "post" else ' <span class="pill">Live</span>' if g["state"] == "in" else ""
        where = esc(g["stadium"] or "") + (f' ({esc(g["city"])})' if g["city"] else "")
        flag = ' <span class="pill q">Weather game</span>' if g["rough"] else ""
        moves = f'<span class="small">Moves most: {moved}</span>' if moved else ""
        cards.append(f'<div class="game"><span class="small muted">{esc(when(g["date"]))}{state}</span><strong>{esc(g["away"])} @ {esc(g["home"])}</strong>'
                     f'<span class="small">{where}</span><span>{esc(cond)}{flag}</span>{moves}</div>')
    rough = [f'{g["away"]} @ {g["home"]}' for g in d["games"] if g["rough"]]
    return page("weather", d,
                f"Week {wk} NFL Weather Report for Fantasy Football | Benny’s Picks",
                f"Week {wk} {d['season']} NFL weather: kickoff forecasts for every open-air stadium, domes and roofs, and the fantasy players the wind, rain, snow and cold move most."
                + (f" Weather games: {', '.join(rough)}." if rough else ""),
                f"Week {wk} NFL weather report",
                "The forecast for the three hours from kickoff at every open-air stadium, from Open-Meteo; domes and retractable roofs play without weather. "
                "Wind over 10 mph hurts deep passing and kickers most, rain and snow shift work to running backs, and freezing cold costs kickers and passers a little. "
                "The percentages are how much the conditions move each player’s projection.",
                f'<div class="games">{"".join(cards)}</div>',
                ("See how the weather moves the players on your own roster, game by game.", "#research-weather", "Open the weather"))


def hub_page(d):
    w0 = d["waiverWeeks"][0]
    items = [("waiver-wire", f"Week {w0} waiver wire pickups", "The best free agents at each position over the next four weeks."),
             ("rankings", f"Week {d['week']} rankings (PPR)", "Every position ranked by projected points, with matchup grades."),
             ("defense-rankings", f"Week {d['week']} defense rankings", "D/STs to start, and the fantasy points every defense allows by position."),
             ("weather", f"Week {d['week']} NFL weather report", "Kickoff forecasts, domes and roofs, and the players the weather moves.")]
    body = '<div class="games">' + "".join(f'<a class="game" href="/weekly/{s}/" style="text-decoration:none;color:inherit"><strong>{esc(t)}</strong><span class="small muted">{esc(x)}</span></a>' for s, t, x in items) + "</div>"
    return page("", d,
                f"Fantasy Football This Week: Week {d['week']} Rankings, Waivers, Defenses & Weather | Benny’s Picks",
                f"Week {d['week']} {d['season']} fantasy football: rankings, waiver wire pickups, D/ST rankings and the NFL weather report, updated every few hours.",
                f"Fantasy football, week {d['week']}",
                "Benny’s weekly pages, from the same model that sets your lineup: updated every few hours with the latest projections, injuries, lines and forecasts.",
                body,
                ("Add your team and Benny sets your lineup, makes your close start/sit calls and finds the waiver pickups that fit it. Free; Sleeper needs no login.", "", "Set your lineup"))


def sitemap(d):
    day = (d["createdAt"] or datetime.now(timezone.utc).isoformat())[:10]
    urls = [("/", None, "daily"), ("/weekly/", day, "daily")] + [(f"/weekly/{s}/", day, "daily") for s, _ in PAGES] + [("/privacy.html", None, "yearly"), ("/terms.html", None, "yearly")]
    rows = "".join(f"  <url><loc>{SITE}{u}</loc>{f'<lastmod>{m}</lastmod>' if m else ''}<changefreq>{c}</changefreq></url>\n" for u, m, c in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}</urlset>\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", default="snapshot.json")
    ap.add_argument("--out", default=ROOT)
    a = ap.parse_args()
    d = collect(a.fixture)
    if not d["rankings"].get("WR") or not d["games"]:
        sys.exit("The weekly pages' data came back thin; keeping the old pages.")
    files = {"weekly/index.html": hub_page(d), "weekly/waiver-wire/index.html": waiver_page(d), "weekly/rankings/index.html": rankings_page(d),
             "weekly/defense-rankings/index.html": defense_page(d), "weekly/weather/index.html": weather_page(d), "sitemap.xml": sitemap(d)}
    for path, text in files.items():
        full = os.path.join(a.out, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"Wrote {len(files)} files for week {d['week']} ({d['season']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
