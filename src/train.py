"""
Training soft prompt tuning.

Format target efektif selalu enam field. Dataset lama lima field akan diperkaya secara
deterministik dengan date dan transaction_type sebelum tokenisasi.

Jalankan: python -m src.train
"""

import json
import random
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Optional, Sequence

from . import config
from .date_utils import resolve_date
from .prompt_utils import build_inference_prompt, _dict_to_json_str
from .transaction_type import classify_transaction_type

TRAINING_FIELDS = (
    "item_name",
    "quantity",
    "unit",
    "total_price",
    "date",
    "transaction_type",
)


class AmbiguousTrainingExampleError(ValueError):
    """Contoh training tidak mempunyai arah income/expense yang jelas."""


def load_jsonl(path: str) -> list:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def load_training_rows(
    base_path: str,
    augmentation_path: Optional[str] = None,
) -> list:
    """Gabungkan data utama dan augmentasi opsional tanpa mengubah file asal."""
    rows = load_jsonl(base_path)
    if augmentation_path and Path(augmentation_path).is_file():
        rows.extend(load_jsonl(augmentation_path))
    return rows


def prepare_training_example(example: Mapping, reference_date: date) -> dict:
    """Ubah contoh legacy menjadi target enam field yang konsisten."""
    user_input = example.get("input")
    source_output = example.get("output")
    if not isinstance(user_input, str) or not user_input.strip():
        raise ValueError("Input training harus berupa teks non-kosong.")
    if not isinstance(source_output, Mapping):
        raise ValueError("Output training harus berupa objek JSON.")

    transaction_type = classify_transaction_type(user_input)
    if transaction_type == "unknown":
        raise AmbiguousTrainingExampleError(
            "Arah transaksi training ambigu; tambahkan konteks beli/restok atau jual."
        )

    resolved_date = resolve_date(user_input, reference_date)
    target = {
        "item_name": source_output.get("item_name"),
        "quantity": source_output.get("quantity"),
        "unit": source_output.get("unit"),
        "total_price": source_output.get("total_price"),
        "date": resolved_date or reference_date.isoformat(),
        "transaction_type": transaction_type,
    }
    return {
        "input": user_input.strip(),
        "reference_date": reference_date.isoformat(),
        "output": target,
    }


def build_training_reference_dates(
    anchor_date: date,
    variants: int,
    step_days: int,
) -> list[date]:
    """Bangun beberapa reference date agar adapter tidak menghafal satu tanggal."""
    if variants < 1:
        raise ValueError("TRAIN_REFERENCE_DATE_VARIANTS minimal 1.")
    if step_days < 1:
        raise ValueError("TRAIN_REFERENCE_DATE_STEP_DAYS minimal 1.")
    return [
        anchor_date - timedelta(days=index * step_days)
        for index in range(variants)
    ]


def prepare_training_rows(
    rows: Sequence[Mapping],
    reference_dates: date | Sequence[date],
) -> tuple[list[dict], list[str]]:
    """Siapkan contoh valid dan laporkan input ambigu yang dikeluarkan."""
    references = (
        [reference_dates]
        if isinstance(reference_dates, date)
        else list(reference_dates)
    )
    if not references:
        raise ValueError("Daftar reference date training tidak boleh kosong.")

    prepared: list[dict] = []
    excluded: list[str] = []
    for index, row in enumerate(rows):
        try:
            prepared.append(
                prepare_training_example(
                    row,
                    references[index % len(references)],
                )
            )
        except AmbiguousTrainingExampleError:
            excluded.append(str(row.get("input", "")))
    return prepared, excluded


def validate_curated_annotations(
    source_rows: Sequence[Mapping],
    prepared_rows: Sequence[Mapping],
) -> None:
    """Pastikan validation enam field tidak diam-diam dikoreksi saat dimuat."""
    if len(source_rows) != len(prepared_rows):
        raise ValueError("Validation mengandung contoh ambigu atau tidak valid.")
    for index, (source, prepared) in enumerate(
        zip(source_rows, prepared_rows),
        start=1,
    ):
        source_output = source.get("output")
        if not isinstance(source_output, Mapping):
            raise ValueError(f"Output validation baris {index} bukan objek JSON.")
        missing = [field for field in TRAINING_FIELDS if field not in source_output]
        if missing:
            raise ValueError(
                f"Validation baris {index} tidak memiliki field: "
                + ", ".join(missing)
            )
        for field in TRAINING_FIELDS:
            if source_output[field] != prepared["output"][field]:
                raise ValueError(
                    f"Anotasi validation baris {index} tidak konsisten pada {field}."
                )


def assert_no_exact_input_overlap(
    first_rows: Sequence[Mapping],
    second_rows: Sequence[Mapping],
    first_name: str,
    second_name: str,
) -> None:
    """Tolak leakage teks input persis antar-split."""
    def normalize(value: object) -> str:
        return re.sub(r"\s+", " ", str(value).strip()).casefold()

    first_inputs = {normalize(row.get("input")) for row in first_rows}
    overlap = sorted(
        first_inputs
        & {normalize(row.get("input")) for row in second_rows}
    )
    if overlap:
        raise ValueError(
            f"Terdapat {len(overlap)} exact overlap antara {first_name} dan "
            f"{second_name}: " + " | ".join(overlap[:5])
        )


def split_training_rows(
    rows: Sequence[dict],
    validation_ratio: float,
    seed: int,
) -> tuple[list[dict], list[dict]]:
    """Buat split validation terstratifikasi tanpa memakai dataset evaluasi akhir."""
    if not 0 < validation_ratio < 1:
        raise ValueError("TRAIN_VALIDATION_RATIO harus lebih dari 0 dan kurang dari 1.")

    randomizer = random.Random(seed)
    groups: dict[str, list[dict]] = {"income": [], "expense": []}
    for row in rows:
        groups[row["output"]["transaction_type"]].append(row)

    train_rows: list[dict] = []
    validation_rows: list[dict] = []
    for transaction_type, group in groups.items():
        if not group:
            raise ValueError(
                f"Data training tidak memiliki contoh {transaction_type}."
            )
        shuffled = list(group)
        randomizer.shuffle(shuffled)
        validation_count = max(1, round(len(shuffled) * validation_ratio))
        validation_count = min(validation_count, len(shuffled) - 1)
        validation_rows.extend(shuffled[:validation_count])
        train_rows.extend(shuffled[validation_count:])

    randomizer.shuffle(train_rows)
    randomizer.shuffle(validation_rows)
    return train_rows, validation_rows


def balance_training_rows(rows: Sequence[dict], seed: int) -> list[dict]:
    """Oversample kelas minoritas pada split training saja."""
    randomizer = random.Random(seed)
    groups: dict[str, list[dict]] = {"income": [], "expense": []}
    for row in rows:
        groups[row["output"]["transaction_type"]].append(row)
    if not all(groups.values()):
        raise ValueError("Balancing membutuhkan contoh income dan expense.")

    target_size = max(len(group) for group in groups.values())
    balanced: list[dict] = []
    for group in groups.values():
        shuffled = list(group)
        randomizer.shuffle(shuffled)
        balanced.extend(
            shuffled[index % len(shuffled)] for index in range(target_size)
        )
    randomizer.shuffle(balanced)
    return balanced


def format_example(example: dict, tokenizer):
    """Gabungkan prompt Soft Prompt dan target enam field."""
    reference_date = date.fromisoformat(example["reference_date"])
    prompt = build_inference_prompt(example["input"], reference_date)
    target = _dict_to_json_str(example["output"])
    full_text = f"{prompt} {target}{tokenizer.eos_token}"

    tokenized = tokenizer(
        full_text,
        truncation=True,
        max_length=config.MAX_SEQ_LENGTH,
        padding="max_length",
    )
    tokenized["labels"] = tokenized["input_ids"].copy()
    return tokenized


def main():
    from datasets import Dataset
    from transformers import (
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )
    from .model_utils import load_model_for_training, load_tokenizer

    reference_date = date.fromisoformat(config.TRAIN_REFERENCE_DATE)
    reference_dates = build_training_reference_dates(
        reference_date,
        config.TRAIN_REFERENCE_DATE_VARIANTS,
        config.TRAIN_REFERENCE_DATE_STEP_DAYS,
    )
    source_rows = load_training_rows(
        config.TRAIN_DATA_PATH,
        config.TRAIN_AUGMENTATION_DATA_PATH,
    )
    prepared_rows, excluded_rows = prepare_training_rows(
        source_rows,
        reference_dates,
    )
    if excluded_rows:
        print(
            f"Mengeluarkan {len(excluded_rows)} contoh training ambigu: "
            + " | ".join(excluded_rows)
        )

    validation_path = Path(config.TRAIN_VALIDATION_DATA_PATH)
    if validation_path.is_file():
        validation_source_rows = load_jsonl(str(validation_path))
        eval_raw, validation_excluded = prepare_training_rows(
            validation_source_rows,
            reference_date,
        )
        if validation_excluded:
            raise ValueError(
                "Validation mengandung arah transaksi ambigu: "
                + " | ".join(validation_excluded)
            )
        validate_curated_annotations(validation_source_rows, eval_raw)
        assert_no_exact_input_overlap(
            prepared_rows,
            eval_raw,
            "training",
            "validation",
        )
        train_raw = prepared_rows
        validation_source = str(validation_path)
    else:
        train_raw, eval_raw = split_training_rows(
            prepared_rows,
            config.TRAIN_VALIDATION_RATIO,
            config.TRAIN_SEED,
        )
        validation_source = "stratified split dari training"

    final_evaluation_path = Path(config.EVAL_DATA_PATH)
    if final_evaluation_path.is_file():
        final_evaluation_rows = load_jsonl(str(final_evaluation_path))
        assert_no_exact_input_overlap(
            train_raw,
            final_evaluation_rows,
            "training",
            "final evaluation",
        )
        assert_no_exact_input_overlap(
            eval_raw,
            final_evaluation_rows,
            "validation",
            "final evaluation",
        )
    if config.BALANCE_TRANSACTION_TYPES:
        train_raw = balance_training_rows(train_raw, config.TRAIN_SEED)

    train_type_counts = {
        transaction_type: sum(
            row["output"]["transaction_type"] == transaction_type
            for row in train_raw
        )
        for transaction_type in ("income", "expense")
    }
    validation_type_counts = {
        transaction_type: sum(
            row["output"]["transaction_type"] == transaction_type
            for row in eval_raw
        )
        for transaction_type in ("income", "expense")
    }
    print(
        "Kontrak Soft Prompt v"
        f"{config.SOFT_PROMPT_CONTRACT_VERSION}: reference_dates="
        f"{[value.isoformat() for value in reference_dates]}, "
        f"train={train_type_counts}, validation={validation_type_counts}, "
        f"validation_source={validation_source}"
    )

    tokenizer = load_tokenizer()
    model = load_model_for_training()

    train_dataset = Dataset.from_list(train_raw)
    train_dataset = train_dataset.map(
        lambda ex: format_example(ex, tokenizer),
        remove_columns=train_dataset.column_names,
    )

    eval_dataset = Dataset.from_list(eval_raw)
    eval_dataset = eval_dataset.map(
        lambda ex: format_example(ex, tokenizer),
        remove_columns=eval_dataset.column_names,
    )

    training_args = TrainingArguments(
        output_dir="checkpoints",
        num_train_epochs=config.NUM_EPOCHS,
        per_device_train_batch_size=config.BATCH_SIZE,
        gradient_accumulation_steps=4,  # simulasikan batch lebih besar tanpa nambah VRAM
        gradient_checkpointing=True,
        learning_rate=config.LEARNING_RATE,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch",
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    trainer.train()
    model.save_pretrained(config.ADAPTER_OUTPUT_DIR)
    tokenizer.save_pretrained(config.ADAPTER_OUTPUT_DIR)
    contract_path = (
        Path(config.ADAPTER_OUTPUT_DIR) / config.SOFT_PROMPT_CONTRACT_FILENAME
    )
    contract_path.write_text(
        json.dumps(
            {
                "contract_version": config.SOFT_PROMPT_CONTRACT_VERSION,
                "base_model": config.BASE_MODEL_NAME,
                "fields": list(TRAINING_FIELDS),
                "prompt_format": (
                    "REFERENCE_DATE: {YYYY-MM-DD}\\nKalimat: {input}\\nJSON:"
                ),
                "training_reference_dates": [
                    value.isoformat() for value in reference_dates
                ],
                "balanced_transaction_types": config.BALANCE_TRANSACTION_TYPES,
                "validation_source": validation_source,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Soft prompt adapter tersimpan di: {config.ADAPTER_OUTPUT_DIR}")

    
if __name__ == "__main__":
    main()
