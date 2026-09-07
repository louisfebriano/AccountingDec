"""Inference OCR text memakai Soft Prompt Nota pada base Llama bersama."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from . import config
from .inference import (
    RECEIPT_ADAPTER_NAME,
    RECEIPT_GENERATION_STOP_STRINGS,
    generate_with_adapter,
)
from .prompt_utils import RECEIPT_PROMPT_FORMAT, build_receipt_prompt
from .receipt_schema import RECEIPT_SCHEMA_FIELDS, ReceiptExtractionSchema


class ReceiptInferenceError(RuntimeError):
    """Base error yang aman dipetakan oleh endpoint receipt."""


class ReceiptAdapterUnavailableError(ReceiptInferenceError):
    """Adapter atau metadata kontrak nota belum tersedia/kompatibel."""


class ReceiptOutputValidationError(ReceiptInferenceError):
    """Model nota tidak menghasilkan satu JSON sesuai schema."""

    def __init__(self, message: str, raw_output: Any = None) -> None:
        super().__init__(message)
        # Output mentah ikut dibawa agar evaluator dapat mencatat kegagalan apa
        # adanya tanpa harus menjalankan ulang generasi.
        self.raw_output = raw_output if isinstance(raw_output, str) else None


class ReceiptGenerationError(ReceiptInferenceError):
    """Generasi model receipt gagal karena masalah runtime internal."""


def validate_receipt_adapter_contract(adapter_path: str | Path) -> dict[str, Any]:
    """Pastikan adapter nota cocok dengan base model, prompt, dan schema saat ini."""
    path = Path(adapter_path)
    adapter_config_path = path / "adapter_config.json"
    contract_path = path / config.SOFT_PROMPT_CONTRACT_FILENAME
    if not path.is_dir() or not adapter_config_path.is_file() or not contract_path.is_file():
        raise ReceiptAdapterUnavailableError(
            f"Adapter Soft Prompt Nota belum tersedia di {path}."
        )

    try:
        adapter_config = json.loads(adapter_config_path.read_text(encoding="utf-8"))
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptAdapterUnavailableError(
            "Metadata adapter Soft Prompt Nota tidak dapat dibaca."
        ) from exc

    expected = {
        "contract_version": config.RECEIPT_SOFT_PROMPT_CONTRACT_VERSION,
        "base_model": config.BASE_MODEL_NAME,
        "fields": list(RECEIPT_SCHEMA_FIELDS),
        "prompt_format": RECEIPT_PROMPT_FORMAT,
    }
    for key, expected_value in expected.items():
        if contract.get(key) != expected_value:
            raise ReceiptAdapterUnavailableError(
                f"Kontrak adapter nota tidak kompatibel pada field {key}."
            )
    if adapter_config.get("peft_type") != "PROMPT_TUNING":
        raise ReceiptAdapterUnavailableError(
            "Adapter nota harus menggunakan PEFT PROMPT_TUNING."
        )
    adapter_base = adapter_config.get("base_model_name_or_path")
    if adapter_base and adapter_base != config.BASE_MODEL_NAME:
        raise ReceiptAdapterUnavailableError(
            "Base model adapter nota tidak cocok dengan konfigurasi CatatKas."
        )
    return contract


def parse_receipt_model_output(raw_output: str) -> dict[str, Any]:
    """Parse seluruh output sebagai tepat satu objek JSON dengan tipe ketat."""
    try:
        payload = json.loads(raw_output.strip())
    except (AttributeError, json.JSONDecodeError) as exc:
        raise ReceiptOutputValidationError(
            "Soft Prompt Nota tidak menghasilkan JSON valid.",
            raw_output,
        ) from exc
    if not isinstance(payload, Mapping):
        raise ReceiptOutputValidationError(
            "Output Soft Prompt Nota harus objek JSON.",
            raw_output,
        )
    try:
        validated = ReceiptExtractionSchema.model_validate(payload, strict=True)
    except ValidationError as exc:
        raise ReceiptOutputValidationError(
            "Schema output Soft Prompt Nota tidak valid.",
            raw_output,
        ) from exc
    return validated.model_dump()


def extract_receipt_with_llama(
    ocr_text: str,
    reference_date: date,
    ocr_result: Any = None,
) -> dict[str, Any]:
    """Ekstrak satu nota dari teks OCR tanpa memakai regex sebagai pengganti Llama."""
    del ocr_result  # Disediakan untuk kompatibilitas metadata OCR di masa depan.
    validate_receipt_adapter_contract(config.RECEIPT_ADAPTER_OUTPUT_DIR)
    prompt = build_receipt_prompt(ocr_text, reference_date)
    try:
        raw_output = generate_with_adapter(
            prompt,
            adapter_name=RECEIPT_ADAPTER_NAME,
            adapter_path=config.RECEIPT_ADAPTER_OUTPUT_DIR,
            max_new_tokens=config.RECEIPT_MAX_NEW_TOKENS,
            stop_strings=RECEIPT_GENERATION_STOP_STRINGS,
        )
    except ReceiptInferenceError:
        raise
    except Exception as exc:
        raise ReceiptGenerationError(
            "Soft Prompt Nota gagal menjalankan inference."
        ) from exc

    return {
        "success": True,
        "data": parse_receipt_model_output(raw_output),
        "raw_output": raw_output,
        "adapter_name": RECEIPT_ADAPTER_NAME,
    }

