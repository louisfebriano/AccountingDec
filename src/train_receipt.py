"""Training PEFT Prompt Tuning khusus OCR nota.

Jalankan secara eksplisit dengan ``python -m src.train_receipt`` setelah ketiga
dataset receipt tersedia. Modul ini tidak pernah dipanggil saat startup API.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from . import config
from .prompt_utils import (
    RECEIPT_PROMPT_FORMAT,
    build_receipt_prompt,
    _dict_to_json_str,
)
from .receipt_parser import compact_receipt_ocr_text
from .receipt_schema import RECEIPT_SCHEMA_FIELDS, ReceiptExtractionSchema


RECEIPT_DATASET_KEYS = {
    "input",
    "reference_date",
    "output",
    "receipt_id",
    "template_id",
    "data_origin",
}


def load_receipt_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Muat JSONL dan berikan lokasi baris yang rusak secara eksplisit."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Dataset receipt tidak ditemukan: {source}")
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSONL {source} baris {line_number} tidak valid.") from exc
        try:
            rows.append(validate_receipt_training_row(row))
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValueError(
                f"Dataset {source} baris {line_number} tidak valid: {exc}"
            ) from exc
    if not rows:
        raise ValueError(f"Dataset receipt kosong: {source}")
    return rows


def load_optional_receipt_jsonl(path: str | Path | None) -> list[dict[str, Any]]:
    """Muat dataset tambahan jika ada; file kosong diperlakukan belum disiapkan."""
    if path is None or not str(path).strip():
        return []
    source = Path(path)
    if not source.is_file() or not source.read_text(encoding="utf-8").strip():
        return []
    return load_receipt_jsonl(source)


def validate_receipt_training_row(row: Any) -> dict[str, Any]:
    """Validasi satu contoh tanpa memperbaiki target secara otomatis."""
    if not isinstance(row, Mapping):
        raise TypeError("Baris dataset harus objek JSON.")
    unknown = set(row) - RECEIPT_DATASET_KEYS
    if unknown:
        raise ValueError("Field dataset tidak didukung: " + ", ".join(sorted(unknown)))
    missing = {"input", "reference_date", "output"} - set(row)
    if missing:
        raise ValueError("Field dataset wajib hilang: " + ", ".join(sorted(missing)))

    ocr_text = row["input"]
    if not isinstance(ocr_text, str) or not ocr_text.strip():
        raise ValueError("input OCR harus berupa string non-kosong.")
    reference_value = row["reference_date"]
    if not isinstance(reference_value, str):
        raise ValueError("reference_date harus string YYYY-MM-DD.")
    try:
        reference_date = date.fromisoformat(reference_value).isoformat()
    except ValueError as exc:
        raise ValueError("reference_date harus tanggal YYYY-MM-DD yang valid.") from exc

    validated_output = ReceiptExtractionSchema.model_validate(
        row["output"],
        strict=True,
    ).model_dump()
    prepared = {
        "input": ocr_text.replace("\r\n", "\n").replace("\r", "\n").strip(),
        "reference_date": reference_date,
        "output": validated_output,
    }
    for key in ("receipt_id", "template_id"):
        value = row.get(key)
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} harus string non-kosong jika diberikan.")
            prepared[key] = value.strip()
    data_origin = row.get("data_origin")
    if data_origin is not None:
        if data_origin not in {"synthetic", "real", "augmented"}:
            raise ValueError(
                "data_origin harus synthetic, real, atau augmented jika diberikan."
            )
        prepared["data_origin"] = data_origin
    return prepared


def _normalized_ocr(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _group_keys(row: Mapping[str, Any]) -> set[str]:
    return {
        f"{key}:{str(row[key]).strip().casefold()}"
        for key in ("receipt_id", "template_id")
        if row.get(key)
    }


def assert_no_receipt_dataset_overlap(
    first_rows: Sequence[Mapping[str, Any]],
    second_rows: Sequence[Mapping[str, Any]],
    first_name: str,
    second_name: str,
) -> None:
    """Tolak overlap OCR persis maupun receipt/template yang sama antar-split."""
    first_inputs = {_normalized_ocr(row.get("input")) for row in first_rows}
    input_overlap = first_inputs & {
        _normalized_ocr(row.get("input")) for row in second_rows
    }
    first_groups = set().union(*(_group_keys(row) for row in first_rows))
    second_groups = set().union(*(_group_keys(row) for row in second_rows))
    group_overlap = first_groups & second_groups
    if input_overlap or group_overlap:
        details = []
        if input_overlap:
            details.append(f"{len(input_overlap)} OCR text sama")
        if group_overlap:
            details.append("group sama: " + ", ".join(sorted(group_overlap)[:5]))
        raise ValueError(
            f"Data leakage antara {first_name} dan {second_name}: " + "; ".join(details)
        )


def validate_receipt_splits(
    train_rows: Sequence[Mapping[str, Any]],
    validation_rows: Sequence[Mapping[str, Any]],
    evaluation_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Periksa seluruh pasangan split sebelum model atau GPU dimuat."""
    assert_no_receipt_dataset_overlap(train_rows, validation_rows, "train", "validation")
    assert_no_receipt_dataset_overlap(train_rows, evaluation_rows, "train", "evaluation")
    assert_no_receipt_dataset_overlap(
        validation_rows,
        evaluation_rows,
        "validation",
        "evaluation",
    )


def _canonical_training_output(value: Mapping[str, Any]) -> dict[str, Any]:
    """Pulihkan tipe target yang dapat diubah oleh serialisasi Arrow Dataset."""
    output = dict(value)
    items = []
    for raw_item in output.get("items") or []:
        item = dict(raw_item)
        quantity = item.get("quantity")
        if isinstance(quantity, float) and quantity.is_integer():
            item["quantity"] = int(quantity)
        items.append(item)
    output["items"] = items
    return ReceiptExtractionSchema.model_validate(output, strict=True).model_dump()


def format_receipt_example(example: Mapping[str, Any], tokenizer: Any) -> dict[str, Any]:
    """Gabungkan prompt receipt dan target JSON memakai kontrak yang sama."""
    output = _canonical_training_output(dict(example["output"]))
    model_ocr_text = compact_receipt_ocr_text(
        str(example["input"]),
        output,
    )
    prompt = build_receipt_prompt(
        model_ocr_text,
        date.fromisoformat(str(example["reference_date"])),
    )
    target = _dict_to_json_str(output)
    tokenized = tokenizer(
        f"{prompt} {target}{tokenizer.eos_token}",
        truncation=False,
        padding=False,
    )
    sequence_length = len(tokenized["input_ids"])
    if sequence_length > config.RECEIPT_MAX_SEQ_LENGTH:
        receipt_label = str(example.get("receipt_id") or "tanpa receipt_id")
        raise ValueError(
            f"Contoh receipt {receipt_label} memiliki "
            f"{sequence_length} token, melebihi RECEIPT_MAX_SEQ_LENGTH="
            f"{config.RECEIPT_MAX_SEQ_LENGTH}. Ringkas OCR atau naikkan batas secara "
            "sadar; target JSON tidak dipotong diam-diam."
        )
    tokenized["labels"] = tokenized["input_ids"].copy()
    return tokenized


def ensure_receipt_training_memory(torch_module: Any) -> tuple[float, float] | None:
    """Gagal lebih awal jika proses lain menyisakan VRAM terlalu sedikit."""
    if not torch_module.cuda.is_available():
        return None
    torch_module.cuda.empty_cache()
    free_bytes, total_bytes = torch_module.cuda.mem_get_info()
    gib = 1024**3
    free_gib = free_bytes / gib
    total_gib = total_bytes / gib
    if free_gib < config.RECEIPT_MIN_FREE_GPU_GB:
        raise RuntimeError(
            f"VRAM bebas hanya {free_gib:.2f} GiB dari {total_gib:.2f} GiB. "
            "Hentikan server API atau proses Python lain yang sedang memuat Llama, "
            "lalu jalankan training dari proses baru. Turunkan "
            "RECEIPT_MIN_FREE_GPU_GB hanya jika penggunaan GPU lain memang disengaja."
        )
    return free_gib, total_gib


def receipt_training_precision(torch_module: Any) -> tuple[bool, bool]:
    """Pilih BF16 pada GPU yang mendukung, lalu FP16 sebagai fallback CUDA."""
    cuda_available = torch_module.cuda.is_available()
    use_bf16 = cuda_available and torch_module.cuda.is_bf16_supported()
    return use_bf16, cuda_available and not use_bf16


def build_receipt_contract(
    train_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bangun metadata audit adapter tanpa mengklaim metrik evaluasi."""
    return {
        "contract_version": config.RECEIPT_SOFT_PROMPT_CONTRACT_VERSION,
        "base_model": config.BASE_MODEL_NAME,
        "fields": list(RECEIPT_SCHEMA_FIELDS),
        "schema": ReceiptExtractionSchema.model_json_schema(),
        "prompt_format": RECEIPT_PROMPT_FORMAT,
        "training_reference_dates": sorted(
            {str(row["reference_date"]) for row in train_rows}
        ),
        "dataset_path": {
            "train": config.RECEIPT_TRAIN_DATA_PATH,
            "validation": config.RECEIPT_VALIDATION_DATA_PATH,
            "evaluation": config.RECEIPT_EVAL_DATA_PATH,
        },
        "additional_real_dataset_path": {
            "train": config.RECEIPT_REAL_TRAIN_DATA_PATH,
            "validation": config.RECEIPT_REAL_VALIDATION_DATA_PATH,
            "evaluation": config.RECEIPT_REAL_EVAL_DATA_PATH,
        },
        "data_origin_counts": {
            origin: sum(row.get("data_origin") == origin for row in train_rows)
            for origin in ("synthetic", "real", "augmented")
        },
        "seed": config.TRAIN_SEED,
    }


def main() -> None:
    """Validasi split, latih Soft Prompt Nota, lalu simpan adapter terpisah."""
    import torch

    parser = argparse.ArgumentParser(description="Training Soft Prompt Nota CatatKas")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Jalankan satu training step tanpa menyimpan adapter.",
    )
    args = parser.parse_args()

    from datasets import Dataset
    from transformers import (
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    from .model_utils import load_model_for_training, load_tokenizer

    train_rows = load_receipt_jsonl(config.RECEIPT_TRAIN_DATA_PATH)
    train_rows.extend(load_optional_receipt_jsonl(config.RECEIPT_REAL_TRAIN_DATA_PATH))
    validation_rows = load_receipt_jsonl(config.RECEIPT_VALIDATION_DATA_PATH)
    validation_rows.extend(
        load_optional_receipt_jsonl(config.RECEIPT_REAL_VALIDATION_DATA_PATH)
    )
    evaluation_rows = load_receipt_jsonl(config.RECEIPT_EVAL_DATA_PATH)
    evaluation_rows.extend(
        load_optional_receipt_jsonl(config.RECEIPT_REAL_EVAL_DATA_PATH)
    )
    validate_receipt_splits(train_rows, validation_rows, evaluation_rows)
    set_seed(config.TRAIN_SEED)

    memory = ensure_receipt_training_memory(torch)
    if memory is not None:
        print(
            f"VRAM sebelum training: {memory[0]:.2f} GiB bebas dari "
            f"{memory[1]:.2f} GiB."
        )
    use_bf16, use_fp16 = receipt_training_precision(torch)

    tokenizer = load_tokenizer()
    model = load_model_for_training(
        prompt_tuning_init_text=config.RECEIPT_PROMPT_TUNING_INIT_TEXT,
    )
    train_dataset = Dataset.from_list(list(train_rows))
    train_dataset = train_dataset.map(
        lambda example: format_receipt_example(example, tokenizer),
        remove_columns=train_dataset.column_names,
    )
    validation_dataset = Dataset.from_list(list(validation_rows))
    validation_dataset = validation_dataset.map(
        lambda example: format_receipt_example(example, tokenizer),
        remove_columns=validation_dataset.column_names,
    )

    temporary_output = tempfile.TemporaryDirectory() if args.smoke_test else None
    try:
        training_args = TrainingArguments(
            output_dir=(
                temporary_output.name
                if temporary_output is not None
                else "checkpoints/receipt"
            ),
            num_train_epochs=config.NUM_EPOCHS,
            max_steps=1 if args.smoke_test else -1,
            per_device_train_batch_size=config.RECEIPT_TRAIN_BATCH_SIZE,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=config.RECEIPT_GRADIENT_ACCUMULATION_STEPS,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            learning_rate=config.LEARNING_RATE,
            logging_steps=1 if args.smoke_test else 10,
            save_strategy="no" if args.smoke_test else "epoch",
            eval_strategy="no" if args.smoke_test else "epoch",
            prediction_loss_only=True,
            bf16=use_bf16,
            fp16=use_fp16,
            report_to="none",
            seed=config.TRAIN_SEED,
            data_seed=config.TRAIN_SEED,
        )
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=validation_dataset,
            data_collator=DataCollatorForLanguageModeling(
                tokenizer,
                mlm=False,
                pad_to_multiple_of=8,
            ),
        )
        trainer.train()
    finally:
        if temporary_output is not None:
            temporary_output.cleanup()

    if args.smoke_test:
        print("Smoke test satu training step berhasil; adapter tidak disimpan.")
        return

    output_path = Path(config.RECEIPT_ADAPTER_OUTPUT_DIR)
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)
    contract_path = output_path / config.SOFT_PROMPT_CONTRACT_FILENAME
    contract_path.write_text(
        json.dumps(build_receipt_contract(train_rows), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Soft Prompt Nota tersimpan di: {output_path}")


if __name__ == "__main__":
    main()
