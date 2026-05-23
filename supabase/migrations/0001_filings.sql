-- Plugfile — saved filings (save / resume). Per-user isolation via RLS.
--
-- Run this once in your Supabase project: SQL Editor → New query → paste →
-- Run. It creates the `filings` table the PWA's save/resume uses. Row-Level
-- Security ensures each signed-in user can only see and modify their own rows;
-- the frontend uses the public anon key + the user's session, never a service
-- key.

create extension if not exists "pgcrypto";

create table if not exists public.filings (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid()
              references auth.users (id) on delete cascade,
  form_type   text not null check (form_type in ('w3', 'w3a')),
  api_number  text,
  title       text,
  step        int,
  data        jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

comment on table public.filings is
  'Plugfile saved W-3 / W-3A wizard state for resume. One row per saved filing.';

-- ---- Row-Level Security: a user only ever touches their own filings --------
alter table public.filings enable row level security;

drop policy if exists "filings_select_own" on public.filings;
create policy "filings_select_own" on public.filings
  for select using (auth.uid() = user_id);

drop policy if exists "filings_insert_own" on public.filings;
create policy "filings_insert_own" on public.filings
  for insert with check (auth.uid() = user_id);

drop policy if exists "filings_update_own" on public.filings;
create policy "filings_update_own" on public.filings
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "filings_delete_own" on public.filings;
create policy "filings_delete_own" on public.filings
  for delete using (auth.uid() = user_id);

create index if not exists filings_user_updated_idx
  on public.filings (user_id, updated_at desc);

-- ---- Table-level privileges --------------------------------------------------
-- RLS controls *which rows* a role may touch, but the role must first hold
-- table privileges. Tables created via raw SQL don't inherit Supabase's default
-- grants, so grant CRUD to the authenticated role explicitly (anon gets none —
-- save/resume requires sign-in). RLS above still restricts each user to their
-- own rows.
grant select, insert, update, delete on public.filings to authenticated;

-- ---- keep updated_at current on every update -------------------------------
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists filings_touch on public.filings;
create trigger filings_touch
  before update on public.filings
  for each row execute function public.touch_updated_at();
