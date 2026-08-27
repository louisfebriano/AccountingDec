"""Layanan OCR nota lokal berbasis PaddleOCR yang dimuat secara lazy."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from . import config
from .receipt_parser import parse_receipt


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
    """Perbaiki orientasi, ukuran, kontras, dan kemiringan ke file JPEG sementara."""
    from PIL import Image, ImageEnhance, ImageOps, ImageStat

    try:
        with Image.open(source_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            max_dimension = config.RECEIPT_MAX_IMAGE_DIMENSION
            if max(image.size) > max_dimension:
                image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            grayscale = image.convert("L")
            deviation = ImageStat.Stat(grayscale).stddev[0]
            if deviation < 38:
                image = ImageEnhance.Contrast(image).enhance(1.25)
            image = _deskew_safely(image)
    except Exception as exc:
        raise InvalidReceiptImageError("Gambar nota gagal diproses.") from exc

    handle = tempfile.NamedTemporaryFile(
        prefix="catatkas-receipt-preprocessed-", suffix=".jpg", delete=False
    )
    output_path = Path(handle.name)
    handle.close()
    try:
        image.save(output_path, format="JPEG", quality=94, optimize=True)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return output_path


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


def extract_receipt(path: Path) -> dict[str, Any]:
    """Praproses gambar, jalankan OCR, lalu parse satu transaksi nota."""
    processed_path: Path | None = None
    try:
        processed_path = preprocess_receipt_image(path)
        model = get_receipt_ocr_model()
        try:
            result = model.ocr(str(processed_path), cls=True)
        except Exception as exc:
            raise ReceiptOcrUnavailableError("OCR nota gagal dijalankan.") from exc
        lines = normalize_paddle_result(result)
        return parse_receipt(
            lines,
            minimum_confidence=config.RECEIPT_MIN_CONFIDENCE,
        )
    finally:
        if processed_path is not None:
            processed_path.unlink(missing_ok=True)
