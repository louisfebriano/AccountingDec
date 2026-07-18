"""
Post-processing: ekstrak JSON dari output model + validasi field + resolve tanggal relatif.
"""

import json
import re
from datetime import date
from typing import Optional
from pydantic import BaseModel, ValidationError

from .date_utils import resolve_relative_date

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

    Field "date" akan di-resolve otomatis lewat rule-based resolver (bukan diserahkan ke
    model, karena model nggak tau tanggal hari ini) kalau salah satu dari ini terjadi:
    - model mengisi null
    - model mengisi teks yang BUKAN format tanggal valid (misal "besok", "kemarin" mentah
      ikut ke-generate sebagai value, bukan di-null-kan sebagaimana harusnya)

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

    if not _is_valid_iso_date(result_data.get("date")) and user_input:
        resolved = resolve_relative_date(user_input, reference_date)
        result_data["date"] = resolved  # None kalau nggak ketemu kata relatif juga

    return {"success": True, "data": result_data, "error": None}