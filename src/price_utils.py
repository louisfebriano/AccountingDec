"""
Ekstrak nominal harga dari teks kalimat secara deterministik (regex-based).

Kenapa terpisah dari model: konversi "90rebu" -> 90000 itu aturan matematis yang pasti,
bukan sesuatu yang perlu "dipahami" LLM. Soft prompt tuning dengan kapasitas kecil
(virtual token terbatas) cenderung menghafal pola persis, bukan generalisasi aturan
kali 1000/100/1000000 secara konsisten kalau ada kata pengganggu di sekitarnya. Jadi
ekstraksi angka dilakukan lewat rule di post-processing, mirip pendekatan resolve
tanggal relatif.
"""

import re
from typing import Optional

# angka (boleh desimal pakai . atau , , atau pemisah ribuan bertitik) + akhiran
# ribuan/ratusan/jutaan
_SUFFIX_PATTERN = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s*(ribu|rebu|rb|ratus|juta|jt|k)\b",
    re.IGNORECASE,
)

# angka penuh dengan pemisah ribuan tanpa akhiran kata, misal "Rp180.000" atau "180.000"
_FULL_NUMBER_PATTERN = re.compile(r"(?:rp\s*)?(\d{1,3}(?:\.\d{3})+)\b", re.IGNORECASE)

# angka polos tanpa titik/akhiran sama sekali, misal "45500" atau "80000".
# Minimal 4 digit karena quantity di domain ini jarang setinggi itu (asumsi domain UMKM kuliner).
_BARE_NUMBER_PATTERN = re.compile(r"\b(\d{4,})\b")

_SUFFIX_MULTIPLIER = {
    "ribu": 1_000,
    "rebu": 1_000,
    "rb": 1_000,
    "k": 1_000,
    "ratus": 100,
    "juta": 1_000_000,
    "jt": 1_000_000,
}


def _parse_number(raw: str) -> float:
    """
    Parse angka yang bisa berupa pemisah ribuan ("180.000" -> 180000) ATAU desimal
    ("1.5" -> 1.5, dipakai buat kasus "1.5juta"). Dibedakan dari panjang digit setelah
    separator terakhir: kalau tepat 3 digit -> pemisah ribuan (dihapus semua),
    kalau bukan -> desimal (koma dinormalisasi jadi titik).
    """
    if "." in raw or "," in raw:
        last_sep_idx = max(raw.rfind("."), raw.rfind(","))
        frac_part = raw[last_sep_idx + 1:]
        if len(frac_part) == 3:
            cleaned = raw.replace(".", "").replace(",", "")
            return float(cleaned)
        cleaned = raw.replace(",", ".")
        return float(cleaned)
    return float(raw)


def extract_price_from_text(text: str) -> Optional[float]:
    """
    Cari pola harga di teks, dicoba berurutan dari yang paling spesifik:
    1. "angka+akhiran ribuan/ratusan/jutaan" (rb/ribu/rebu/k/ratus/juta/jt) -> ambil yang
       TERAKHIR muncul (asumsi: harga total biasanya disebut di bagian akhir kalimat).
    2. Angka dengan pemisah ribuan bertitik ("180.000") -> ambil yang terakhir.
    3. Angka polos 4+ digit ("80000") -> ambil yang PALING BESAR nilainya (bukan yang
       terakhir muncul, karena angka besar seperti ini biasanya harga meski posisinya
       di tengah kalimat, sedangkan quantity/berat biasanya jauh lebih kecil).
    Return None kalau tidak ada pola yang cocok sama sekali.
    """
    matches = list(_SUFFIX_PATTERN.finditer(text))
    if matches:
        raw_num, suffix = matches[-1].groups()
        multiplier = _SUFFIX_MULTIPLIER[suffix.lower()]
        return _parse_number(raw_num) * multiplier

    full_matches = list(_FULL_NUMBER_PATTERN.finditer(text))
    if full_matches:
        raw_num = full_matches[-1].group(1).replace(".", "")
        return float(raw_num)

    bare_matches = _BARE_NUMBER_PATTERN.findall(text)
    if bare_matches:
        return float(max(bare_matches, key=lambda s: int(s)))

    return None


def has_explicit_price_format(text: str) -> bool:
    """
    Cek apakah teks mengandung pola harga yang JELAS/eksplisit -- akhiran ribuan/ratusan/
    jutaan (rb/ribu/rebu/k/ratus/juta/jt) atau format titik ribuan ("180.000"). SENGAJA
    TIDAK memakai fallback "angka polos 4+ digit" seperti di extract_price_from_text,
    karena fallback itu gampang salah tangkap angka lain yang bukan harga (nomor telepon,
    kode barang, dll) -- cukup aman untuk override harga hasil model, tapi terlalu longgar
    kalau dipakai untuk validasi "apakah ini kalimat transaksi".
    """
    if _SUFFIX_PATTERN.search(text):
        return True
    if _FULL_NUMBER_PATTERN.search(text):
        return True
    return False