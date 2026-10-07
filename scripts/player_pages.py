"""Write the static player pages search engines read: one per QB, RB, WR and TE with a history file, and a directory.

Usage: python scripts/player_pages.py [--out .]

Reads players/data/<id>.json (scripts/model/player_history.py), share-players.json (name, position, team, ESPN id for
the headshot, from scripts/player_ids.py) and snapshot.json (who Sleeper projects this week), and writes:
  players/<slug>/index.html   his season-by-season fantasy stats, finishes, and this season's and last season's game
                              logs; this week's trained projection is filled in by the page from /model/proj.json, so
                              the HTML only changes when his games or team do
  players/index.html          every player page, by position
  players/slugs.json          {"s": {sleeperId: slug}}: a slug is given once and kept, so addresses never change
Pages go to players on an NFL team or with a projection this week. The app's own player page (/#player/<id>) has the
full breakdown; each static page links there. A file is only rewritten when its text changed. Run by
.github/workflows/refresh-data.yml after player_history.py; weekly_pages.py then adds these pages to sitemap.xml.
"""
import argparse
import html
import json
import os
import re
import sys
import unicodedata
from urllib.parse import quote

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from weekly_pages import POS_NAME, ROOT, SITE, page  # noqa: E402

esc = html.escape
POS = ("QB", "RB", "WR", "TE")
TEAM_NAME = {"ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills", "CAR": "Carolina Panthers",
             "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys", "DEN": "Denver Broncos",
             "DET": "Detroit Lions", "GB": "Green Bay Packers", "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
             "KC": "Kansas City Chiefs", "LV": "Las Vegas Raiders", "LAC": "Los Angeles Chargers", "LAR": "Los Angeles Rams", "MIA": "Miami Dolphins",
             "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants", "NYJ": "New York Jets",
             "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SF": "San Francisco 49ers", "SEA": "Seattle Seahawks", "TB": "Tampa Bay Buccaneers",
             "TEN": "Tennessee Titans", "WAS": "Washington Commanders"}
POS_WORD = {"QB": "quarterback", "RB": "running back", "WR": "wide receiver", "TE": "tight end"}
HEADSHOT = "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{}.png&w=264&h=192&scale=crop"
# his card for link previews (1200×630, drawn by share/lib/player.mjs on share.bennyspicks.us), not the small headshot
PREVIEW = "https://share.bennyspicks.us/pcard?id={}"
# the stat columns each position's tables show: (key, header)
SEASON_COLS = {"QB": [("cmpatt", "Cmp/Att"), ("pyd", "Pass yds"), ("ptd", "Pass TD"), ("int", "INT"), ("ryd", "Rush yds"), ("rtd", "Rush TD")],
               "RB": [("car", "Car"), ("ryd", "Rush yds"), ("rtd", "Rush TD"), ("rec", "Rec"), ("recyd", "Rec yds"), ("rectd", "Rec TD")],
               "WR": [("tgt", "Tgt"), ("rec", "Rec"), ("recyd", "Rec yds"), ("rectd", "Rec TD")]}
SEASON_COLS["TE"] = SEASON_COLS["WR"]
GAME_COLS = {"QB": SEASON_COLS["QB"], "RB": SEASON_COLS["RB"], "WR": SEASON_COLS["WR"] + [("car", "Car"), ("ryd", "Rush yds")]}
GAME_COLS["TE"] = GAME_COLS["WR"]
CSS = """<style>
.phead { display: flex; align-items: center; gap: 16px; }
.phead img { width: 110px; height: 80px; object-fit: cover; border-radius: 12px; background: var(--surface-2); flex: none; }
.phead p { margin: 4px 0 0; }
.now { display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; padding: 12px 16px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
.now[hidden] { display: none; }
.now b { font-family: "Saira Condensed", sans-serif; font-size: 30px; color: var(--accent); }
.news[hidden] { display: none; }
.news ul { list-style: none; margin: 0; padding: 0; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
.news li { padding: 10px 16px; border-bottom: 1px solid var(--line); } .news li:last-child { border-bottom: 0; }
.news li b { display: block; }
.talk[hidden] { display: none; }
.dir { columns: 3 220px; gap: 24px; } .dir a { display: block; padding: 2px 0; }
.dir h3 { margin: 10px 0 2px; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); break-after: avoid; }
</style>"""


def slugify(name):
    t = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"['’.]", "", t)   # Ja'Marr -> jamarr, A.J. -> aj
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "player"


def n(x, d=0):
    if x is None:
        return "—"
    return f"{x:.{d}f}" if d else f"{round(x):,}"


def cell(row, k):
    return f'{n(row.get("cmp"))}/{n(row.get("patt"))}' if k == "cmpatt" else n(row.get(k))


def rows_of(cols, rows):
    return [dict(zip(cols, r)) for r in rows]


def season_table(h):
    pos, cols = h["pos"], SEASON_COLS[h["pos"]]
    trs = "".join(
        f'<tr><td class="l">{s["season"]}</td><td class="l">{esc(s["team"])}</td><td>{s["gp"]}</td><td><strong>{s["ppr"]:.1f}</strong></td>'
        f'<td>{s["ppr"] / max(1, s["gp"]):.1f}</td><td>{pos}{s["rank"]}</td>' + "".join(f"<td>{cell(s, k)}</td>" for k, _ in cols) + "</tr>"
        for s in reversed(rows_of(h["scols"], h["seasons"])))
    return (f'<div class="tscroll"><table><thead><tr><th class="l">Season</th><th class="l">Team</th><th>GP</th><th>PPR pts</th><th>Pts/g</th>'
            f'<th title="His rank at {pos} by total PPR points">Finish</th>' + "".join(f"<th>{l}</th>" for _, l in cols) + f"</tr></thead><tbody>{trs}</tbody></table></div>")


def game_table(h, season):
    pos, cols = h["pos"], GAME_COLS[h["pos"]]
    games = rows_of(h["gcols"], h["games"].get(str(season), []))
    trs = "".join(f'<tr><td class="l">{g["week"]}</td><td class="l">{esc(g["opp"] or "")}</td><td><strong>{g["ppr"]:.1f}</strong></td>'
                  + "".join(f"<td>{cell(g, k)}</td>" for k, _ in cols) + f'<td class="hide-s">{"—" if g["snp"] is None else str(round(g["snp"] * 100)) + "%"}</td></tr>'
                  for g in games)
    return (f'<div class="tscroll"><table><thead><tr><th class="l">Wk</th><th class="l">Opp</th><th>PPR pts</th>' + "".join(f"<th>{l}</th>" for _, l in cols)
            + f'<th class="hide-s">Snaps</th></tr></thead><tbody>{trs}</tbody></table></div>')


_cloud = []


def cloud():
    """The app's accounts backend (CLOUD in index.html: project URL and publishable key), or None without one. The pages
    ask it for their comment count; a page carries the count and a link only, never the comments, so what people post
    isn't served to search engines from here."""
    if not _cloud:
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            m = re.search(r"const CLOUD = \{ url: '([^']*)', key: '([^']*)' \}", f.read())
        if not m:
            print("player_pages.py: no CLOUD in index.html, so no comment counts", file=sys.stderr)
        _cloud.append(m.groups() if m and all(m.groups()) else None)
    return _cloud[0]


def talk_script(sid):
    c = cloud()
    if not c:
        return ""
    return (f'fetch({json.dumps(c[0] + "/rest/v1/discussion_counts?select=n&player_id=eq." + sid)},{{headers:{{apikey:{json.dumps(c[1])}}}}})'
            f'.then(r=>r.ok?r.json():null).then(j=>{{const n=j&&j[0]&&j[0].n;if(!n)return;'
            f'document.getElementById("talk-n").textContent=n+(n===1?" comment":" comments");document.getElementById("talk").hidden=false}}).catch(()=>{{}});')


def player_page(sid, h, info, slug, season):
    name, pos, team = h["name"], h["pos"], info[2] if info else None
    espn = info[3] if info else None
    seasons = rows_of(h["scols"], h["seasons"])
    last = seasons[-1]
    done = [s for s in seasons if s["season"] < season]
    best = max(done, key=lambda s: s["ppr"], default=None)
    where = f"{POS_WORD[pos]} for the {TEAM_NAME[team]}" if team in TEAM_NAME else f"free-agent {POS_WORD[pos]}"
    span = f"{seasons[0]['season']}–{last['season']}" if len(seasons) > 1 else str(last["season"])
    intro = (f"{esc(name)} is a {where}. His fantasy football stats season by season ({span}), where he finished at {pos} each year, and his "
             f"game logs, in PPR scoring. For this week’s projection, matchup and Benny’s start/sit call, open him in Benny’s Picks.")
    facts = []
    if last["season"] == season:
        facts.append(f'{season} so far: {last["gp"]} game{"s" if last["gp"] != 1 else ""}, {last["ppr"] / max(1, last["gp"]):.1f} PPR points a game, {pos}{last["rank"]} in total points')
    if best:
        facts.append(f'Best season: {best["season"]}, {best["ppr"]:.1f} points ({pos}{best["rank"]})')
    img = f'<img src="{esc(HEADSHOT.format(espn))}" alt="{esc(name)}" width="110" height="80" loading="lazy">' if espn else ""
    body = [f'<div class="phead">{img}<div><strong>{esc(POS_NAME[pos][:-1])} · {esc(TEAM_NAME.get(team, "Free agent"))}</strong>'
            + "".join(f'<p class="small">{esc(f)}.</p>' for f in facts) + "</div></div>",
            f'<div class="now" id="now" hidden><span>Week <span id="now-w"></span> projection</span><b id="now-p"></b><span class="small muted">PPR points · likely <span id="now-r"></span> · '
            f'<a href="/#player/{esc(sid)}">why, and how he fits your lineup</a></span></div>',
            '<section class="news" id="news" hidden><h2>Latest news</h2><ul id="news-l"></ul></section>',
            *([f'<p class="talk" id="talk" hidden><a href="/#player/{esc(sid)}/talk">💬 <span id="talk-n"></span>: join the discussion →</a></p>'] if cloud() else []),
            f'<h2 id="seasons">Fantasy stats by season</h2>{season_table(h)}']
    logs = [s for s in (season, season - 1) if h["games"].get(str(s))]
    for s in logs:
        body.append(f'<h2 id="games-{s}">{s} game log</h2>{game_table(h, s)}')
    body.append('<p class="small muted" style="margin:0">Regular season only, from nflverse box scores. PPR points count an interception as −1 '
                '(Sleeper’s scoring). Snaps: his share of his team’s offensive snaps.</p>')
    path = f"/players/{slug}/"
    ld = {"@context": "https://schema.org", "@type": "ProfilePage", "url": SITE + path, "name": f"{name} fantasy football stats",
          "mainEntity": {"@type": "Person", "name": name, **({"image": HEADSHOT.format(espn)} if espn else {}),
                         **({"memberOf": {"@type": "SportsTeam", "name": TEAM_NAME[team]}} if team in TEAM_NAME else {})},
          "isPartOf": {"@type": "WebSite", "name": "Benny’s Picks", "url": SITE + "/"}}
    script = (f'<script>fetch("/model/proj.json").then(r=>r.json()).then(j=>{{const x=j.ids&&j.ids[{json.dumps(sid)}];if(!x||x[0]==null)return;'
              f'const f=v=>Math.max(0,v).toFixed(1);document.getElementById("now-w").textContent=j.week;document.getElementById("now-p").textContent=f(x[0]);'
              f'document.getElementById("now-r").textContent=f(x[0]-.674*x[2])+"–"+f(x[0]+.674*x[2]);document.getElementById("now").hidden=false}}).catch(()=>{{}});'
              # his latest news (scripts/news.py), filled in here so the page itself only changes about weekly
              f'fetch("/news/players/"+{json.dumps(sid)}+".json").then(r=>r.ok?r.json():null).then(j=>{{const it=j&&j.items||[];if(!it.length)return;'
              f'const l=document.getElementById("news-l");for(const i of it.slice(0,5)){{const li=document.createElement("li"),b=document.createElement((i.url||"").startsWith("https://")?"a":"b");'
              f'b.textContent=i.title;if(b.tagName==="A"){{b.href=i.url;b.rel="noopener";b.style.fontWeight="600";b.style.display="block"}}const m=document.createElement("span");m.className="small muted";'
              f'm.textContent=[i.sub,i.src,new Date(i.t).toLocaleDateString([],{{month:"short",day:"numeric"}})].filter(Boolean).join(" · ");li.append(b,m);l.append(li)}}'
              f'document.getElementById("news").hidden=false}}).catch(()=>{{}});'
              # how many comments he has (the comments themselves stay in the app)
              + talk_script(sid) + '</script>')
    top = f"{best['season']} {pos}{best['rank']}" if best else f"{season} {pos}{last['rank']}"
    return page(None, {}, f"{name} Fantasy Stats, Game Log & Projections | Benny’s Picks",
                f"{name} ({pos}, {team or 'FA'}) fantasy football stats: season-by-season PPR points and finishes ({top}), game logs, and this week’s projection.",
                f"{name} fantasy stats", intro, "\n".join(body) + script,
                (f"See {esc(name)}’s projection this week, why, and whether to start him on your team.", f"#player/{sid}", "Open in Benny’s Picks"),
                path=path, ld=ld, image=PREVIEW.format(quote(sid, safe="")), head=CSS)


def directory_page(entries):
    body = []
    for pos in POS:
        group = sorted((e for e in entries if e[1] == pos), key=lambda e: (e[2] or "ZZ", e[0]))
        if not group:
            continue
        links, cur = [], None
        for name, _, team, slug in group:
            if team != cur:
                cur = team
                links.append(f'<h3>{esc(TEAM_NAME.get(team, "Free agents"))}</h3>')
            links.append(f'<a href="/players/{slug}/">{esc(name)}</a>')
        body.append(f'<h2 id="{pos.lower()}">{POS_NAME[pos]}</h2><div class="dir">{"".join(links)}</div>')
    jump = '<div class="jump">' + "".join(f'<a href="#{p.lower()}">{POS_NAME[p]}</a>' for p in POS) + "</div>"
    return page(None, {}, "NFL Player Fantasy Stats & Game Logs: QB, RB, WR, TE | Benny’s Picks",
                "Fantasy football stats, season finishes and game logs for every NFL quarterback, running back, wide receiver and tight end, by team.",
                "NFL player fantasy stats", "Every quarterback, running back, wide receiver and tight end on an NFL team, by position and team. Each page has "
                "his fantasy points and finish season by season, his game logs, and this week’s projection.",
                jump + "\n".join(body), ("Search any player in Benny’s Picks for his projection, matchup and start/sit call.", "#players", "Search players"),
                path="/players/", head=CSS)


def write(path, text):
    """Write a file only when its text changed; True when it did."""
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=ROOT)
    a = ap.parse_args()
    data_dir = os.path.join(ROOT, "players", "data")
    with open(os.path.join(ROOT, "share-players.json"), encoding="utf-8") as f:
        share = json.load(f)["p"]
    with open(os.path.join(ROOT, "snapshot.json"), encoding="utf-8") as f:
        snap = json.load(f)
    season = int(snap["season"])
    projected = {r[0] for r in snap["proj"] if r[2] in POS}
    slug_path = os.path.join(a.out, "players", "slugs.json")
    try:
        with open(slug_path, encoding="utf-8") as f:
            slugs = json.load(f).get("s", {})
    except (OSError, ValueError):
        slugs = {}
    used = set(slugs.values())

    entries, wrote = [], 0
    for fn in sorted(os.listdir(data_dir)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        with open(os.path.join(data_dir, fn), encoding="utf-8") as f:
            h = json.load(f)
        sid, info = h["id"], share.get(h["id"])
        team = info[2] if info else None
        if h["pos"] not in POS or not h["seasons"] or not (team or sid in projected):
            continue
        if sid not in slugs:
            base = slugify(h["name"])
            for cand in (base, f"{base}-{h['pos'].lower()}-{(team or 'fa').lower()}", f"{base}-{sid}"):
                if cand not in used:
                    slugs[sid] = cand
                    used.add(cand)
                    break
        slug = slugs[sid]
        wrote += write(os.path.join(a.out, "players", slug, "index.html"), player_page(sid, h, info, slug, season))
        entries.append((h["name"], h["pos"], team, slug))
    wrote += write(os.path.join(a.out, "players", "index.html"), directory_page(entries))
    write(slug_path, json.dumps({"s": dict(sorted(slugs.items()))}, separators=(",", ":"), ensure_ascii=False))
    print(f"Player pages: {len(entries)} players, {wrote} files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
