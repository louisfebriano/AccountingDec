"""Validasi silang hasil Soft Prompt Nota terhadap OCR dan parser deterministik."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .receipt_parser import amounts_differ


def _append_unique(values: list[str], message: str) -> None:
    if message not in values:
        values.append(message)


def _normalized_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 1
    ]


def _supported_by_ocr(value: str | None, ocr_text: str) -> bool:
    if value is None:
        return True
    value_tokens = _normalized_tokens(value)
    if not value_tokens:
        return False
    ocr_tokens = set(_normalized_tokens(ocr_text))
    matched = sum(token in ocr_tokens for token in value_tokens)
    return matched == len(value_tokens)


def validate_receipt_semantics(
    llama_receipt: Mapping[str, Any],
    rule_result: Mapping[str, Any],
    ocr_text: str,
) -> dict[str, Any]:
    """Bandingkan hasil Llama tanpa mengganti nilainya secara diam-diam."""
    rule_receipt = rule_result.get("receipt") or {}
    warnings = list(rule_receipt.get("warnings") or [])
    items = list(llama_receipt.get("items") or [])

    available_line_totals = [
        item["line_total"]
        for item in items
        if item.get("line_total") is not None
    ]
    subtotal = llama_receipt.get("subtotal")
    if available_line_totals and subtotal is not None:
        if amounts_differ(sum(available_line_totals), subtotal):
            _append_unique(
                warnings,
                "Jumlah line_total item tidak sama dengan subtotal hasil model.",
            )

    total = llama_receipt.get("total")
    if subtotal is not None and total is not None:
        expected_total = (
            subtotal
            - (llama_receipt.get("discount") or 0)
            + (llama_receipt.get("tax") or 0)
            + (llama_receipt.get("service_charge") or 0)
        )
        if amounts_differ(expected_total, total):
            _append_unique(
                warnings,
                "Subtotal, diskon, pajak, dan biaya layanan tidak sesuai total model.",
            )

    total_candidates = list(rule_result.get("total_candidates") or [])
    if total_candidates:
        if total is None:
            _append_unique(
                warnings,
                "Total hasil model kosong meskipun kandidat total terbaca OCR.",
            )
        elif all(amounts_differ(total, candidate) for candidate in total_candidates):
            _append_unique(
                warnings,
                "Total hasil model berbeda dari kandidat total yang terbaca OCR.",
            )

    rule_date = rule_result.get("date")
    model_date = llama_receipt.get("date")
    if (model_date is not None or rule_date is not None) and model_date != rule_date:
        _append_unique(
            warnings,
            "Tanggal hasil model berbeda dari tanggal yang dibaca parser OCR.",
        )

    rule_items = list(rule_receipt.get("items") or [])
    if len(rule_items) != len(items):
        _append_unique(
            warnings,
            "Jumlah item hasil model berbeda dari jumlah item parser OCR.",
        )

    if not _supported_by_ocr(llama_receipt.get("merchant_name"), ocr_text):
        _append_unique(
            warnings,
            "Nama merchant hasil model tidak memiliki dukungan penuh pada teks OCR.",
        )

    for index, item in enumerate(items, start=1):
        item_name = item.get("item_name")
        if not _supported_by_ocr(item_name, ocr_text):
            _append_unique(
                warnings,
                f"Item {index} ({item_name}) tidak memiliki dukungan penuh pada teks OCR.",
            )
        quantity = item.get("quantity")
        unit_price = item.get("unit_price")
        line_total = item.get("line_total")
        if quantity is not None and unit_price is None:
            _append_unique(
                warnings,
                f"Item {index} memiliki quantity tetapi unit_price tidak tersedia.",
            )
        if quantity is not None and unit_price is not None and line_total is None:
            _append_unique(
                warnings,
                f"Item {index} memiliki quantity dan unit_price tetapi line_total tidak tersedia.",
            )
        if quantity is not None and unit_price is not None and line_total is not None:
            calculated = round(quantity * unit_price)
            if amounts_differ(calculated, line_total):
                _append_unique(
                    warnings,
                    f"Perhitungan quantity × unit_price item {index} tidak sesuai line_total.",
                )

    return {
        "status": "valid" if not warnings else "needs_confirmation",
        "warnings": warnings,
        "audit": {
            "llama": dict(llama_receipt),
            "rule_based": {
                "receipt": rule_receipt,
                "date": rule_date,
                "total_candidates": total_candidates,
            },
        },
    }


def fallback_validation(
    rule_result: Mapping[str, Any],
    reason: str,
) -> dict[str, Any]:
    """Tandai fallback rule-based secara eksplisit untuk respons dan log audit."""
    rule_receipt = rule_result.get("receipt") or {}
    warnings = list(rule_receipt.get("warnings") or [])
    _append_unique(warnings, reason)
    return {
        "status": "needs_confirmation",
        "warnings": warnings,
        "audit": {
            "llama": None,
            "rule_based": {
                "receipt": rule_receipt,
                "date": rule_result.get("date"),
                "total_candidates": list(rule_result.get("total_candidates") or []),
            },
        },
    }
