"""Koreksi typo transkrip suara memakai base Llama 3.2 secara terkendali."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from . import config


VOICE_NORMALIZATION_INSTRUCTION = (
    "Kamu adalah korektor transkripsi transaksi bahasa Indonesia. Perbaiki hanya "
    "salah eja atau kata yang keliru didengar, misalnya 'karong' menjadi 'karung' "
    "atau 'kristok' menjadi 'restok'. "
    "Jangan mengubah angka, nominal, quantity, tanggal, nama barang, atau maksud "
    "transaksi. Pertahankan urutan kata sedekat mungkin. Jawab hanya dengan satu "
    "baris teks hasil koreksi tanpa penjelasan, label, tanda kutip, atau markdown."
)

_NUMBER_TOKEN_PATTERN = re.compile(r"\d+(?:[.,]\d+)*")
_LEADING_LABEL_PATTERN = re.compile(
    r"^(?:hasil(?:\s+koreksi)?|koreksi|transkrip)\s*:\s*",
    re.IGNORECASE,
)


def _clean_candidate(raw_output: str) -> str:
    """Ambil satu baris jawaban dan buang wrapper yang tidak diminta."""
    candidate = str(raw_output or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:text)?\s*|\s*```$", "", candidate, flags=re.I)
    try:
        decoded = json.loads(candidate)
        if isinstance(decoded, str):
            candidate = decoded
    except (json.JSONDecodeError, TypeError):
        pass
    candidate = _LEADING_LABEL_PATTERN.sub("", candidate.strip())
    return re.sub(r"\s+", " ", candidate).strip().strip('"\'')


def _is_safe_correction(original: str, candidate: str) -> bool:
    """Tolak keluaran yang mengubah angka atau menulis ulang kalimat terlalu jauh."""
    if not candidate or "{" in candidate or "}" in candidate:
        return False
    if _NUMBER_TOKEN_PATTERN.findall(original) != _NUMBER_TOKEN_PATTERN.findall(candidate):
        return False
    if len(candidate) > max(len(original) * 2, len(original) + 80):
        return False
    similarity = SequenceMatcher(None, original.casefold(), candidate.casefold()).ratio()
    return similarity >= 0.55


def correct_voice_transcript_with_llama(text: str) -> str:
    """Koreksi typo dengan Llama; kembalikan input jika output tidak aman."""
    if not text or not text.strip() or not config.VOICE_LLM_NORMALIZATION_ENABLED:
        return text

    from .inference import generate_with_base_model

    raw_output = generate_with_base_model(
        [
            {"role": "system", "content": VOICE_NORMALIZATION_INSTRUCTION},
            {"role": "user", "content": text.strip()},
        ],
        max_new_tokens=config.VOICE_LLM_NORMALIZATION_MAX_NEW_TOKENS,
    )
    candidate = _clean_candidate(raw_output)
    return candidate if _is_safe_correction(text.strip(), candidate) else text.strip()
