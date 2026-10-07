"""supabase/community.sql against a throwaway Postgres, probed the way the page and a stranger with the publishable key
would: as anon, as signed-in people, as a moderator and as a banned account.

It's not Supabase: a stub stands in for its auth schema (auth.uid() reads request.jwt.claim.sub, as Supabase's does)
and its anon/authenticated roles. Every test runs twice: once with Supabase's usual default privileges (everything on
new tables), and once with none (a project made with "automatically expose new tables" off), so community.sql's own
grants have to be right and enough.

The database comes from PG_DSN (CI: a postgres service) or, locally, pgserver (pip install pgserver psycopg[binary]);
with neither the tests skip. Each test makes its own people, so the per-account caps never collide."""
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

SQL = (Path(__file__).resolve().parent.parent / "supabase" / "community.sql").read_text(encoding="utf-8")
SQL = SQL.replace("notify pgrst, 'reload schema';", "")

ROLES = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
end $$;
"""
STUB = """
grant usage on schema public to anon, authenticated;
create schema auth; grant usage on schema auth to anon, authenticated;
create table auth.users (id uuid primary key, created_at timestamptz not null default now());
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant execute on function auth.uid() to anon, authenticated;
create table public.entitlements (user_id uuid primary key references auth.users (id) on delete cascade, pro_until timestamptz);
alter table public.entitlements enable row level security;
"""
DEFAULTS = """
alter default privileges in schema public grant all on tables to anon, authenticated;
alter default privileges in schema public grant all on functions to anon, authenticated;
alter default privileges in schema public grant all on sequences to anon, authenticated;
"""


@pytest.fixture(scope="session")
def server():
    dsn = os.environ.get("PG_DSN")
    if dsn:
        yield dsn
        return
    pgserver = pytest.importorskip("pgserver")
    d = tempfile.mkdtemp(prefix="pgc-")
    srv = pgserver.get_server(d, cleanup_mode="stop")
    yield srv.get_uri()
    srv.cleanup()
    shutil.rmtree(d, ignore_errors=True)


class DB:
    def __init__(self, conn):
        self.c = conn

    def sql(self, q, args=None):
        """As the owner (the SQL editor)."""
        cur = self.c.execute(q, args)
        return cur.fetchall() if cur.description else cur.rowcount

    def as_(self, who, q, args=None):
        """As anon (who=None) or as a signed-in person, the way PostgREST runs a request."""
        with self.c.transaction():
            self.c.execute("set local role " + ("anon" if who is None else "authenticated"))
            self.c.execute("select set_config('request.jwt.claim.sub', %s, true)", (who or "",))
            cur = self.c.execute(q, args)
            return cur.fetchall() if cur.description else cur.rowcount

    def one(self, who, q, args=None):
        return self.as_(who, q, args)[0][0]

    def refused(self, who, q, args=None, says=None):
        with pytest.raises(psycopg.Error) as e:
            self.as_(who, q, args)
        if says:
            assert says in str(e.value), str(e.value)
        return e.value

    def person(self, admin=False, banned=False, profile=True, age_days=30):
        uid = str(uuid.uuid4())
        self.sql("insert into auth.users (id, created_at) values (%s, now() - make_interval(days => %s))", (uid, age_days))
        if profile:
            self.as_(uid, "insert into profiles (user_id, handle) values (auth.uid(), %s)", ("u" + uid.replace("-", "")[:12],))
        if admin:
            self.sql("insert into admins (user_id) values (%s)", (uid,))
        if banned:
            self.sql("insert into bans (user_id) values (%s)", (uid,))
        return uid

    def post(self, who, body="Start him", player="4046", parent=None):
        return str(self.one(who, "insert into comments (player_id, parent_id, author_id, body, season, week) values (%s, %s, auth.uid(), %s, 2026, 5) returning id",
                            (player, parent, body)))

    def row(self, cid):
        r = self.sql("select body, author_id, deleted_at, hidden_at, hidden_reason, parent_id from comments where id = %s", (cid,))
        return r[0] if r else None


@pytest.fixture(scope="module", params=["defaults", "strict"])
def db(server, request):
    name = f"community_{request.param}_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(server, autocommit=True) as admin:
        admin.execute(ROLES)
        admin.execute(f"create database {name}")
    dsn = server.rsplit("/", 1)[0] + "/" + name
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute(STUB + (DEFAULTS if request.param == "defaults" else ""))
    conn.execute(SQL)
    conn.execute(SQL)   # safe to re-run
    yield DB(conn)
    conn.close()
    with psycopg.connect(server, autocommit=True) as admin:
        admin.execute(f"drop database {name} with (force)")


# ---------- privileges ----------

def test_no_privileges_beyond_what_the_page_uses(db):
    for t in ("profiles", "comments", "reactions", "reports", "admins", "bans", "mod_log", "blocked_terms"):
        for r in ("anon", "authenticated"):
            for p in ("TRUNCATE", "TRIGGER", "REFERENCES"):
                assert not db.sql("select has_table_privilege(%s, %s, %s)", (r, "public." + t, p))[0][0], f"{r} {p} {t}"
    for t in ("reports", "admins", "bans", "mod_log", "blocked_terms"):
        db.refused(None, f"select * from {t}")
    for t in ("admins", "bans", "blocked_terms"):
        db.refused(db.person(), f"select * from {t}")


# ---------- profiles ----------

def test_profiles(db):
    a, b, x = db.person(profile=False), db.person(), db.person(profile=False, banned=True)
    db.as_(a, "insert into profiles (user_id, handle) values (auth.uid(), 'alice_' || substr(md5(auth.uid()::text), 1, 6))")
    h = db.one(a, "select handle from profiles where user_id = auth.uid()")
    db.refused(b, "update profiles set handle = %s where user_id = auth.uid()", (h.upper(),))   # unique ignoring case
    db.refused(a, "insert into profiles (user_id, handle) values (%s, 'xxxxx')", (x,))          # someone else's
    db.refused(x, "insert into profiles (user_id, handle) values (auth.uid(), 'spammer1')")    # banned
    c = db.person(profile=False)
    db.refused(c, "insert into profiles (user_id, handle) values (auth.uid(), 'Benny')")       # reserved
    db.refused(a, "update profiles set handle = 'a b' where user_id = auth.uid()")             # bad characters
    assert db.as_(a, "update profiles set handle = %s where user_id = %s returning handle", ("pwned_" + b[:4], b)) == []
    db.refused(a, "update profiles set created_at = now() where user_id = auth.uid()")
    old = db.person(profile=False)   # a backdated name doesn't make a new account look old
    assert db.one(old, "insert into profiles (user_id, handle, created_at) values (auth.uid(), %s, '2000-01-01') returning created_at > now() - interval '1 minute'",
                  ("n" + old.replace("-", "")[:12],))
    db.refused(a, "delete from profiles where user_id = auth.uid()")
    assert db.one(None, "select count(*) from profiles where user_id = %s", (a,)) == 1


def test_renaming(db):
    a = db.person(profile=False)
    db.as_(a, "insert into profiles (user_id, handle) values (auth.uid(), 'first_' || substr(md5(auth.uid()::text), 1, 6))")
    h = db.one(a, "select handle from profiles where user_id = auth.uid()")
    assert db.one(None, "select handle_changed_at is null from profiles where user_id = %s", (a,))   # the first name is free
    # a change of letter case only is free, and doesn't start the clock
    db.as_(a, "update profiles set handle = %s where user_id = auth.uid()", (h.upper(),))
    assert db.one(None, "select handle_changed_at is null from profiles where user_id = %s", (a,))
    new = "second_" + a.replace("-", "")[:6]
    db.as_(a, "update profiles set handle = %s where user_id = auth.uid()", (new,))
    assert db.one(None, "select handle from profiles where user_id = %s", (a,)) == new
    assert db.one(None, "select handle_changed_at > now() - interval '1 minute' from profiles where user_id = %s", (a,))
    # a second change inside 30 days is refused, with the date
    e = db.refused(a, "update profiles set handle = %s where user_id = auth.uid()", ("third_" + a.replace("-", "")[:6],), says="You can change your username again on")
    assert e.sqlstate == "23514"
    # the page can't write the clock, and a case-only change still works inside the window
    db.refused(a, "update profiles set handle_changed_at = null where user_id = auth.uid()")
    db.as_(a, "update profiles set handle = %s where user_id = auth.uid()", (new.upper(),))
    # 30 days on, it works again
    db.sql("update profiles set handle_changed_at = now() - interval '31 days' where user_id = %s", (a,))
    db.as_(a, "update profiles set handle = %s where user_id = auth.uid()", ("third_" + a.replace("-", "")[:6],))
    # the blocked-word check still applies to a rename
    db.sql("insert into blocked_terms (term) values ('zzbadzz') on conflict do nothing")
    db.sql("update profiles set handle_changed_at = null where user_id = %s", (a,))
    db.refused(a, "update profiles set handle = 'xx_zzbadzz_xx' where user_id = auth.uid()")
    db.sql("delete from blocked_terms where term = 'zzbadzz'")


def test_profile_by_handle(db):
    a, b = db.person(), db.person(profile=False)
    db.as_(b, "insert into profiles (user_id, handle) values (auth.uid(), 'ab_' || substr(md5(auth.uid()::text), 1, 6))")
    hb = db.one(b, "select handle from profiles where user_id = auth.uid()")
    ha = db.one(a, "select handle from profiles where user_id = auth.uid()")
    c1, c2, c3 = db.post(a, "visible"), db.post(a, "will be hidden"), db.post(a, "will be deleted")
    db.sql("update comments set hidden_at = now() where id = %s", (c2,))
    db.sql("delete from comments where id = %s", (c3,))
    for who in (None, a, b):   # anyone can ask
        r = db.as_(who, "select user_id, handle, n_comments from profile_by_handle(%s)", (ha.upper(),))   # ignoring case
        assert len(r) == 1 and str(r[0][0]) == a and r[0][1] == ha and r[0][2] == 1
    assert db.as_(None, "select * from profile_by_handle('nobody_here')") == []
    # an underscore is not a wildcard: "ab_xxxxxx" must not match "abcxxxxxx"
    assert db.as_(None, "select * from profile_by_handle(%s)", (hb.replace("_", "%"),)) == []
    assert db.as_(None, "select * from profile_by_handle(%s)", (hb.replace("_", "c"),)) == []
    assert len(db.as_(None, "select * from profile_by_handle(%s)", (hb,))) == 1


# ---------- posting ----------

def test_posting(db):
    a, b, x = db.person(), db.person(), db.person(banned=True)
    db.refused(None, "insert into comments (player_id, author_id, body) values ('4046', %s, 'hi')", (a,))
    root = db.one(a, "insert into comments (player_id, author_id, body, created_at) values ('4046', auth.uid(), 'Start him', '2020-01-01') returning id")
    assert db.one(None, "select created_at > now() - interval '1 minute' from comments where id = %s", (root,))
    db.refused(a, "insert into comments (player_id, author_id, body) values ('4046', %s, 'fake')", (b,))
    db.refused(a, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), '   ')")
    db.refused(a, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), %s)", ("x" * 1001,))
    db.refused(a, "insert into comments (player_id, author_id, body) values ('<script>', auth.uid(), 'x')")
    assert db.one(a, "insert into comments (player_id, author_id, body, hidden_at, deleted_at) values ('4046', auth.uid(), 'x', now(), now()) returning hidden_at is null and deleted_at is null")
    # a reply moves to its thread's first comment and that comment's player
    rep = db.one(b, "insert into comments (player_id, parent_id, author_id, body) values ('9999', %s, auth.uid(), 'Agree') returning id", (root,))
    assert db.row(rep)[5] == root and db.one(None, "select player_id from comments where id = %s", (rep,)) == "4046"
    assert db.one(a, "insert into comments (player_id, parent_id, author_id, body) values ('4046', %s, auth.uid(), 'thanks') returning parent_id", (rep,)) == root
    assert db.one(None, "select count(*) from comments where id = %s or parent_id = %s", (root, root)) == 3
    db.refused(a, "update comments set body = 'edited' where id = %s", (root,))
    assert db.as_(a, "update comments set hidden_at = now() where id = %s returning id", (root,)) == []
    db.refused(x, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), 'spam')")
    assert db.as_(a, "delete from comments where id = %s returning id", (rep,)) == []      # someone else's


def test_counts_and_my_replies(db):
    a, b = db.person(), db.person()
    root = db.post(a, player="DAL")
    db.post(b, parent=root)
    db.post(a, parent=root)
    assert db.as_(None, "select n, n7 from discussion_counts where player_id = 'DAL'") == [(3, 3)]
    assert db.one(a, "select count(*) from my_replies(now() - interval '1 hour')") == 1
    assert db.one(b, "select count(*) from my_replies(now() - interval '1 hour')") == 1
    db.refused(None, "select * from my_replies(now())")


def test_rate_limit(db):
    a = db.person()
    for k in range(5):
        db.post(a, f"take {k}")
    db.refused(a, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), 'one too many')", says="at most 5 comments a minute")


# ---------- hiding ----------

def test_hiding_a_thread(db):
    a, b, m = db.person(), db.person(), db.person(admin=True)
    root = db.post(a, player="KC")
    db.post(b, parent=root)
    db.post(a, parent=root)
    assert db.as_(m, "update comments set hidden_at = now(), hidden_reason = 'rude' where id = %s returning id", (root,)) != []
    assert db.one(None, "select count(*) from comments where player_id = 'KC'") == 0
    assert db.one(m, "select count(*) from comments where player_id = 'KC' and hidden_at is not null") == 3
    assert db.one(None, "select count(*) from comments where hidden_reason is not null") == 0
    db.refused(b, "insert into comments (player_id, parent_id, author_id, body) values ('KC', %s, auth.uid(), 'x')", (root,))
    db.refused(m, "update comments set body = 'x' where id = %s", (root,))
    assert db.as_(m, "update comments set hidden_at = null where id = %s returning hidden_reason", (root,)) == [(None,)]
    assert db.one(None, "select count(*) from comments where player_id = 'KC'") == 3
    assert db.one(m, "select count(*) from comments where player_id = 'KC' and hidden_reason is not null") == 0


# ---------- reactions ----------

def test_reactions(db):
    a, b = db.person(), db.person()
    root = db.post(a)
    rep = db.post(b, parent=root)
    db.as_(a, "insert into reactions (comment_id, user_id, emoji) values (%s, auth.uid(), '🔥')", (root,))
    db.as_(b, "insert into reactions (comment_id, user_id, emoji) values (%s, auth.uid(), '🔥')", (root,))
    db.refused(a, "insert into reactions (comment_id, user_id, emoji) values (%s, auth.uid(), '👍')", (root,))
    nid = "inj-8484-Out-" + a[:8]
    db.as_(a, "insert into reactions (news_id, user_id, emoji) values (%s, auth.uid(), '📉')", (nid,))
    db.refused(a, "insert into reactions (comment_id, news_id, user_id, emoji) values (%s, 'x', auth.uid(), '🔥')", (rep,))
    db.refused(a, "insert into reactions (comment_id, user_id, emoji) values (%s, auth.uid(), '💩')", (rep,))
    db.refused(a, "insert into reactions (comment_id, user_id, emoji) values (%s, %s, '🔥')", (rep, b))
    assert db.as_(b, "delete from reactions where user_id = %s returning id", (a,)) == []
    assert db.as_(None, "select emoji, n from reaction_counts where comment_id = %s", (root,)) == [("🔥", 2)]
    assert db.as_(None, "select emoji, n from reaction_counts where news_id = %s", (nid,)) == [("📉", 1)]
    assert len(db.as_(a, "delete from reactions where news_id = %s and user_id = auth.uid() returning id", (nid,))) == 1
    db.refused(a, "update reactions set emoji = '👍' where user_id = auth.uid()")


# ---------- reports ----------

def test_reports(db):
    a, b, m = db.person(), db.person(), db.person(admin=True)
    root = db.post(a)
    rep = db.post(b, parent=root)
    db.as_(b, "insert into reports (target_kind, target_id, reporter_id, reason, note) values ('comment', %s, auth.uid(), 'abuse', 'see the last line')", (root,))
    db.refused(b, "insert into reports (target_kind, target_id, reporter_id, reason) values ('comment', %s, auth.uid(), 'spam')", (root,))
    db.refused(b, "insert into reports (target_kind, target_id, reporter_id, reason, note) values ('comment', %s, auth.uid(), 'spam', %s)", (rep, "x" * 301))
    assert db.one(a, "select count(*) from reports") == 0
    assert db.one(m, "select count(*) from reports where target_id = %s", (root,)) == 1
    assert db.as_(b, "update reports set resolved_at = now() returning id") == []
    assert db.one(a, "insert into reports (target_kind, target_id, reporter_id, reason, resolved_at) values ('comment', %s, auth.uid(), 'spam', now()) returning resolved_at", (rep,)) is None
    assert len(db.as_(m, "update reports set resolved_at = now(), resolved_by = auth.uid() where target_id = %s returning id", (root,))) == 1
    db.refused(m, "update reports set reason = 'other'")
    db.refused(m, "delete from reports")


def test_moderator_tables(db):
    a, m = db.person(), db.person(admin=True)
    db.refused(a, "insert into admins values (auth.uid())")
    db.refused(a, "delete from bans")
    assert db.one(a, "select public.is_admin()") is False
    assert db.one(m, "select public.is_admin()") is True
    assert db.one(None, "select public.is_admin()") is False


# ---------- deleting ----------

def test_deleting_keeps_other_peoples_replies(db):
    a, b = db.person(), db.person()
    root = db.post(a, player="BUF")
    rep = db.post(b, parent=root)
    db.as_(b, "insert into reactions (comment_id, user_id, emoji) values (%s, auth.uid(), '👍')", (root,))
    # the first release's page deletes directly: the row stays as a placeholder, and the delete reports no row
    assert db.as_(a, "delete from comments where id = %s returning id", (root,)) == []
    body, author, deleted, *_ = db.row(root)
    assert body == "" and author is None and deleted is not None
    assert db.one(None, "select count(*) from comments where id = %s", (rep,)) == 1
    assert db.one(None, "select count(*) from reactions where comment_id = %s", (root,)) == 0
    assert db.as_(None, "select n from discussion_counts where player_id = 'BUF'") == [(1,)]
    db.refused(a, "insert into comments (player_id, parent_id, author_id, body) values ('BUF', %s, auth.uid(), 'x')", (root,), says="was deleted")
    db.refused(b, "select public.delete_comment(%s)", (root,))     # a placeholder belongs to nobody
    # the last reply goes, and the placeholder with it
    assert db.one(b, "select public.delete_comment(%s)", (rep,)) == "deleted"
    assert db.row(root) is None


def test_deleting_without_other_replies(db):
    a, b = db.person(), db.person()
    lone = db.post(a)
    assert db.one(a, "select public.delete_comment(%s)", (lone,)) == "deleted" and db.row(lone) is None
    own = db.post(a)
    mine = db.post(a, parent=own)
    assert db.one(a, "select public.delete_comment(%s)", (own,)) == "deleted"
    assert db.row(own) is None and db.row(mine) is None
    kept = db.post(a)
    db.post(b, parent=kept)
    assert db.one(a, "select public.delete_comment(%s)", (kept,)) == "kept"
    db.refused(b, "select public.delete_comment(%s)", (db.post(a),), says="can't do that")


def test_hidden_replies_dont_keep_a_thread(db):
    a, b, m = db.person(), db.person(), db.person(admin=True)
    root = db.post(a)
    rep = db.post(b, parent=root)
    db.as_(m, "update comments set hidden_at = now(), hidden_reason = 'spam' where id = %s", (rep,))
    assert db.one(a, "select public.delete_comment(%s)", (root,)) == "deleted"
    assert db.row(rep) is None


def test_moderator_deletes_a_thread(db):
    a, b, m = db.person(), db.person(), db.person(admin=True)
    root = db.post(a)
    rep = db.post(b, parent=root)
    assert db.one(m, "select public.delete_comment(%s)", (root,)) == "kept"
    assert db.one(m, "select public.delete_comment(%s)", (root,)) == "deleted"   # the placeholder: the whole thread
    assert db.row(root) is None and db.row(rep) is None


def test_deleting_an_account(db):
    a, b = db.person(), db.person()
    root = db.post(a, player="MIA")
    theirs = db.post(b, parent=root)
    other = db.post(b, player="MIA")
    mine = db.post(a, parent=other)
    lone = db.post(a, player="MIA")
    db.sql("delete from auth.users where id = %s", (a,))
    assert db.one(None, "select count(*) from profiles where user_id = %s", (a,)) == 0
    assert db.one(None, "select count(*) from comments where author_id = %s", (a,)) == 0
    assert db.row(root)[0] == "" and db.row(root)[1] is None
    assert db.row(theirs) is not None and db.row(other) is not None
    assert db.row(mine) is None and db.row(lone) is None


# ---------- moderation log and bans ----------

def log(db, target):
    return [r[0] for r in db.sql("select action from mod_log where target_id = %s order by id", (target,))]


def test_moderation_log(db):
    a, b, m = db.person(), db.person(), db.person(admin=True)
    root = db.post(a)
    db.post(b, parent=root)
    db.as_(m, "update comments set hidden_at = now(), hidden_reason = 'rude' where id = %s", (root,))
    db.as_(m, "update comments set hidden_at = null where id = %s", (root,))
    assert log(db, root) == ["hide", "restore"]        # once each, not once per reply
    db.as_(b, "insert into reports (target_kind, target_id, reporter_id, reason) values ('comment', %s, auth.uid(), 'spam')", (root,))
    c = db.person()
    db.as_(c, "insert into reports (target_kind, target_id, reporter_id, reason) values ('comment', %s, auth.uid(), 'abuse')", (root,))
    db.as_(m, "update reports set resolved_at = now(), resolved_by = auth.uid() where target_id = %s and resolved_at is null", (root,))
    assert log(db, root) == ["hide", "restore", "dismiss"]
    other = db.post(b, "a rude take")
    db.as_(m, "select public.delete_comment(%s)", (other,))
    assert log(db, other) == ["delete"] and db.sql("select note from mod_log where target_id = %s", (other,)) == [("a rude take",)]
    own = db.post(m)
    db.as_(m, "select public.delete_comment(%s)", (own,))
    assert log(db, own) == []                           # a moderator deleting their own comment isn't moderation
    assert db.one(m, "select count(*) from mod_log where target_id = %s", (root,)) == 3
    assert db.one(a, "select count(*) from mod_log") == 0
    db.refused(m, "insert into mod_log (action, target_kind, target_id) values ('ban', 'user', %s)", (a,))
    db.refused(m, "delete from mod_log")


def test_bans(db):
    a, b, m = db.person(), db.person(), db.person(admin=True)
    root = db.post(a)
    rep = db.post(b, parent=root)
    mine = db.post(a, parent=db.post(b))
    db.refused(b, "select public.ban_user(%s, 'spam', false)", (a,), says="Only moderators")
    db.refused(None, "select public.ban_user(%s, 'spam', false)", (a,))
    db.refused(m, "select public.ban_user(auth.uid(), 'oops', false)", says="can't be banned")
    db.as_(m, "select public.ban_user(%s, 'spam', true)", (a,))
    assert db.row(root)[4] == "banned" and db.row(rep)[4] == "__parent" and db.row(mine)[4] == "banned"
    db.refused(a, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), 'back')")
    db.refused(a, "insert into reactions (comment_id, user_id, emoji) values (%s, auth.uid(), '🔥')", (rep,))
    handle = db.one(None, "select handle from profiles where user_id = %s", (a,))
    assert (a, handle, "spam") in [(str(r[0]), r[1], r[2]) for r in db.as_(m, "select user_id, handle, reason from public.list_bans()")]
    db.refused(b, "select * from public.list_bans()")
    assert log(db, a) == ["ban"]                        # the hidden comments aren't logged one by one
    assert log(db, root) == []
    db.refused(b, "select public.unban_user(%s)", (a,))
    db.as_(m, "select public.unban_user(%s)", (a,))
    assert log(db, a) == ["ban", "unban"]
    db.post(a, "I'm back")
    assert db.row(root)[3] is not None                  # lifting the ban doesn't bring the comments back


# ---------- spam and content ----------

def test_links(db):
    a = db.person()
    db.post(a, "see https://example.com and www.example.org")
    db.refused(a, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), 'http://a.co http://b.co HTTPS://c.co')", says="At most 2 links")


def test_new_accounts(db):
    n = db.person(age_days=0)
    db.refused(n, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), 'buy at https://spam.example')", says="after their first day")
    for k in range(10):
        if k == 5:
            db.sql("update comments set created_at = now() - interval '2 hours' where author_id = %s", (n,))
        db.post(n, f"take {k}")
    db.sql("update comments set created_at = now() - interval '2 hours' where author_id = %s", (n,))
    db.refused(n, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), 'eleven')", says="10 comments on their first day")


def test_blocked_terms(db):
    term = "zq" + uuid.uuid4().hex[:6]
    db.sql("insert into blocked_terms values (%s)", (term,))
    try:
        a = db.person()
        db.refused(a, "insert into comments (player_id, author_id, body) values ('4046', auth.uid(), %s)", (f"what a {term.upper()}!",), says="isn't allowed")
        db.post(a, f"{term}s is a different word")
        db.refused(a, "update profiles set handle = %s where user_id = auth.uid()", (f"x_{term}_x",), says="name isn't available")
        with pytest.raises(psycopg.Error):
            db.sql("insert into blocked_terms values ('Bad*')")
    finally:
        db.sql("delete from blocked_terms where term = %s", (term,))
