-- Benny's Picks accounts: run once in Supabase → SQL Editor. Safe to re-run.
-- Each person can read and change only their own rows (row-level security), so the publishable key in index.html is safe to share.

-- One row per person: every team, plus the overrides, model weights and coaching edits shared by all teams.
-- `rev` goes up by one on every save; a device saves only if nobody else saved since it last looked, and otherwise merges first.
create table if not exists public.user_state (
  user_id uuid primary key references auth.users (id) on delete cascade,
  state jsonb not null check (octet_length(state::text) < 2000000),
  rev bigint not null default 1,
  updated_at timestamptz not null default now()
);

-- One row per saved weekly lineup: Benny's starters and bench, their projections, and what they scored.
create table if not exists public.lineups (
  user_id uuid not null references auth.users (id) on delete cascade,
  team_id text not null check (char_length(team_id) <= 64),
  season int not null,
  week int not null check (week between 1 and 22),
  data jsonb not null check (octet_length(data::text) < 50000),
  updated_at timestamptz not null default now(),
  primary key (user_id, team_id, season, week)
);

create or replace function public.touch_updated_at() returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at = now(); return new; end $$;
drop trigger if exists user_state_touch on public.user_state;
create trigger user_state_touch before update on public.user_state for each row execute function public.touch_updated_at();
drop trigger if exists lineups_touch on public.lineups;
create trigger lineups_touch before update on public.lineups for each row execute function public.touch_updated_at();

alter table public.user_state enable row level security;
alter table public.lineups enable row level security;

drop policy if exists "own state" on public.user_state;
create policy "own state" on public.user_state for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "own lineups" on public.lineups;
create policy "own lineups" on public.lineups for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- Delete account: removes the sign-in and, through the foreign keys, every row above.
create or replace function public.delete_my_account() returns void
  language sql security definer set search_path = '' as $$
  delete from auth.users where id = (select auth.uid());
$$;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;
