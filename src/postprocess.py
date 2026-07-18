"""
Post-processing: ekstrak JSON dari output model + validasi field.
"""

import json
from typing import Optional
from pydantic import BaseModel, ValidationError


class TransaksiSchema(BaseModel):
    item_name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    total_price: Optional[float] = None
    date: Optional[str] = None


def parse_and_validate(raw_output: str) -> dict:
    """
        Parse raw output model jadi dict terstruktur + validasi.
        Ambil HANYA objek JSON pertama yang valid (abaikan teks/JSON tambahan setelahnya,
        karena model kadang lanjut generate pola few-shot lain).
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

    return {"success": True, "data": validated.model_dump(), "error": None}
