"""
Post-processing: ekstrak JSON dari output model + validasi field + resolve tanggal relatif
+ validasi/override harga secara deterministik.
"""

import json
import re
from datetime import date
from typing import Optional
from pydantic import BaseModel, ValidationError

from .date_utils import resolve_date
from .price_utils import extract_price_from_text

ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TransaksiSchema(BaseModel):
    item_name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    total_price: Optional[float] = None
    date: Optional[str] = None


def _is_valid_iso_date(value: Optional[str]) -> bool:
    if not value or not ISO_DATE_PATTERN.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def parse_and_validate(
    raw_output: str,
    user_input: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> dict:
    """
    Parse raw output model jadi dict terstruktur + validasi.
    Ambil HANYA objek JSON pertama yang valid (abaikan teks/JSON tambahan setelahnya,
    karena model kadang lanjut generate pola few-shot lain).

    Aturan pengisian field "date":
    1. Kalau model sudah kasih tanggal format ISO valid -> dipakai apa adanya.
    2. Kalau tidak, coba resolve dari kata relatif di kalimat ("kemarin", "besok", dll).
    3. Kalau masih tidak ketemu -> default ke reference_date (hari ini kalau tidak dikirim
       eksplisit), asumsinya transaksi tanpa keterangan waktu terjadi saat dicatat.

    Aturan pengisian field "total_price":
    Kalau user_input mengandung pola "angka+akhiran ribuan/ratusan" yang jelas
    (rb/ribu/rebu/k/ratus), nilai itu yang dipakai (override hasil model). Ini karena
    konversi satuan harga adalah aturan matematis pasti, bukan sesuatu yang perlu "ditebak"
    model -- lebih reliable diambil lewat rule daripada bergantung ke soft prompt yang
    kapasitasnya terbatas untuk generalisasi ke variasi kalimat baru.

    Return dict {"success": bool, "data": ..., "error": ...}
    """
    start = raw_output.find("{")
    if start == -1:
        return {"success": False, "data": None, "error": "Tidak ditemukan JSON pada output"}

    decoder = json.JSONDecoder()
    try:
        raw_dict, _end_index = decoder.raw_decode(raw_output, start)
    except json.JSONDecodeError as e:
        return {"success": False, "data": None, "error": f"JSON tidak valid: {e}"}

    try:
        validated = TransaksiSchema(**raw_dict)
    except ValidationError as e:
        return {"success": False, "data": None, "error": f"Validasi gagal: {e}"}

    result_data = validated.model_dump()
    reference_date = reference_date or date.today()

    # ---- Resolve date ----
    # Prioritas: kalau kalimat mengandung kata/pola tanggal relatif ("kemarin", "3 hari lalu",
    # dll), SELALU pakai hasil resolver -- jangan percaya tanggal dari model sama sekali untuk
    # kasus ini, karena model bisa hallucinate tanggal yang formatnya valid tapi isinya ngasal
    # (mirip alasan kenapa total_price di-override lewat rule juga).
    resolved = resolve_date(user_input, reference_date) if user_input else None
    if resolved is not None:
        result_data["date"] = resolved
    elif not _is_valid_iso_date(result_data.get("date")):
        result_data["date"] = reference_date.isoformat()

    # ---- Override total_price kalau pola harga eksplisit ketemu di kalimat asli ----
    if user_input:
        extracted_price = extract_price_from_text(user_input)
        if extracted_price is not None:
            result_data["total_price"] = extracted_price

    return {"success": True, "data": result_data, "error": None}