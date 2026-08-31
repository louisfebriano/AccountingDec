-- Migrasi idempotent untuk profil pengguna CatatKas di schema public.
-- Nilai yang sudah ada dipertahankan; hanya tipe VARCHAR yang diubah menjadi TEXT.

alter table public.users
    alter column name type text using name::text;
