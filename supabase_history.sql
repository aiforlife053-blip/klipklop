create table if not exists public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.youtube_connections (
  user_id uuid primary key references auth.users(id) on delete cascade,
  channel_id text,
  channel_title text,
  access_token text not null,
  refresh_token text,
  token_type text,
  scopes text[] not null default '{}',
  expires_at timestamptz,
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.videos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  source_url text not null,
  title text,
  status text not null default 'processing' check (status in ('processing', 'staged', 'saved', 'deleted', 'expired', 'error')),
  generated_count int not null default 3,
  storage_path text,
  file_exists boolean not null default true,
  error text,
  staged_at timestamptz,
  saved_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.clips (
  id uuid primary key default gen_random_uuid(),
  video_id uuid not null references public.videos(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  title text,
  caption text,
  storage_path text,
  thumbnail_path text,
  subtitle_path text,
  duration_seconds numeric,
  status text not null default 'staged' check (status in ('staged', 'saved', 'uploaded', 'deleted', 'expired', 'error')),
  file_exists boolean not null default true,
  youtube_video_id text,
  staged_at timestamptz not null default now(),
  saved_at timestamptz,
  uploaded_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.activity_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  action text not null,
  detail text,
  created_at timestamptz not null default now()
);

alter table public.user_settings enable row level security;
alter table public.youtube_connections enable row level security;
alter table public.videos enable row level security;
alter table public.clips enable row level security;
alter table public.activity_logs enable row level security;

create policy "user_settings own row" on public.user_settings for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "youtube_connections own row" on public.youtube_connections for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "videos own rows" on public.videos for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "clips own rows" on public.clips for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "activity_logs own rows" on public.activity_logs for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create index if not exists videos_user_created_idx on public.videos(user_id, created_at desc);
create index if not exists videos_user_status_idx on public.videos(user_id, status);
create index if not exists clips_user_created_idx on public.clips(user_id, created_at desc);
create index if not exists clips_user_status_saved_idx on public.clips(user_id, status, saved_at desc);
create index if not exists clips_video_idx on public.clips(video_id);
create index if not exists activity_logs_user_created_idx on public.activity_logs(user_id, created_at desc);
