"""Checks on scripts/news.py's change detection, on small made-up inputs (no network).

Run: python -m pytest tests/test_news.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import news as N  # noqa: E402

NOW = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(hours=3)


def row(sid, name, pos="RB", team="ATL", inj=None, proj=12.0):
    return [sid, name, pos, team, inj, proj, "TB", 0]


def test_first_run_only_records():
    st = {}
    rows = [row("1", "Star Back", inj="Out", proj=0.5)]
    assert N.injury_events(st, rows, {"1": 15}, NOW) == []
    assert st["inj"] == {"1": "Out"}
    assert N.team_events(st, {"1": ["Star Back", "RB", "ATL", 1]}, {"1": 15}, NOW) == []
    assert N.depth_events(st, {"1": ["ATL", "RB", 1]}, {}, {"1": 15}, NOW) == []
    assert N.trend_events(st, [("1", 5000)], {}, NOW) == []


def test_injury_changes():
    st = {}
    rel = {"1": 15, "2": 15, "3": 15, "4": 0.5}
    N.injury_events(st, [row("1", "A", inj="Questionable"), row("2", "B"), row("3", "C", inj="Out"), row("4", "D")], rel, NOW)
    out = N.injury_events(st, [row("1", "A", inj="Out"), row("2", "B", inj="Questionable"), row("3", "C"), row("4", "D", inj="Out")], rel, LATER)
    by = {i["ids"][0]: i for i in out}
    assert by["1"]["title"] == "A listed Out" and by["1"]["sub"] == "was Questionable"
    assert by["2"]["sub"] == "new on the injury report"
    assert by["3"]["title"] == "C off the injury report"
    assert "4" not in by                     # doesn't matter enough to report
    # unchanged next run: nothing
    assert N.injury_events(st, [row("1", "A", inj="Out"), row("2", "B", inj="Questionable"), row("3", "C"), row("4", "D", inj="Out")], rel, LATER) == []


def test_new_player_isnt_news():
    st = {}
    N.injury_events(st, [row("1", "A")], {"1": 15, "9": 15}, NOW)
    assert N.injury_events(st, [row("1", "A"), row("9", "Rookie", inj="Questionable")], {"1": 15, "9": 15}, LATER) == []


def test_dropped_off_projections_keeps_status():
    st = {}
    N.injury_events(st, [row("1", "A", inj="IR")], {"1": 15}, NOW)
    N.injury_events(st, [], {"1": 15}, LATER)
    assert st["inj"] == {"1": "IR"}


def test_team_changes():
    st = {}
    rel = {"1": 10, "2": 10, "3": 10}
    N.team_events(st, {"1": ["A", "WR", "DAL", 1], "2": ["B", "WR", None, 2], "3": ["C", "RB", "NYJ", 3]}, rel, NOW)
    out = N.team_events(st, {"1": ["A", "WR", "NYJ", 1], "2": ["B", "WR", "KC", 2], "3": ["C", "RB", None, 3]}, rel, LATER)
    titles = sorted(i["title"] for i in out)
    assert titles == ["A joins NYJ", "B signs with KC", "C is a free agent"]


def test_depth_moves():
    st = {}
    rel = {"1": 10, "2": 10, "3": 1}
    N.depth_events(st, {"1": ["ATL", "RB", 2], "2": ["ATL", "RB", 1], "3": ["ATL", "WR", 5]}, {}, rel, NOW)
    out = N.depth_events(st, {"1": ["ATL", "RB", 1], "2": ["ATL", "RB", 2], "3": ["ATL", "WR", 3]}, {"1": "A", "2": "B", "3": "C"}, rel, LATER)
    by = {i["ids"][0]: i["title"] for i in out}
    assert by["1"].startswith("A moves up to RB1")
    assert by["2"].startswith("B drops to RB2")
    assert by["3"].startswith("C moves up to WR3")   # a new starter is news even before he matters
    # a team change is the team source's news, not a depth move
    assert N.depth_events(st, {"1": ["NYJ", "RB", 3]}, {}, rel, LATER) == []


def test_depth_chart_newest_snapshot_and_ids():
    f = pd.DataFrame({"dt": ["2026-10-05T06:00:00Z", "2026-10-06T06:00:00Z", "2026-10-06T06:00:00Z", "2026-10-06T06:00:00Z"],
                      "team": ["ATL"] * 4, "espn_id": [11, 11, 11, 22], "gsis_id": ["g1", "g1", "g1", "g2"],
                      "pos_abb": ["RB", "RB", "RB", "WR"], "pos_rank": [1, 3, 2, 1]})
    assert N.depth_chart(f, {"g2": "200"}, {"11": "100"}) == {"100": ["ATL", "RB", 2], "200": ["ATL", "WR", 1]}


def test_trending_entry():
    st = {}
    N.trend_events(st, [("1", 900), ("2", 800)], {}, NOW)
    out = N.trend_events(st, [("3", 1000), ("1", 900)], {"3": "Hot Pickup"}, LATER)
    assert [i["ids"] for i in out] == [["3"]] and "1,000" in out[0]["sub"]


def art(aid, headline, athletes, premium=False):
    return {"id": aid, "headline": headline, "published": "2026-10-06T20:50:56Z", "premium": premium,
            "links": {"web": {"href": f"https://www.espn.com/nfl/story/_/id/{aid}"}},
            "categories": [{"type": "athlete", "athleteId": a} for a in athletes] + [{"type": "league", "description": "NFL"}]}


def test_articles_map_espn_ids():
    espn2sid = {"301": "1", "302": "2", "303": "3", "304": "4", "305": "5", "306": "6"}
    names = {"1": "Jalen Hurts", "2": "B Two", "3": "C Three", "4": "D Four", "5": "E Five", "6": "F Six"}
    out = N.article_items([
        art(1, "Hurts limited in practice", [301, 999]),
        art(2, "Nobody we know", [999]),
        art(3, "Premium story", [301], premium=True),
        art(4, "Buzz: offense just got harder for Jalen Hurts", [301, 302, 303, 304, 305, 306]),
        art(5, "Week 5 buzz", [301, 302, 303, 304, 305, 306]),
    ], espn2sid, names)
    by = {i["id"]: i for i in out}
    assert set(by) == {"espn-1", "espn-4", "espn-5"}  # unknown players and premium stories dropped
    assert by["espn-1"]["ids"] == ["1"] and by["espn-1"]["src"] == "ESPN" and by["espn-1"]["url"].startswith("https://")
    assert by["espn-4"]["ids"] == ["1"]               # a roundup goes to the player its headline names
    assert by["espn-5"]["ids"] == []                  # or to nobody: it stays in the feed only


def test_merge_dedup_and_retention():
    old = [N.item("injury", "a", "2026-09-01T00:00:00Z", [("1", "A")], "old"), N.item("injury", "b", "2026-10-05T00:00:00Z", [("1", "A")], "b")]
    new = [N.item("injury", "b", "2026-10-06T00:00:00Z", [("1", "A")], "b again"), N.item("team", "c", "2026-10-06T01:00:00Z", [("1", "A")], "c")]
    items = N.merge(old, new, NOW)
    assert [i["id"] for i in items] == ["c", "b"]     # 14 days, newest first, an id once
    many = [N.item("trend", f"x{k}", N.iso(NOW - timedelta(minutes=k)), [], "x") for k in range(500)]
    assert len(N.merge([], many, NOW)) == N.FEED_MAX
    assert len(N.player_items([], many)) == N.PLAYER_MAX


def test_seen_ids_never_repeat():
    new = [N.item("injury", "a", N.iso(NOW), [], "a"), N.item("injury", "a", N.iso(NOW), [], "a"), N.item("injury", "b", N.iso(NOW), [], "b")]
    assert [i["id"] for i in N.fresh(new, ["b"])] == ["a"]
