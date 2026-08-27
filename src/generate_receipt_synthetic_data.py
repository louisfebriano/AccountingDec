"""Generator deterministik dataset nota sintetis untuk bootstrap Prompt Tuning."""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence

from . import config
from .train_receipt import (
    validate_receipt_splits,
    validate_receipt_training_row,
)


MERCHANTS = (
    "Toko Berkah Jaya",
    "Warung Sari Rasa",
    "Kedai Nusantara",
    "Dapur Bu Rina",
    "Toko Makmur Abadi",
    "RM Selera Kampung",
    "Grosir Pangan Kita",
    "Pasar Segar Mandiri",
    "Koperasi Maju Bersama",
    "Toko Sumber Rejeki",
    "Depot Rasa Ibu",
    "Kedai Kopi Pagi",
    "Toko Mitra Kuliner",
    "Warung Barokah",
    "Pusat Bahan Kue",
    "Toko Harapan Baru",
)

ITEM_CATALOG = (
    ("Beras premium", "kg", 16000),
    ("Minyak goreng", "liter", 18000),
    ("Tepung terigu", "kg", 14000),
    ("Gula pasir", "kg", 17000),
    ("Telur ayam", "butir", 2500),
    ("Gas LPG 3 kg", "tabung", 22000),
    ("Cabai merah", "kg", 60000),
    ("Bawang merah", "kg", 42000),
    ("Bawang putih", "kg", 40000),
    ("Daging ayam", "kg", 38000),
    ("Santan kelapa", "bungkus", 8000),
    ("Kecap manis", "botol", 15000),
    ("Air mineral", "botol", 5000),
    ("Teh celup", "kotak", 12000),
    ("Kopi bubuk", "bungkus", 18000),
    ("Mie telur", "bungkus", 9000),
    ("Nasi goreng", "porsi", 18000),
    ("Ayam geprek", "porsi", 20000),
    ("Soto ayam", "porsi", 17000),
    ("Es teh manis", "gelas", 6000),
    ("Jus jeruk", "gelas", 12000),
    ("Kopi susu", "gelas", 15000),
    ("Roti bakar", "porsi", 16000),
    ("Kerupuk udang", "bungkus", 7000),
    ("Saus sambal", "botol", 13000),
    ("Kotak makanan", "pak", 25000),
    ("Sedotan kertas", "pak", 12000),
    ("Tisu makan", "pak", 10000),
    ("Sabun cuci piring", "botol", 16000),
    ("Garam halus", "bungkus", 5000),
)

MONTH_NAMES = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

SPLIT_LAYOUTS = {
    "train": (0, 1, 2, 3, 4),
    "validation": (5, 6),
    "evaluation": (7, 8),
}


def _format_amount(value: int, rng: random.Random) -> str:
    """Bentuk nominal bergaya hasil OCR Indonesia."""
    grouped_dot = f"{value:,}".replace(",", ".")
    grouped_comma = f"{value:,}"
    grouped_space = f"{value:,}".replace(",", " ")
    return rng.choice(
        (
            str(value),
            grouped_dot,
            grouped_comma,
            grouped_space,
            f"Rp {grouped_dot}",
            f"Rp{grouped_dot}",
        )
    )


def _format_quantity(value: int | float, rng: random.Random) -> str:
    if isinstance(value, int):
        return str(value)
    rendered = f"{value:g}"
    return rendered.replace(".", ",") if rng.random() < 0.5 else rendered


def _format_date(value: date, rng: random.Random) -> str:
    return rng.choice(
        (
            value.strftime("%d/%m/%Y"),
            value.strftime("%d-%m-%Y"),
            value.isoformat(),
            f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}",
        )
    )


def _choose_quantity(unit: str, rng: random.Random) -> int | float:
    if unit == "kg":
        return rng.choice((0.5, 1, 1.5, 2, 3))
    return rng.randint(1, 5)


def _build_item(
    rng: random.Random,
    catalog_item: tuple[str, str, int] | None = None,
) -> tuple[dict[str, Any], str, int]:
    """Buat target item, baris OCR, dan nilai aktual untuk perhitungan nota."""
    item_name, unit, unit_price = catalog_item or rng.choice(ITEM_CATALOG)
    quantity = _choose_quantity(unit, rng)
    actual_line_total = round(quantity * unit_price)
    mode = rng.choices(
        ("full", "compact", "name_total", "unit_price_only"),
        weights=(62, 18, 12, 8),
        k=1,
    )[0]
    quantity_text = _format_quantity(quantity, rng)
    unit_price_text = _format_amount(unit_price, rng)
    line_total_text = _format_amount(actual_line_total, rng)

    if mode == "full":
        output = {
            "item_name": item_name,
            "quantity": quantity,
            "unit": unit,
            "unit_price": unit_price,
            "line_total": actual_line_total,
        }
        line = (
            f"{quantity_text} {unit} {item_name} "
            f"@ {unit_price_text}  {line_total_text}"
        )
    elif mode == "compact":
        output = {
            "item_name": item_name,
            "quantity": quantity,
            "unit": None,
            "unit_price": None,
            "line_total": actual_line_total,
        }
        line = f"{quantity_text} x {item_name}  {line_total_text}"
    elif mode == "name_total":
        output = {
            "item_name": item_name,
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "line_total": actual_line_total,
        }
        line = f"{item_name}  {line_total_text}"
    else:
        output = {
            "item_name": item_name,
            "quantity": quantity,
            "unit": unit,
            "unit_price": unit_price,
            "line_total": None,
        }
        line = f"{quantity_text} {unit} {item_name} @ {unit_price_text}"
    return output, line, actual_line_total


def _layout_labels(layout: int) -> dict[str, str]:
    variants = (
        {"number": "NO. NOTA", "date": "TANGGAL", "subtotal": "SUBTOTAL", "discount": "DISKON", "tax": "PAJAK", "service": "SERVICE", "total": "TOTAL"},
        {"number": "INVOICE", "date": "TGL", "subtotal": "JUMLAH", "discount": "POTONGAN", "tax": "PPN", "service": "BIAYA LAYANAN", "total": "TOTAL BAYAR"},
        {"number": "N0. N0TA", "date": "TGL.", "subtotal": "SUBT0TAL", "discount": "DISK0N", "tax": "PAJAK", "service": "SERVICE CHARGE", "total": "GRAND T0TAL"},
        {"number": "TRX", "date": "DATE", "subtotal": "SUB TOTAL", "discount": "DISC", "tax": "TAX", "service": "SVC", "total": "AMOUNT"},
        {"number": "FAKTUR", "date": "TANGGAL TRANSAKSI", "subtotal": "TOTAL ITEM", "discount": "POTONGAN HARGA", "tax": "PPN 10%", "service": "ONGKOS LAYANAN", "total": "JUMLAH DIBAYAR"},
        {"number": "NOMOR", "date": "WAKTU TRANSAKSI", "subtotal": "SUB-JUMLAH", "discount": "HEMAT", "tax": "PB1", "service": "LAYANAN", "total": "TAGIHAN"},
        {"number": "REF", "date": "TGL BELI", "subtotal": "JML BARANG", "discount": "VOUCHER", "tax": "PAJAK RESTO", "service": "BIAYA SERVIS", "total": "BAYAR"},
        {"number": "RECEIPT", "date": "PURCHASE DATE", "subtotal": "NET ITEM", "discount": "PROMO", "tax": "TAX 10%", "service": "SERVICE FEE", "total": "FINAL TOTAL"},
        {"number": "KODE NOTA", "date": "DIBUAT", "subtotal": "JUMLAH SEMENTARA", "discount": "POTONGAN", "tax": "PAJAK DAERAH", "service": "BIAYA TAMBAHAN", "total": "TOTAL AKHIR"},
    )
    return variants[layout]


def _render_receipt(
    *,
    layout: int,
    merchant_name: str | None,
    receipt_number: str | None,
    receipt_date: date | None,
    item_lines: Sequence[str],
    subtotal: int | None,
    discount: int | None,
    tax: int | None,
    service_charge: int | None,
    total: int | None,
    rng: random.Random,
) -> str:
    labels = _layout_labels(layout)
    separators = ("--------------------------------", "================================", "................................", "- - - - - - - - - - - - - - -")
    separator = separators[layout % len(separators)]
    title = merchant_name or rng.choice(("NOTA PEMBELIAN", "STRUK BELANJA", "BUKTI TRANSAKSI"))
    lines = [title]
    if merchant_name is not None and rng.random() < 0.7:
        lines.append(rng.choice(("Cabang Karawang", "Cabang Bandung", "Cabang Bekasi", "Cabang Jakarta")))
    if receipt_number is not None:
        lines.append(f"{labels['number']}: {receipt_number}")
    if receipt_date is not None:
        lines.append(f"{labels['date']}: {_format_date(receipt_date, rng)}")
    if rng.random() < 0.45:
        lines.append(f"KASIR: {rng.choice(('ANI', 'BUDI', 'RINA', 'SARI', 'D01'))}")
    lines.extend((separator, rng.choice(("QTY ITEM HARGA JUMLAH", "RINCIAN BELANJA", "NAMA BARANG        JUMLAH"))))
    lines.extend(item_lines or ("RINCIAN BARANG TIDAK TERBACA",))
    lines.append(separator)

    summary = (
        ("subtotal", subtotal),
        ("discount", discount),
        ("tax", tax),
        ("service", service_charge),
        ("total", total),
    )
    for key, value in summary:
        if value is not None:
            joiner = rng.choice((": ", "  ", " .... "))
            lines.append(f"{labels[key]}{joiner}{_format_amount(value, rng)}")

    if total is not None and rng.random() < 0.3:
        cash = ((total + 9999) // 10000) * 10000
        lines.append(f"TUNAI: {_format_amount(cash, rng)}")
        lines.append(f"KEMBALI: {_format_amount(cash - total, rng)}")
    lines.append(rng.choice(("TERIMA KASIH", "-- LUNAS --", "SIMPAN NOTA INI", "TERIMA KASIH ATAS KUNJUNGAN ANDA")))
    return "\n".join(lines)


def generate_receipt_row(
    split: str,
    index: int,
    rng: random.Random,
) -> dict[str, Any]:
    """Buat satu contoh sintetik yang seluruh targetnya diturunkan dari OCR text."""
    if split not in SPLIT_LAYOUTS:
        raise ValueError(f"Split tidak didukung: {split}")
    layout = rng.choice(SPLIT_LAYOUTS[split])
    receipt_date_value = date(2024, 1, 1) + timedelta(days=rng.randint(0, 1095))
    reference_date = receipt_date_value + timedelta(days=rng.randint(0, 30))

    merchant_name = rng.choice(MERCHANTS) if rng.random() < 0.9 else None
    receipt_number = (
        f"{rng.choice(('INV', 'TRX', 'NT', 'FK'))}/{receipt_date_value:%y%m}/{index + 1:05d}"
        if rng.random() < 0.78
        else None
    )
    exposed_date = receipt_date_value if rng.random() < 0.9 else None
    item_count = 0 if rng.random() < 0.04 else rng.randint(1, 5)
    selected_catalog = list(ITEM_CATALOG)
    rng.shuffle(selected_catalog)

    items: list[dict[str, Any]] = []
    item_lines: list[str] = []
    actual_subtotal = 0
    for catalog_item in selected_catalog[:item_count]:
        item, line, line_total = _build_item(rng, catalog_item)
        items.append(item)
        item_lines.append(line)
        actual_subtotal += line_total

    if not items:
        actual_subtotal = rng.randrange(15000, 200001, 5000)

    subtotal = actual_subtotal if rng.random() < 0.86 else None
    discount: int | None = None
    if rng.random() < 0.34:
        choices = [0, 1000, 2000, 5000, round(actual_subtotal * 0.05)]
        discount = rng.choice([value for value in choices if value <= actual_subtotal])
    tax: int | None = None
    if rng.random() < 0.38:
        tax = rng.choice((0, round((actual_subtotal - (discount or 0)) * 0.1)))
    service_charge: int | None = None
    if rng.random() < 0.24:
        service_charge = rng.choice((0, 1000, 2000, 3000, 5000))
    actual_total = actual_subtotal - (discount or 0) + (tax or 0) + (service_charge or 0)
    total = actual_total if rng.random() < 0.96 else None

    ocr_text = _render_receipt(
        layout=layout,
        merchant_name=merchant_name,
        receipt_number=receipt_number,
        receipt_date=exposed_date,
        item_lines=item_lines,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        service_charge=service_charge,
        total=total,
        rng=rng,
    )
    row = {
        "receipt_id": f"synthetic-{split}-{index + 1:05d}",
        "template_id": f"synthetic-layout-{layout}",
        "data_origin": "synthetic",
        "input": ocr_text,
        "reference_date": reference_date.isoformat(),
        "output": {
            "merchant_name": merchant_name,
            "receipt_number": receipt_number,
            "date": exposed_date.isoformat() if exposed_date is not None else None,
            "items": items,
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "service_charge": service_charge,
            "total": total,
            "transaction_type": "expense",
        },
    }
    return validate_receipt_training_row(row)


def generate_dataset(split: str, count: int, seed: int) -> list[dict[str, Any]]:
    """Buat satu split dengan random generator lokal yang reproducible."""
    if count <= 0:
        raise ValueError("Jumlah contoh harus lebih besar dari nol.")
    rng = random.Random(seed)
    return [generate_receipt_row(split, index, rng) for index in range(count)]


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Tulis JSONL UTF-8 setelah seluruh baris berhasil divalidasi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows
    )
    path.write_text(content + "\n", encoding="utf-8")


def generate_and_write(
    *,
    train_count: int,
    validation_count: int,
    evaluation_count: int,
    seed: int,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Buat, periksa leakage, lalu tulis ketiga split sintetik."""
    train_rows = generate_dataset("train", train_count, seed)
    validation_rows = generate_dataset("validation", validation_count, seed + 1)
    evaluation_rows = generate_dataset("evaluation", evaluation_count, seed + 2)
    validate_receipt_splits(train_rows, validation_rows, evaluation_rows)

    destination = Path(output_dir)
    paths = {
        "train": destination / Path(config.RECEIPT_TRAIN_DATA_PATH).name,
        "validation": destination / Path(config.RECEIPT_VALIDATION_DATA_PATH).name,
        "evaluation": destination / Path(config.RECEIPT_EVAL_DATA_PATH).name,
    }
    for split, rows in (
        ("train", train_rows),
        ("validation", validation_rows),
        ("evaluation", evaluation_rows),
    ):
        write_jsonl(paths[split], rows)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Buat dataset sintetis Soft Prompt Nota CatatKas",
    )
    parser.add_argument("--train-count", type=int, default=400)
    parser.add_argument("--validation-count", type=int, default=80)
    parser.add_argument("--evaluation-count", type=int, default=80)
    parser.add_argument("--seed", type=int, default=config.TRAIN_SEED)
    parser.add_argument("--output-dir", default="data/processed")
    args = parser.parse_args()

    paths = generate_and_write(
        train_count=args.train_count,
        validation_count=args.validation_count,
        evaluation_count=args.evaluation_count,
        seed=args.seed,
        output_dir=args.output_dir,
    )
    print(
        f"Dataset sintetis dibuat: train={args.train_count}, "
        f"validation={args.validation_count}, evaluation={args.evaluation_count}"
    )
    for split, path in paths.items():
        print(f"- {split}: {path}")


if __name__ == "__main__":
    main()
