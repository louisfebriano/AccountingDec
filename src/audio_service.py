"""Layanan speech-to-text bahasa Indonesia berbasis faster-whisper."""

import re
from pathlib import Path
from threading import Lock
from typing import Any, Union

from . import config

_whisper_model: Any = None
_model_lock = Lock()


def get_whisper_model() -> Any:
    """Muat model Whisper secara lazy dan cache satu instance untuk seluruh proses."""
    global _whisper_model

    if _whisper_model is None:
        with _model_lock:
            if _whisper_model is None:
                from faster_whisper import WhisperModel

                _whisper_model = WhisperModel(
                    config.WHISPER_MODEL_SIZE,
                    device=config.WHISPER_DEVICE,
                    compute_type=config.WHISPER_COMPUTE_TYPE,
                )
    return _whisper_model


def transcribe_audio(audio_path: Union[str, Path]) -> str:
    """Transkripsikan audio Indonesia dan gabungkan segmennya menjadi teks bersih."""
    model = get_whisper_model()
    segments, _info = model.transcribe(
        str(audio_path),
        language=config.WHISPER_LANGUAGE,
        vad_filter=config.WHISPER_VAD_FILTER,
    )
    transcript = " ".join(
        segment.text.strip() for segment in segments if segment.text.strip()
    )
    return re.sub(r"\s+", " ", transcript).strip()
