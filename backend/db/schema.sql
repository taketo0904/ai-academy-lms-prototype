-- 組織アカウント基盤（Supabase Postgres想定）。
-- 個人アカウントではなく「組織(organizations)」を単位にし、
-- 同じ会社のメンバーが成果物・設定・利用枠を共有できるようにする。
--
-- 前提: Anthropicの課金上限はワークスペース単位でしかAPI経由で設定できず、
-- 顧客ごとにAnthropicのAPIキーを自動発行することはできない（Console手動のみ）。
-- そのため各組織にAnthropicキーは持たせず、バックエンドの共有キー1本を使い、
-- 利用回数・課金上限はこのDB側（usage_records / organizations.plan）で管理する。

-- 組織（＝契約単位。3人チームなら1組織、将来の顧客企業も1組織）
create table organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan text not null default 'free' check (plan in ('free', 'standard', 'premium')),
  created_at timestamptz not null default now()
);

-- ユーザープロフィール（auth.users を Supabase Auth 側で作成した後、1:1で紐づく）
create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now()
);

-- 組織メンバーシップ（誰がどの組織に所属し、どんな役割か）
create table memberships (
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  role text not null default 'member' check (role in ('owner', 'admin', 'member')),
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

-- エージェント実行履歴＋課金上限判定の元データ（サーバー側で必ず記録＝クライアント側の回数チェックを回避できない）
create table usage_records (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  agent_id text not null,
  input_tokens integer,
  output_tokens integer,
  created_at timestamptz not null default now()
);

-- 承認・公開されたエージェント（今はlocalStorageのみ→組織単位で共有）
create table published_agents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  source_draft_id uuid,
  cat text not null,
  name text not null,
  in_spec text,
  out_spec text,
  prompt text,
  tags text[] default '{}',
  created_by uuid references profiles(id),
  created_at timestamptz not null default now()
);

-- 作成リクエスト＋承認キュー（今はlocalStorageのみ→組織単位で共有・監査可能に）
create table agent_drafts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  source text not null default 'manual' check (source in ('manual', 'auto')),
  origin text,
  cat text,
  in_spec text,
  out_spec text,
  prompt text,
  sample text,
  status text not null default 'draft' check (status in ('draft', 'approved', 'rejected')),
  created_by uuid references profiles(id),
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create index idx_usage_records_org_month on usage_records (organization_id, created_at);
create index idx_memberships_user on memberships (user_id);

-- Row Level Security: 自分が所属する組織のデータしか見えないようにする
alter table organizations enable row level security;
alter table profiles enable row level security;
alter table memberships enable row level security;
alter table usage_records enable row level security;
alter table published_agents enable row level security;
alter table agent_drafts enable row level security;

create policy "org visible to members" on organizations for select
  using (id in (select organization_id from memberships where user_id = auth.uid()));

create policy "own profile visible and editable" on profiles for all
  using (id = auth.uid());

create policy "memberships visible to same org" on memberships for select
  using (organization_id in (select organization_id from memberships where user_id = auth.uid()));

create policy "usage visible to same org" on usage_records for select
  using (organization_id in (select organization_id from memberships where user_id = auth.uid()));

create policy "published_agents visible to same org" on published_agents for select
  using (organization_id in (select organization_id from memberships where user_id = auth.uid()));

create policy "agent_drafts visible to same org" on agent_drafts for select
  using (organization_id in (select organization_id from memberships where user_id = auth.uid()));

-- ============================================================
-- マイライブラリ（メモ・会話・成果物）。個人所有＝本人にしか見えない。
-- 今はブラウザのlocalStorageだけにあるものを、アカウントに紐づけて永続化・端末間で共有する。
-- ============================================================

create table library_notes (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  title text not null,
  body text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table library_conversations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  title text not null,
  agent_id text,
  messages jsonb not null default '[]',  -- [{role:"user"|"assistant", content:"..."}]
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table library_outputs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  title text not null,
  source_name text,  -- 実行元のエージェント/ワークフロー名
  body text not null,
  created_at timestamptz not null default now()
);

create index idx_library_notes_user on library_notes (user_id, created_at desc);
create index idx_library_conversations_user on library_conversations (user_id, updated_at desc);
create index idx_library_outputs_user on library_outputs (user_id, created_at desc);

alter table library_notes enable row level security;
alter table library_conversations enable row level security;
alter table library_outputs enable row level security;

create policy "own notes only" on library_notes for all
  using (user_id = auth.uid());
create policy "own conversations only" on library_conversations for all
  using (user_id = auth.uid());
create policy "own outputs only" on library_outputs for all
  using (user_id = auth.uid());

-- ============================================================
-- 接続サービス（Yoom型: 利用者本人が自分のGitHub/Notion/Google Driveなどを
-- OAuthで接続する）。トークンは本人にしか見えない（RLS）＋バックエンドの
-- service_roleキー経由でのみエージェント実行時に読み出す想定。
-- 注意: 現状は平文保存。本番運用でトークン件数が増える場合はSupabase Vault
-- （pgsodium暗号化）への移行を検討すること（初期版のスコープ外として保留）。
-- ============================================================

create table connected_accounts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  provider text not null check (provider in ('github', 'notion', 'google')),
  account_label text,       -- 表示用（例: GitHubのユーザー名／Notionワークスペース名）
  access_token text not null,
  refresh_token text,
  expires_at timestamptz,
  scopes text[] default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, provider)
);

create index idx_connected_accounts_user on connected_accounts (user_id);

alter table connected_accounts enable row level security;

create policy "own connections only" on connected_accounts for all
  using (user_id = auth.uid());
