"""Loader dan konversi dataset CORD dari Hugging Face untuk fitur nota."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Mapping, Sequence

from .train_receipt import validate_receipt_training_row


CORD_DATASET_NAME = "naver-clova-ix/cord-v2"
CORD_DATASET_SPLITS = ("train", "validation", "test")


def load_cord_dataset() -> Any:
    """Muat dataset CORD v2 beserta gambar nota dan ground truth dari Hugging Face."""
    from datasets import load_dataset

    return load_dataset(CORD_DATASET_NAME)


def parse_cord_ground_truth(ground_truth: Any) -> dict[str, Any]:
    """Baca kolom ``ground_truth`` CORD (JSON string) menjadi mapping terstruktur."""
    if isinstance(ground_truth, Mapping):
        return dict(ground_truth)
    if isinstance(ground_truth, str):
        value = json.loads(ground_truth)
        if not isinstance(value, Mapping):
            raise ValueError("ground_truth CORD harus berupa objek JSON.")
        return dict(value)
    raise ValueError("ground_truth CORD harus berupa string JSON atau mapping.")


def _lookup(source: Mapping[str, Any], keys: Sequence[str]) -> Any:
    """Cari nilai pada mapping utama atau pada blok ``gt_parse`` CORD."""
    gt_parse = source.get("gt_parse") if isinstance(source.get("gt_parse"), Mapping) else {}
    for key in keys:
        if source.get(key) is not None:
            return source[key]
    for key in keys:
        if gt_parse.get(key) is not None:
            return gt_parse[key]
    return None


def _parse_cord_amount(value: Any) -> int | None:
    """Ubah nominal CORD (Rp, titik, atau koma ribuan) menjadi integer rupiah."""
    digits = re.sub(r"\D", "", str(value or "").lower())
    return int(digits) if digits else None


def _parse_cord_quantity(value: Any) -> float | None:
    """Baca quantity CORD setelah menghapus akar x/@ dan pemisah desimal."""
    text = re.sub(r"[xX@]", "", str(value or "").strip().lower()).replace(" ", "")
    if not text or not re.fullmatch(r"\d+(?:[.,]\d+)?", text):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _menu_entries(ground_truth: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Kembalikan daftar menu CORD; menu bisa berupa list atau satu entry tunggal."""
    gt_parse = (
        ground_truth.get("gt_parse")
        if isinstance(ground_truth.get("gt_parse"), Mapping)
        else {}
    )
    menu = gt_parse.get("menu")
    entries: list[Mapping[str, Any]] = []
    if isinstance(menu, list):
        entries = [entry for entry in menu if isinstance(entry, Mapping)]
    elif isinstance(menu, Mapping):
        entries = [menu]
    return entries


def extract_cord_items(ground_truth: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Ubah menu CORD menjadi rincian item yang konsisten dengan schema nota."""
    items: list[dict[str, Any]] = []
    for entry in _menu_entries(ground_truth):
        item_name = str(_lookup(entry, ("nm", "name")) or "").strip()
        if not item_name:
            continue
        unit_price = _parse_cord_amount(_lookup(entry, ("unitprice", "unit_price")))
        line_total = _parse_cord_amount(_lookup(entry, ("price", "line_total", "item_subtotal")))
        quantity = _parse_cord_quantity(_lookup(entry, ("cnt", "quantity", "qty")))
        if quantity is None or quantity <= 0:
            quantity = None
            if unit_price and line_total:
                quantity = line_total / unit_price
        if quantity is None or quantity <= 0:
            continue
        quantity_value = int(quantity) if float(quantity).is_integer() else quantity
        if line_total is None and unit_price:
            line_total = int(round(float(quantity) * unit_price))
        items.append(
            {
                "item_name": item_name[:200],
                "quantity": quantity_value,
                "unit": None,
                "unit_price": int(unit_price) if unit_price is not None else None,
                "line_total": int(line_total) if line_total is not None else None,
            }
        )
    return items


def compute_cord_total(ground_truth: Mapping[str, Any]) -> int | None:
    """Hitung total nota dari jumlah harga barang per item."""
    items = extract_cord_items(ground_truth)
    line_totals = [
        item["line_total"]
        for item in items
        if item.get("line_total") is not None
    ]
    if line_totals:
        return sum(line_totals)
    gt_parse = (
        ground_truth.get("gt_parse")
        if isinstance(ground_truth.get("gt_parse"), Mapping)
        else {}
    )
    total_block = gt_parse.get("total") if isinstance(gt_parse.get("total"), Mapping) else {}
    subtotal_block = (
        gt_parse.get("sub_total") if isinstance(gt_parse.get("sub_total"), Mapping) else {}
    )
    total = _parse_cord_amount(total_block.get("total_price"))
    if total is None:
        total = _parse_cord_amount(subtotal_block.get("subtotal_price"))
    return total


def _cord_date(ground_truth: Mapping[str, Any]) -> str | None:
    """Baca tanggal nota CORD; tanggal tidak valid diabaikan."""
    raw = _lookup(ground_truth, ("date", "transaction_date", "tanggal", "tgl", "purchase_date"))
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _cord_text(ground_truth: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    """Baca teks opsional (merchant/nomor nota) CORD sebagai string atau null."""
    value = _lookup(ground_truth, keys)
    text = str(value or "").strip()
    return text or None


def build_cord_receipt_output(
    ground_truth: Mapping[str, Any],
    *,
    reference_date: date,
) -> dict[str, Any]:
    """Bentuk output nota CORD dengan field transaksi yang relevan untuk CatatKas.

    Field nota seperti subtotal, diskon, pajak, dan biaya layanan tidak dibawa ke
    target training; total dihitung dari harga barang per item.
    """
    items = extract_cord_items(ground_truth)
    total = compute_cord_total(ground_truth)
    if total is None:
        total = sum(
            item["line_total"]
            for item in items
            if item.get("line_total") is not None
        ) or None
    merchant_name = _cord_text(
        ground_truth,
        ("merchant_name", "merchant", "store_name", "store"),
    )
    receipt_number = _cord_text(
        ground_truth,
        ("receipt_number", "receipt_no", "invoice", "trx", "receipt"),
    )
    return {
        "merchant_name": merchant_name,
        "receipt_number": receipt_number,
        "date": _cord_date(ground_truth) or reference_date.isoformat(),
        "items": items,
        "subtotal": None,
        "discount": None,
        "tax": None,
        "service_charge": None,
        "total": total,
        "transaction_type": "expense",
    }


def build_cord_training_row(
    *,
    receipt_id: str,
    ocr_text: str,
    reference_date: date,
    ground_truth: Mapping[str, Any],
    data_origin: str = "real",
) -> dict[str, Any]:
    """Bangun satu baris training CatatKas dari contoh nota CORD."""
    row = {
        "receipt_id": receipt_id,
        "data_origin": data_origin,
        "input": ocr_text.replace("\r\n", "\n").replace("\r", "\n").strip(),
        "reference_date": reference_date.isoformat(),
        "output": build_cord_receipt_output(ground_truth, reference_date=reference_date),
    }
    return validate_receipt_training_row(row)
