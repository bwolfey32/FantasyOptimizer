-- Benny's Picks community: a discussion on every player's page and card, reactions, reports and moderation.
-- Run once in Supabase → SQL Editor, after schema.sql. Safe to re-run.
-- Then make yourself a moderator (your id is under Authentication → Users):
--   insert into public.admins (user_id) values ('<your auth user id>');
--
-- Unlike every table in schema.sql, these are shared: anyone can read the discussion with the publishable key, and any
-- signed-in account can post. So the database, not the page, enforces every rule: who may write what (row-level
-- security), which columns may change (column grants), how much (the cap triggers) and what a row may hold (checks).
-- The page only decides which buttons to show.
-- Each table grants exactly what the page uses rather than relying on the project's default privileges, which differ
-- between projects (one made with "automatically expose new tables" off grants nothing), and takes back the rest.

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

-- What moderators did: hides, restores, deletes of other people's comments (with the text), dismissed reports, bans
-- and unbans. Written only by this file's triggers and functions (nobody has insert); moderators read it in #mod.
create table if not exists public.mod_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor uuid references auth.users (id) on delete set null,
  action text not null check (action in ('hide', 'restore', 'delete', 'dismiss', 'ban', 'unban')),
  target_kind text not null check (target_kind in ('comment', 'user')),
  target_id uuid not null,
  note text check (char_length(note) <= 300)
);
create index if not exists mod_log_at_idx on public.mod_log (at desc);
alter table public.mod_log enable row level security;
drop policy if exists "moderators read the log" on public.mod_log;
create policy "moderators read the log" on public.mod_log for select to authenticated using ((select public.is_admin()));
revoke all on public.mod_log from anon, authenticated;
grant select on public.mod_log to authenticated;

-- Words no comment or public name may contain, added in the SQL editor (insert into public.blocked_terms values ('…')).
-- Lower case letters and digits, with single spaces for a phrase. Matched as whole words in comments and anywhere in a
-- name. No policy, so the list can't be read through the API.
create table if not exists public.blocked_terms (
  term text primary key check (term ~ '^[a-z0-9]+( [a-z0-9]+)*$')
);
alter table public.blocked_terms enable row level security;
revoke all on public.blocked_terms from anon, authenticated;
create or replace function public.has_blocked_term(t text) returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.blocked_terms b where lower(t) ~ ('\m' || b.term || '\M'))
$$;
revoke all on function public.has_blocked_term(text) from public, anon, authenticated;

-- Banning from #mod: a moderator bans (optionally hiding everything the account has posted) or lifts a ban, and sees
-- who is banned. Each refuses anyone who isn't a moderator, and each is logged.
create or replace function public.ban_user(uid uuid, reason text default null, hide_all boolean default false) returns void
  language plpgsql security definer set search_path = '' as $$
begin
  if not (select public.is_admin()) then raise exception 'Only moderators can do that' using errcode = '42501'; end if;
  if uid = (select auth.uid()) or exists (select 1 from public.admins a where a.user_id = uid) then
    raise exception 'Moderators can''t be banned' using errcode = 'check_violation';
  end if;
  insert into public.bans (user_id, reason) values (uid, left(reason, 200))
    on conflict (user_id) do update set reason = excluded.reason;
  if hide_all then
    update public.comments set hidden_at = now(), hidden_reason = 'banned' where author_id = uid and hidden_at is null;
  end if;
  insert into public.mod_log (actor, action, target_kind, target_id, note) values ((select auth.uid()), 'ban', 'user', uid, left(reason, 300));
end $$;
create or replace function public.unban_user(uid uuid) returns void language plpgsql security definer set search_path = '' as $$
begin
  if not (select public.is_admin()) then raise exception 'Only moderators can do that' using errcode = '42501'; end if;
  delete from public.bans where user_id = uid;
  if found then insert into public.mod_log (actor, action, target_kind, target_id) values ((select auth.uid()), 'unban', 'user', uid); end if;
end $$;
create or replace function public.list_bans() returns table (user_id uuid, handle text, reason text, created_at timestamptz)
  language plpgsql stable security definer set search_path = '' as $$
begin
  if not (select public.is_admin()) then raise exception 'Only moderators can do that' using errcode = '42501'; end if;
  return query select b.user_id, p.handle, b.reason, b.created_at from public.bans b
    left join public.profiles p on p.user_id = b.user_id order by b.created_at desc;
end $$;
revoke all on function public.ban_user(uuid, text, boolean) from public, anon;
revoke all on function public.unban_user(uuid) from public, anon;
revoke all on function public.list_bans() from public, anon;
grant execute on function public.ban_user(uuid, text, boolean) to authenticated;
grant execute on function public.unban_user(uuid) to authenticated;
grant execute on function public.list_bans() to authenticated;

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
revoke insert, update, delete, truncate, references, trigger on public.profiles from anon;
revoke update, delete, truncate, references, trigger on public.profiles from authenticated;
grant select on public.profiles to anon, authenticated;
grant insert on public.profiles to authenticated;
grant update (handle) on public.profiles to authenticated;

-- A name can't contain a blocked word anywhere (names run words together, like bad_guy). created_at is the server's
-- clock, whatever the page sent. The first name is free; after that a name can change once every 30 days (a change of
-- letter case only is always free). handle_changed_at is the trigger's own: no grant lets the page write it.
alter table public.profiles add column if not exists handle_changed_at timestamptz;
create or replace function public.profiles_before_write() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then new.created_at := now(); new.handle_changed_at := null;
  else
    new.created_at := old.created_at; new.handle_changed_at := old.handle_changed_at;
    if lower(new.handle) <> lower(old.handle) then
      if old.handle_changed_at is not null and old.handle_changed_at > now() - interval '30 days' then
        raise exception 'You can change your username again on %', to_char(old.handle_changed_at + interval '30 days', 'FMMon FMDD, YYYY') using errcode = 'check_violation';
      end if;
      new.handle_changed_at := now();
    end if;
  end if;
  if exists (select 1 from public.blocked_terms b where position(replace(b.term, ' ', '') in lower(new.handle)) > 0) then
    raise exception 'That name isn''t available. Try another.' using errcode = 'check_violation';
  end if;
  return new;
end $$;
drop trigger if exists profiles_write on public.profiles;
create trigger profiles_write before insert or update of handle on public.profiles for each row execute function public.profiles_before_write();
-- Deleting an account (delete_my_account in schema.sql removes the sign-in, and with it this row) deletes its comments
-- one by one first, so a thread other people replied to keeps their replies under a placeholder (comments_before_delete).
create or replace function public.profiles_before_delete() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  delete from public.comments where author_id = old.user_id;
  return old;
end $$;
drop trigger if exists profiles_delete on public.profiles;
create trigger profiles_delete before delete on public.profiles for each row execute function public.profiles_before_delete();

-- ---------- Comments ----------
-- One discussion per player (his Sleeper id; a D/ST's is its team), with one level of replies: a reply always hangs off
-- the comment that started the thread. season and week say when it was written, so an old take reads as old. Comments
-- can't be edited (delete and post again). A moderator hides a comment rather than deleting it, which keeps it for review.
-- Deleting a thread's first comment once other people have replied leaves a placeholder (deleted_at set, no text and no
-- author) so their replies stay; see comments_before_delete.
create table if not exists public.comments (
  id uuid primary key default gen_random_uuid(),
  player_id text not null check (player_id ~ '^[A-Za-z0-9]{1,8}$'),
  parent_id uuid references public.comments (id) on delete cascade,
  author_id uuid references public.profiles (user_id) on delete set null,
  body text not null,
  season int check (season between 2019 and 2100),
  week int check (week between 0 and 22),
  hidden_at timestamptz,
  hidden_reason text check (char_length(hidden_reason) <= 200),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  constraint comments_parent_not_self check (parent_id is null or parent_id <> id)
);
-- the table as first released had no placeholders (author required, deleting it took the replies): bring it up to date
alter table public.comments add column if not exists deleted_at timestamptz;
alter table public.comments alter column author_id drop not null;
alter table public.comments drop constraint if exists comments_author_id_fkey;
alter table public.comments add constraint comments_author_id_fkey foreign key (author_id) references public.profiles (user_id) on delete set null;
alter table public.comments drop constraint if exists comments_body_check;
alter table public.comments add constraint comments_body_check
  check (char_length(body) <= 1000 and (char_length(btrim(body)) >= 1 or (deleted_at is not null and body = '')));
alter table public.comments drop constraint if exists comments_placeholder;
alter table public.comments add constraint comments_placeholder check ((deleted_at is null) = (author_id is not null));
create index if not exists comments_player_idx on public.comments (player_id, created_at desc);
create index if not exists comments_parent_idx on public.comments (parent_id);
create index if not exists comments_author_idx on public.comments (author_id, created_at desc);
create index if not exists comments_hidden_idx on public.comments (hidden_at) where hidden_at is not null;

/* Before a comment is saved: the server's clock and no moderation fields, whatever the page sent; a reply moves to the
   thread's first comment and its player; and the caps, so one account can't flood the discussion: 5 comments a minute,
   60 a day, at most 2 links, and on an account's first day 10 comments and no links (most spam comes from accounts made
   to post it). Then the blocked words. Security definer so the counts include the author's hidden comments, the parent
   check sees a hidden parent (which can't be replied to), and it can read the account's age and the word list. */
create or replace function public.comments_before_insert() returns trigger language plpgsql security definer set search_path = '' as $$
declare p record; age interval; links int;
begin
  new.created_at := now(); new.hidden_at := null; new.hidden_reason := null; new.deleted_at := null;
  if new.parent_id is not null then
    select c.id, c.parent_id, c.player_id, c.hidden_at, c.deleted_at into p from public.comments c where c.id = new.parent_id;
    if not found or p.hidden_at is not null then raise exception 'That comment is no longer there' using errcode = 'check_violation'; end if;
    if p.parent_id is not null then
      select c.id, c.parent_id, c.player_id, c.hidden_at, c.deleted_at into p from public.comments c where c.id = p.parent_id;
      if not found or p.hidden_at is not null then raise exception 'That comment is no longer there' using errcode = 'check_violation'; end if;
    end if;
    if p.deleted_at is not null then raise exception 'That comment was deleted' using errcode = 'check_violation'; end if;
    new.parent_id := p.id; new.player_id := p.player_id;
  end if;
  if (select count(*) from public.comments c where c.author_id = new.author_id and c.created_at > now() - interval '1 minute') >= 5 then
    raise exception 'Slow down: at most 5 comments a minute' using errcode = 'check_violation';
  end if;
  if (select count(*) from public.comments c where c.author_id = new.author_id and c.created_at > now() - interval '1 day') >= 60 then
    raise exception 'That''s the limit of 60 comments a day' using errcode = 'check_violation';
  end if;
  links := (select count(*) from regexp_matches(new.body, '(https?://|www\.)', 'gi'));
  if links > 2 then raise exception 'At most 2 links in a comment' using errcode = 'check_violation'; end if;
  begin
    select now() - u.created_at into age from auth.users u where u.id = new.author_id;
  exception when insufficient_privilege then   -- if auth.users can't be read here, the public name's age stands in
    select now() - p.created_at into age from public.profiles p where p.user_id = new.author_id;
  end;
  if age < interval '1 day' then
    if links > 0 then raise exception 'New accounts can post links after their first day' using errcode = 'check_violation'; end if;
    if (select count(*) from public.comments c where c.author_id = new.author_id and c.created_at > now() - interval '1 day') >= 10 then
      raise exception 'New accounts can post 10 comments on their first day' using errcode = 'check_violation';
    end if;
  end if;
  if public.has_blocked_term(new.body) then raise exception 'That contains a word that isn''t allowed here' using errcode = 'check_violation'; end if;
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
-- Security definer to write the moderation log; only a moderator's update gets this far (the policy and grants below).
-- What a hide or ban does to other rows ('__parent' replies, a ban's 'banned' comments) isn't logged row by row; the hide
-- or ban itself is.
create or replace function public.comments_after_update() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.hidden_at is not distinct from old.hidden_at then return null; end if;
  if new.parent_id is null then
    if new.hidden_at is not null then
      update public.comments set hidden_at = new.hidden_at, hidden_reason = '__parent' where parent_id = new.id and hidden_at is null;
    else
      update public.comments set hidden_at = null where parent_id = new.id and hidden_reason = '__parent';
    end if;
  end if;
  if (case when new.hidden_at is null then coalesce(old.hidden_reason, '') <> '__parent' else coalesce(new.hidden_reason, '') not in ('__parent', 'banned') end)
     and (select public.is_admin()) then
    insert into public.mod_log (actor, action, target_kind, target_id, note)
      values ((select auth.uid()), case when new.hidden_at is null then 'restore' else 'hide' end, 'comment', new.id, new.hidden_reason);
  end if;
  return null;
end $$;
drop trigger if exists comments_hide_thread on public.comments;
create trigger comments_hide_thread after update of hidden_at on public.comments for each row execute function public.comments_after_update();

/* Deleting. A thread's first comment that other people have replied to (visibly) isn't removed: it becomes a placeholder,
   with its text, author and reactions gone, so the replies stay. That holds however the delete arrives: from the page,
   from deleting an account (profiles_before_delete), or from a moderator, whose deletes of other people's comments are
   logged with the text. Deleting a placeholder (a moderator) removes the whole thread. When the last reply under a
   placeholder goes, the placeholder goes too. */
create or replace function public.comments_before_delete() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if pg_trigger_depth() = 1 and old.author_id is distinct from (select auth.uid()) and (select public.is_admin()) then
    insert into public.mod_log (actor, action, target_kind, target_id, note) values ((select auth.uid()), 'delete', 'comment', old.id, left(old.body, 300));
  end if;
  if old.parent_id is null and old.deleted_at is null and exists (
      select 1 from public.comments r where r.parent_id = old.id and r.hidden_at is null and r.author_id is distinct from old.author_id) then
    delete from public.reactions where comment_id = old.id;
    update public.comments set body = '', author_id = null, deleted_at = now() where id = old.id;
    return null;
  end if;
  return old;
end $$;
drop trigger if exists comments_delete on public.comments;
create trigger comments_delete before delete on public.comments for each row execute function public.comments_before_delete();
create or replace function public.comments_after_delete() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if old.parent_id is not null then
    delete from public.comments t where t.id = old.parent_id and t.deleted_at is not null
      and not exists (select 1 from public.comments r where r.parent_id = t.id);
  end if;
  return null;
end $$;
drop trigger if exists comments_delete_after on public.comments;
create trigger comments_delete_after after delete on public.comments for each row execute function public.comments_after_delete();

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
revoke insert, update, delete, truncate, references, trigger on public.comments from anon;
revoke update, truncate, references, trigger on public.comments from authenticated;
grant select on public.comments to anon, authenticated;
grant insert, delete on public.comments to authenticated;
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
revoke insert, update, delete, truncate, references, trigger on public.reactions from anon;
revoke update, truncate, references, trigger on public.reactions from authenticated;
grant select on public.reactions to anon, authenticated;
grant insert, delete on public.reactions to authenticated;

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
revoke update, delete, truncate, references, trigger on public.reports from authenticated;
grant select, insert on public.reports to authenticated;
-- resolving reports goes in the moderation log once per comment, however many reports it had
create or replace function public.reports_after_update() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.mod_log (actor, action, target_kind, target_id)
    select distinct (select auth.uid()), 'dismiss', n.target_kind, n.target_id
    from new_rows n join old_rows o on o.id = n.id where o.resolved_at is null and n.resolved_at is not null;
  return null;
end $$;
drop trigger if exists reports_resolved on public.reports;
create trigger reports_resolved after update on public.reports referencing old table as old_rows new table as new_rows
  for each statement execute function public.reports_after_update();
grant update (resolved_at, resolved_by) on public.reports to authenticated;

-- ---------- Reading helpers ----------
-- Comment counts per player (all time, and the last 7 days) for the counts on cards and "Most discussed". Runs as the
-- caller, so it counts only what they may read.
create or replace view public.discussion_counts with (security_invoker = on) as
  select player_id, count(*)::int as n, count(*) filter (where created_at > now() - interval '7 days')::int as n7, max(created_at) as last_at
  from public.comments where hidden_at is null and deleted_at is null group by player_id;
revoke all on public.discussion_counts from anon, authenticated;
grant select on public.discussion_counts to anon, authenticated;

-- Reactions counted per comment or news item and emoji: at most six rows a target, so a screenful fits in one request.
create or replace view public.reaction_counts with (security_invoker = on) as
  select comment_id, news_id, emoji, count(*)::int as n from public.reactions group by comment_id, news_id, emoji;
revoke all on public.reaction_counts from anon, authenticated;
grant select on public.reaction_counts to anon, authenticated;

-- Replies since a time in the threads you've posted in, by other people: the alerts bell.
create or replace function public.my_replies(since timestamptz) returns setof public.comments language sql stable security invoker set search_path = '' as $$
  select c.* from public.comments c
  where c.parent_id in (select coalesce(m.parent_id, m.id) from public.comments m where m.author_id = (select auth.uid()))
    and c.author_id <> (select auth.uid()) and c.created_at > since and c.hidden_at is null and c.deleted_at is null
  order by c.created_at desc limit 50
$$;
revoke all on function public.my_replies(timestamptz) from public, anon;
grant execute on function public.my_replies(timestamptz) to authenticated;

-- Delete a comment as the caller (the policies decide whether they may): 'deleted', or 'kept' when other people's
-- replies keep it as a placeholder (comments_before_delete).
create or replace function public.delete_comment(cid uuid) returns text language plpgsql security invoker set search_path = '' as $$
declare n int;
begin
  delete from public.comments where id = cid;
  get diagnostics n = row_count;
  if n > 0 then return 'deleted'; end if;
  if exists (select 1 from public.comments c where c.id = cid and c.deleted_at = now()) then return 'kept'; end if;
  raise exception 'Your account can''t do that' using errcode = '42501';
end $$;
revoke all on function public.delete_comment(uuid) from public, anon;
grant execute on function public.delete_comment(uuid) to authenticated;

-- A profile page: one person by username, matched whole and ignoring case (a LIKE would treat _ as a wildcard), with how
-- many comments of theirs are showing. Security definer so the count doesn't depend on who asks.
create or replace function public.profile_by_handle(h text) returns table (user_id uuid, handle text, created_at timestamptz, n_comments int)
  language sql stable security definer set search_path = '' as $$
  select p.user_id, p.handle, p.created_at,
    (select count(*)::int from public.comments c where c.author_id = p.user_id and c.hidden_at is null and c.deleted_at is null)
  from public.profiles p where lower(p.handle) = lower(h) limit 1
$$;
revoke all on function public.profile_by_handle(text) from public;
grant execute on function public.profile_by_handle(text) to anon, authenticated;

commit;
notify pgrst, 'reload schema';
