-- Migrasi untuk instalasi CatatKas yang sudah memiliki tiga tabel transaksi.
-- Jalankan melalui Supabase SQL Editor sebelum mengaktifkan kode Auth baru.

alter table public.transactions
    add column if not exists user_id uuid references auth.users(id) on delete cascade;

-- ADD COLUMN IF NOT EXISTS tidak menambahkan foreign key apabila kolom user_id
-- sudah dibuat sebelumnya. Tambahkan constraint secara idempotent pada kondisi itu.
do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.transactions'::regclass
          and contype = 'f'
          and confrelid = 'auth.users'::regclass
          and conkey = array[
              (select attnum
               from pg_attribute
               where attrelid = 'public.transactions'::regclass
                 and attname = 'user_id')
          ]::smallint[]
    ) then
        alter table public.transactions
            add constraint transactions_user_id_auth_fkey
            foreign key (user_id) references auth.users(id) on delete cascade;
    end if;
end
$$;

create index if not exists transactions_user_date_idx
    on public.transactions (user_id, transaction_date desc, created_at desc);

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

alter table public.transactions enable row level security;
alter table public.audit_logs enable row level security;
revoke all on public.transactions from anon, authenticated;
revoke all on public.audit_logs from anon, authenticated;

comment on table public.audit_logs is
    'Log generik CatatKas untuk autentikasi, ekstraksi, transaksi, dan health check.';

-- Data lama sengaja tidak dipasangkan ke sembarang akun. Setelah user pertama
-- terdaftar, ambil UUID-nya dari Authentication > Users, lalu jalankan sendiri:
--
-- update public.transactions
-- set user_id = 'UUID-USER-YANG-BENAR'
-- where user_id is null;
--
-- Setelah tidak ada row null, kunci kolom agar semua data selalu memiliki owner:
-- alter table public.transactions alter column user_id set not null;
