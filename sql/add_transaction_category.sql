-- Tambahkan kolom kategori pada transaksi CatatKas untuk UMKM.
-- Jalankan sekali melalui Supabase SQL Editor pada instalasi yang sudah ada.
-- Migrasi idempotent: kolom dan constraint dapat dibuat ulang tanpa menghapus
-- nilai kategori yang sudah tersimpan.

begin;

alter table public.transactions
    add column if not exists category text;

alter table public.transactions
    drop constraint if exists transactions_category_length;
alter table public.transactions
    add constraint transactions_category_length
    check (category is null or char_length(category) <= 50);

comment on column public.transactions.category is
    'Kategori UMKM untuk satu transaksi, maksimal 50 karakter, null bila belum dipilih.';

commit;
