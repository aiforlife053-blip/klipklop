begin;

alter table public.user_settings
  add column if not exists hook_api_key_secret_id uuid references vault.secrets(id) on delete set null;

create or replace function public.klipklop_provider_column(p_provider text)
returns text
language sql
immutable
set search_path = ''
as $$
  select case p_provider
    when 'highlight' then 'highlight_api_key_secret_id'
    when 'caption' then 'caption_api_key_secret_id'
    when 'hook' then 'hook_api_key_secret_id'
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
begin
  if public.klipklop_provider_column(p_provider) is null or nullif(p_secret, '') is null then
    raise exception 'invalid provider key';
  end if;
  select case p_provider
    when 'highlight' then highlight_api_key_secret_id
    when 'caption' then caption_api_key_secret_id
    when 'hook' then hook_api_key_secret_id
  end into secret_id
  from public.user_settings where user_id = p_user_id;
  if secret_id is null then
    secret_id := vault.create_secret(p_secret, 'klipklop-' || p_user_id || '-' || p_provider);
    insert into public.user_settings (user_id, highlight_api_key_secret_id, caption_api_key_secret_id, hook_api_key_secret_id)
    values (p_user_id, case when p_provider = 'highlight' then secret_id end, case when p_provider = 'caption' then secret_id end, case when p_provider = 'hook' then secret_id end)
    on conflict (user_id) do update set
      highlight_api_key_secret_id = case when p_provider = 'highlight' then secret_id else public.user_settings.highlight_api_key_secret_id end,
      caption_api_key_secret_id = case when p_provider = 'caption' then secret_id else public.user_settings.caption_api_key_secret_id end,
      hook_api_key_secret_id = case when p_provider = 'hook' then secret_id else public.user_settings.hook_api_key_secret_id end,
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
  where id = (select case p_provider when 'highlight' then highlight_api_key_secret_id when 'caption' then caption_api_key_secret_id when 'hook' then hook_api_key_secret_id end from public.user_settings where user_id = p_user_id)
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
      and case p_provider when 'highlight' then highlight_api_key_secret_id when 'caption' then caption_api_key_secret_id when 'hook' then hook_api_key_secret_id end is not null
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
  select case p_provider when 'highlight' then highlight_api_key_secret_id when 'caption' then caption_api_key_secret_id when 'hook' then hook_api_key_secret_id end
  into secret_id from public.user_settings where user_id = p_user_id for update;
  update public.user_settings set
    highlight_api_key_secret_id = case when p_provider = 'highlight' then null else highlight_api_key_secret_id end,
    caption_api_key_secret_id = case when p_provider = 'caption' then null else caption_api_key_secret_id end,
    hook_api_key_secret_id = case when p_provider = 'hook' then null else hook_api_key_secret_id end,
    updated_at = now()
  where user_id = p_user_id;
  if secret_id is not null then
    delete from vault.secrets where id = secret_id;
  end if;
end
$$;

commit;
