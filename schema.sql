-- =========================================================================
-- Internal Training Survey Form — Supabase Schema
-- ABC-MIB Group Co., Ltd.
--
-- Run this entire file once in the Supabase SQL Editor
-- (Project → SQL Editor → New query → paste → Run).
-- =========================================================================

-- Needed for gen_random_uuid()
create extension if not exists pgcrypto;

-- -------------------------------------------------------------------------
-- 1. USERS PROFILE
-- Extends auth.users with app-specific role/profile data.
-- -------------------------------------------------------------------------
create table if not exists public.users_profile (
    id          uuid primary key references auth.users(id) on delete cascade,
    email       text,
    role        text not null default 'user' check (role in ('admin', 'user')),
    full_name   text,
    department  text,
    position    text,
    created_at  timestamptz not null default now()
);

-- Auto-create a profile row whenever someone signs up via Supabase Auth.
-- Any email listed in admin_emails is auto-assigned role='admin' on sign-up.
-- Add more addresses to the array below to grant additional default admins.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
declare
    admin_emails text[] := array['abc576887@gmail.com'];
    assigned_role text := 'user';
begin
    if lower(new.email) = any (select lower(e) from unnest(admin_emails) as e) then
        assigned_role := 'admin';
    end if;

    insert into public.users_profile (id, email, role)
    values (new.id, new.email, assigned_role)
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_user();

-- -------------------------------------------------------------------------
-- 2. SURVEY RESPONSES
-- -------------------------------------------------------------------------
create table if not exists public.survey_responses (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid references auth.users(id) on delete set null,

    -- Basic info
    trainee_name      text not null,
    position          text,
    department        text,
    training_course   text not null,
    start_date        date,
    completed_date    date,
    training_hours    numeric,
    time_range        text,
    presenter_name    text,

    -- Rating questions: 1-4 (4=Excellent, 3=Good, 2=Average, 1=Poor)
    q1_enjoyable                integer check (q1_enjoyable between 1 and 4),
    q2_organized                integer check (q2_organized between 1 and 4),
    q3_satisfied                integer check (q3_satisfied between 1 and 4),
    q4_improved_understanding   integer check (q4_improved_understanding between 1 and 4),
    q5_respect_ideas            integer check (q5_respect_ideas between 1 and 4),
    q6_presenter_rating         integer check (q6_presenter_rating between 1 and 4),

    -- Open feedback
    q7_understanding_notes      text,
    q8_interesting_thing        text,
    q9_knowledge_application    text,
    q10_challenge_addressed     text,
    q11_future_topics           text,

    created_at  timestamptz not null default now()
);

create index if not exists idx_survey_responses_user_id    on public.survey_responses(user_id);
create index if not exists idx_survey_responses_course     on public.survey_responses(training_course);
create index if not exists idx_survey_responses_department on public.survey_responses(department);
create index if not exists idx_survey_responses_created_at on public.survey_responses(created_at);

-- -------------------------------------------------------------------------
-- 3. ROW LEVEL SECURITY
-- -------------------------------------------------------------------------
alter table public.users_profile    enable row level security;
alter table public.survey_responses enable row level security;

-- Helper: is the currently authenticated user an admin?
create or replace function public.is_admin()
returns boolean
language sql
security definer set search_path = public
stable
as $$
    select exists (
        select 1 from public.users_profile
        where id = auth.uid() and role = 'admin'
    );
$$;

-- users_profile policies
drop policy if exists "profile_select_own_or_admin" on public.users_profile;
create policy "profile_select_own_or_admin"
    on public.users_profile for select
    using (auth.uid() = id or public.is_admin());

drop policy if exists "profile_update_own" on public.users_profile;
create policy "profile_update_own"
    on public.users_profile for update
    using (auth.uid() = id)
    with check (auth.uid() = id);

drop policy if exists "profile_update_admin" on public.users_profile;
create policy "profile_update_admin"
    on public.users_profile for update
    using (public.is_admin());

-- survey_responses policies
drop policy if exists "responses_insert_own" on public.survey_responses;
create policy "responses_insert_own"
    on public.survey_responses for insert
    with check (auth.uid() = user_id);

drop policy if exists "responses_select_own" on public.survey_responses;
create policy "responses_select_own"
    on public.survey_responses for select
    using (auth.uid() = user_id);

drop policy if exists "responses_select_admin" on public.survey_responses;
create policy "responses_select_admin"
    on public.survey_responses for select
    using (public.is_admin());

drop policy if exists "responses_delete_admin" on public.survey_responses;
create policy "responses_delete_admin"
    on public.survey_responses for delete
    using (public.is_admin());

-- =========================================================================
-- 4. BACKFILL: promote an existing account that signed up BEFORE the
-- admin_emails list above included it. Safe to run even if the account
-- doesn't exist yet or is already an admin.
-- =========================================================================
update public.users_profile
set role = 'admin'
where lower(email) = lower('abc576887@gmail.com');

-- To promote any OTHER user to admin later (one not in admin_emails),
-- run the same pattern manually with their email:
-- update public.users_profile set role = 'admin' where email = 'someone@abc-mib.com';
