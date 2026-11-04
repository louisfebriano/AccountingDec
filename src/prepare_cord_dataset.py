"""Persiapan dataset CORD dari Hugging Face untuk training dan validasi nota."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import config
from .cord_dataset import (
    CORD_DATASET_SPLITS,
    build_cord_training_row,
    load_cord_dataset,
    parse_cord_ground_truth,
)
from .receipt_service import extract_receipt


SPLIT_OUTPUT_ATTRIBUTES = {
    "train": "RECEIPT_CORD_TRAIN_DATA_PATH",
    "validation": "RECEIPT_CORD_VALIDATION_DATA_PATH",
    "test": "RECEIPT_CORD_EVAL_DATA_PATH",
}


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Tulis JSONL UTF-8 setelah seluruh baris berhasil dibangun."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows
    )
    path.write_text(content + "\n", encoding="utf-8")


def _save_cord_image(
    example: Mapping[str, Any],
    directory: Path,
    index: int,
) -> Path:
    """Simpan gambar CORD hasil load_dataset ke berkas sementara untuk OCR."""
    from PIL import Image

    image = example.get("image")
    if image is None:
        raise ValueError("Contoh CORD wajib memiliki gambar nota.")
    target = directory / f"cord-{index:05d}.png"
    image.save(target, format="PNG")
    return target


def prepare_cord_split(
    dataset: Any,
    split: str,
    *,
    reference_date: date,
) -> list[dict[str, Any]]:
    """Jalankan OCR lokal untuk satu split CORD lalu bangun baris training CatatKas."""
    if split not in CORD_DATASET_SPLITS:
        raise ValueError(f"Split CORD tidak didukung: {split}")
    rows: list[dict[str, Any]] = []
    for index, example in enumerate(list(dataset[split])):
        ground_truth = parse_cord_ground_truth(example.get("ground_truth"))
        with tempfile.TemporaryDirectory(prefix="catatkas-cord-") as directory:
            image_path = _save_cord_image(example, Path(directory), index)
            parsed = extract_receipt(image_path)
        rows.append(
            build_cord_training_row(
                receipt_id=f"cord-{split}-{index + 1:05d}",
                ocr_text=str(parsed.get("ocr_text") or parsed.get("ocr_model_text") or ""),
                reference_date=reference_date,
                ground_truth=ground_truth,
            )
        )
    return rows


def build_argument_parser() -> argparse.ArgumentParser:
    """Bangun CLI persiapan dataset CORD."""
    parser = argparse.ArgumentParser(description="Persiapan dataset CORD dari Hugging Face")
    parser.add_argument(
        "--splits",
        nargs="*",
        default=list(CORD_DATASET_SPLITS),
        help="Daftar split CORD: train, validation, test.",
    )
    parser.add_argument(
        "--reference-date",
        type=lambda value: date.fromisoformat(value),
        default=date.today(),
        help="Tanggal acuan YYYY-MM-DD untuk field date nota.",
    )
    parser.add_argument(
        "--train-output",
        default=None,
        help="Output JSONL training. Default dari RECEIPT_CORD_TRAIN_DATA_PATH.",
    )
    parser.add_argument(
        "--validation-output",
        default=None,
        help="Output JSONL validasi. Default dari RECEIPT_CORD_VALIDATION_DATA_PATH.",
    )
    parser.add_argument(
        "--eval-output",
        default=None,
        help="Output JSONL evaluasi. Default dari RECEIPT_CORD_EVAL_DATA_PATH.",
    )
    return parser


def main() -> None:
    """Muat dataset CORD, jalankan OCR, lalu tulis JSONL training CatatKas."""
    args = build_argument_parser().parse_args()
    dataset = load_cord_dataset()
    outputs = {
        "train": args.train_output or getattr(config, "RECEIPT_CORD_TRAIN_DATA_PATH"),
        "validation": (
            args.validation_output
            or getattr(config, "RECEIPT_CORD_VALIDATION_DATA_PATH")
        ),
        "test": args.eval_output or getattr(config, "RECEIPT_CORD_EVAL_DATA_PATH"),
    }
    for split in args.splits:
        rows = prepare_cord_split(dataset, split, reference_date=args.reference_date)
        output_path = Path(outputs[split])
        _write_jsonl(output_path, rows)
        print(f"CORD split {split}: {len(rows)} baris -> {output_path}")


if __name__ == "__main__":
    main()
