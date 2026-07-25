"""
Resolve tanggal dari teks kalimat jadi format absolut (ISO: YYYY-MM-DD).

Dua jenis pola yang ditangani, dengan prioritas beda:
1. Tanggal eksplisit ("tanggal 2 Juli", "2/7/2026", dll) -> prioritas tertinggi,
   diambil rule-based (bukan dari model), karena lebih presisi & tidak butuh
   "pemahaman" -- cuma soal parsing nama bulan/angka.
2. Tanggal relatif ("kemarin", "3 hari lalu", dll) -> dipakai HANYA kalau tidak
   ada tanggal eksplisit yang ketemu di kalimat yang sama.

Kenapa terpisah dari model: LLM nggak bisa "tau" tanggal hari ini kecuali dikasih tau
eksplisit, dan bahkan kalau dikasih tau, reasoning-nya nggak selalu reliable (bisa
hallucinate tanggal yang formatnya valid tapi isinya ngasal, atau salah prioritas kalau
ada 2 sinyal tanggal sekaligus dalam satu kalimat).
"""

import re
from datetime import date, timedelta
from typing import Optional

MONTH_NAMES = {
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8, "ags": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12,
}
_MONTH_PATTERN = "|".join(sorted(MONTH_NAMES.keys(), key=len, reverse=True))

# "tanggal 2 juli", "2 juli 2026", "tgl 2/7", dst.
_DATE_WITH_MONTH_NAME = re.compile(
    rf"\b(?:tanggal|tgl)?\s*(\d{{1,2}})\s+({_MONTH_PATTERN})(?:\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)
# "2/7/2026", "02-07-2026" (ada tahun -> aman, kecil kemungkinan ketuker pecahan/angka lain)
_DATE_NUMERIC_WITH_YEAR = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
# "tanggal 2/7", "tgl 2-7" (tanpa tahun, TAPI wajib didahului kata "tanggal"/"tgl" biar
# nggak ketuker sama pecahan kayak "3/4 kg" atau angka lain yang kebetulan berpola sama)
_DATE_NUMERIC_NO_YEAR = re.compile(r"\b(?:tanggal|tgl)\s*(\d{1,2})[/-](\d{1,2})\b")

# Pola numerik (dicek lebih dulu, lebih spesifik): "2 hari yang lalu", "3 hari lalu",
# "2 minggu lalu", dst. Angkanya dipakai buat hitung delta secara dinamis.
_NUMERIC_WEEKS_AGO = re.compile(r"\b(\d+)\s*minggu\s+(?:yang\s+)?lalu\b")
_NUMERIC_DAYS_AGO = re.compile(r"\b(\d+)\s*hari\s+(?:yang\s+)?lalu\b")
_NUMERIC_DAYS_AHEAD = re.compile(r"\b(\d+)\s*hari\s+(?:lagi|kemudian)\b")

# Pola kata tetap (fixed keyword, delta harinya sudah pasti).
# Urutan penting: frasa lebih spesifik/panjang dicek duluan sebelum yang lebih umum,
# supaya "kemarin lusa" nggak ke-match sebagai "kemarin" duluan.
RELATIVE_DATE_PATTERNS = [
    (r"\bkemarin\s+lusa\b", -2),
    (r"\bminggu\s+kemarin\b", -7),
    (r"\bbulan\s+kemarin\b", -30),
    (r"\bkemarin\b", -1),
    (r"\bkmrn\b", -1),
    (r"\blusa\b", 2),
    (r"\bbesok\b", 1),
    (r"\bbsk\b", 1),
    (r"\bhari\s+ini\b", 0),
    (r"\bsekarang\b", 0),
    (r"\btadi\s+pagi\b", 0),
    (r"\btadi\s+siang\b", 0),
    (r"\btadi\s+sore\b", 0),
    (r"\btadi\s+malam\b", 0),
    (r"\btadi\b", 0),
    (r"\bseminggu\s+(?:yang\s+)?lalu\b", -7),
    (r"\bminggu\s+lalu\b", -7),
    (r"\bsebulan\s+(?:yang\s+)?lalu\b", -30),
    (r"\bbulan\s+lalu\b", -30),
]


def extract_explicit_date(user_input: str, reference_date: Optional[date] = None) -> Optional[str]:
    """
    Cari tanggal eksplisit di kalimat: "tanggal 2 Juli", "2 Juli 2026", "2/7/2026", dll.
    Kalau tahun tidak disebut, asumsikan tahun dari reference_date. Return None kalau
    tidak ada pola tanggal eksplisit yang cocok, atau kalau hasilnya bukan tanggal valid.
    """
    reference_date = reference_date or date.today()
    text_lower = user_input.lower()

    match = _DATE_WITH_MONTH_NAME.search(text_lower)
    if match:
        day_str, month_name, year_str = match.groups()
        day = int(day_str)
        month = MONTH_NAMES[month_name.lower()]
        year = int(year_str) if year_str else reference_date.year
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    match = _DATE_NUMERIC_WITH_YEAR.search(text_lower)
    if match:
        day_str, month_str, year_str = match.groups()
        day, month, year = int(day_str), int(month_str), int(year_str)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return None
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    match = _DATE_NUMERIC_NO_YEAR.search(text_lower)
    if match:
        day_str, month_str = match.groups()
        day, month = int(day_str), int(month_str)
        year = reference_date.year
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return None
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    return None


def resolve_relative_date(user_input: str, reference_date: Optional[date] = None) -> Optional[str]:
    """
    Cari kata/pola tanggal relatif di user_input, hitung tanggal absolutnya berdasarkan
    reference_date. Return string ISO (YYYY-MM-DD) kalau ketemu, atau None kalau nggak ada
    pola relatif yang dikenali sama sekali.
    """
    reference_date = reference_date or date.today()
    text_lower = user_input.lower()

    match = _NUMERIC_WEEKS_AGO.search(text_lower)
    if match:
        n = int(match.group(1))
        return (reference_date - timedelta(weeks=n)).isoformat()

    match = _NUMERIC_DAYS_AGO.search(text_lower)
    if match:
        n = int(match.group(1))
        return (reference_date - timedelta(days=n)).isoformat()

    match = _NUMERIC_DAYS_AHEAD.search(text_lower)
    if match:
        n = int(match.group(1))
        return (reference_date + timedelta(days=n)).isoformat()

    for pattern, delta_days in RELATIVE_DATE_PATTERNS:
        if re.search(pattern, text_lower):
            resolved = reference_date + timedelta(days=delta_days)
            return resolved.isoformat()

    return None


def resolve_date(user_input: str, reference_date: Optional[date] = None) -> Optional[str]:
    """
    Entry point utama. Prioritas:
    1. Tanggal eksplisit ("tanggal 2 Juli", dll) -- paling presisi, dicek duluan.
    2. Tanggal relatif ("kemarin", "3 hari lalu", dll) -- fallback kalau tidak ada
       tanggal eksplisit di kalimat yang sama.
    Return None kalau dua-duanya tidak ketemu (kalimat tidak menyebut tanggal sama sekali).
    """
    explicit = extract_explicit_date(user_input, reference_date)
    if explicit is not None:
        return explicit
    return resolve_relative_date(user_input, reference_date)