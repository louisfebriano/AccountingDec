-- Perbaiki instalasi CatatKas lama yang membuat foreign key receipt_items
-- pada kolom id. Jalankan sekali melalui Supabase SQL Editor.
-- Migrasi ini tidak menghapus receipts, receipt_items, atau transactions.

begin;

do $$
begin
    if exists (
        select 1
        from public.receipts r
        left join public.transactions t on t.id = r.transaction_id
        where t.id is null
    ) then
        raise exception
            'Migrasi dibatalkan: receipts memiliki transaction_id tanpa transactions.';
    end if;

    if exists (
        select 1
        from public.receipt_items ri
        left join public.receipts r on r.id = ri.receipt_id
        where r.id is null
    ) then
        raise exception
            'Migrasi dibatalkan: receipt_items memiliki receipt_id tanpa receipts.';
    end if;
end
$$;

-- Constraint ini salah: id item adalah identitas item, bukan id nota.
alter table public.receipt_items
    drop constraint if exists receipt_items_id_fkey;

-- Samakan relasi receipt -> transaction dengan skema CatatKas terbaru.
alter table public.receipts
    drop constraint if exists receipts_transaction_id_fkey;
alter table public.receipts
    add constraint receipts_transaction_id_fkey
    foreign key (transaction_id)
    references public.transactions(id)
    on delete cascade;

-- Relasi yang benar untuk seluruh rincian barang pada sebuah nota.
alter table public.receipt_items
    drop constraint if exists receipt_items_receipt_id_fkey;
alter table public.receipt_items
    add constraint receipt_items_receipt_id_fkey
    foreign key (receipt_id)
    references public.receipts(id)
    on delete cascade;

-- Quantity nota dapat berupa pecahan dan confidence memakai rentang desimal 0..1.
alter table public.receipt_items
    alter column quantity type numeric(14, 3)
        using quantity::numeric(14, 3),
    alter column confidence type numeric(5, 4)
        using confidence::numeric(5, 4);

alter table public.receipts
    alter column confidence type numeric(5, 4)
        using confidence::numeric(5, 4);

alter table public.receipts
    drop constraint if exists receipts_confidence_range;
alter table public.receipts
    add constraint receipts_confidence_range
    check (confidence is null or confidence between 0 and 1);

alter table public.receipt_items
    drop constraint if exists receipt_items_quantity_positive;
alter table public.receipt_items
    add constraint receipt_items_quantity_positive
    check (quantity is null or quantity > 0);

alter table public.receipt_items
    drop constraint if exists receipt_items_confidence_range;
alter table public.receipt_items
    add constraint receipt_items_confidence_range
    check (confidence is null or confidence between 0 and 1);

create index if not exists receipt_items_receipt_id_idx
    on public.receipt_items (receipt_id, line_number);

commit;
