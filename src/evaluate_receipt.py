"""Evaluator khusus output Soft Prompt Nota tanpa membuat prediksi palsu."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from . import config
from .receipt_inference import (
    ReceiptOutputValidationError,
    extract_receipt_with_llama,
    parse_receipt_model_output,
)
from .receipt_schema import ReceiptExtractionSchema
from .train_receipt import load_receipt_jsonl


SCALAR_FIELDS = (
    "merchant_name",
    "receipt_number",
    "date",
    "subtotal",
    "discount",
    "tax",
    "service_charge",
    "total",
    "transaction_type",
)
ITEM_FIELDS = ("quantity", "unit", "unit_price", "line_total")


def _normalized_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _validated_prediction(row: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        if isinstance(row.get("raw_output"), str):
            return parse_receipt_model_output(row["raw_output"])
        return ReceiptExtractionSchema.model_validate(row.get("output"), strict=True).model_dump()
    except (ReceiptOutputValidationError, ValidationError, TypeError, ValueError):
        return None


def _match_items(
    target_items: Sequence[Mapping[str, Any]],
    predicted_items: Sequence[Mapping[str, Any]],
) -> tuple[list[tuple[Mapping[str, Any], Mapping[str, Any]]], int, int, int]:
    targets_by_name: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in target_items:
        targets_by_name[_normalized_name(item.get("item_name"))].append(item)
    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    false_positive = 0
    for predicted in predicted_items:
        name = _normalized_name(predicted.get("item_name"))
        candidates = targets_by_name.get(name) or []
        if candidates:
            pairs.append((candidates.pop(0), predicted))
        else:
            false_positive += 1
    false_negative = sum(len(values) for values in targets_by_name.values())
    return pairs, len(pairs), false_positive, false_negative


def evaluate_receipt_predictions(
    targets: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Hitung metrik receipt dari target dan prediksi yang benar-benar diberikan."""
    if len(targets) != len(predictions):
        raise ValueError("Jumlah target dan prediksi receipt harus sama.")
    valid_json = 0
    exact_matches = 0
    scalar_correct = {field: 0 for field in SCALAR_FIELDS}
    item_field_correct = {field: 0 for field in ITEM_FIELDS}
    matched_item_count = 0
    item_tp = item_fp = item_fn = 0

    for target_row, prediction_row in zip(targets, predictions):
        target = ReceiptExtractionSchema.model_validate(
            target_row["output"],
            strict=True,
        ).model_dump()
        prediction = _validated_prediction(prediction_row)
        if prediction is None:
            item_fn += len(target["items"])
            continue
        valid_json += 1
        if prediction == target:
            exact_matches += 1
        for field in SCALAR_FIELDS:
            if prediction[field] == target[field]:
                scalar_correct[field] += 1
        pairs, tp, fp, fn = _match_items(target["items"], prediction["items"])
        item_tp += tp
        item_fp += fp
        item_fn += fn
        matched_item_count += len(pairs)
        for target_item, predicted_item in pairs:
            for field in ITEM_FIELDS:
                if target_item[field] == predicted_item[field]:
                    item_field_correct[field] += 1

    total = len(targets)
    precision = _safe_ratio(item_tp, item_tp + item_fp)
    recall = _safe_ratio(item_tp, item_tp + item_fn)
    item_f1 = _safe_ratio(2 * precision * recall, precision + recall)
    scalar_accuracy = {
        field: _safe_ratio(correct, total)
        for field, correct in scalar_correct.items()
    }
    return {
        "examples": total,
        "json_validity_rate": _safe_ratio(valid_json, total),
        "field_level_accuracy": _safe_ratio(sum(scalar_correct.values()), total * len(SCALAR_FIELDS)),
        "merchant_name_accuracy": scalar_accuracy["merchant_name"],
        "date_accuracy": scalar_accuracy["date"],
        "total_price_accuracy": scalar_accuracy["total"],
        "scalar_field_accuracy": scalar_accuracy,
        "item_name_precision": precision,
        "item_name_recall": recall,
        "item_name_f1": item_f1,
        "quantity_accuracy": _safe_ratio(item_field_correct["quantity"], matched_item_count),
        "unit_accuracy": _safe_ratio(item_field_correct["unit"], matched_item_count),
        "unit_price_accuracy": _safe_ratio(item_field_correct["unit_price"], matched_item_count),
        "line_total_accuracy": _safe_ratio(item_field_correct["line_total"], matched_item_count),
        "exact_transaction_match": _safe_ratio(exact_matches, total),
    }


def load_prediction_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"File prediksi receipt tidak ditemukan: {source}")
    rows = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Prediksi baris {line_number} bukan JSON valid.") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Prediksi baris {line_number} harus objek JSON.")
        rows.append(value)
    return rows


def collect_model_predictions(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Jalankan adapter nyata; error adapter diteruskan dan tidak difabrikasi."""
    predictions = []
    for row in rows:
        result = extract_receipt_with_llama(
            str(row["input"]),
            date.fromisoformat(str(row["reference_date"])),
        )
        predictions.append({"raw_output": result["raw_output"]})
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluasi Soft Prompt Nota CatatKas")
    parser.add_argument("--data", default=config.RECEIPT_EVAL_DATA_PATH)
    parser.add_argument("--predictions", default=None)
    parser.add_argument("--output", default="receipt-evaluation-report.json")
    args = parser.parse_args()

    targets = load_receipt_jsonl(args.data)
    predictions = (
        load_prediction_jsonl(args.predictions)
        if args.predictions
        else collect_model_predictions(targets)
    )
    report = evaluate_receipt_predictions(targets, predictions)
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
