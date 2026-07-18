"""
Resolve kata tanggal relatif ("kemarin", "hari ini", "3 hari lalu", dll) jadi tanggal
absolut (ISO format).

Kenapa terpisah dari model: LLM nggak bisa "tau" tanggal hari ini kecuali dikasih tau
eksplisit, dan bahkan kalau dikasih tau, reasoning-nya nggak selalu reliable (bisa
hallucinate tanggal yang formatnya valid tapi isinya ngasal). Jadi resolusi tanggal
relatif dilakukan lewat rule di post-processing, bukan diserahkan ke model.
"""

import re
from datetime import date, timedelta
from typing import Optional

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
    (r"\bminggu\s+kemarin\b", -7),
    (r"\bsebulan\s+(?:yang\s+)?lalu\b", -30),
    (r"\bbulan\s+lalu\b", -30),
]


def resolve_relative_date(user_input: str, reference_date: Optional[date] = None) -> Optional[str]:
    """
    Cari kata/pola tanggal relatif di user_input, hitung tanggal absolutnya berdasarkan
    reference_date. Return string ISO (YYYY-MM-DD) kalau ketemu, atau None kalau nggak ada
    pola relatif yang dikenali sama sekali.
    """
    reference_date = reference_date or date.today()
    text_lower = user_input.lower()

    # Pola numerik dicek lebih dulu (lebih spesifik) sebelum fallback ke keyword tetap,
    # supaya "2 minggu lalu" nggak ke-match sebagai "minggu lalu" biasa (-7 hari).
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