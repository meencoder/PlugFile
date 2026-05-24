-- Plugfile — operator → plugging-company sharing.
--
-- Lets a filing's owner (the operator) share one filing with a named plugging
-- company by EMAIL, granting that company VIEW + EDIT access to that single
-- row. Access is matched on the signed-in user's email claim, so the plugger
-- gets access as soon as they sign in with that address (no pre-existing
-- account or user-id needed). RLS still confines everyone else.
--
-- Run once in the Supabase SQL Editor, after 0001_filings.sql.

-- 1) The share target (a single named collaborator email per filing).
alter table public.filings
  add column if not exists shared_with_email text;

create index if not exists filings_shared_email_idx
  on public.filings (lower(shared_with_email));

-- 2) Second set of RLS policies (OR'd with the owner policies from 0001):
--    a user whose email matches shared_with_email may SELECT and UPDATE the
--    filing. No INSERT/DELETE for the sharee — they can view and edit, not
--    create-as-owner or delete the owner's filing.
drop policy if exists "filings_select_shared" on public.filings;
create policy "filings_select_shared" on public.filings
  for select using (
    shared_with_email is not null
    and lower(shared_with_email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );

drop policy if exists "filings_update_shared" on public.filings;
create policy "filings_update_shared" on public.filings
  for update using (
    shared_with_email is not null
    and lower(shared_with_email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  ) with check (
    shared_with_email is not null
    and lower(shared_with_email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );

-- 3) Guard: a non-owner editor must NOT change ownership or the share target
--    (so a shared plugger can edit the filing's content but can't hijack it).
create or replace function public.filings_guard_share()
returns trigger language plpgsql as $$
begin
  if auth.uid() is distinct from old.user_id then          -- editor is not the owner
    if new.user_id is distinct from old.user_id
       or new.shared_with_email is distinct from old.shared_with_email then
      raise exception 'A shared editor cannot change ownership or sharing.';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists filings_guard_share_trg on public.filings;
create trigger filings_guard_share_trg
  before update on public.filings
  for each row execute function public.filings_guard_share();
