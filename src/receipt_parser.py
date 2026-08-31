"""Parser deterministik untuk hasil OCR nota berbahasa Indonesia."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Any, Iterable, Mapping, Optional, Sequence


MAX_RECEIPT_ITEMS = 50
MAX_OCR_TEXT_LENGTH = 12_000

_MONTHS = {
    "jan": 1,
    "januari": 1,
    "feb": 2,
    "februari": 2,
    "mar": 3,
    "maret": 3,
    "apr": 4,
    "april": 4,
    "mei": 5,
    "jun": 6,
    "juni": 6,
    "jul": 7,
    "juli": 7,
    "agu": 8,
    "agt": 8,
    "agustus": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "okt": 10,
    "oktober": 10,
    "nov": 11,
    "november": 11,
    "des": 12,
    "desember": 12,
}

_MONEY_PATTERN = re.compile(
    r"(?<![\d/.-])(?:rp\.?\s*)?(\d{1,3}(?:[.,\s]\d{3})+|\d{3,})(?![\d/.-])",
    re.IGNORECASE,
)
_DATE_NUMERIC_PATTERN = re.compile(
    r"(?<!\d)(?:(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})|(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4}))(?!\d)"
)
_DATE_MONTH_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})\s+(jan(?:uari)?|feb(?:ruari)?|mar(?:et)?|apr(?:il)?|mei|jun(?:i)?|jul(?:i)?|agu(?:stus)?|agt|sep(?:t(?:ember)?)?|okt(?:ober)?|nov(?:ember)?|des(?:ember)?)\s+(\d{4})(?!\d)",
    re.IGNORECASE,
)
_TABULAR_PRICE_SUFFIX_PATTERN = re.compile(
    r"(?P<currency>(?:r|2)p\.?\s*)?"
    r"(?P<amount>\d{1,3}(?:[.,\s]\d{2,3})+|\d{3,})\s*$",
    re.IGNORECASE,
)
_STRICT_RUPIAH_PATTERN = re.compile(
    r"(?:\d{1,3}(?:[.,\s]\d{3})+|\d{3,})$"
)
_RETAIL_ITEM_AMOUNTS_PATTERN = re.compile(
    r"(?<![\d.,])(?P<quantity>\d{1,3}(?:[.,]\d+)?)\s+"
    r"(?P<unit_price>\d{1,3}(?:[.,]\d{3})+|\d{3,})\s+"
    r"(?P<line_total>\d{1,3}(?:[.,]\d{3})+|\d{3,})(?![\d.,])"
)
_KNOWN_ITEM_UNITS = (
    "buah",
    "bungkus",
    "botol",
    "dus",
    "gram",
    "gr",
    "kg",
    "kotak",
    "liter",
    "ltr",
    "ikat",
    "pack",
    "pak",
    "pcs",
    "porsi",
    "sachet",
    "unit",
)

_OCR_HEADER_ALIASES = (
    (r"\bnota\s*no\.?", "NOTA NO."),
    (r"\bnotano\.?", "NOTA NO."),
    (r"\bbanyak\s*-?\s*nya\b", "BANYAKNYA"),
    (r"\bbanyaavta\b", "BANYAKNYA"),
    (r"\bnama\s*barang\b", "NAMA BARANG"),
    (r"\bnamabarang\b", "NAMA BARANG"),
    (r"\bnasadarang\b", "NAMA BARANG"),
    (r"\bharsa\b", "HARGA"),
    (r"\b(?:juniah|jdalan)\b", "JUMLAH"),
    (r"\b(?:juniah|jdalan)(?=\s*rp)", "JUMLAH "),
    (r"\bhormatkami\b", "Hormat Kami"),
    (r"\bt[0o]tal\b", "TOTAL"),
)
_OCR_CURRENCY_PREFIX = re.compile(
    r"(?<![A-Za-z0-9])(?:rp|ro|r0|pp|2p|p)\s*[.,]?\s*"
    r"(?=\d{1,3}(?:[.,\-\s]\d{2,3})|\d{3,})",
    re.IGNORECASE,
)
_OCR_ROW_UNIT_PATTERN = "|".join(
    sorted((re.escape(unit) for unit in _KNOWN_ITEM_UNITS), key=len, reverse=True)
)
_COMPACT_KEEP_PATTERN = re.compile(
    r"\b(?:no\.?\s*(?:struk|nota)|nomor|bon|invoice|receipt|ref|"
    r"tgl|tanggal|date|purchase\s+date|nama\s*barang|rincian\s*barang|"
    r"qty|harga|jumlah|sub\s*total|total|disc(?:ount)?|diskon|potongan|"
    r"pajak|ppn|tax|service|bayar|tunai|cash|qris|gopay|kembali(?:an)?)\b",
    re.IGNORECASE,
)
_COMPACT_NOISE_PATTERN = re.compile(
    r"\b(?:alamat|jalan|jl\.?|rt\.?\s*\d|rw\.?\s*\d|kel(?:urahan)?\.?|"
    r"kec(?:amatan)?\.?|npwp|telp|telepon|whatsapp|sms|kritik|saran|"
    r"terima\s*kasih|atas\s*kunjungan|hormat\s*kami|"
    r"barang\s+yang\s+sudah\s+dibeli|"
    r"tidak\s+(?:dapat|bisa)\s+(?:ditukar|dikembalikan)|"
    r"website|instagram|facebook)\b",
    re.IGNORECASE,
)
_COMPACT_RECEIPT_CODE_PATTERN = re.compile(
    r"\b[A-Z]{1,5}\d{1,4}[./-][A-Z0-9./-]{4,}\b",
    re.IGNORECASE,
)
_COMPACT_DAMAGED_DATE_PATTERN = re.compile(
    r"(?:^|\s)T?\d{1,2}[-/.]\d{1,2}[-/.]\d{2,6}",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReceiptLine:
    """Satu baris OCR yang sudah diurutkan berdasarkan posisi."""

    text: str
    confidence: float
    box: tuple[tuple[float, float], ...] = ()

    @property
    def x(self) -> float:
        return min((point[0] for point in self.box), default=0.0)

    @property
    def y(self) -> float:
        return min((point[1] for point in self.box), default=0.0)

    @property
    def center_y(self) -> float:
        if not self.box:
            return self.y
        return mean(point[1] for point in self.box)

    @property
    def height(self) -> float:
        values = [point[1] for point in self.box]
        return max(values, default=0.0) - min(values, default=0.0)


def parse_rupiah(value: Any) -> Optional[int]:
    """Ubah representasi nominal Rupiah menjadi integer tanpa menebak desimal."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def parse_receipt_quantity(
    value: Any,
    *,
    unit_price: Optional[int] = None,
    line_total: Optional[int] = None,
) -> Optional[float]:
    """Bedakan separator desimal/ribuan quantity memakai line total bila tersedia."""
    text = re.sub(r"\s+", "", str(value or "").strip())
    if not text or not re.fullmatch(r"\d+(?:[.,]\d+)*", text):
        return None

    candidates: list[float] = []
    if text.count(".") + text.count(",") <= 1:
        try:
            candidates.append(float(text.replace(",", ".")))
        except ValueError:
            pass
    groups = re.split(r"[.,]", text)
    if len(groups) > 1 and all(len(group) == 3 for group in groups[1:]):
        candidates.append(float("".join(groups)))
    if not candidates:
        candidates.append(float("".join(groups)))

    unique_candidates = list(dict.fromkeys(candidates))
    if unit_price is not None and line_total is not None and unit_price > 0:
        return min(
            unique_candidates,
            key=lambda quantity: abs(quantity * unit_price - line_total),
        )
    return unique_candidates[0]


def extract_rupiah_values(text: str) -> list[int]:
    """Ambil kandidat nominal dari sebuah baris OCR."""
    return [
        value
        for match in _MONEY_PATTERN.finditer(text)
        if (value := parse_rupiah(match.group(0))) is not None
    ]


def parse_receipt_date(text: str) -> Optional[str]:
    """Ekstrak tanggal absolut umum pada nota tanpa menebak tanggal pemindaian."""
    month_match = _DATE_MONTH_PATTERN.search(text)
    if month_match:
        day_value, month_name, year_value = month_match.groups()
        month_value = _MONTHS.get(month_name.lower())
        if month_value:
            try:
                return date(int(year_value), month_value, int(day_value)).isoformat()
            except ValueError:
                return None

    numeric_match = _DATE_NUMERIC_PATTERN.search(text)
    if not numeric_match:
        return None
    iso_year, iso_month, iso_day, day_value, month_value, year_value = numeric_match.groups()
    try:
        if iso_year:
            parsed = date(int(iso_year), int(iso_month), int(iso_day))
        else:
            year_number = int(year_value)
            if year_number < 100:
                year_number += 2000
            parsed = date(year_number, int(month_value), int(day_value))
    except ValueError:
        return None
    return parsed.isoformat()


def _coerce_box(value: Any) -> tuple[tuple[float, float], ...]:
    try:
        return tuple((float(point[0]), float(point[1])) for point in value)
    except (TypeError, ValueError, IndexError):
        return ()


def normalize_ocr_lines(lines: Iterable[Any]) -> list[ReceiptLine]:
    """Bersihkan, urutkan, dan gabungkan token OCR yang berada pada baris sama."""
    normalized: list[ReceiptLine] = []
    for value in lines:
        if isinstance(value, ReceiptLine):
            line = value
        elif isinstance(value, str):
            line = ReceiptLine(value, 1.0)
        elif isinstance(value, dict):
            line = ReceiptLine(
                str(value.get("text") or ""),
                float(value.get("confidence") or 0.0),
                _coerce_box(value.get("box")),
            )
        else:
            continue
        text = re.sub(r"\s+", " ", line.text).strip()[:500]
        if text:
            normalized.append(ReceiptLine(text, max(0.0, min(line.confidence, 1.0)), line.box))

    if not any(line.box for line in normalized):
        return normalized

    ordered = sorted(normalized, key=lambda line: (line.center_y, line.x))
    groups: list[list[ReceiptLine]] = []
    for line in ordered:
        if not groups:
            groups.append([line])
            continue
        current = groups[-1]
        center = mean(item.center_y for item in current)
        tolerance = max(6.0, mean(max(item.height, 8.0) for item in current) * 0.55)
        if abs(line.center_y - center) <= tolerance:
            current.append(line)
        else:
            groups.append([line])

    merged: list[ReceiptLine] = []
    for group in groups:
        group.sort(key=lambda line: line.x)
        merged.append(
            ReceiptLine(
                " ".join(line.text for line in group),
                mean(line.confidence for line in group),
                tuple(point for line in group for point in line.box),
            )
        )
    return merged


def clean_receipt_ocr_text(text: str) -> str:
    """Rapikan error OCR umum tanpa menebak karakter nama barang yang hilang."""
    cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(
        r"(?i)\baifamart\s+(?=alfamart\b)",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\btota[i1]\b", "TOTAL", cleaned)
    cleaned = re.sub(r"(?<=\d)[sS](?=[.,]\d{3}\b)", "5", cleaned)
    cleaned = re.sub(
        r"\b6(?=[aeiou][A-Za-z]{2,}\b)",
        "G",
        cleaned,
        flags=re.IGNORECASE,
    )
    for pattern, replacement in _OCR_HEADER_ALIASES:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?i)jumlah\s*rp", "JUMLAH Rp", cleaned)
    cleaned = _OCR_CURRENCY_PREFIX.sub("Rp ", cleaned)
    cleaned = re.sub(r"(?<=\d)[\-–—](?=\d{3}\b)", ".", cleaned)
    cleaned = re.sub(
        rf"(?<=\d)\s*(?P<unit>{_OCR_ROW_UNIT_PATTERN})\b",
        lambda match: f" {match.group('unit').lower()}",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Nota tabel beresolusi rendah kadang dibaca sebagai satu paragraf. Pecah hanya
    # pada marker struktural yang kuat agar nama barang tidak direkayasa.
    cleaned = re.sub(
        rf"(?<!^)(?<!\n)\s+(?=\d+(?:[.,]\d+)?\s*(?:{_OCR_ROW_UNIT_PATTERN})\b)",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+(?=(?:JUMLAH\s+Rp|TANDA\s+TERIMA|PERHATIAN\s*:|HORMAT\s+KAMI)\b)",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Struk minimarket dapat dikembalikan OCR sebagai satu paragraf. Pisahkan kasir,
    # baris produk, dan ringkasan hanya saat pola nominalnya lengkap.
    cleaned = re.sub(
        r"(?i)(\bkasir\s*:\s*[A-Za-z0-9._-]+)\s+",
        r"\1\n",
        cleaned,
    )
    retail_amount = r"\d{1,3}(?:[.,]\d{3})+"
    cleaned = re.sub(
        rf"({retail_amount})\s+"
        rf"(?=[A-Za-z][A-Za-z0-9+&./'-]*"
        rf"(?:\s+[A-Za-z0-9+&./'-]+){{0,5}}\s+"
        rf"\d{{1,3}}(?:[.,]\d+)?\s+{retail_amount}\s+{retail_amount})",
        r"\1\n",
        cleaned,
    )
    cleaned = re.sub(
        r"(?<!^)(?<!\n)\s+"
        r"(?=(?:(?<!total\s)disc\.?|total\s+(?:item|disc\.?|belanja)|gopay\b|"
        r"kembali(?:an)?\b|ppn\s+dpp\b))",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    return "\n".join(
        re.sub(r"[ \t]+", " ", line).strip()
        for line in cleaned.splitlines()
        if line.strip()
    )


def clean_receipt_ocr_lines(lines: Sequence[ReceiptLine]) -> list[ReceiptLine]:
    """Terapkan pembersihan per deteksi sambil mempertahankan confidence OCR."""
    cleaned_lines: list[ReceiptLine] = []
    for line in lines:
        for text in clean_receipt_ocr_text(line.text).splitlines():
            if text:
                cleaned_lines.append(ReceiptLine(text, line.confidence, line.box))
    return cleaned_lines


def _looks_like_item_detail_line(text: str) -> bool:
    """Kenali baris quantity/harga yang terpisah dari nama barang."""
    if _RETAIL_ITEM_AMOUNTS_PATTERN.search(text) or _parse_quantity_pattern(text):
        return True
    if not extract_rupiah_values(text):
        return False
    return not re.search(r"[A-Za-z]", text) or bool(
        re.search(
            rf"\b(?:{_OCR_ROW_UNIT_PATTERN}|rp)\b",
            text,
            re.IGNORECASE,
        )
    )


def compact_receipt_ocr_text(
    text: str,
    receipt: Mapping[str, Any] | None = None,
) -> str:
    """Ringkas OCR untuk model tanpa menghapus field transaksi yang terdeteksi."""
    cleaned = clean_receipt_ocr_text(text)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) <= 3:
        return cleaned

    keep: set[int] = set()
    receipt_data = dict(receipt or {})

    # Dua baris teks awal biasanya nama merchant dan cabang/subjudul. Alamat,
    # telepon, serta NPWP sesudahnya tidak perlu memenuhi context window model.
    header_count = 0
    for index, line in enumerate(lines[:6]):
        if not re.search(r"[A-Za-z]", line):
            continue
        if _COMPACT_NOISE_PATTERN.search(line):
            continue
        keep.add(index)
        header_count += 1
        if header_count == 2:
            break

    summary_indices: set[int] = set()
    for index, line in enumerate(lines):
        if (
            _COMPACT_KEEP_PATTERN.search(line)
            or _COMPACT_RECEIPT_CODE_PATTERN.search(line)
            or _COMPACT_DAMAGED_DATE_PATTERN.search(line)
        ):
            keep.add(index)
            if re.search(
                r"\b(?:sub\s*total|total|disc(?:ount)?|diskon|pajak|ppn|tax|"
                r"service|bayar|tunai|cash|qris|gopay|kembali(?:an)?)\b",
                line,
                re.IGNORECASE,
            ):
                summary_indices.add(index)

    receipt_lines = [ReceiptLine(line, 1.0) for line in lines]
    table_bounds = _item_table_bounds(receipt_lines)
    if table_bounds:
        keep.update(range(table_bounds[0] - 1, table_bounds[1]))

    item_names = [
        str(item.get("item_name") or "").strip().casefold()
        for item in receipt_data.get("items") or []
        if str(item.get("item_name") or "").strip()
    ]
    for index, line in enumerate(lines):
        normalized_line = re.sub(r"\s+", " ", line).casefold()
        matches_item = any(
            item_name in normalized_line
            or (len(normalized_line) >= 4 and normalized_line in item_name)
            for item_name in item_names
        )
        has_item_amounts = bool(
            _looks_like_item_detail_line(line)
            or (
                re.search(r"[A-Za-z]", line)
                and len(extract_rupiah_values(line)) >= 2
            )
        )
        if not matches_item and not has_item_amounts:
            continue
        if _COMPACT_NOISE_PATTERN.search(line) and not matches_item:
            continue
        keep.add(index)
        if index + 1 < len(lines) and _looks_like_item_detail_line(lines[index + 1]):
            keep.add(index + 1)

    # Tanpa item atau ringkasan keuangan yang cukup jelas, jangan mengambil risiko
    # membuang teks yang mungkin dibutuhkan model.
    if not item_names or not summary_indices:
        return cleaned

    compacted = "\n".join(line for index, line in enumerate(lines) if index in keep)
    return compacted if compacted and len(compacted) < len(cleaned) else cleaned


def _label_value(lines: Sequence[ReceiptLine], pattern: str) -> Optional[int]:
    matcher = re.compile(pattern, re.IGNORECASE)
    for index, line in enumerate(lines):
        if not matcher.search(line.text):
            continue
        label_match = matcher.search(line.text)
        remainder = line.text[label_match.end():] if label_match else line.text
        signed_value = re.search(
            r"[-–—]\s*(?:rp\.?\s*)?"
            r"(\d{1,3}(?:[.,\s]\d{3})+|\d{3,})",
            remainder,
            re.IGNORECASE,
        )
        if signed_value:
            return parse_rupiah(signed_value.group(1))
        values = extract_rupiah_values(line.text)
        if values:
            return values[-1]
        if index + 1 < len(lines):
            values = extract_rupiah_values(lines[index + 1].text)
            if values:
                return values[-1]
    return None


def _total_candidates(lines: Sequence[ReceiptLine]) -> list[dict[str, Any]]:
    positive_labels = (
        (r"\bgrand\s*total\b", 120),
        (r"\btotal\s+belanja\b", 118),
        (r"\btotal\s+(?:bayar|pembayaran)\b", 115),
        (r"\bbayar\b", 110),
        (r"\bjumlah\b", 100),
        (r"(?<!sub)\btotal\b", 90),
    )
    excluded = re.compile(
        r"\b(?:sub\s*total|total\s+(?:items?|disc(?:ount)?|diskon)|"
        r"kembali(?:an)?|change|tunai|cash|uang\s+diterima)\b",
        re.IGNORECASE,
    )
    candidates: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if excluded.search(line.text):
            continue
        for pattern, priority in positive_labels:
            if not re.search(pattern, line.text, re.IGNORECASE):
                continue
            values = extract_rupiah_values(line.text)
            is_table_header = bool(
                re.search(
                    r"\b(?:nama\s*barang|harga|banyak(?:nya)?|qty)\b",
                    line.text,
                    re.IGNORECASE,
                )
            )
            if (
                not values
                and not is_table_header
                and len(line.text.split()) <= 4
                and index + 1 < len(lines)
            ):
                values = extract_rupiah_values(lines[index + 1].text)
            if values:
                candidates.append(
                    {
                        "value": values[-1],
                        "label": line.text[:120],
                        "confidence": round(line.confidence, 4),
                        "score": priority + line.confidence,
                    }
                )
            break
    candidates.sort(key=lambda item: item["score"], reverse=True)
    unique: list[dict[str, Any]] = []
    seen: set[int] = set()
    for candidate in candidates:
        if candidate["value"] not in seen:
            unique.append(candidate)
            seen.add(candidate["value"])
    return unique


def _receipt_number(lines: Sequence[ReceiptLine]) -> Optional[str]:
    pattern = re.compile(
        r"\b(?:no(?:mor)?\.?\s*(?:nota|struk|invoice)?|invoice|inv|receipt)\s*[:#-]?\s*([a-z0-9][a-z0-9./-]{2,})",
        re.IGNORECASE,
    )
    for line in lines:
        if match := pattern.search(line.text):
            return match.group(1)[:100]
    return None


def _merchant_name(lines: Sequence[ReceiptLine]) -> Optional[str]:
    rejected = re.compile(
        r"\b(?:nota|invoice|receipt|faktur|tanggal|date|kasir|telp|telepon|alamat|total|subtotal|diskon|pajak)\b",
        re.IGNORECASE,
    )
    for line in lines[:6]:
        alfamart_branch = re.search(
            r"\b(ALFAMART(?:\s+[A-Z0-9.-]+){0,3})\s*(?=/)",
            line.text,
            re.IGNORECASE,
        )
        if alfamart_branch:
            return alfamart_branch.group(1).strip()[:200]
        if re.search(r"\bALFAMART\b", line.text, re.IGNORECASE):
            return "ALFAMART"
        if rejected.search(line.text) or not re.search(r"[A-Za-z]", line.text):
            continue
        if len(extract_rupiah_values(line.text)) > 0:
            continue
        return line.text[:200]
    return None


def _is_item_name(text: str) -> bool:
    if not re.search(r"[A-Za-z]", text):
        return False
    return not re.search(
        r"\b(?:total|subtotal|diskon|discount|pajak|tax|service|tunai|cash|kembali|change|tanggal|date|invoice|nota|receipt|kasir|telp|alamat)\b",
        text,
        re.IGNORECASE,
    )


def _parse_quantity_pattern(
    text: str,
) -> Optional[tuple[float, Optional[str], int, Optional[int]]]:
    match = re.search(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*([a-zA-Z]{1,12})?\s*[xX@]\s*((?:rp\.?\s*)?(?:\d{1,3}(?:[.,]\d{3})+|\d{3,}))",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    unit = match.group(2).lower() if match.group(2) else None
    unit_price = parse_rupiah(match.group(3))
    if unit_price is None:
        return None
    suffix_values = extract_rupiah_values(text[match.end():])
    explicit_line_total = suffix_values[-1] if suffix_values else None
    quantity = parse_receipt_quantity(
        match.group(1),
        unit_price=unit_price,
        line_total=explicit_line_total,
    )
    if quantity is None:
        return None
    return quantity, unit, unit_price, explicit_line_total


def _item_table_bounds(lines: Sequence[ReceiptLine]) -> tuple[int, int] | None:
    """Temukan rentang isi tabel barang berdasarkan header dan footer nota."""
    start: Optional[int] = None
    for index, line in enumerate(lines):
        compact = re.sub(r"\s+", "", line.text).lower()
        has_item_label = "namabarang" in compact or "rincianbarang" in compact
        has_column_label = any(
            label in compact for label in ("banyak", "harga", "jumlah", "qty")
        )
        if has_item_label and has_column_label:
            start = index + 1
            break
    if start is None:
        return None

    footer = re.compile(
        r"\b(?:perhatian|sub\s*total|grand\s*total|total|tunai|cash|"
        r"kembali(?:an)?|tanda\s+terima)\b|\bjumlah\s*(?:rp|2p)\b",
        re.IGNORECASE,
    )
    end = len(lines)
    for index in range(start, len(lines)):
        if footer.search(lines[index].text):
            end = index
            break
    return start, end


def _parse_tabular_item_line(
    line: ReceiptLine,
    *,
    allow_missing_quantity: bool,
) -> Optional[dict[str, Any]]:
    """Parse baris tabel ``quantity + nama + harga`` secara konservatif."""
    price_match = _TABULAR_PRICE_SUFFIX_PATTERN.search(line.text)
    if not price_match:
        return None

    currency = price_match.group("currency")
    if not currency and not re.search(r"\s", line.text[: price_match.start()]):
        return None

    prefix = line.text[: price_match.start()].strip(" -:|.")
    if extract_rupiah_values(prefix):
        # Dua nominal atau lebih pada satu deteksi biasanya berarti beberapa kolom/
        # item melebur. Jangan memilih nominal terakhir secara diam-diam.
        return None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    item_name = prefix
    quantity_match = re.match(
        r"^(\d+(?:[.,]\d+)?)\s+(.+)$",
        prefix,
        re.IGNORECASE,
    )
    if quantity_match:
        quantity = parse_receipt_quantity(quantity_match.group(1))
        remainder = quantity_match.group(2).strip()
        units = "|".join(re.escape(value) for value in _KNOWN_ITEM_UNITS)
        unit_match = re.match(rf"^({units})\b\s*(.+)$", remainder, re.IGNORECASE)
        if unit_match:
            unit = unit_match.group(1).lower()
            item_name = unit_match.group(2).strip()
        else:
            item_name = remainder
    elif not allow_missing_quantity:
        return None

    if not item_name or not _is_item_name(item_name):
        return None

    amount = price_match.group("amount").strip()
    unit_price = parse_rupiah(amount) if _STRICT_RUPIAH_PATTERN.fullmatch(amount) else None
    line_total: Optional[int] = None
    if quantity is not None and unit_price is not None:
        calculated = quantity * unit_price
        line_total = int(calculated) if calculated.is_integer() else round(calculated)

    return {
        "item_name": item_name[:200],
        "quantity": (
            int(quantity) if quantity is not None and quantity.is_integer() else quantity
        ),
        "unit": unit,
        "unit_price": unit_price,
        "line_total": line_total,
        "confidence": round(line.confidence, 4),
    }


def _retail_item_from_match(
    item_name: str,
    match: re.Match[str],
    confidence: float,
) -> Optional[dict[str, Any]]:
    """Bentuk item dari pola retail ``nama qty harga jumlah``."""
    cleaned_name = item_name.strip(" -:|.")
    if "kasir" in cleaned_name.lower():
        cleaned_name = re.sub(
            r"(?is)^.*\bkasir\s*:\s*[A-Za-z0-9._-]+\s*",
            "",
            cleaned_name,
        ).strip(" -:|.")
    if not cleaned_name or not _is_item_name(cleaned_name):
        return None

    unit_price = parse_rupiah(match.group("unit_price"))
    line_total = parse_rupiah(match.group("line_total"))
    if unit_price is None or line_total is None:
        return None
    quantity = parse_receipt_quantity(
        match.group("quantity"),
        unit_price=unit_price,
        line_total=line_total,
    )
    if quantity is None:
        return None
    return {
        "item_name": cleaned_name[:200],
        "quantity": int(quantity) if quantity.is_integer() else quantity,
        "unit": None,
        "unit_price": unit_price,
        "line_total": line_total,
        "confidence": round(confidence, 4),
    }


def _parse_retail_item_line(line: ReceiptLine) -> list[dict[str, Any]]:
    """Ambil satu atau beberapa item retail yang melebur dalam satu baris OCR."""
    matches = list(_RETAIL_ITEM_AMOUNTS_PATTERN.finditer(line.text))
    items: list[dict[str, Any]] = []
    previous_end = 0
    for match in matches:
        item = _retail_item_from_match(
            line.text[previous_end:match.start()],
            match,
            line.confidence,
        )
        previous_end = match.end()
        if item is not None:
            items.append(item)
    return items


def _extract_items(lines: Sequence[ReceiptLine]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    table_bounds = _item_table_bounds(lines)
    index = 0
    while index < len(lines) and len(items) < MAX_RECEIPT_ITEMS:
        line = lines[index]
        quantity_info = _parse_quantity_pattern(line.text)
        item_name: Optional[str] = None
        confidence_values = [line.confidence]

        retail_items = _parse_retail_item_line(line)
        if retail_items:
            items.extend(retail_items[: MAX_RECEIPT_ITEMS - len(items)])
            index += 1
            continue

        if _is_item_name(line.text) and index + 1 < len(lines):
            retail_amounts = _RETAIL_ITEM_AMOUNTS_PATTERN.fullmatch(
                lines[index + 1].text.strip()
            )
            if retail_amounts:
                retail_item = _retail_item_from_match(
                    line.text,
                    retail_amounts,
                    mean((line.confidence, lines[index + 1].confidence)),
                )
                if retail_item is not None:
                    items.append(retail_item)
                    index += 2
                    continue

        if not quantity_info:
            inside_table = bool(
                table_bounds
                and table_bounds[0] <= index < table_bounds[1]
            )
            tabular_item = _parse_tabular_item_line(
                line,
                allow_missing_quantity=inside_table,
            )
            if tabular_item:
                items.append(tabular_item)
                index += 1
                continue

        if quantity_info:
            prefix = line.text[: re.search(r"\d", line.text).start()].strip(" -:.")
            item_name = prefix if _is_item_name(prefix) else None
        elif _is_item_name(line.text) and index + 1 < len(lines):
            next_line = lines[index + 1]
            quantity_info = _parse_quantity_pattern(next_line.text)
            if quantity_info:
                item_name = line.text
                confidence_values.append(next_line.confidence)

        if not quantity_info or not item_name:
            index += 1
            continue

        quantity, unit, unit_price, explicit_line_total = quantity_info
        line_total: Optional[int] = explicit_line_total
        current_values = extract_rupiah_values(line.text)
        if len(current_values) >= 2:
            line_total = current_values[-1]
        next_offset = 1 if _parse_quantity_pattern(line.text) else 2
        if line_total is None and index + next_offset < len(lines):
            total_line = lines[index + next_offset]
            values = extract_rupiah_values(total_line.text)
            if values and not re.search(r"[A-Za-z]", total_line.text):
                line_total = values[-1]
                confidence_values.append(total_line.confidence)

        if line_total is None:
            calculated = quantity * unit_price
            line_total = int(calculated) if calculated.is_integer() else round(calculated)

        items.append(
            {
                "item_name": item_name[:200],
                "quantity": int(quantity) if quantity.is_integer() else quantity,
                "unit": unit,
                "unit_price": unit_price,
                "line_total": line_total,
                "confidence": round(mean(confidence_values), 4),
            }
        )
        index += next_offset
    return items


def amounts_differ(left: int, right: int) -> bool:
    """Bandingkan nominal menggunakan toleransi Rupiah yang dipakai parser."""
    tolerance = max(100, round(max(abs(left), abs(right)) * 0.02))
    return abs(left - right) > tolerance


def parse_receipt(
    ocr_lines: Iterable[Any],
    *,
    minimum_confidence: float = 0.5,
) -> dict[str, Any]:
    """Ekstrak satu transaksi induk dan rincian item dari baris OCR nota."""
    raw_lines = normalize_ocr_lines(ocr_lines)
    raw_ocr_text = "\n".join(line.text for line in raw_lines)[:MAX_OCR_TEXT_LENGTH].strip()
    lines = clean_receipt_ocr_lines(raw_lines)
    ocr_text = "\n".join(line.text for line in lines)[:MAX_OCR_TEXT_LENGTH].strip()
    if not ocr_text:
        return {
            "ocr_text": "",
            "ocr_raw_text": raw_ocr_text,
            "receipt": None,
            "total_candidates": [],
        }

    candidates = _total_candidates(lines)
    total = candidates[0]["value"] if candidates else None
    subtotal = _label_value(lines, r"\b(?:sub\s*total|total\s+items?)\b")
    discount = _label_value(lines, r"\b(?:disc(?:ount)?|diskon|potongan)\b")
    tax = _label_value(lines, r"\b(?:pajak|tax|ppn)\b")
    service_charge = _label_value(lines, r"\b(?:service(?:\s+charge)?|layanan)\b")
    items = _extract_items(lines)
    parsed_date = next((value for line in lines if (value := parse_receipt_date(line.text))), None)
    warnings: list[str] = []

    if not candidates:
        warnings.append("Total akhir tidak ditemukan. Isi nominal setelah memeriksa nota.")
    elif len(candidates) > 1:
        warnings.append("Beberapa kandidat total ditemukan. Pilih total akhir yang benar.")
    if parsed_date is None:
        warnings.append("Tanggal transaksi tidak ditemukan. Pilih tanggal pembelian.")
    if items and any(
        item["quantity"] is None
        or item["unit_price"] is None
        or item["line_total"] is None
        for item in items
    ):
        warnings.append(
            "Sebagian rincian barang tidak lengkap. Periksa quantity dan nominal pada nota."
        )
    for item in items:
        quantity = item.get("quantity")
        unit_price = item.get("unit_price")
        line_total = item.get("line_total")
        if quantity is None or unit_price is None or line_total is None:
            continue
        calculated = round(quantity * unit_price)
        if amounts_differ(calculated, line_total):
            warnings.append(
                f"Perhitungan item {item['item_name']} tidak sesuai: "
                f"quantity x harga = Rp{calculated:,}, tetapi nota mencetak "
                f"Rp{line_total:,}."
            )

    average_confidence = mean(line.confidence for line in lines)
    if average_confidence < minimum_confidence:
        warnings.append("Keyakinan OCR rendah. Periksa kembali seluruh hasil nota.")

    line_total_sum = sum(item["line_total"] for item in items if item["line_total"] is not None)
    # Subtotal nota seharusnya sama persis dengan penjumlahan total per item.
    # Jangan gunakan toleransi persentase karena pada nota bernilai besar selisih
    # ratusan ribu dapat ikut dianggap benar.
    if items and subtotal is not None and line_total_sum != subtotal:
        warnings.append("Jumlah rincian barang tidak sama dengan subtotal nota.")

    if subtotal is not None and total is not None:
        tax_is_included = any(
            re.search(
                r"\bPPN\b.*\bDPP\b|\bDPP\b.*\bPPN\b",
                line.text,
                re.IGNORECASE,
            )
            for line in lines
        )
        expected_total = (
            subtotal
            - (discount or 0)
            + (0 if tax_is_included else (tax or 0))
            + (service_charge or 0)
        )
        if amounts_differ(expected_total, total):
            warnings.append("Total akhir perlu diperiksa kembali.")

    receipt = {
        "merchant_name": _merchant_name(lines),
        "receipt_number": _receipt_number(lines),
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "service_charge": service_charge,
        "total": total,
        "items": items,
        "confidence": round(average_confidence, 4),
        "warnings": warnings,
    }
    return {
        "ocr_text": ocr_text,
        "ocr_raw_text": raw_ocr_text,
        "receipt": receipt,
        "total_candidates": [candidate["value"] for candidate in candidates],
        "date": parsed_date,
    }
