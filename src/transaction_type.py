"""Klasifikasi rule-based arah transaksi UMKM dari teks pengguna."""

import re
from typing import Iterable, Literal, Pattern

TransactionType = Literal["income", "expense", "unknown"]

# Frasa di bawah sengaja hanya berisi sinyal arah transaksi yang kuat. Kata ambigu
# seperti "bayar", "transfer", "masuk", dan "keluar" ditangani lewat konteks khusus.
INCOME_PHRASES = (
    "jual",
    "menjual",
    "terjual",
    "laku",
    "penjualan",
    "pemasukan",
    "pendapatan",
    "hasil penjualan",
    "uang masuk",
    "duit masuk",
    "masuk uang",
    "masuk duit",
    "pemasukkan",
    "penghasilan",
    "omzet",
    "income",
)

EXPENSE_PHRASES = (
    "belanja",
    "restok",
    "restock",
    "ristok",
    "kulakan",
    "pengeluaran",
    "biaya operasional",
    "uang keluar",
    "bayar listrik",
    "bayar sewa",
    "bayar gaji",
    "bayar bahan",
)

# "stok <nama barang>" => restock/pembelian stok = pengeluaran. Kata "stok"
# TIDAK dipakai sebagai frasa bebas agar kalimat laporan pemasukan seperti
# "Stok habis, semua laku 300rb" tidak berubah menjadi ambigu: penanda yang
# mengecualikan menangani frasa kondisi stok (habis/kosong/menipis/masih/tinggal).
_STOCK_RESTOCK_PATTERN = re.compile(
    r"\b(?:stok|stock)\s+"
    r"(?!habis|kosong|menipis|abisin|masih|tinggal|banyak|sedikit|sudah|dah)\b"
    r"[a-z]\w*",
    re.IGNORECASE,
)

# Nominal rupiah untuk aturan arah transaksi. Kuantitas seperti "10 karung" atau
# "2 dus" sengaja tidak dianggap nominal, sehingga tidak berubah menjadi uang
# masuk/keluar hanya karena ada angka di dekat kata kerja.
_NOMINAL_PATTERN = (
    r"(?:rp\s*)?(?:"
    r"\d{1,3}(?:\s\d{3})+"
    r"|\d{4,}"
    r"|\d+(?:[.,]\d+)?\s*(?:rb|ribu|rebu|k|jt|juta|ratus)"
    r")\b"
)

# "masuk 300rb", "dapet 150rb", "terima 250rb" adalah uang masuk bagi pemilik
# usaha. Pemilik usaha mencatat arus kasnya sendiri, jadi kata "masuk" sudah
# cukup jelas sebagai pemasukan tanpa perlu frase "duit masuk".
_INFLOW_VERB_PATTERN = re.compile(
    rf"\b(?:masuk|dapet|dapat|nerima|menerima|terima)\s+{_NOMINAL_PATTERN}"
)

# Pesanan/pembeli yang datang adalah pemasukan. "saya order bahan" tidak ikut
# tertangkap karena pola ini mensyaratkan tanda pesanan masuk.
_ORDER_INCOME_PATTERN = re.compile(
    r"\b(?:"
    r"ada\s+(?:yang\s+)?(?:order|mesan|pesan)"
    r"|(?:orderan|pesanan)\s+(?:masuk|datang)"
    r"|(?:terima|menerima|dapat)\s+(?:pesanan|orderan)"
    r")\b"
)

# Aturan konteks membedakan siapa yang membayar dan tujuan pembayarannya.
INCOME_CONTEXT_PATTERNS = (
    re.compile(r"\b(?:pelanggan|pembeli)\s+(?:sudah\s+)?(?:bayar|membayar)\b"),
    re.compile(r"\bmenerima\s+pembayaran\s+dari\s+(?:pelanggan|pembeli)\b"),
    _INFLOW_VERB_PATTERN,
    _ORDER_INCOME_PATTERN,
)

_CUSTOMER_PURCHASE_PATTERN = re.compile(
    r"\b(?:pelanggan|pembeli)\s+(?:sudah\s+)?(?:beli|membeli)\b"
)
_PURCHASE_PATTERN = re.compile(r"\b(?:beli|membeli)\b")

# "bayar 75rb buat listrik" / "bayar wifi 300rb": nominal dapat berada di antara
# kata kerja dan tujuan pembayaran, jadi aturan "bayar <tujuan>" lama perlu
# dilengkapi. Daftar tujuan sengaja terbatas pada biaya usaha agar pembayaran
# pelanggan (mis. "Pelanggan bayar pesanan 150rb") tetap dibaca sebagai pemasukan.
_PAYMENT_PURPOSE_PATTERN = re.compile(
    r"\b(?:bayar|membayar|byr)\b.{0,60}?"
    r"\b(?:listrik|air|wifi|internet|sewa|kontrakan|lapak|gaji|bahan|supplier|"
    r"pemasok|tagihan|utang|hutang|cicilan|sampah|kebersihan|transport|bensin|"
    r"parkir|pajak|iuran)\b"
)

# "keluar 25 ribu" adalah uang keluar pemilik usaha. Nominal wajib ada supaya
# kata "keluar" pada konteks lain (mis. "barang keluar gudang") tidak otomatis
# dianggap pengeluaran.
_OUTFLOW_VERB_PATTERN = re.compile(rf"\bkeluar\s+{_NOMINAL_PATTERN}")

EXPENSE_CONTEXT_PATTERNS = (
    re.compile(
        r"\b(?:bayar|membayar)\s+(?:tagihan\s+)?"
        r"(?:listrik|sewa|gaji|bahan)\b"
    ),
    re.compile(r"\b(?:bayar|membayar)\s+(?:ke\s+)?(?:supplier|pemasok)\b"),
    re.compile(r"\b(?:saya|aku|kami|kita)\s+(?:beli|membeli)\b"),
    _PAYMENT_PURPOSE_PATTERN,
    _OUTFLOW_VERB_PATTERN,
)

GENERAL_INCOME_PHRASES = (
    "pemasukan",
    "pemasukkan",
    "duit masuk",
    "uang masuk",
    "masuk uang",
    "masuk duit",
    "pendapatan",
    "penghasilan",
    "omzet",
    "hasil penjualan",
    "income",
)


def _normalize_for_matching(text: str) -> str:
    """Ubah tanda baca menjadi spasi agar pencocokan frasa tetap berbatas kata."""
    normalized = re.sub(r"[^\w]+", " ", text.casefold(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _compile_phrase_pattern(phrases: Iterable[str]) -> Pattern[str]:
    """Kompilasi daftar frasa menjadi regex dengan batas kata eksplisit."""
    alternatives = []
    for phrase in sorted(phrases, key=len, reverse=True):
        words = [re.escape(word) for word in phrase.split()]
        alternatives.append(r"\s+".join(words))
    return re.compile(rf"\b(?:{'|'.join(alternatives)})\b")


_INCOME_PHRASE_PATTERN = _compile_phrase_pattern(INCOME_PHRASES)
_EXPENSE_PHRASE_PATTERN = _compile_phrase_pattern(EXPENSE_PHRASES)
_GENERAL_INCOME_PATTERN = _compile_phrase_pattern(GENERAL_INCOME_PHRASES)
_ITEM_SALE_SIGNAL_PATTERN = re.compile(
    r"\b(?:jual|menjual|terjual|laku)\b|"
    r"\b(?:pelanggan|pembeli)\s+(?:sudah\s+)?(?:beli|membeli)\b"
)


def _matches_context(text: str, patterns: Iterable[Pattern[str]]) -> bool:
    """Return True apabila salah satu aturan konteks cocok."""
    return any(pattern.search(text) is not None for pattern in patterns)


def classify_transaction_type(text: str) -> TransactionType:
    """Klasifikasikan teks sebagai income, expense, atau unknown."""
    if not text or not text.strip():
        return "unknown"

    normalized = _normalize_for_matching(text)
    customer_purchase = _CUSTOMER_PURCHASE_PATTERN.search(normalized) is not None
    has_purchase = _PURCHASE_PATTERN.search(normalized) is not None
    has_income = (
        _INCOME_PHRASE_PATTERN.search(normalized) is not None
        or _matches_context(normalized, INCOME_CONTEXT_PATTERNS)
        or customer_purchase
    )
    has_expense = (
        _EXPENSE_PHRASE_PATTERN.search(normalized) is not None
        or _matches_context(normalized, EXPENSE_CONTEXT_PATTERNS)
        or (_STOCK_RESTOCK_PATTERN.search(normalized) is not None)
        or (has_purchase and not customer_purchase)
    )

    if has_income == has_expense:
        return "unknown"
    return "income" if has_income else "expense"


def is_general_income_transaction(text: str) -> bool:
    """Cek pemasukan umum yang tidak menyatakan penjualan barang secara eksplisit."""
    if classify_transaction_type(text) != "income":
        return False
    normalized = _normalize_for_matching(text)
    return (
        _GENERAL_INCOME_PATTERN.search(normalized) is not None
        and _ITEM_SALE_SIGNAL_PATTERN.search(normalized) is None
    )
