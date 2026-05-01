-- Supabase user onboarding intake table.
-- Run this once in the Supabase SQL editor for the project.

create table if not exists public.user_onboarding_intake (
  user_id uuid primary key references auth.users(id) on delete cascade,
  referral_source text not null,
  profession text not null,
  use_cases text[] not null default '{}',
  work_environment text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_onboarding_intake_use_cases_nonempty
    check (cardinality(use_cases) > 0)
);

alter table public.user_onboarding_intake
  add column if not exists referral_source text,
  add column if not exists profession text,
  add column if not exists use_cases text[] not null default '{}',
  add column if not exists work_environment text,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

alter table public.user_onboarding_intake enable row level security;

grant usage on schema public to anon, authenticated;
grant select on public.user_onboarding_intake to authenticated;
grant insert (
  user_id,
  referral_source,
  profession,
  use_cases,
  work_environment
) on public.user_onboarding_intake to authenticated;
grant update (
  referral_source,
  profession,
  use_cases,
  work_environment
) on public.user_onboarding_intake to authenticated;

drop policy if exists "user_onboarding_intake_select_own" on public.user_onboarding_intake;
create policy "user_onboarding_intake_select_own"
  on public.user_onboarding_intake for select
  to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "user_onboarding_intake_insert_own" on public.user_onboarding_intake;
create policy "user_onboarding_intake_insert_own"
  on public.user_onboarding_intake for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "user_onboarding_intake_update_own" on public.user_onboarding_intake;
create policy "user_onboarding_intake_update_own"
  on public.user_onboarding_intake for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create or replace function private.touch_user_onboarding_intake_updated_at()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists user_onboarding_intake_touch_updated_at
  on public.user_onboarding_intake;
create trigger user_onboarding_intake_touch_updated_at
  before update on public.user_onboarding_intake
  for each row execute procedure private.touch_user_onboarding_intake_updated_at();
