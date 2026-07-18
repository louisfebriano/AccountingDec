"""
Resolve kata tanggal relatif ("kemarin", "hari ini", dll) jadi tanggal absolut (ISO format).

Kenapa terpisah dari model: LLM nggak bisa "tau" tanggal hari ini kecuali dikasih tau eksplisit,
dan bahkan kalau dikasih tau, reasoning-nya nggak selalu reliable. Jadi resolusi tanggal relatif
dilakukan lewat rule sederhana di post-processing, bukan diserahkan ke model.
"""

import re
from datetime import date, timedelta
from typing import Optional

# Urutan penting: frasa lebih spesifik/panjang dicek duluan sebelum yang lebih umum,
# supaya "kemarin lusa" nggak ke-match sebagai "kemarin" duluan.
RELATIVE_DATE_PATTERNS = [
    (r"\bkemarin\s+lusa\b", -2),
    (r"\bkemarin\b", -1),
    (r"\blusa\b", 2),
    (r"\bbesok\b", 1),
    (r"\bhari\s+ini\b", 0),
    (r"\bsekarang\b", 0),
    (r"\btadi\s+pagi\b", 0),
    (r"\btadi\s+siang\b", 0),
    (r"\btadi\s+sore\b", 0),
    (r"\btadi\s+malam\b", 0),
    (r"\btadi\b", 0),
    (r"\bminggu\s+lalu\b", -7),
    (r"\bminggu\s+kemarin\b", -7),
]


def resolve_relative_date(user_input: str, reference_date: Optional[date] = None) -> Optional[str]:
    """
    Cari kata tanggal relatif di user_input, hitung tanggal absolutnya berdasarkan reference_date.
    Return string ISO (YYYY-MM-DD) kalau ketemu, atau None kalau nggak ada kata relatif yang dikenali.
    """
    reference_date = reference_date or date.today()
    text_lower = user_input.lower()

    for pattern, delta_days in RELATIVE_DATE_PATTERNS:
        if re.search(pattern, text_lower):
            resolved = reference_date + timedelta(days=delta_days)
            return resolved.isoformat()

    return None