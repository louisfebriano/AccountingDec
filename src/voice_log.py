"""Log berkas khusus pemrosesan input suara (Whisper + normalisasi + ekstraksi).

Console uvicorn tetap menampilkan log `[voice:<id>]`; modul ini menambahkan
salinan terstruktur satu baris JSON per tahap ke berkas agar mudah ditelusuri
setelah sesi terminal tertutup. Teks dibatasi panjangnya dan audio/foto tidak
pernah ditulis ke sini.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import config

_LOGGER_NAME = "catatkas.voice"
_MAX_TEXT_LENGTH = 5000
_TEXT_FIELDS = {"transcript", "llama_corrected_text", "normalized_text"}

_logger: Optional[logging.Logger] = None
_logger_lock = threading.Lock()


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    # Jangan diteruskan ke root agar baris JSON tidak tercetak dua kali.
    logger.propagate = False
    handler: logging.Handler
    try:
        path = Path(config.VOICE_LOG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=max(config.VOICE_LOG_MAX_BYTES, 1024),
            backupCount=max(config.VOICE_LOG_BACKUP_COUNT, 0),
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
    except OSError:
        # Disk penuh atau folder tidak dapat dibuat tidak boleh menggagalkan request.
        handler = logging.NullHandler()
    logger.addHandler(handler)
    return logger


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        with _logger_lock:
            if _logger is None:
                _logger = _build_logger()
    return _logger


def reset_voice_logger() -> None:
    """Tutup dan buang handler lama; dipakai saat konfigurasi berubah atau di tes."""
    global _logger
    with _logger_lock:
        logger = logging.getLogger(_LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        _logger = None


def _limited_text(value: Any) -> tuple[str, bool]:
    text = "" if value is None else str(value)
    if len(text) <= _MAX_TEXT_LENGTH:
        return text, False
    return text[:_MAX_TEXT_LENGTH], True


def log_voice_event(
    request_id: str,
    stage: str,
    **fields: Any,
) -> None:
    """Tulis satu baris JSON ke log suara tanpa membuat request gagal."""
    if not config.VOICE_LOG_ENABLED:
        return
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "request_id": request_id,
        "stage": stage,
    }
    for key, value in fields.items():
        if key in _TEXT_FIELDS:
            text, truncated = _limited_text(value)
            record[key] = text
            if truncated:
                record[f"{key}_truncated"] = True
        else:
            record[key] = value
    try:
        _get_logger().info(json.dumps(record, ensure_ascii=False, default=str))
    except OSError:
        # Menulis log adalah fitur pendukung; kegagalannya tidak boleh terlihat
        # oleh pengguna atau mengubah hasil ekstraksi.
        pass
