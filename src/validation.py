"""
Validasi input: cek apakah kalimat relevan dengan konteks transaksi UMKM, SEBELUM
dikirim ke model. Ini rule-based (bukan minta model menilai sendiri) supaya:
1. Cepat dan murah -- tidak buang waktu generate di GPU untuk kalimat yang jelas
   di luar konteks (misal chat random, pertanyaan umum, dll).
2. Konsisten -- tidak bergantung ke "mood" atau interpretasi model yang bisa berubah-ubah.
"""

import re
from typing import Tuple

from .price_utils import has_explicit_price_format

# Kata kerja/konteks umum yang muncul di kalimat transaksi UMKM.
TRANSACTION_KEYWORDS = [
    "beli", "belanja", "restock", "restok", "stock", "stok",
    "jual", "terjual", "laku",
    "bayar", "membayar",
    "dapat", "terima", "masuk",
    "keluar", "pengeluaran", "pemasukan",
    "ambil", "order", "pesan", "kulakan",
]

_HAS_DIGIT = re.compile(r"\d")


def validate_transaction_context(text: str) -> Tuple[bool, str]:
    """
    Return (is_valid, reason).
    is_valid=False kalau kalimat kemungkinan besar BUKAN kalimat transaksi.

    Aturan (kombinasi 2 sinyal, sengaja tidak terlalu ketat/longgar):
    1. Harus ada minimal satu angka (quantity/harga transaksi selalu berupa angka).
    2. DAN harus ada kata kerja transaksi ATAU pola harga yang jelas (rb/ribu/k/dll).
    """
    if not text or not text.strip():
        return False, "Input kosong"

    if not _HAS_DIGIT.search(text):
        return False, "Tidak ditemukan angka (quantity/harga) pada kalimat"

    text_lower = text.lower()
    has_keyword = any(kw in text_lower for kw in TRANSACTION_KEYWORDS)
    has_price_pattern = has_explicit_price_format(text)

    if not has_keyword and not has_price_pattern:
        return False, "Kalimat tidak mengandung kata kerja transaksi maupun pola harga yang jelas"

    return True, ""