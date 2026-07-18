"""
Post-processing: ekstrak JSON dari output model + validasi field + resolve tanggal relatif.
"""

import json
from datetime import date
from typing import Optional
from pydantic import BaseModel, ValidationError

from .date_utils import resolve_relative_date


class TransaksiSchema(BaseModel):
    item_name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    total_price: Optional[float] = None
    date: Optional[str] = None


def parse_and_validate(
    raw_output: str,
    user_input: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> dict:
    """
    Parse raw output model jadi dict terstruktur + validasi.
    Ambil HANYA objek JSON pertama yang valid (abaikan teks/JSON tambahan setelahnya,
    karena model kadang lanjut generate pola few-shot lain).

    Kalau field "date" hasil model masih null DAN user_input mengandung kata tanggal
    relatif ("kemarin", "hari ini", dll), field date akan diisi otomatis lewat rule-based
    resolver (bukan diserahkan ke model, karena model nggak tau tanggal hari ini).

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

    if result_data.get("date") is None and user_input:
        resolved = resolve_relative_date(user_input, reference_date)
        if resolved is not None:
            result_data["date"] = resolved

    return {"success": True, "data": result_data, "error": None}