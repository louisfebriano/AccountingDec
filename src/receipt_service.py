"""Layanan OCR nota lokal berbasis PaddleOCR yang dimuat secara lazy."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from statistics import mean
from threading import Lock
from typing import Any, Iterable, Sequence

from . import config
from .receipt_parser import (
    clean_receipt_ocr_text,
    compact_receipt_ocr_text,
    extract_rupiah_values,
    parse_receipt,
)


class InvalidReceiptImageError(ValueError):
    """Gambar upload rusak atau format isinya tidak sesuai."""


class ReceiptOcrUnavailableError(RuntimeError):
    """Dependensi atau model OCR tidak dapat digunakan."""


_ocr_model: Any = None
_model_lock = Lock()


def get_receipt_ocr_model() -> Any:
    """Muat dan cache satu instance PaddleOCR tanpa memengaruhi startup API."""
    global _ocr_model
    if _ocr_model is None:
        with _model_lock:
            if _ocr_model is None:
                try:
                    from paddleocr import PaddleOCR
                except ImportError as exc:
                    raise ReceiptOcrUnavailableError(
                        "Dependensi PaddleOCR belum terpasang."
                    ) from exc
                try:
                    _ocr_model = PaddleOCR(
                        use_angle_cls=True,
                        use_gpu=False,
                        lang=config.RECEIPT_OCR_LANGUAGE,
                        show_log=False,
                        use_space_char=True,
                        det_db_box_thresh=config.RECEIPT_OCR_DET_BOX_THRESHOLD,
                        det_db_unclip_ratio=1.8,
                        drop_score=config.RECEIPT_OCR_DROP_SCORE,
                    )
                except Exception as exc:
                    raise ReceiptOcrUnavailableError(
                        "Model OCR nota tidak dapat dimuat."
                    ) from exc
    return _ocr_model


def validate_receipt_image(path: Path, expected_format: str | None = None) -> str:
    """Validasi isi gambar menggunakan decoder, bukan hanya nama atau MIME type."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            detected = str(image.format or "").upper()
            if image.width * image.height > config.RECEIPT_MAX_IMAGE_PIXELS:
                raise InvalidReceiptImageError(
                    "Resolusi gambar nota terlalu besar."
                )
            image.verify()
    except InvalidReceiptImageError:
        raise
    except Exception as exc:
        raise InvalidReceiptImageError("File bukan gambar yang valid atau sudah rusak.") from exc

    aliases = {"JPG": "JPEG"}
    detected = aliases.get(detected, detected)
    expected = aliases.get(str(expected_format or "").upper(), str(expected_format or "").upper())
    if detected not in {"JPEG", "PNG", "WEBP"}:
        raise InvalidReceiptImageError("Isi gambar harus berformat JPEG, PNG, atau WebP.")
    if expected and detected != expected:
        raise InvalidReceiptImageError("Ekstensi, MIME type, dan isi gambar tidak sesuai.")
    return detected


def _deskew_safely(image: Any) -> Any:
    """Koreksi kemiringan kecil bila OpenCV tersedia; abaikan estimasi berisiko."""
    try:
        import cv2
        import numpy as np

        gray = np.array(image.convert("L"))
        _threshold, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        coordinates = cv2.findNonZero(binary)
        if coordinates is None or len(coordinates) < 20:
            return image
        angle = cv2.minAreaRect(coordinates)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) < 0.3 or abs(angle) > 5:
            return image
        return image.rotate(angle, resample=2, expand=True, fillcolor="white")
    except (ImportError, ValueError, TypeError):
        return image


def preprocess_receipt_image(source_path: Path) -> Path:
    """Perbaiki orientasi, resolusi, kontras, dan kemiringan untuk OCR."""
    from PIL import Image, ImageEnhance, ImageOps, ImageStat

    try:
        with Image.open(source_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            max_dimension = config.RECEIPT_MAX_IMAGE_DIMENSION
            long_edge = max(image.size)
            target_long_edge = min(
                config.RECEIPT_OCR_TARGET_LONG_EDGE,
                max_dimension,
            )
            if long_edge < target_long_edge:
                scale = target_long_edge / long_edge
                image = image.resize(
                    (
                        max(1, round(image.width * scale)),
                        max(1, round(image.height * scale)),
                    ),
                    Image.Resampling.LANCZOS,
                )
            elif long_edge > max_dimension:
                image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            grayscale = ImageOps.autocontrast(image.convert("L"), cutoff=1)
            deviation = ImageStat.Stat(grayscale).stddev[0]
            if deviation < 38:
                grayscale = ImageEnhance.Contrast(grayscale).enhance(1.35)
            grayscale = ImageEnhance.Sharpness(grayscale).enhance(1.8)
            image = _deskew_safely(grayscale)
    except Exception as exc:
        raise InvalidReceiptImageError("Gambar nota gagal diproses.") from exc

    handle = tempfile.NamedTemporaryFile(
        prefix="catatkas-receipt-preprocessed-", suffix=".png", delete=False
    )
    output_path = Path(handle.name)
    handle.close()
    try:
        image.save(output_path, format="PNG", optimize=True)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return output_path


def create_threshold_receipt_variant(source_path: Path) -> Path | None:
    """Buat varian threshold adaptif; kembalikan None bila varian tidak aman dibuat."""
    output_path: Path | None = None
    try:
        import cv2

        grayscale = cv2.imread(str(source_path), cv2.IMREAD_GRAYSCALE)
        if grayscale is None:
            return None
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(grayscale)
        threshold = cv2.adaptiveThreshold(
            clahe,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            15,
        )
        handle = tempfile.NamedTemporaryFile(
            prefix="catatkas-receipt-threshold-",
            suffix=".png",
            delete=False,
        )
        output_path = Path(handle.name)
        handle.close()
        if not cv2.imwrite(str(output_path), threshold):
            output_path.unlink(missing_ok=True)
            return None
        return output_path
    except Exception:
        if output_path is not None:
            output_path.unlink(missing_ok=True)
        return None


def _line_from_entry(entry: Any) -> dict[str, Any] | None:
    """Normalisasi bentuk keluaran PaddleOCR 2.x menjadi kontrak internal."""
    if not isinstance(entry, (list, tuple)) or len(entry) < 2:
        return None
    box, value = entry[0], entry[1]
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    if not isinstance(value[0], str) or not isinstance(value[1], (int, float)):
        return None
    text = re.sub(r"\s+", " ", str(value[0] or "")).strip()
    if not text:
        return None
    try:
        confidence = float(value[1])
    except (TypeError, ValueError):
        confidence = 0.0
    return {"text": text, "confidence": confidence, "box": box}


def normalize_paddle_result(result: Any) -> list[dict[str, Any]]:
    """Ambil baris, confidence, dan koordinat dari hasil OCR yang didukung."""
    if not result:
        return []
    pages: Iterable[Any] = result if isinstance(result, (list, tuple)) else [result]
    lines: list[dict[str, Any]] = []
    for page in pages:
        entries = page if isinstance(page, (list, tuple)) else []
        if entries and _line_from_entry(entries):
            entries = [entries]
        for entry in entries:
            line = _line_from_entry(entry)
            if line:
                lines.append(line)
    return lines


def score_ocr_candidate(lines: Sequence[dict[str, Any]]) -> float:
    """Nilai hasil OCR berdasarkan struktur, confidence, keyword, dan nominal."""
    if not lines:
        return float("-inf")
    texts = [str(line.get("text") or "") for line in lines]
    combined = clean_receipt_ocr_text("\n".join(texts))
    confidences = [float(line.get("confidence") or 0.0) for line in lines]
    keyword_count = len(
        re.findall(
            r"\b(?:nota|struk|nama\s*barang|harga|jumlah|total|rp|tanggal)\b",
            combined,
            re.IGNORECASE,
        )
    )
    amount_count = len(extract_rupiah_values(combined))
    parsed = parse_receipt(lines)
    receipt = parsed.get("receipt") or {}
    items = list(receipt.get("items") or [])
    complete_prices = sum(
        isinstance(item.get("unit_price"), int) and item["unit_price"] > 0
        for item in items
    )
    long_block_penalty = 20 if len(lines) <= 2 and len(combined) > 180 else 0
    return (
        mean(confidences) * 20
        + min(len(lines), 40) * 1.25
        + min(keyword_count, 15) * 2
        + min(amount_count, 20) * 2
        + min(len(items), 10) * 5
        + min(complete_prices, 10) * 2
        + (4 if receipt.get("total") is not None else 0)
        - long_block_penalty
    )


def select_best_ocr_lines(
    candidates: Sequence[Sequence[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], int, list[float]]:
    """Pilih pass OCR terbaik tanpa menggabungkan teks dari pass berbeda."""
    if not candidates:
        return [], 0, []
    scores = [score_ocr_candidate(candidate) for candidate in candidates]
    selected_index = max(range(len(candidates)), key=scores.__getitem__)
    return list(candidates[selected_index]), selected_index, scores


def extract_receipt(path: Path) -> dict[str, Any]:
    """Praproses gambar, jalankan OCR, lalu parse satu transaksi nota."""
    processed_paths: list[Path] = []
    try:
        processed_path = preprocess_receipt_image(path)
        processed_paths.append(processed_path)
        if config.RECEIPT_OCR_MULTIPASS:
            threshold_path = create_threshold_receipt_variant(processed_path)
            if threshold_path is not None:
                processed_paths.append(threshold_path)
        model = get_receipt_ocr_model()
        candidates: list[list[dict[str, Any]]] = []
        last_error: Exception | None = None
        for candidate_path in processed_paths:
            try:
                result = model.ocr(str(candidate_path), cls=True)
            except Exception as exc:
                last_error = exc
                continue
            candidates.append(normalize_paddle_result(result))
        if not candidates and last_error is not None:
            raise ReceiptOcrUnavailableError("OCR nota gagal dijalankan.") from last_error

        lines, selected_pass, scores = select_best_ocr_lines(candidates)
        parsed = parse_receipt(
            lines,
            minimum_confidence=config.RECEIPT_MIN_CONFIDENCE,
        )
        parsed["ocr_model_text"] = compact_receipt_ocr_text(
            parsed.get("ocr_text") or "",
            parsed.get("receipt"),
        )
        parsed["ocr_diagnostics"] = {
            "passes": len(candidates),
            "selected_pass": selected_pass,
            "scores": [round(score, 4) for score in scores],
        }
        return parsed
    finally:
        for processed_path in processed_paths:
            processed_path.unlink(missing_ok=True)
