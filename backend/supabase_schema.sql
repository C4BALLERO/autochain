-- AutoChain — esquema de Supabase
-- Pega esto en Supabase → SQL Editor → New query → Run

create extension if not exists pgcrypto;

-- Standalone KYC: a person verifies their identity once (wallet + ID photo,
-- the photo itself lives in the private owner-id-photos Storage bucket), then
-- can register any number of vehicles under that same wallet.
create table if not exists users (
  owner_wallet text primary key,
  owner_name text not null,
  created_at timestamptz not null default now()
);

create table if not exists vehicles (
  id uuid primary key default gen_random_uuid(),
  owner_name text not null,
  plate text not null,
  doc_id_hash text not null,
  owner_wallet text not null,
  brand text not null,
  model text not null,
  color text not null,
  year text not null,
  ruat_number text not null,
  description text,
  photo_count integer not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists cases (
  id uuid primary key default gen_random_uuid(),
  vehicle_id uuid not null references vehicles(id) on delete cascade,
  reward_amount numeric not null,
  theft_location text not null,
  theft_description text,
  onchain_case_id integer,
  status text not null default 'open',
  reported_at timestamptz not null default now()
);

create table if not exists tips (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references cases(id) on delete cascade,
  collaborator_wallet text not null,
  similarity double precision not null,
  tier text not null,
  latitude double precision,
  longitude double precision,
  location_note text,
  paid boolean not null default false,
  tx_hash text,
  payout_error text,
  created_at timestamptz not null default now()
);

create index if not exists idx_cases_vehicle on cases(vehicle_id);
create index if not exists idx_tips_case on tips(case_id);
