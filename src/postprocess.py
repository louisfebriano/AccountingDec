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
from .transaction_type import TransactionType

_PRICE_EXPRESSION_PATTERN = re.compile(
    r"(?:rp\s*)?(?:\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*"
    r"(?:ribu|rebu|rb|ratus|juta|jt|k)\b|"
    r"(?:rp\s*)?\d{1,3}(?:\.\d{3})+\b|\b\d{4,}\b",
    re.IGNORECASE,
)
_DATE_EXPRESSION_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(
        r"\b(?:tanggal\s+)?\d{1,2}\s+"
        r"(?:januari|februari|maret|april|mei|juni|juli|agustus|"
        r"september|oktober|november|desember)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+(?:[.,]\d+)?\s+(?:hari|minggu|bulan|tahun)\s+"
        r"(?:yang\s+)?(?:lalu|kemudian)\b",
        re.IGNORECASE,
    ),
)
_NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
_GENERIC_ITEM_NAMES = {
    "barang",
    "belanja",
    "dagangan",
    "item",
    "jualan",
    "kebutuhan",
    "pembelian",
    "penjualan",
    "pesanan",
    "produk",
    "stok",
}
_UNIT_ALIASES = {
    "ball": ("ball", "bal"),
    "biji": ("biji",),
    "box": ("box",),
    "buah": ("buah",),
    "bungkus": ("bungkus", "bks"),
    "botol": ("botol", "btl"),
    "dus": ("dus",),
    "galon": ("galon",),
    "gelas": ("gelas",),
    "gram": ("gram", "gr"),
    "gross": ("gross",),
    "ikat": ("ikat",),
    "karung": ("karung", "krg"),
    "kg": ("kg", "kilo", "kilogram"),
    "kodi": ("kodi",),
    "kotak": ("kotak",),
    "lembar": ("lembar", "lbr"),
    "liter": ("liter", "ltr"),
    "loyang": ("loyang",),
    "lusin": ("lusin",),
    "ml": ("ml", "mililiter"),
    "pak": ("pak",),
    "papan": ("papan",),
    "pcs": ("pcs",),
    "porsi": ("porsi",),
    "renceng": ("renceng",),
    "rim": ("rim",),
    "roll": ("roll",),
    "slop": ("slop",),
    "tabung": ("tabung", "tbg"),
    "tray": ("tray",),
    "unit": ("unit",),
}

_UNIT_ALIAS_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in _UNIT_ALIASES.items()
    for alias in aliases
}
_UNIT_TOKEN_PATTERN = "|".join(
    re.escape(alias)
    for alias in sorted(_UNIT_ALIAS_TO_CANONICAL, key=len, reverse=True)
)
_QUANTITY_TOKEN_PATTERN = r"\d+(?:[.,]\d+)?"
_FRACTION_VALUES = {
    "setengah": 0.5,
    "seperempat": 0.25,
    "tiga perempat": 0.75,
}
_FRACTION_TOKEN_PATTERN = "|".join(
    re.escape(value) for value in sorted(_FRACTION_VALUES, key=len, reverse=True)
)
_OUTER_PACKAGE_BEFORE_CONTENT = re.compile(
    rf"\b(?P<quantity>{_QUANTITY_TOKEN_PATTERN})\s+"
    rf"(?P<unit>{_UNIT_TOKEN_PATTERN})\s+isi\s+"
    rf"{_QUANTITY_TOKEN_PATTERN}(?:\s+(?:{_UNIT_TOKEN_PATTERN}))?\b",
    re.IGNORECASE,
)
_OUTER_PACKAGE_AFTER_CONTENT = re.compile(
    rf"\bisi\s+{_QUANTITY_TOKEN_PATTERN}"
    rf"(?:\s+(?:{_UNIT_TOKEN_PATTERN}))?\s+"
    rf"(?P<quantity>{_QUANTITY_TOKEN_PATTERN})\s+"
    rf"(?P<unit>{_UNIT_TOKEN_PATTERN})\b",
    re.IGNORECASE,
)
_FRACTION_QUANTITY_UNIT_PATTERN = re.compile(
    rf"\b(?P<quantity>{_FRACTION_TOKEN_PATTERN})\s+"
    rf"(?P<unit>{_UNIT_TOKEN_PATTERN})\b",
    re.IGNORECASE,
)
_NUMERIC_QUANTITY_UNIT_PATTERN = re.compile(
    rf"\b(?P<quantity>{_QUANTITY_TOKEN_PATTERN})\s+"
    rf"(?P<unit>{_UNIT_TOKEN_PATTERN})\b",
    re.IGNORECASE,
)

_SALE_UNIT_PATTERN = (
    r"porsi|pcs|buah|gelas|botol|bungkus|kotak|dus|karung|liter|kg|kilo|gram|"
    r"tabung|loyang"
)
_SALE_PRICE_PATTERN = (
    r"(?:rp\s*)?(?:\d{4,}|\d{1,3}(?:\.\d{3})+|"
    r"\d+(?:[.,]\d+)?\s*(?:ribu|rebu|rb|juta|jt|k))"
)
_QUANTITY_BEFORE_ITEM_SALE = re.compile(
    rf"\b(?P<quantity>\d+(?:[.,]\d+)?)\s+"
    rf"(?:(?P<unit>{_SALE_UNIT_PATTERN})\s+)?"
    r"(?P<item>[a-z][a-z\s]*?)\s+"
    r"(?:laku(?:\s+terjual)?|terjual)\b",
    re.IGNORECASE,
)
_TERJUAL_BEFORE_QUANTITY = re.compile(
    rf"\bterjual\s+(?P<quantity>\d+(?:[.,]\d+)?)\s+"
    rf"(?:(?P<unit>{_SALE_UNIT_PATTERN})\s+)?"
    r"(?P<item>[a-z][a-z\s]*?)\s+(?:total\s+)?"
    rf"{_SALE_PRICE_PATTERN}\b",
    re.IGNORECASE,
)
_ITEM_BEFORE_SALE_QUANTITY = re.compile(
    rf"\b(?P<item>[a-z][a-z\s]*?)\s+(?:laku|terjual)\s+"
    rf"(?P<quantity>\d+(?:[.,]\d+)?)\s+"
    rf"(?:(?P<unit>{_SALE_UNIT_PATTERN})\s+)?(?:total\s+)?"
    rf"{_SALE_PRICE_PATTERN}\b",
    re.IGNORECASE,
)
_JUAL_ITEM_QUANTITY = re.compile(
    rf"\b(?:jual|menjual)\s+(?P<item>[a-z][a-z\s]*?)\s+"
    rf"(?P<quantity>\d+(?:[.,]\d+)?)\s+"
    rf"(?:(?P<unit>{_SALE_UNIT_PATTERN})\s+)?(?:total\s+)?"
    rf"{_SALE_PRICE_PATTERN}\b",
    re.IGNORECASE,
)
_CUSTOMER_BUYS_ITEM = re.compile(
    rf"\b(?:pelanggan|pembeli)\s+(?:beli|membeli)\s+"
    rf"(?P<quantity>\d+(?:[.,]\d+)?)\s+"
    rf"(?:(?P<unit>{_SALE_UNIT_PATTERN})\s+)?"
    r"(?P<item>[a-z][a-z\s]*?)\s+(?:total\s+)?"
    rf"{_SALE_PRICE_PATTERN}\b",
    re.IGNORECASE,
)
_CLEAR_SALE_PATTERNS = (
    _QUANTITY_BEFORE_ITEM_SALE,
    _TERJUAL_BEFORE_QUANTITY,
    _ITEM_BEFORE_SALE_QUANTITY,
    _JUAL_ITEM_QUANTITY,
    _CUSTOMER_BUYS_ITEM,
)


class TransaksiSchema(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    total_price: Optional[float] = None
    date: Optional[str] = None
    transaction_type: TransactionType = "unknown"


def _extract_clear_sale_details(text: str) -> Optional[dict]:
    """Ambil detail penjualan untuk pola jumlah dan barang yang sangat jelas."""
    candidate = text
    for date_pattern in _DATE_EXPRESSION_PATTERNS:
        candidate = date_pattern.sub(" ", candidate)
    normalized = re.sub(
        r"[^\w.,]+",
        " ",
        candidate,
        flags=re.UNICODE,
    ).strip()
    match = None
    for pattern in _CLEAR_SALE_PATTERNS:
        match = pattern.search(normalized)
        if match is not None:
            break
    if match is None:
        return None

    quantity = float(match.group("quantity").replace(",", "."))
    if quantity.is_integer():
        quantity = int(quantity)
    return {
        "item_name": re.sub(r"\s+", " ", match.group("item")).strip().capitalize(),
        "quantity": quantity,
        "unit": match.group("unit").lower() if match.group("unit") else None,
    }


def _normalize_grounding_text(value: str) -> str:
    """Normalisasi teks agar frasa dan bentuk rapat seperti ``2krg`` dapat dicocokkan."""
    value = value.lower()
    value = re.sub(r"(?<=\d)(?=[^\W\d_])|(?<=[^\W\d_])(?=\d)", " ", value)
    value = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", " ", value)
    return re.sub(r"[^\w.,]+", " ", value, flags=re.UNICODE).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    """Cek frasa utuh pada teks yang sudah dinormalisasi."""
    if not phrase:
        return False
    return re.search(rf"(?:^|\s){re.escape(phrase)}(?:$|\s)", text) is not None


def _is_item_name_mentioned(item_name: Optional[str], user_input: str) -> bool:
    """Terima nama barang hanya jika seluruh tokennya benar-benar ada pada input."""
    if not item_name:
        return False

    normalized_item = _normalize_grounding_text(item_name)
    if normalized_item in _GENERIC_ITEM_NAMES:
        return False

    input_tokens = set(_normalize_grounding_text(user_input).split())
    item_tokens = normalized_item.split()
    return bool(item_tokens) and all(token in input_tokens for token in item_tokens)


def _text_without_price_date_or_item(
    user_input: str,
    item_name: Optional[str],
) -> str:
    """Sisakan teks yang aman dipakai untuk mengecek quantity dan unit."""
    candidate = _PRICE_EXPRESSION_PATTERN.sub(" ", user_input)
    for pattern in _DATE_EXPRESSION_PATTERNS:
        candidate = pattern.sub(" ", candidate)

    normalized = _normalize_grounding_text(candidate)
    normalized_item = _normalize_grounding_text(item_name or "")
    if normalized_item:
        normalized = re.sub(
            rf"(?:^|\s){re.escape(normalized_item)}(?:$|\s)",
            " ",
            normalized,
        )
    return re.sub(r"\s+", " ", normalized).strip()


def _is_quantity_mentioned(quantity: Optional[float], candidate_text: str) -> bool:
    """Pastikan quantity ada di input setelah harga, tanggal, dan nama barang dibuang."""
    if quantity is None:
        return False

    expected = float(quantity)
    for raw_number in _NUMBER_PATTERN.findall(candidate_text):
        try:
            if float(raw_number.replace(",", ".")) == expected:
                return True
        except ValueError:
            continue
    return False


def _canonicalize_unit(unit: Optional[str]) -> Optional[str]:
    """Ubah alias unit seperti ``bks`` dan ``tbg`` ke bentuk kanonis."""
    if not unit:
        return None
    normalized = _normalize_grounding_text(unit)
    return _UNIT_ALIAS_TO_CANONICAL.get(normalized)


def _is_unit_mentioned(unit: Optional[str], candidate_text: str) -> bool:
    """Cocokkan unit model dengan bentuk lengkap atau singkatannya pada input."""
    if not unit:
        return False

    canonical_unit = _canonicalize_unit(unit)
    if canonical_unit is None:
        return False
    aliases = _UNIT_ALIASES[canonical_unit]
    return any(_contains_phrase(candidate_text, alias) for alias in aliases)


def _parse_quantity_value(raw_value: str) -> float | int:
    """Parse quantity numerik atau pecahan lisan yang sudah dipastikan jelas."""
    normalized = re.sub(r"\s+", " ", raw_value.casefold()).strip()
    if normalized in _FRACTION_VALUES:
        return _FRACTION_VALUES[normalized]
    value = float(normalized.replace(",", "."))
    return int(value) if value.is_integer() else value


def _quantity_unit_from_match(match: re.Match) -> dict:
    """Bangun detail quantity/unit kanonis dari regex bernama."""
    return {
        "quantity": _parse_quantity_value(match.group("quantity")),
        "unit": _canonicalize_unit(match.group("unit")),
    }


def _extract_clear_quantity_unit(
    user_input: str,
    item_name: Optional[str],
) -> Optional[dict]:
    """Ambil quantity/unit eksplisit tanpa memakai angka harga atau ukuran item."""
    candidate_text = _text_without_price_date_or_item(user_input, item_name)
    if not candidate_text:
        return None

    # Pada "2 dus isi 24 botol" maupun "isi 24 botol 2 dus", dus adalah
    # kemasan transaksi dan botol adalah isi per kemasan.
    for pattern in (
        _OUTER_PACKAGE_BEFORE_CONTENT,
        _OUTER_PACKAGE_AFTER_CONTENT,
    ):
        match = pattern.search(candidate_text)
        if match is not None:
            return _quantity_unit_from_match(match)

    fraction_match = _FRACTION_QUANTITY_UNIT_PATTERN.search(candidate_text)
    if fraction_match is not None:
        return _quantity_unit_from_match(fraction_match)

    numeric_matches = list(_NUMERIC_QUANTITY_UNIT_PATTERN.finditer(candidate_text))
    if not numeric_matches:
        return None

    # Jika ukuran produk belum tercakup nama barang, pasangan terakhir biasanya
    # merupakan jumlah transaksi: "gas 3 kg 2 tabung" -> 2 tabung.
    return _quantity_unit_from_match(numeric_matches[-1])


def _null_unmentioned_optional_fields(result_data: dict, user_input: str) -> None:
    """Null-kan item, quantity, dan unit yang tidak dapat dilacak ke input pengguna."""
    model_item = result_data.get("item_name")
    item_is_mentioned = _is_item_name_mentioned(model_item, user_input)
    if not item_is_mentioned:
        result_data["item_name"] = None

    candidate_text = _text_without_price_date_or_item(
        user_input,
        model_item if item_is_mentioned else None,
    )
    if not _is_quantity_mentioned(result_data.get("quantity"), candidate_text):
        result_data["quantity"] = None
    canonical_unit = _canonicalize_unit(result_data.get("unit"))
    if not _is_unit_mentioned(canonical_unit, candidate_text):
        result_data["unit"] = None
    else:
        result_data["unit"] = canonical_unit


def _first_json_object(raw_output: str) -> tuple[Optional[dict], Optional[str]]:
    """Ambil HANYA objek JSON pertama yang valid dari output model.

    Model kadang tetap menulis contoh few-shot lain setelah JSON utama selesai.
    Semua teks setelah objek pertama sengaja diabaikan.
    """
    start = raw_output.find("{")
    if start == -1:
        return None, "Tidak ditemukan JSON pada output"
    try:
        parsed, _end_index = json.JSONDecoder().raw_decode(raw_output, start)
    except json.JSONDecodeError as exc:
        return None, f"JSON tidak valid: {exc}"
    if not isinstance(parsed, dict):
        return None, "JSON yang dihasilkan bukan objek"
    return parsed, None


def _apply_date_rule(user_input: Optional[str], reference_date: date) -> str:
    """Tentukan tanggal transaksi dari kalimat atau dari ``reference_date``.

    Tanggal keluaran model tidak dipercaya karena model dapat mengarang tanggal
    ISO yang valid tetapi tidak pernah disebut pengguna.
    """
    resolved = resolve_date(user_input, reference_date) if user_input else None
    return resolved or reference_date.isoformat()


def _apply_price_rule(result_data: dict, user_input: str) -> None:
    """Ambil nominal hanya dari pola harga yang benar-benar ada di kalimat.

    Konversi "180rb" menjadi 180000 adalah aturan matematis pasti, jadi lebih
    aman dihitung dengan regex daripada ditebak model. Bila kalimat tidak
    menyebut nominal, nilainya ``None`` dan pengguna mengisinya di dialog
    konfirmasi.
    """
    result_data["total_price"] = extract_price_from_text(user_input)


def _apply_tracked_quantity_rules(
    result_data: dict,
    user_input: str,
    transaction_type: TransactionType,
) -> None:
    """Lengkapi quantity/unit untuk pola yang jelas tertulis di kalimat.

    Dua pola yang ditangani:
    1. Jumlah dan satuan eksplisit, termasuk bentuk rapat ("500gram"), singkatan
       ("3tbg"), pecahan ("setengah kg"), dan kemasan bertingkat ("2 dus isi 24 botol").
    2. Penjualan yang menyebut jumlah barang secara jelas, misalnya "3 bakmi laku".
    """
    quantity_unit = _extract_clear_quantity_unit(user_input, result_data.get("item_name"))
    if quantity_unit is not None:
        result_data.update(quantity_unit)

    if transaction_type == "income":
        sale_details = _extract_clear_sale_details(user_input)
        if sale_details is not None:
            result_data.update(sale_details)


def parse_and_validate(
    raw_output: str,
    user_input: Optional[str] = None,
    reference_date: Optional[date] = None,
    transaction_type: TransactionType = "unknown",
) -> dict:
    """Ubah output mentah model menjadi satu transaksi terstruktur.

    Urutan kerjanya:

    1. Ambil objek JSON pertama dari output model.
    2. Paksa ``transaction_type`` memakai hasil aturan ``transaction_type.py``,
       bukan tebakan model.
    3. Tentukan ``date`` dari kalimat atau ``reference_date``.
    4. Tentukan ``total_price`` dari pola harga di kalimat.
    5. Kosongkan item/quantity/unit yang tidak dapat dilacak ke kalimat
       (mencegah data karangan), lalu lengkapi dengan pola yang jelas.

    Return ``{"success": bool, "data": dict | None, "error": str | None}``.
    """
    raw_dict, parse_error = _first_json_object(raw_output)
    if parse_error is not None:
        return {"success": False, "data": None, "error": parse_error}

    # Nilai rule-based selalu diprioritaskan agar klasifikasi konsisten dan tidak
    # bergantung pada output soft prompt.
    raw_dict["transaction_type"] = transaction_type

    try:
        validated = TransaksiSchema(**raw_dict)
    except ValidationError as exc:
        return {"success": False, "data": None, "error": f"Validasi gagal: {exc}"}

    result_data = validated.model_dump()
    reference_date = reference_date or date.today()
    result_data["date"] = _apply_date_rule(user_input, reference_date)

    if user_input:
        _apply_price_rule(result_data, user_input)

    # Tanpa user_input tidak ada sumber yang dapat dipakai untuk membuktikan
    # nilai item/quantity/unit, jadi ketiganya dikosongkan.
    _null_unmentioned_optional_fields(result_data, user_input or "")
    if user_input:
        _apply_tracked_quantity_rules(result_data, user_input, transaction_type)

    return {"success": True, "data": result_data, "error": None}
