begin;

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  highlight_api_key_secret_id uuid references vault.secrets(id) on delete set null,
  caption_api_key_secret_id uuid references vault.secrets(id) on delete set null,
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_settings_object check (jsonb_typeof(settings) = 'object')
);

create table if not exists public.jobs (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'queued',
  queue_position integer,
  progress smallint not null default 0,
  input_metadata jsonb not null default '{}'::jsonb,
  output_metadata jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  finished_at timestamptz,
  constraint jobs_status check (status in ('queued', 'running', 'completed', 'failed', 'cancelled')),
  constraint jobs_progress check (progress between 0 and 100),
  constraint jobs_queue_position check (queue_position is null or queue_position > 0),
  constraint jobs_input_object check (jsonb_typeof(input_metadata) = 'object'),
  constraint jobs_output_object check (jsonb_typeof(output_metadata) = 'object')
);

create table if not exists public.oauth_transactions (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null,
  state_hash text not null unique,
  code_verifier_ciphertext bytea,
  code_verifier_nonce bytea,
  encryption_version smallint not null default 1,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint oauth_transactions_provider check (provider in ('youtube')),
  constraint oauth_transactions_expiry check (expires_at > created_at),
  constraint oauth_transactions_encryption_version check (encryption_version > 0),
  constraint oauth_transactions_cipher_pair check ((code_verifier_ciphertext is null) = (code_verifier_nonce is null))
);

create table if not exists public.oauth_connections (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null,
  provider_account_id text not null,
  access_token_ciphertext bytea,
  access_token_nonce bytea,
  refresh_token_ciphertext bytea,
  refresh_token_nonce bytea,
  encryption_version smallint not null default 1,
  scopes text[] not null default '{}',
  token_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint oauth_connections_identity unique (user_id, provider, provider_account_id),
  constraint oauth_connections_provider check (provider in ('youtube')),
  constraint oauth_connections_encryption_version check (encryption_version > 0),
  constraint oauth_connections_access_pair check ((access_token_ciphertext is null) = (access_token_nonce is null)),
  constraint oauth_connections_refresh_pair check ((refresh_token_ciphertext is null) = (refresh_token_nonce is null)),
  constraint oauth_connections_has_token check (access_token_ciphertext is not null or refresh_token_ciphertext is not null)
);

create index if not exists jobs_user_created_idx on public.jobs (user_id, created_at desc);
create index if not exists jobs_queue_idx on public.jobs (created_at) where status = 'queued';
create index if not exists oauth_transactions_user_expiry_idx on public.oauth_transactions (user_id, expires_at);
create index if not exists oauth_transactions_expiry_idx on public.oauth_transactions (expires_at) where consumed_at is null;
create index if not exists oauth_connections_user_idx on public.oauth_connections (user_id);

alter table public.user_settings owner to postgres;
alter table public.jobs owner to postgres;
alter table public.oauth_transactions owner to postgres;
alter table public.oauth_connections owner to postgres;

alter table public.user_settings enable row level security;
alter table public.jobs enable row level security;
alter table public.oauth_transactions enable row level security;
alter table public.oauth_connections enable row level security;
alter table public.user_settings force row level security;
alter table public.jobs force row level security;
alter table public.oauth_transactions force row level security;
alter table public.oauth_connections force row level security;

drop policy if exists user_settings_owner_select on public.user_settings;
create policy user_settings_owner_select on public.user_settings for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists user_settings_owner_insert on public.user_settings;
create policy user_settings_owner_insert on public.user_settings for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists user_settings_owner_update on public.user_settings;
create policy user_settings_owner_update on public.user_settings for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists jobs_owner_select on public.jobs;
create policy jobs_owner_select on public.jobs for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists oauth_connections_owner_status on public.oauth_connections;
create policy oauth_connections_owner_status on public.oauth_connections for select to authenticated using ((select auth.uid()) = user_id);

revoke all on public.user_settings, public.jobs, public.oauth_transactions, public.oauth_connections from anon, authenticated;
grant select (user_id, settings, created_at, updated_at) on public.user_settings to authenticated;
grant insert (user_id, settings) on public.user_settings to authenticated;
grant update (settings, updated_at) on public.user_settings to authenticated;
grant select on public.jobs to authenticated;
grant select (id, user_id, provider, provider_account_id, scopes, token_expires_at, created_at, updated_at) on public.oauth_connections to authenticated;
grant all on public.user_settings, public.jobs, public.oauth_transactions, public.oauth_connections to service_role;

revoke all on vault.secrets from anon, authenticated;

create or replace function public.klipklop_provider_column(p_provider text)
returns text
language sql
immutable
set search_path = ''
as $$
  select case p_provider
    when 'highlight' then 'highlight_api_key_secret_id'
    when 'caption' then 'caption_api_key_secret_id'
    else null
  end
$$;

create or replace function public.klipklop_set_provider_key(p_user_id uuid, p_provider text, p_secret text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  secret_id uuid;
  reference_column text := public.klipklop_provider_column(p_provider);
begin
  if reference_column is null or nullif(p_secret, '') is null then
    raise exception 'invalid provider key';
  end if;
  select case p_provider
    when 'highlight' then highlight_api_key_secret_id
    when 'caption' then caption_api_key_secret_id
  end into secret_id
  from public.user_settings where user_id = p_user_id;
  if secret_id is null then
    secret_id := vault.create_secret(p_secret, 'klipklop-' || p_user_id || '-' || p_provider);
    insert into public.user_settings (user_id, highlight_api_key_secret_id, caption_api_key_secret_id)
    values (p_user_id, case when p_provider = 'highlight' then secret_id end, case when p_provider = 'caption' then secret_id end)
    on conflict (user_id) do update set
      highlight_api_key_secret_id = case when p_provider = 'highlight' then secret_id else public.user_settings.highlight_api_key_secret_id end,
      caption_api_key_secret_id = case when p_provider = 'caption' then secret_id else public.user_settings.caption_api_key_secret_id end,
      updated_at = now();
  else
    perform vault.update_secret(secret_id, p_secret);
  end if;
end
$$;

create or replace function public.klipklop_read_provider_key(p_user_id uuid, p_provider text)
returns text
language sql
security definer
set search_path = ''
as $$
  select decrypted_secret
  from vault.decrypted_secrets
  where id = (select case p_provider when 'highlight' then highlight_api_key_secret_id when 'caption' then caption_api_key_secret_id end from public.user_settings where user_id = p_user_id)
    and public.klipklop_provider_column(p_provider) is not null
$$;

create or replace function public.klipklop_provider_key_exists(p_user_id uuid, p_provider text)
returns boolean
language sql
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.user_settings
    where user_id = p_user_id
      and case p_provider when 'highlight' then highlight_api_key_secret_id when 'caption' then caption_api_key_secret_id end is not null
      and public.klipklop_provider_column(p_provider) is not null
  )
$$;

create or replace function public.klipklop_delete_provider_key(p_user_id uuid, p_provider text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  secret_id uuid;
begin
  if public.klipklop_provider_column(p_provider) is null then
    raise exception 'invalid provider';
  end if;
  select case p_provider when 'highlight' then highlight_api_key_secret_id when 'caption' then caption_api_key_secret_id end
  into secret_id from public.user_settings where user_id = p_user_id for update;
  update public.user_settings set
    highlight_api_key_secret_id = case when p_provider = 'highlight' then null else highlight_api_key_secret_id end,
    caption_api_key_secret_id = case when p_provider = 'caption' then null else caption_api_key_secret_id end,
    updated_at = now()
  where user_id = p_user_id;
  if secret_id is not null then
    delete from vault.secrets where id = secret_id;
  end if;
end
$$;

revoke all on function public.klipklop_provider_column(text) from public, anon, authenticated;
revoke all on function public.klipklop_set_provider_key(uuid, text, text) from public, anon, authenticated;
revoke all on function public.klipklop_read_provider_key(uuid, text) from public, anon, authenticated;
revoke all on function public.klipklop_provider_key_exists(uuid, text) from public, anon, authenticated;
revoke all on function public.klipklop_delete_provider_key(uuid, text) from public, anon, authenticated;
grant execute on function public.klipklop_set_provider_key(uuid, text, text) to service_role;
grant execute on function public.klipklop_read_provider_key(uuid, text) to service_role;
grant execute on function public.klipklop_provider_key_exists(uuid, text) to service_role;
grant execute on function public.klipklop_delete_provider_key(uuid, text) to service_role;

commit;
