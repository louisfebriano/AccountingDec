"""
Ekstrak nominal harga dari teks kalimat secara deterministik (regex-based).

Kenapa terpisah dari model: konversi "90rebu" -> 90000 itu aturan matematis yang pasti,
bukan sesuatu yang perlu "dipahami" LLM. Soft prompt tuning dengan kapasitas kecil
(virtual token terbatas) cenderung menghafal pola persis, bukan generalisasi aturan
kali 1000/100 secara konsisten kalau ada kata pengganggu di sekitarnya. Jadi ekstraksi
angka dilakukan lewat rule di post-processing, mirip pendekatan resolve tanggal relatif.
"""

import re
from typing import Optional

# angka (boleh pakai . atau , sebagai pemisah ribuan) + akhiran ribuan/ratusan
_SUFFIX_PATTERN = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(ribu|rebu|rb|ratus|k)\b", re.IGNORECASE
)

# angka penuh dengan pemisah ribuan tanpa akhiran kata, misal "Rp180.000" atau "180.000"
_FULL_NUMBER_PATTERN = re.compile(r"(?:rp\s*)?(\d{1,3}(?:\.\d{3})+)\b", re.IGNORECASE)

_SUFFIX_MULTIPLIER = {
    "ribu": 1000,
    "rebu": 1000,
    "rb": 1000,
    "k": 1000,
    "ratus": 100,
}


def extract_price_from_text(text: str) -> Optional[float]:
    """
    Cari pola "angka+akhiran ribuan" di teks. Kalau ada beberapa kandidat, ambil yang
    TERAKHIR muncul di kalimat (asumsi: harga total biasanya disebut di bagian akhir,
    setelah nama barang & quantity). Return None kalau tidak ada pola yang cocok sama sekali
    (biar tidak asal override kalau memang kalimatnya tidak menyebut harga jelas).
    """
    matches = list(_SUFFIX_PATTERN.finditer(text))
    if matches:
        raw_num, suffix = matches[-1].groups()
        raw_num = raw_num.replace(".", "").replace(",", "")
        multiplier = _SUFFIX_MULTIPLIER[suffix.lower()]
        return float(raw_num) * multiplier

    full_matches = list(_FULL_NUMBER_PATTERN.finditer(text))
    if full_matches:
        raw_num = full_matches[-1].group(1).replace(".", "")
        return float(raw_num)

    return None