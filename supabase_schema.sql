create extension if not exists pgcrypto;

create table if not exists public.product_batches (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    source_file_name text,
    created_at timestamptz not null default now()
);

create table if not exists public.products (
    id uuid primary key default gen_random_uuid(),
    batch_id uuid not null references public.product_batches(id) on delete cascade,
    id_product text not null,
    product_name text not null default '',
    reference text not null default '',
    description_short text not null default '',
    description text not null default '',
    filters_json jsonb not null default '[]'::jsonb,
    features text not null default '',
    disabled_features text not null default '',
    image_main text not null default '',
    image_template text not null default '',
    image_1 text not null default '',
    image_2 text not null default '',
    all_images text not null default '',
    catalog_file text not null default '',
    catalog_text text not null default '',
    status text not null default 'todo',
    operator text not null default '',
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (batch_id, id_product)
);

create index if not exists products_batch_id_idx on public.products(batch_id);
create index if not exists products_status_idx on public.products(status);

create table if not exists public.product_assets (
    id uuid primary key default gen_random_uuid(),
    product_id uuid not null references public.products(id) on delete cascade,
    asset_type text not null,
    role text not null default '',
    file_name text not null,
    storage_path text not null,
    public_url text not null default '',
    content_type text not null default '',
    created_at timestamptz not null default now()
);

create index if not exists product_assets_product_id_idx on public.product_assets(product_id);

alter table public.product_batches enable row level security;
alter table public.products enable row level security;
alter table public.product_assets enable row level security;

drop policy if exists "service role full access batches" on public.product_batches;
drop policy if exists "service role full access products" on public.products;
drop policy if exists "service role full access assets" on public.product_assets;

create policy "service role full access batches"
on public.product_batches
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create policy "service role full access products"
on public.products
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create policy "service role full access assets"
on public.product_assets
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');
