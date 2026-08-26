"""Evaluasi empat konfigurasi ekstraksi transaksi.

Base Llama memakai explicit instruction melalui chat template, sedangkan adapter
Soft Prompt tetap memakai format prompt yang digunakan saat training. Masing-masing
raw output digunakan ulang oleh varian post-processing.
"""

from __future__ import annotations

import argparse
import gc
import json
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import config
from .postprocess import parse_and_validate
from .prompt_utils import build_explicit_instruction_prompt, build_inference_prompt
from .transaction_type import (
    classify_transaction_type,
    is_general_income_transaction,
)

FIELDS = (
    "item_name",
    "quantity",
    "unit",
    "total_price",
    "date",
    "transaction_type",
)
NUMERIC_FIELDS = {"quantity", "total_price"}
TRANSACTION_TYPES = {"income", "expense"}
STOP_STRINGS = (".Kalimat:", "\n\n", "\nKalimat", "Kalimat:")

CONFIGURATIONS = {
    "llama": {
        "label": "Llama + Explicit Instruction",
        "short_label": "Llama+Instr",
        "raw_source": "base_explicit",
        "soft_prompt": False,
        "postprocessing": False,
        "experiment_group": "main_comparison",
    },
    "llama_soft_prompt": {
        "label": "Llama + Soft Prompt",
        "short_label": "Llama+SP",
        "raw_source": "soft_prompt",
        "soft_prompt": True,
        "postprocessing": False,
        "experiment_group": "main_comparison",
    },
    "llama_postprocessing": {
        "label": "Llama + Explicit Instruction + Post-processing",
        "short_label": "Llama+Instr+PP",
        "raw_source": "base_explicit",
        "soft_prompt": False,
        "postprocessing": True,
        "experiment_group": "main_comparison",
    },
    "llama_soft_prompt_postprocessing": {
        "label": "Llama + Soft Prompt + Post-processing",
        "short_label": "Llama+SP+PP",
        "raw_source": "soft_prompt",
        "soft_prompt": True,
        "postprocessing": True,
        "experiment_group": "main_comparison",
    },
}

_MISSING = object()


class DatasetValidationError(ValueError):
    """Dataset tidak memenuhi kontrak evaluasi enam field."""


class ModelEvaluationError(RuntimeError):
    """Model tidak dapat dimuat atau dijalankan untuk evaluasi."""


def validate_soft_prompt_contract(adapter_path: str | Path) -> dict[str, Any]:
    """Tolak adapter lama agar evaluasi enam field tidak memberi hasil menyesatkan."""
    contract_path = Path(adapter_path) / config.SOFT_PROMPT_CONTRACT_FILENAME
    if not contract_path.is_file():
        raise ModelEvaluationError(
            "Adapter masih memakai kontrak lama atau metadata tidak ditemukan. "
            "Jalankan `python -m src.train` sebelum evaluasi enam field."
        )
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelEvaluationError(f"Metadata adapter tidak valid: {exc}") from exc
    if contract.get("contract_version") != config.SOFT_PROMPT_CONTRACT_VERSION:
        raise ModelEvaluationError(
            "Versi kontrak adapter tidak cocok. Latih ulang adapter dengan kode saat ini."
        )
    if tuple(contract.get("fields", ())) != FIELDS:
        raise ModelEvaluationError(
            "Field kontrak adapter tidak cocok dengan evaluator enam field."
        )
    return contract


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Muat JSONL dan sertakan nomor baris pada pesan data yang rusak."""
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise DatasetValidationError(
                    f"JSONL tidak valid pada baris {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(row, dict):
                raise DatasetValidationError(
                    f"Baris {line_number} harus berupa objek JSON."
                )
            rows.append(row)
    return rows


def validate_evaluation_dataset(dataset: Sequence[Mapping[str, Any]]) -> None:
    """Pastikan setiap contoh memiliki input dan ground truth enam field lengkap."""
    if not dataset:
        raise DatasetValidationError("Dataset evaluasi kosong.")

    errors: list[str] = []
    for index, example in enumerate(dataset, start=1):
        user_input = example.get("input")
        target = example.get("output")
        if not isinstance(user_input, str) or not user_input.strip():
            errors.append(f"data {index}: field input harus berupa teks non-kosong")
        if not isinstance(target, Mapping):
            errors.append(f"data {index}: field output harus berupa objek JSON")
            continue

        missing_fields = [field for field in FIELDS if field not in target]
        if missing_fields:
            errors.append(
                f"data {index}: target tidak memiliki field "
                + ", ".join(missing_fields)
            )
            continue

        transaction_type = target.get("transaction_type")
        normalized_type = (
            transaction_type.strip().casefold()
            if isinstance(transaction_type, str)
            else transaction_type
        )
        if normalized_type not in TRANSACTION_TYPES:
            errors.append(
                f"data {index}: transaction_type target harus income atau expense"
            )

    if errors:
        preview = "\n- ".join(errors[:10])
        remainder = len(errors) - 10
        suffix = f"\n- ... dan {remainder} masalah lain" if remainder > 0 else ""
        raise DatasetValidationError(
            "Dataset belum siap untuk evaluasi enam field:\n- " + preview + suffix
        )


def _reject_nonstandard_json_constant(value: str) -> None:
    """Tolak NaN/Infinity yang diterima parser Python tetapi bukan JSON standar."""
    raise ValueError(f"Konstanta JSON non-standar: {value}")


def parse_raw_json(raw_output: Any) -> dict[str, Any]:
    """Parse keluaran model persis apa adanya tanpa ekstraksi atau perbaikan."""
    if not isinstance(raw_output, str):
        return {
            "valid_json": False,
            "prediction": None,
            "error": "Keluaran model bukan teks.",
        }
    try:
        prediction = json.loads(
            raw_output,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "valid_json": False,
            "prediction": None,
            "error": f"JSON mentah tidak valid: {exc}",
        }
    if not isinstance(prediction, dict):
        return {
            "valid_json": False,
            "prediction": None,
            "error": "Keluaran JSON mentah bukan objek.",
        }
    return {"valid_json": True, "prediction": prediction, "error": None}


def apply_system_postprocessing(
    raw_output: Any,
    user_input: str,
    reference_date: date,
) -> dict[str, Any]:
    """Terapkan classifier dan parser produksi pada keluaran model yang sudah ada."""
    if not isinstance(raw_output, str):
        return {
            "valid_json": False,
            "prediction": None,
            "error": "Keluaran model bukan teks.",
        }

    transaction_type = classify_transaction_type(user_input)
    if transaction_type == "unknown":
        return {
            "valid_json": False,
            "prediction": None,
            "error": "Post-processing menghasilkan transaction_type unknown.",
        }

    try:
        result = parse_and_validate(
            raw_output,
            user_input=user_input,
            reference_date=reference_date,
            transaction_type=transaction_type,
        )
    except Exception as exc:  # pragma: no cover - perlindungan batas integrasi
        return {
            "valid_json": False,
            "prediction": None,
            "error": f"Post-processing gagal: {exc}",
        }

    prediction = result.get("data")
    if not result.get("success") or not isinstance(prediction, dict):
        return {
            "valid_json": False,
            "prediction": None,
            "error": result.get("error") or "Post-processing tidak menghasilkan objek.",
        }
    return {"valid_json": True, "prediction": prediction, "error": None}


def _as_decimal(value: Any) -> Decimal | None:
    """Ubah representasi angka sederhana menjadi Decimal untuk perbandingan."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str) and re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value.strip()
    ):
        text = value.strip()
    else:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def values_match(field: str, target: Any, prediction: Any) -> bool:
    """Bandingkan nilai dengan normalisasi ringan yang tidak mengekstrak informasi."""
    if prediction is _MISSING:
        return False
    if target is None or prediction is None:
        return target is None and prediction is None

    if field in NUMERIC_FIELDS:
        target_number = _as_decimal(target)
        prediction_number = _as_decimal(prediction)
        if target_number is not None and prediction_number is not None:
            return target_number == prediction_number

    if isinstance(target, str) and isinstance(prediction, str):
        normalize = lambda value: re.sub(r"\s+", " ", value.strip()).casefold()
        return normalize(target) == normalize(prediction)

    return type(target) is type(prediction) and target == prediction


def score_prediction(
    target: Mapping[str, Any],
    prediction: Mapping[str, Any] | None,
    valid_json: bool,
) -> dict[str, Any]:
    """Hitung TP/FP/FN dan kecocokan enam field untuk satu contoh."""
    field_matches = {field: False for field in FIELDS}
    tp = fp = fn = 0

    if not valid_json or prediction is None:
        fn = sum(target.get(field) is not None for field in FIELDS)
        return {"tp": tp, "fp": fp, "fn": fn, "field_matches": field_matches}

    for field in FIELDS:
        target_value = target.get(field)
        predicted_value = prediction.get(field, _MISSING)
        matched = values_match(field, target_value, predicted_value)
        field_matches[field] = matched

        if matched:
            if target_value is not None:
                tp += 1
            continue

        if predicted_value is not _MISSING and predicted_value is not None:
            fp += 1
        if target_value is not None:
            fn += 1

    return {"tp": tp, "fp": fp, "fn": fn, "field_matches": field_matches}


def _percentage(numerator: int, denominator: int) -> float:
    return numerator / denominator * 100 if denominator else 0.0


def evaluate_configuration(
    dataset: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
    max_error_examples: int = 20,
) -> dict[str, Any]:
    """Agregasikan lima metrik penelitian untuk satu konfigurasi."""
    if len(dataset) != len(predictions):
        raise ValueError("Jumlah prediksi harus sama dengan jumlah data uji.")

    total = len(dataset)
    valid_json_count = 0
    tp = fp = fn = 0
    field_correct = {field: 0 for field in FIELDS}
    error_examples: list[dict[str, Any]] = []

    for index, (example, result) in enumerate(zip(dataset, predictions), start=1):
        valid_json = bool(result.get("valid_json"))
        prediction = result.get("prediction")
        if valid_json:
            valid_json_count += 1

        score = score_prediction(example["output"], prediction, valid_json)
        tp += score["tp"]
        fp += score["fp"]
        fn += score["fn"]
        for field, matched in score["field_matches"].items():
            field_correct[field] += int(matched)

        wrong_fields = [
            field for field, matched in score["field_matches"].items() if not matched
        ]
        if wrong_fields and len(error_examples) < max_error_examples:
            error_examples.append(
                {
                    "index": index,
                    "input": example["input"],
                    "target": dict(example["output"]),
                    "prediction": prediction,
                    "raw_output": result.get("raw_output"),
                    "valid_json": valid_json,
                    "error": result.get("error"),
                    "wrong_fields": wrong_fields,
                }
            )

    precision = _percentage(tp, tp + fp)
    recall = _percentage(tp, tp + fn)
    f1_score = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    correct_fields = sum(field_correct.values())
    total_fields = total * len(FIELDS)

    return {
        "json_validity_rate": _percentage(valid_json_count, total),
        "precision": precision,
        "recall": recall,
        "f1_score": f1_score,
        "overall_field_accuracy": _percentage(correct_fields, total_fields),
        "field_accuracy": {
            field: _percentage(field_correct[field], total) for field in FIELDS
        },
        "counts": {
            "total_examples": total,
            "valid_json": valid_json_count,
            "invalid_json": total - valid_json_count,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "correct_fields": correct_fields,
            "total_fields": total_fields,
        },
        "error_examples": error_examples,
    }


def _prediction_results(
    dataset: Sequence[Mapping[str, Any]],
    raw_records: Sequence[Mapping[str, Any]],
    reference_date: date,
    use_postprocessing: bool,
) -> list[dict[str, Any]]:
    if len(dataset) != len(raw_records):
        raise ValueError("Jumlah keluaran mentah harus sama dengan jumlah data uji.")

    results: list[dict[str, Any]] = []
    for example, record in zip(dataset, raw_records):
        raw_output = record.get("raw_output")
        inference_error = record.get("error")
        if inference_error:
            parsed = {
                "valid_json": False,
                "prediction": None,
                "error": f"Inferensi gagal: {inference_error}",
            }
        elif use_postprocessing:
            parsed = apply_system_postprocessing(
                raw_output,
                example["input"],
                reference_date,
            )
        else:
            parsed = parse_raw_json(raw_output)
        results.append({**parsed, "raw_output": raw_output})
    return results


def evaluate_from_raw_outputs(
    dataset: Sequence[Mapping[str, Any]],
    raw_outputs_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    reference_date: date,
    max_error_examples: int = 20,
) -> dict[str, dict[str, Any]]:
    """Bangun empat konfigurasi dari dua kumpulan keluaran mentah."""
    validate_evaluation_dataset(dataset)
    required_sources = {
        definition["raw_source"] for definition in CONFIGURATIONS.values()
    }
    missing_sources = required_sources - set(raw_outputs_by_model)
    if missing_sources:
        raise ValueError(
            "Keluaran mentah belum lengkap: " + ", ".join(sorted(missing_sources))
        )

    configuration_results: dict[str, dict[str, Any]] = {}
    for key, definition in CONFIGURATIONS.items():
        predictions = _prediction_results(
            dataset,
            raw_outputs_by_model[definition["raw_source"]],
            reference_date,
            use_postprocessing=definition["postprocessing"],
        )
        configuration_results[key] = evaluate_configuration(
            dataset,
            predictions,
            max_error_examples=max_error_examples,
        )
    return configuration_results


def _clear_model_memory() -> None:
    """Bersihkan cache setelah referensi model dilepas oleh pemanggil."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _run_inference_pass(
    dataset: Sequence[Mapping[str, Any]],
    tokenizer: Any,
    model: Any,
    seed: int,
    reference_date: date,
    prompt_mode: str,
) -> list[dict[str, Any]]:
    """Jalankan satu model secara deterministik untuk seluruh data uji."""
    try:
        import torch
        from transformers import set_seed
    except ImportError as exc:  # pragma: no cover - bergantung lingkungan model
        raise ModelEvaluationError(f"Dependensi model belum tersedia: {exc}") from exc

    set_seed(seed)
    model.eval()
    records: list[dict[str, Any]] = []
    for index, example in enumerate(dataset, start=1):
        if prompt_mode == "minimal":
            prompt = build_inference_prompt(example["input"], reference_date)
        elif prompt_mode == "explicit_instruction":
            prompt = build_explicit_instruction_prompt(
                tokenizer,
                example["input"],
                reference_date,
            )
        else:
            raise ValueError(f"Mode prompt evaluasi tidak dikenal: {prompt_mode}")
        try:
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                output_ids = model.generate(
                    **inputs,
                    max_new_tokens=config.MAX_NEW_TOKENS,
                    do_sample=False,
                    tokenizer=tokenizer,
                    stop_strings=list(STOP_STRINGS),
                )
            raw_output = tokenizer.decode(
                output_ids[0][inputs["input_ids"].shape[1] :],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            for stop_string in STOP_STRINGS:
                if raw_output.endswith(stop_string):
                    raw_output = raw_output[: -len(stop_string)]
                    break
        except Exception as exc:
            raise ModelEvaluationError(
                f"Inferensi gagal pada data {index}: {exc}"
            ) from exc
        records.append({"raw_output": raw_output, "error": None})
    return records


def collect_raw_model_outputs(
    dataset: Sequence[Mapping[str, Any]],
    adapter_path: str,
    seed: int,
    reference_date: date,
) -> dict[str, list[dict[str, Any]]]:
    """Hasilkan dua lintasan inferensi dengan dua kali pemuatan model."""
    try:
        from .model_utils import (
            load_base_model,
            load_model_for_inference,
            load_tokenizer,
        )

        tokenizer = load_tokenizer()
        base_model = load_base_model()
    except Exception as exc:
        raise ModelEvaluationError(f"Model dasar tidak dapat dimuat: {exc}") from exc

    try:
        base_explicit_records = _run_inference_pass(
            dataset,
            tokenizer,
            base_model,
            seed,
            reference_date,
            "explicit_instruction",
        )
    finally:
        del base_model
        _clear_model_memory()

    try:
        soft_prompt_model = load_model_for_inference(adapter_path)
    except Exception as exc:
        raise ModelEvaluationError(
            f"Model dengan Soft Prompt tidak dapat dimuat: {exc}"
        ) from exc
    try:
        soft_prompt_records = _run_inference_pass(
            dataset,
            tokenizer,
            soft_prompt_model,
            seed,
            reference_date,
            "minimal",
        )
    finally:
        del soft_prompt_model
        _clear_model_memory()

    return {
        "base_explicit": base_explicit_records,
        "soft_prompt": soft_prompt_records,
    }


def _normalized_input(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def build_dataset_audit(
    dataset: Sequence[Mapping[str, Any]],
    evaluation_path: str | Path,
    training_path: str | Path | None,
) -> dict[str, Any]:
    """Audit overlap teks dan cakupan field tanpa mengubah data evaluasi."""
    audit: dict[str, Any] = {
        "evaluation_path": str(evaluation_path),
        "total_examples": len(dataset),
        "ground_truth_policy": "Target dinilai apa adanya; null tidak diisi otomatis.",
        "date_annotation_policy": (
            "Ground truth tanggal ditulis eksplisit berdasarkan reference date tetap; "
            "evaluator tidak mengubahnya."
        ),
        "non_transaction_policy": (
            "Tidak ada penyaringan konteks otomatis; dataset harus hanya berisi "
            "transaksi dengan ground truth enam field."
        ),
    }
    if not training_path:
        audit["training_overlap"] = {
            "status": "not_checked",
            "reason": "Path data training tidak diberikan.",
        }
        return audit

    train_path = Path(training_path)
    if not train_path.exists():
        audit["training_overlap"] = {
            "status": "not_checked",
            "training_path": str(training_path),
            "reason": "File data training tidak ditemukan.",
        }
        return audit

    training_data = load_jsonl(train_path)
    training_sources = [str(train_path)]
    augmentation_path = Path(config.TRAIN_AUGMENTATION_DATA_PATH)
    if augmentation_path.is_file() and augmentation_path.resolve() != train_path.resolve():
        training_data.extend(load_jsonl(augmentation_path))
        training_sources.append(str(augmentation_path))
    training_inputs = {
        _normalized_input(row.get("input")) for row in training_data if row.get("input")
    }
    overlaps = [
        example["input"]
        for example in dataset
        if _normalized_input(example["input"]) in training_inputs
    ]
    field_coverage = {
        field: sum(
            isinstance(row.get("output"), Mapping) and field in row["output"]
            for row in training_data
        )
        for field in FIELDS
    }
    audit["training_overlap"] = {
        "status": (
            "exact_input_overlap_detected" if overlaps else "no_exact_input_overlap_detected"
        ),
        "training_path": str(training_path),
        "training_sources": training_sources,
        "training_examples": len(training_data),
        "exact_input_overlap_count": len(overlaps),
        "exact_input_overlap_examples": overlaps[:20],
        "scope_note": (
            "Audit hanya memeriksa kecocokan teks input secara tepat setelah normalisasi "
            "case dan spasi; provenance adapter dan kemiripan semantik belum terverifikasi."
        ),
        "training_target_field_coverage": field_coverage,
        "effective_training_contract": (
            "src.train memperkaya sumber legacy menjadi enam field: date diselesaikan "
            "terhadap beberapa variasi TRAIN_REFERENCE_DATE dan transaction_type "
            "diturunkan dari arah transaksi yang eksplisit; contoh ambigu dikeluarkan."
        ),
    }
    return audit


def build_report(
    dataset: Sequence[Mapping[str, Any]],
    raw_outputs_by_model: Mapping[str, Sequence[Mapping[str, Any]]],
    data_path: str | Path,
    training_path: str | Path | None,
    adapter_path: str,
    reference_date: date,
    seed: int,
    results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Susun laporan JSON yang dapat diaudit dan dipakai dalam skripsi."""
    aggregate_income_count = sum(
        is_general_income_transaction(example["input"]) for example in dataset
    )
    observed_types = sorted(
        {
            str(example["output"]["transaction_type"]).strip().casefold()
            for example in dataset
        }
    )
    raw_model_outputs = {
        source: [
            {
                "index": index,
                "input": dataset[index - 1]["input"],
                "raw_output": record.get("raw_output"),
                "error": record.get("error"),
            }
            for index, record in enumerate(records, start=1)
        ]
        for source, records in raw_outputs_by_model.items()
    }
    return {
        "status": "completed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": config.BASE_MODEL_NAME,
        "adapter_path": adapter_path,
        "dataset": build_dataset_audit(dataset, data_path, training_path),
        "evaluation_settings": {
            "reference_date": reference_date.isoformat(),
            "fields": list(FIELDS),
            "observed_transaction_types": observed_types,
            "prompts": {
                "base_llama": (
                    "Llama chat template dengan explicit instruction enam field"
                ),
                "soft_prompt": (
                    "REFERENCE_DATE: {date}\\nKalimat: {input}\\nJSON: "
                    "(format training adapter enam field)"
                ),
                "few_shot_examples": 0,
            },
            "seed": seed,
            "decoding": "deterministic (do_sample=False)",
            "max_new_tokens": config.MAX_NEW_TOKENS,
            "quantization_4bit": config.USE_4BIT,
            "soft_prompt_contract_version": config.SOFT_PROMPT_CONTRACT_VERSION,
            "raw_inference_passes": 2,
            "model_loads": 2,
            "normalization": (
                "trim/collapse whitespace and casefold strings; numeric equivalence "
                "only for quantity and total_price"
            ),
            "metric_values": "percent (0-100)",
        },
        "configuration_definitions": CONFIGURATIONS,
        "raw_model_outputs": raw_model_outputs,
        "configurations": dict(results),
        "methodology_notes": [
            (
                "Raw base explicit dan Soft Prompt masing-masing digunakan ulang untuk "
                "varian post-processing sehingga hanya ada dua inference pass."
            ),
            (
                "Base Llama memakai explicit instruction, sedangkan Soft Prompt memakai "
                "format training adapter. Karena prompt berbeda, perbandingan ini mengukur "
                "konfigurasi praktis dan bukan ablation murni adapter saja."
            ),
            (
                "Konfigurasi raw dinilai dengan json.loads pada seluruh output dan tidak "
                "mendapat ekstraksi objek, perbaikan harga/tanggal, atau classifier aturan."
            ),
            (
                "Post-processing memakai classifier transaction_type dan parse_and_validate "
                "yang sama dengan pipeline produksi."
            ),
            (
                "Validasi konteks produksi tidak dipakai untuk menyaring data eksperimen; "
                "dataset evaluasi harus sudah hanya berisi transaksi ber-ground-truth."
            ),
            (
                "Pipeline produksi memiliki fast path pemasukan agregat yang melewati Llama. "
                "Evaluator tetap mengirim semua contoh melalui lintasan model agar variabel "
                "eksperimen terkontrol; hasil contoh fast path bukan bukti Soft Prompt."
            ),
            (
                f"Dataset memuat {aggregate_income_count} contoh yang terdeteksi sebagai "
                "pemasukan agregat oleh aturan produksi."
            ),
            (
                "Training Soft Prompt efektif memakai target enam field dan prompt yang "
                "membawa REFERENCE_DATE. Sumber legacy lima field diperkaya oleh src.train; "
                "adapter lama harus dilatih ulang agar kontrak ini berlaku pada raw output."
            ),
        ],
    }


def print_summary(report: Mapping[str, Any]) -> None:
    """Tampilkan tabel metrik utama dan akurasi per field di terminal."""
    results = report["configurations"]
    label_width = 42
    print("\nHASIL EVALUASI EMPAT KONFIGURASI")
    print(
        f"{'Konfigurasi':<{label_width}} {'JSON Valid':>11} {'Precision':>10} "
        f"{'Recall':>8} {'F1-Score':>9} {'Field Acc':>10}"
    )
    print("-" * 96)
    for key, definition in CONFIGURATIONS.items():
        metrics = results[key]
        print(
            f"{definition['label']:<{label_width}} "
            f"{metrics['json_validity_rate']:>10.2f}% "
            f"{metrics['precision']:>9.2f}% "
            f"{metrics['recall']:>7.2f}% "
            f"{metrics['f1_score']:>8.2f}% "
            f"{metrics['overall_field_accuracy']:>9.2f}%"
        )

    short_labels = [definition["short_label"] for definition in CONFIGURATIONS.values()]
    print("\nAKURASI PER FIELD")
    print(f"{'Field':<19}" + "".join(f"{label:>15}" for label in short_labels))
    print("-" * (19 + 15 * len(short_labels)))
    for field in FIELDS:
        values = [results[key]["field_accuracy"][field] for key in CONFIGURATIONS]
        print(f"{field:<19}" + "".join(f"{value:>14.2f}%" for value in values))

    print("\nJUMLAH TP / FP / FN")
    for key, definition in CONFIGURATIONS.items():
        counts = results[key]["counts"]
        print(
            f"- {definition['label']}: TP={counts['tp']}, "
            f"FP={counts['fp']}, FN={counts['fn']}"
        )


def write_report(report: Mapping[str, Any], output_path: str | Path) -> Path:
    """Simpan laporan JSON dan buat direktori tujuan bila belum ada."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return path


def evaluate(
    data_path: str,
    adapter_path: str | None = None,
    reference_date: date | None = None,
    output_path: str | None = None,
    training_path: str | None = config.TRAIN_DATA_PATH,
    seed: int = 42,
    max_error_examples: int = 20,
    raw_outputs_by_model: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Jalankan evaluasi lengkap; raw_outputs dapat diinjeksi untuk unit test."""
    if reference_date is None:
        raise ValueError("reference_date wajib diisi agar evaluasi dapat direproduksi.")

    dataset = load_jsonl(data_path)
    validate_evaluation_dataset(dataset)
    adapter_path = adapter_path or config.ADAPTER_OUTPUT_DIR
    raw_outputs = raw_outputs_by_model
    if raw_outputs is None:
        validate_soft_prompt_contract(adapter_path)
        raw_outputs = collect_raw_model_outputs(
            dataset,
            adapter_path,
            seed,
            reference_date,
        )
    results = evaluate_from_raw_outputs(
        dataset,
        raw_outputs,
        reference_date,
        max_error_examples=max_error_examples,
    )
    report = build_report(
        dataset,
        raw_outputs,
        data_path,
        training_path,
        adapter_path,
        reference_date,
        seed,
        results,
    )
    print_summary(report)
    if output_path:
        saved_path = write_report(report, output_path)
        print(f"\nLaporan tersimpan di: {saved_path}")
    return report


def _reference_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "reference-date harus berformat YYYY-MM-DD dan merupakan tanggal valid"
        ) from exc


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bandingkan Llama/Soft Prompt dengan dan tanpa post-processing."
    )
    parser.add_argument("--data", default=config.EVAL_DATA_PATH)
    parser.add_argument("--adapter", default=config.ADAPTER_OUTPUT_DIR)
    parser.add_argument("--train-data", default=config.TRAIN_DATA_PATH)
    parser.add_argument("--output", default="results/evaluation_report.json")
    parser.add_argument(
        "--reference-date",
        required=True,
        type=_reference_date,
        help="Tanggal tetap YYYY-MM-DD untuk resolver tanggal post-processing.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-error-examples", type=int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        evaluate(
            args.data,
            adapter_path=args.adapter,
            reference_date=args.reference_date,
            output_path=args.output,
            training_path=args.train_data,
            seed=args.seed,
            max_error_examples=max(args.max_error_examples, 0),
        )
    except (DatasetValidationError, ModelEvaluationError, OSError, ValueError) as exc:
        print(f"Evaluasi gagal: {exc}", file=sys.stderr)
        print("Tidak ada metrik model yang dibuat atau direkayasa.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
