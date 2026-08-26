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
    "kulakan",
    "pengeluaran",
    "biaya operasional",
    "uang keluar",
    "bayar listrik",
    "bayar sewa",
    "bayar gaji",
    "bayar bahan",
)

# Aturan konteks membedakan siapa yang membayar dan tujuan pembayarannya.
INCOME_CONTEXT_PATTERNS = (
    re.compile(r"\b(?:pelanggan|pembeli)\s+(?:sudah\s+)?(?:bayar|membayar)\b"),
    re.compile(r"\bmenerima\s+pembayaran\s+dari\s+(?:pelanggan|pembeli)\b"),
)

_CUSTOMER_PURCHASE_PATTERN = re.compile(
    r"\b(?:pelanggan|pembeli)\s+(?:sudah\s+)?(?:beli|membeli)\b"
)
_PURCHASE_PATTERN = re.compile(r"\b(?:beli|membeli)\b")

EXPENSE_CONTEXT_PATTERNS = (
    re.compile(
        r"\b(?:bayar|membayar)\s+(?:tagihan\s+)?"
        r"(?:listrik|sewa|gaji|bahan)\b"
    ),
    re.compile(r"\b(?:bayar|membayar)\s+(?:ke\s+)?(?:supplier|pemasok)\b"),
    re.compile(r"\b(?:saya|aku|kami|kita)\s+(?:beli|membeli)\b"),
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
