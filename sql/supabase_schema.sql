-- Jalankan sekali melalui Supabase SQL Editor untuk project CatatKas baru.
-- Backend memakai koneksi PostgreSQL server-side; foto, audio, raw OCR, dan raw
-- output model tidak disimpan pada tabel ini.

create extension if not exists pgcrypto;

create table if not exists public.transactions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    source text not null check (source in ('manual', 'text', 'voice', 'receipt')),
    transaction_type text not null check (transaction_type in ('income', 'expense')),
    item_name text,
    quantity numeric(14, 3) check (quantity is null or quantity > 0),
    unit text,
    total_price bigint not null check (total_price > 0),
    transaction_date date not null,
    category text constraint transactions_category_length
        check (category is null or char_length(category) <= 50),
    original_text text,
    transcript text,
    normalized_text text,
    note text,
    reference_date date,
    extraction_method text,
    created_at timestamptz not null default now(),
    updated_at timestamptz
);

create table if not exists public.receipts (
    id uuid primary key default gen_random_uuid(),
    transaction_id uuid not null unique
        references public.transactions(id) on delete cascade,
    merchant_name text,
    receipt_number text,
    subtotal bigint check (subtotal is null or subtotal >= 0),
    discount bigint check (discount is null or discount >= 0),
    tax bigint check (tax is null or tax >= 0),
    service_charge bigint check (service_charge is null or service_charge >= 0),
    total bigint check (total is null or total >= 0),
    confidence numeric(5, 4) check (confidence is null or confidence between 0 and 1),
    created_at timestamptz not null default now()
);

create table if not exists public.receipt_items (
    id uuid primary key default gen_random_uuid(),
    receipt_id uuid not null references public.receipts(id) on delete cascade,
    line_number integer not null check (line_number > 0),
    item_name text not null,
    quantity numeric(14, 3) check (quantity is null or quantity > 0),
    unit text,
    unit_price bigint check (unit_price is null or unit_price >= 0),
    line_total bigint check (line_total is null or line_total >= 0),
    confidence numeric(5, 4) check (confidence is null or confidence between 0 and 1),
    created_at timestamptz not null default now(),
    unique (receipt_id, line_number)
);

create index if not exists transactions_date_idx
    on public.transactions (transaction_date desc, created_at desc);
create index if not exists transactions_user_date_idx
    on public.transactions (user_id, transaction_date desc, created_at desc);
create index if not exists receipts_transaction_id_idx
    on public.receipts (transaction_id);
create index if not exists receipt_items_receipt_id_idx
    on public.receipt_items (receipt_id, line_number);

create table if not exists public.audit_logs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users(id) on delete set null,
    event_type text not null,
    entity_type text,
    entity_id text,
    status text not null check (status in ('success', 'failure')),
    http_method text,
    path text,
    status_code integer,
    ip_address inet,
    user_agent text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists audit_logs_user_created_idx
    on public.audit_logs (user_id, created_at desc);
create index if not exists audit_logs_event_created_idx
    on public.audit_logs (event_type, created_at desc);

-- PWA tidak mengakses Supabase Data API secara langsung. Tutup tabel dari role
-- browser; koneksi PostgreSQL backend menggunakan role pemilik database.
alter table public.transactions enable row level security;
alter table public.receipts enable row level security;
alter table public.receipt_items enable row level security;
alter table public.audit_logs enable row level security;
revoke all on public.transactions from anon, authenticated;
revoke all on public.receipts from anon, authenticated;
revoke all on public.receipt_items from anon, authenticated;
revoke all on public.audit_logs from anon, authenticated;
