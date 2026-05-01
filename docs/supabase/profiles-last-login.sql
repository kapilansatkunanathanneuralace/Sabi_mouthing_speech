-- Supabase user profile table and server-side last-login tracking.
-- Run this once in the Supabase SQL editor for the project.

create schema if not exists private;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_login_at timestamptz
);

alter table public.profiles
  add column if not exists display_name text,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now(),
  add column if not exists last_login_at timestamptz;

alter table public.profiles enable row level security;

grant usage on schema public to anon, authenticated;
grant select on public.profiles to authenticated;
grant insert (id, display_name) on public.profiles to authenticated;
grant update (display_name) on public.profiles to authenticated;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
  on public.profiles for select
  to authenticated
  using ((select auth.uid()) = id);

drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own"
  on public.profiles for insert
  to authenticated
  with check ((select auth.uid()) = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
  on public.profiles for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

create or replace function private.touch_profiles_updated_at()
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

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row execute procedure private.touch_profiles_updated_at();

create or replace function private.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, last_login_at)
  values (
    new.id,
    nullif(trim(coalesce(new.raw_user_meta_data ->> 'display_name', '')), ''),
    new.last_sign_in_at
  )
  on conflict (id) do update
    set
      display_name = coalesce(public.profiles.display_name, excluded.display_name),
      last_login_at = coalesce(excluded.last_login_at, public.profiles.last_login_at);

  return new;
end;
$$;

drop trigger if exists on_auth_user_created_profiles on auth.users;
create trigger on_auth_user_created_profiles
  after insert on auth.users
  for each row execute procedure private.handle_new_auth_user();

create or replace function private.sync_auth_user_last_login()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if old.last_sign_in_at is distinct from new.last_sign_in_at then
    insert into public.profiles (id, last_login_at)
    values (new.id, new.last_sign_in_at)
    on conflict (id) do update
      set last_login_at = excluded.last_login_at;
  end if;

  return new;
end;
$$;

drop trigger if exists on_auth_user_last_sign_in_profiles on auth.users;
create trigger on_auth_user_last_sign_in_profiles
  after update of last_sign_in_at on auth.users
  for each row execute procedure private.sync_auth_user_last_login();
