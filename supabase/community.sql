-- Benny's Picks community: a discussion on every player's page and card, reactions, reports and moderation.
-- Run once in Supabase → SQL Editor, after schema.sql. Safe to re-run.
-- Then make yourself a moderator (your id is under Authentication → Users):
--   insert into public.admins (user_id) values ('<your auth user id>');
--
-- Unlike every table in schema.sql, these are shared: anyone can read the discussion with the publishable key, and any
-- signed-in account can post. So the database, not the page, enforces every rule: who may write what (row-level
-- security), which columns may change (column grants), how much (the cap triggers) and what a row may hold (checks).
-- The page only decides which buttons to show.

begin;

-- ---------- Moderators and banned accounts ----------
-- Neither table has a policy, so only the SQL editor (and the service role) can read or change them: nobody can make
-- themselves a moderator or lift their own ban through the API. The functions take no argument, so they can't be used to
-- ask about anyone else; calling them as (select public.is_admin()) in a policy runs them once per query, not per row.
create table if not exists public.admins (
  user_id uuid primary key references auth.users (id) on delete cascade,
  created_at timestamptz not null default now()
);
alter table public.admins enable row level security;
revoke all on public.admins from anon, authenticated;

create table if not exists public.bans (
  user_id uuid primary key references auth.users (id) on delete cascade,
  reason text,
  created_at timestamptz not null default now()
);
alter table public.bans enable row level security;
revoke all on public.bans from anon, authenticated;

create or replace function public.is_admin() returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.admins where user_id = (select auth.uid()))
$$;
create or replace function public.is_banned() returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.bans where user_id = (select auth.uid()))
$$;
revoke all on function public.is_admin() from public;
revoke all on function public.is_banned() from public;
grant execute on function public.is_admin() to anon, authenticated;
grant execute on function public.is_banned() to anon, authenticated;

-- ---------- Profiles: the public name on a comment ----------
-- Letters, digits and underscores, 3 to 20 of them, unique ignoring case; a few names that would read as the site's own
-- are kept back. Changing it renames every comment, since comments point here.
create table if not exists public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  handle text not null check (handle ~ '^[A-Za-z0-9_]{3,20}$'),
  created_at timestamptz not null default now()
);
alter table public.profiles drop constraint if exists profiles_handle_reserved;
alter table public.profiles add constraint profiles_handle_reserved check (lower(handle) !~ '^(benny|bennys|bennyspicks|bennys_picks|admin|admins|moderator|mod|mods|support|staff|official)$');
create unique index if not exists profiles_handle_uniq on public.profiles (lower(handle));
alter table public.profiles enable row level security;
drop policy if exists "public read profiles" on public.profiles;
create policy "public read profiles" on public.profiles for select to anon, authenticated using (true);
drop policy if exists "own profile insert" on public.profiles;
create policy "own profile insert" on public.profiles for insert to authenticated
  with check ((select auth.uid()) = user_id and not (select public.is_banned()));
drop policy if exists "own profile update" on public.profiles;
create policy "own profile update" on public.profiles for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id and not (select public.is_banned()));
revoke insert, update, delete on public.profiles from anon;
revoke update on public.profiles from authenticated;
grant update (handle) on public.profiles to authenticated;

-- ---------- Comments ----------
-- One discussion per player (his Sleeper id; a D/ST's is its team), with one level of replies: a reply always hangs off
-- the comment that started the thread. season and week say when it was written, so an old take reads as old. Comments
-- can't be edited (delete and post again). A moderator hides a comment rather than deleting it, which keeps it for review.
create table if not exists public.comments (
  id uuid primary key default gen_random_uuid(),
  player_id text not null check (player_id ~ '^[A-Za-z0-9]{1,8}$'),
  parent_id uuid references public.comments (id) on delete cascade,
  author_id uuid not null references public.profiles (user_id) on delete cascade,
  body text not null check (char_length(btrim(body)) between 1 and 1000),
  season int check (season between 2019 and 2100),
  week int check (week between 0 and 22),
  hidden_at timestamptz,
  hidden_reason text check (char_length(hidden_reason) <= 200),
  created_at timestamptz not null default now(),
  constraint comments_parent_not_self check (parent_id is null or parent_id <> id)
);
create index if not exists comments_player_idx on public.comments (player_id, created_at desc);
create index if not exists comments_parent_idx on public.comments (parent_id);
create index if not exists comments_author_idx on public.comments (author_id, created_at desc);
create index if not exists comments_hidden_idx on public.comments (hidden_at) where hidden_at is not null;

/* Before a comment is saved: the server's clock and no moderation fields, whatever the page sent; a reply moves to the
   thread's first comment and its player; and the caps, so one account can't flood the discussion: 5 comments a minute,
   60 a day. Security definer so the counts include the author's hidden comments and the parent check sees a hidden
   parent (which can't be replied to). */
create or replace function public.comments_before_insert() returns trigger language plpgsql security definer set search_path = '' as $$
declare p record;
begin
  new.created_at := now(); new.hidden_at := null; new.hidden_reason := null;
  if new.parent_id is not null then
    select c.id, c.parent_id, c.player_id, c.hidden_at into p from public.comments c where c.id = new.parent_id;
    if not found or p.hidden_at is not null then raise exception 'That comment is no longer there' using errcode = 'check_violation'; end if;
    if p.parent_id is not null then
      select c.id, c.parent_id, c.player_id, c.hidden_at into p from public.comments c where c.id = p.parent_id;
      if not found or p.hidden_at is not null then raise exception 'That comment is no longer there' using errcode = 'check_violation'; end if;
    end if;
    new.parent_id := p.id; new.player_id := p.player_id;
  end if;
  if (select count(*) from public.comments c where c.author_id = new.author_id and c.created_at > now() - interval '1 minute') >= 5 then
    raise exception 'Slow down: at most 5 comments a minute' using errcode = 'check_violation';
  end if;
  if (select count(*) from public.comments c where c.author_id = new.author_id and c.created_at > now() - interval '1 day') >= 60 then
    raise exception 'That''s the limit of 60 comments a day' using errcode = 'check_violation';
  end if;
  return new;
end $$;
drop trigger if exists comments_insert on public.comments;
create trigger comments_insert before insert on public.comments for each row execute function public.comments_before_insert();

/* Hiding and restoring: restoring clears the moderator's note (it would otherwise show once the comment is back), and
   hiding a thread's first comment hides its replies too, marked '__parent' so restoring it brings back exactly those. */
create or replace function public.comments_before_update() returns trigger language plpgsql set search_path = '' as $$
begin
  if new.hidden_at is null then new.hidden_reason := null; end if;
  return new;
end $$;
drop trigger if exists comments_update on public.comments;
create trigger comments_update before update on public.comments for each row execute function public.comments_before_update();
create or replace function public.comments_after_update() returns trigger language plpgsql set search_path = '' as $$
begin
  if new.parent_id is null and new.hidden_at is distinct from old.hidden_at then
    if new.hidden_at is not null then
      update public.comments set hidden_at = new.hidden_at, hidden_reason = '__parent' where parent_id = new.id and hidden_at is null;
    else
      update public.comments set hidden_at = null where parent_id = new.id and hidden_reason = '__parent';
    end if;
  end if;
  return null;
end $$;
drop trigger if exists comments_hide_thread on public.comments;
create trigger comments_hide_thread after update of hidden_at on public.comments for each row execute function public.comments_after_update();

alter table public.comments enable row level security;
drop policy if exists "public read comments" on public.comments;
create policy "public read comments" on public.comments for select to anon, authenticated
  using (hidden_at is null or (select public.is_admin()));
drop policy if exists "post as yourself" on public.comments;
create policy "post as yourself" on public.comments for insert to authenticated
  with check ((select auth.uid()) = author_id and not (select public.is_banned()));
drop policy if exists "delete own or moderate" on public.comments;
create policy "delete own or moderate" on public.comments for delete to authenticated
  using ((select auth.uid()) = author_id or (select public.is_admin()));
drop policy if exists "moderators hide" on public.comments;
create policy "moderators hide" on public.comments for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
-- a policy says which rows; the grant says which columns: without it the moderator policy would also allow rewriting
-- a comment's text or author
revoke insert, update, delete on public.comments from anon;
revoke update on public.comments from authenticated;
grant update (hidden_at, hidden_reason) on public.comments to authenticated;

-- ---------- Reactions ----------
-- One per person on a comment or on a news item (scripts/news.py's item id; news lives in a file, so no foreign key).
-- Changing your reaction is delete-then-insert. The unique indexes are partial because the unused target is null, and
-- nulls never collide in a plain unique index.
create table if not exists public.reactions (
  id uuid primary key default gen_random_uuid(),
  comment_id uuid references public.comments (id) on delete cascade,
  news_id text check (news_id ~ '^[A-Za-z0-9_.:-]{1,80}$'),
  user_id uuid not null references auth.users (id) on delete cascade,
  emoji text not null check (emoji in ('👍', '🔥', '🤔', '😂', '📈', '📉')),
  created_at timestamptz not null default now(),
  constraint reactions_one_target check ((comment_id is not null)::int + (news_id is not null)::int = 1)
);
create unique index if not exists reactions_comment_user_uniq on public.reactions (comment_id, user_id) where comment_id is not null;
create unique index if not exists reactions_news_user_uniq on public.reactions (news_id, user_id) where news_id is not null;
create index if not exists reactions_user_idx on public.reactions (user_id, created_at desc);

create or replace function public.reactions_before_insert() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  new.created_at := now();
  if (select count(*) from public.reactions r where r.user_id = new.user_id and r.created_at > now() - interval '1 day') >= 500 then
    raise exception 'That''s the limit of 500 reactions a day' using errcode = 'check_violation';
  end if;
  return new;
end $$;
drop trigger if exists reactions_insert on public.reactions;
create trigger reactions_insert before insert on public.reactions for each row execute function public.reactions_before_insert();

alter table public.reactions enable row level security;
drop policy if exists "public read reactions" on public.reactions;
create policy "public read reactions" on public.reactions for select to anon, authenticated using (true);
drop policy if exists "react as yourself" on public.reactions;
create policy "react as yourself" on public.reactions for insert to authenticated
  with check ((select auth.uid()) = user_id and not (select public.is_banned()));
drop policy if exists "remove own reaction" on public.reactions;
create policy "remove own reaction" on public.reactions for delete to authenticated using ((select auth.uid()) = user_id);
revoke insert, update, delete on public.reactions from anon;
revoke update on public.reactions from authenticated;

-- ---------- Reports ----------
-- Anyone signed in can report a comment once while the report is open; moderators see and resolve them. No foreign key
-- to the comment, so the report stays as a record after the comment is deleted. Nobody can delete a report.
create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  target_kind text not null check (target_kind = 'comment'),
  target_id uuid not null,
  reporter_id uuid not null references auth.users (id) on delete cascade,
  reason text not null check (reason in ('spam', 'abuse', 'off-topic', 'misinformation', 'other')),
  note text check (char_length(note) <= 300),
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by uuid references auth.users (id) on delete set null
);
create unique index if not exists reports_open_uniq on public.reports (target_kind, target_id, reporter_id) where resolved_at is null;
create index if not exists reports_open_idx on public.reports (created_at desc) where resolved_at is null;

create or replace function public.reports_before_insert() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  new.created_at := now(); new.resolved_at := null; new.resolved_by := null;
  if (select count(*) from public.reports r where r.reporter_id = new.reporter_id and r.created_at > now() - interval '1 day') >= 30 then
    raise exception 'That''s the limit of 30 reports a day' using errcode = 'check_violation';
  end if;
  return new;
end $$;
drop trigger if exists reports_insert on public.reports;
create trigger reports_insert before insert on public.reports for each row execute function public.reports_before_insert();

alter table public.reports enable row level security;
drop policy if exists "own or moderator read reports" on public.reports;
create policy "own or moderator read reports" on public.reports for select to authenticated
  using ((select auth.uid()) = reporter_id or (select public.is_admin()));
drop policy if exists "report as yourself" on public.reports;
create policy "report as yourself" on public.reports for insert to authenticated
  with check ((select auth.uid()) = reporter_id and not (select public.is_banned()));
drop policy if exists "moderators resolve" on public.reports;
create policy "moderators resolve" on public.reports for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
revoke all on public.reports from anon;
revoke update, delete on public.reports from authenticated;
grant update (resolved_at, resolved_by) on public.reports to authenticated;

-- ---------- Reading helpers ----------
-- Comment counts per player (all time, and the last 7 days) for the counts on cards and "Most discussed". Runs as the
-- caller, so it counts only what they may read.
create or replace view public.discussion_counts with (security_invoker = on) as
  select player_id, count(*)::int as n, count(*) filter (where created_at > now() - interval '7 days')::int as n7, max(created_at) as last_at
  from public.comments where hidden_at is null group by player_id;
revoke all on public.discussion_counts from anon, authenticated;
grant select on public.discussion_counts to anon, authenticated;

-- Replies since a time in the threads you've posted in, by other people: the alerts bell.
create or replace function public.my_replies(since timestamptz) returns setof public.comments language sql stable security invoker set search_path = '' as $$
  select c.* from public.comments c
  where c.parent_id in (select coalesce(m.parent_id, m.id) from public.comments m where m.author_id = (select auth.uid()))
    and c.author_id <> (select auth.uid()) and c.created_at > since and c.hidden_at is null
  order by c.created_at desc limit 50
$$;
revoke all on function public.my_replies(timestamptz) from public, anon;
grant execute on function public.my_replies(timestamptz) to authenticated;

commit;
notify pgrst, 'reload schema';
