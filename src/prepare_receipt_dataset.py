"""Siapkan dataset Soft Prompt Nota dari gambar dan anotasi yang diverifikasi."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import config
from .receipt_service import extract_receipt, validate_receipt_image
from .train_receipt import (
    validate_receipt_splits,
    validate_receipt_training_row,
)


ANNOTATION_SCHEMA_VERSION = 1
RECEIPT_SPLITS = ("train", "validation", "evaluation")
SUPPORTED_IMAGE_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}


class ReceiptDatasetPreparationError(ValueError):
    """Data gambar atau anotasi tidak aman digunakan untuk training."""


def parse_reference_date(value: str) -> date:
    """Parse tanggal ISO untuk CLI dengan pesan kesalahan yang ringkas."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "reference date harus berformat YYYY-MM-DD"
        ) from exc


def discover_receipt_images(image_dir: str | Path) -> list[tuple[str, Path]]:
    """Temukan gambar; file langsung di root dianggap sebagai split train."""
    root = Path(image_dir)
    if not root.exists():
        return []
    discovered: list[tuple[str, Path]] = []
    for image_path in sorted(root.rglob("*"), key=lambda value: value.as_posix().casefold()):
        if not image_path.is_file() or image_path.suffix.lower() not in SUPPORTED_IMAGE_FORMATS:
            continue
        relative = image_path.relative_to(root)
        first_part = relative.parts[0].casefold() if len(relative.parts) > 1 else ""
        split = first_part if first_part in RECEIPT_SPLITS else "train"
        discovered.append((split, image_path))
    return discovered


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized[:48] or "receipt"


def receipt_id_for_image(image_path: Path, digest: str) -> str:
    """Buat ID stabil dari nama dan isi gambar, bukan path absolut pengguna."""
    return f"real-{_safe_slug(image_path.stem)}-{digest[:12]}"


def _receipt_output_draft(parsed: Mapping[str, Any]) -> dict[str, Any]:
    receipt = parsed.get("receipt")
    receipt = receipt if isinstance(receipt, Mapping) else {}
    items = []
    for raw_item in receipt.get("items") or []:
        if not isinstance(raw_item, Mapping):
            continue
        item_name = str(raw_item.get("item_name") or "").strip()
        if not item_name:
            continue
        items.append(
            {
                "item_name": item_name,
                "quantity": raw_item.get("quantity"),
                "unit": raw_item.get("unit"),
                "unit_price": raw_item.get("unit_price"),
                "line_total": raw_item.get("line_total"),
            }
        )
    return {
        "merchant_name": receipt.get("merchant_name"),
        "receipt_number": receipt.get("receipt_number"),
        "date": parsed.get("date"),
        "items": items,
        "subtotal": receipt.get("subtotal"),
        "discount": receipt.get("discount"),
        "tax": receipt.get("tax"),
        "service_charge": receipt.get("service_charge"),
        "total": receipt.get("total"),
        "transaction_type": "expense",
    }


def build_annotation_draft(
    *,
    image_path: Path,
    image_root: Path,
    split: str,
    reference_date: date,
    parsed: Mapping[str, Any],
    digest: str,
) -> dict[str, Any]:
    """Bentuk anotasi yang wajib diperiksa manusia sebelum dikompilasi."""
    receipt = parsed.get("receipt")
    receipt = receipt if isinstance(receipt, Mapping) else {}
    warnings = [str(value) for value in receipt.get("warnings") or []]
    notes = [
        "Output masih rancangan parser; periksa terhadap gambar asli sebelum verifikasi."
    ]
    notes.extend(warnings)
    return {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "receipt_id": receipt_id_for_image(image_path, digest),
        "template_id": None,
        "data_origin": "real",
        "split": split,
        "source_image": image_path.relative_to(image_root).as_posix(),
        "source_sha256": digest,
        "reference_date": reference_date.isoformat(),
        "ocr": {
            "engine": "PaddleOCR",
            "language": config.RECEIPT_OCR_LANGUAGE,
            "raw_text": str(parsed.get("ocr_raw_text") or ""),
            "text": str(parsed.get("ocr_text") or ""),
            "model_text": str(parsed.get("ocr_model_text") or ""),
            "diagnostics": parsed.get("ocr_diagnostics") or {},
        },
        "output": _receipt_output_draft(parsed),
        "annotation_status": "pending_review",
        "annotation_notes": notes,
    }


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def prepare_receipt_annotations(
    image_dir: str | Path,
    annotation_dir: str | Path,
    reference_date: date,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Jalankan OCR sekali per gambar dan buat draft anotasi terpisah."""
    image_root = Path(image_dir)
    annotation_root = Path(annotation_dir)
    created: list[Path] = []
    skipped: list[Path] = []
    errors: list[dict[str, str]] = []

    for split, image_path in discover_receipt_images(image_root):
        try:
            digest = _sha256(image_path)
            receipt_id = receipt_id_for_image(image_path, digest)
            annotation_path = annotation_root / split / f"{receipt_id}.json"
            if annotation_path.exists() and not overwrite:
                skipped.append(annotation_path)
                continue
            validate_receipt_image(
                image_path,
                SUPPORTED_IMAGE_FORMATS[image_path.suffix.lower()],
            )
            parsed = extract_receipt(image_path)
            draft = build_annotation_draft(
                image_path=image_path,
                image_root=image_root,
                split=split,
                reference_date=reference_date,
                parsed=parsed,
                digest=digest,
            )
            _atomic_write_json(annotation_path, draft)
            created.append(annotation_path)
        except Exception as exc:
            errors.append(
                {
                    "image": image_path.relative_to(image_root).as_posix(),
                    "error": str(exc),
                }
            )
    return {"created": created, "skipped": skipped, "errors": errors}


def _load_annotation(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReceiptDatasetPreparationError(
            f"Anotasi {path} bukan JSON valid."
        ) from exc
    if not isinstance(value, dict):
        raise ReceiptDatasetPreparationError(f"Anotasi {path} harus objek JSON.")
    return value


def _safe_source_image(image_root: Path, source_image: Any) -> Path:
    if not isinstance(source_image, str) or not source_image.strip():
        raise ReceiptDatasetPreparationError("source_image wajib berupa path relatif.")
    root = image_root.resolve()
    candidate = (root / source_image).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ReceiptDatasetPreparationError(
            "source_image tidak boleh menunjuk keluar dari folder image."
        ) from exc
    return candidate


def annotation_to_training_row(
    annotation: Mapping[str, Any],
    *,
    annotation_path: Path,
    image_root: Path,
    verify_image: bool = True,
) -> dict[str, Any] | None:
    """Konversi satu anotasi verified ke kontrak JSONL training yang ketat."""
    if annotation.get("schema_version") != ANNOTATION_SCHEMA_VERSION:
        raise ReceiptDatasetPreparationError(
            f"{annotation_path}: schema_version tidak didukung."
        )
    status = annotation.get("annotation_status")
    if status == "pending_review":
        return None
    if status != "verified":
        raise ReceiptDatasetPreparationError(
            f"{annotation_path}: annotation_status harus pending_review atau verified."
        )
    split = annotation.get("split")
    if split not in RECEIPT_SPLITS:
        raise ReceiptDatasetPreparationError(
            f"{annotation_path}: split harus train, validation, atau evaluation."
        )
    receipt_id = annotation.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        raise ReceiptDatasetPreparationError(
            f"{annotation_path}: receipt_id wajib berupa string."
        )
    ocr = annotation.get("ocr")
    if not isinstance(ocr, Mapping) or not isinstance(ocr.get("text"), str):
        raise ReceiptDatasetPreparationError(
            f"{annotation_path}: ocr.text wajib berupa string."
        )
    if verify_image:
        source_path = _safe_source_image(image_root, annotation.get("source_image"))
        if not source_path.is_file():
            raise ReceiptDatasetPreparationError(
                f"{annotation_path}: gambar sumber tidak ditemukan: {source_path}"
            )
        expected_digest = annotation.get("source_sha256")
        if not isinstance(expected_digest, str) or _sha256(source_path) != expected_digest:
            raise ReceiptDatasetPreparationError(
                f"{annotation_path}: isi gambar berubah; jalankan OCR ulang."
            )
    row: dict[str, Any] = {
        "receipt_id": receipt_id.strip(),
        "data_origin": "real",
        "input": ocr["text"],
        "reference_date": annotation.get("reference_date"),
        "output": annotation.get("output"),
    }
    template_id = annotation.get("template_id")
    if template_id is not None:
        row["template_id"] = template_id
    try:
        return validate_receipt_training_row(row)
    except (TypeError, ValueError) as exc:
        raise ReceiptDatasetPreparationError(f"{annotation_path}: {exc}") from exc


def _atomic_write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def build_real_receipt_datasets(
    annotation_dir: str | Path,
    image_dir: str | Path,
    output_paths: Mapping[str, str | Path],
    *,
    verify_images: bool = True,
) -> dict[str, Any]:
    """Validasi anotasi manusia lalu tulis tiga JSONL nyata secara atomik."""
    annotation_root = Path(annotation_dir)
    image_root = Path(image_dir)
    rows_by_split: dict[str, list[dict[str, Any]]] = {
        split: [] for split in RECEIPT_SPLITS
    }
    pending = 0
    seen_receipts: dict[str, Path] = {}

    annotation_paths = sorted(
        (
            path
            for path in annotation_root.rglob("*.json")
            if path.is_file()
        ),
        key=lambda value: value.as_posix().casefold(),
    ) if annotation_root.exists() else []
    for annotation_path in annotation_paths:
        annotation = _load_annotation(annotation_path)
        row = annotation_to_training_row(
            annotation,
            annotation_path=annotation_path,
            image_root=image_root,
            verify_image=verify_images,
        )
        if row is None:
            pending += 1
            continue
        receipt_id = str(row["receipt_id"])
        previous = seen_receipts.get(receipt_id)
        if previous is not None:
            raise ReceiptDatasetPreparationError(
                f"receipt_id {receipt_id} digunakan oleh {previous} dan {annotation_path}."
            )
        seen_receipts[receipt_id] = annotation_path
        split = str(annotation["split"])
        rows_by_split[split].append(row)

    verified_count = sum(len(rows) for rows in rows_by_split.values())
    if verified_count == 0:
        raise ReceiptDatasetPreparationError(
            "Belum ada anotasi verified. Periksa output lalu ubah annotation_status."
        )
    validate_receipt_splits(
        rows_by_split["train"],
        rows_by_split["validation"],
        rows_by_split["evaluation"],
    )
    for split in RECEIPT_SPLITS:
        output_path = output_paths.get(split)
        if output_path is None:
            raise ReceiptDatasetPreparationError(f"Output split {split} belum ditentukan.")
        _atomic_write_jsonl(Path(output_path), rows_by_split[split])
    return {
        "counts": {split: len(rows_by_split[split]) for split in RECEIPT_SPLITS},
        "pending": pending,
        "outputs": {split: str(output_paths[split]) for split in RECEIPT_SPLITS},
    }


def _default_output_paths() -> dict[str, str]:
    return {
        "train": config.RECEIPT_REAL_TRAIN_DATA_PATH,
        "validation": config.RECEIPT_REAL_VALIDATION_DATA_PATH,
        "evaluation": config.RECEIPT_REAL_EVAL_DATA_PATH,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Siapkan dataset Soft Prompt Nota dari gambar nyata."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    ocr_parser = subparsers.add_parser("ocr", help="OCR gambar menjadi draft anotasi")
    ocr_parser.add_argument("--image-dir", default=config.RECEIPT_IMAGE_DATA_DIR)
    ocr_parser.add_argument("--annotation-dir", default=config.RECEIPT_ANNOTATION_DIR)
    ocr_parser.add_argument(
        "--reference-date",
        type=parse_reference_date,
        default=date.today(),
        help="Tanggal acuan YYYY-MM-DD; default tanggal lokal saat perintah dijalankan.",
    )
    ocr_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Timpa draft yang sudah ada, termasuk koreksi manualnya.",
    )

    build_parser = subparsers.add_parser(
        "build", help="Kompilasi anotasi verified menjadi JSONL"
    )
    build_parser.add_argument("--image-dir", default=config.RECEIPT_IMAGE_DATA_DIR)
    build_parser.add_argument("--annotation-dir", default=config.RECEIPT_ANNOTATION_DIR)
    build_parser.add_argument("--train-output", default=config.RECEIPT_REAL_TRAIN_DATA_PATH)
    build_parser.add_argument(
        "--validation-output",
        default=config.RECEIPT_REAL_VALIDATION_DATA_PATH,
    )
    build_parser.add_argument("--eval-output", default=config.RECEIPT_REAL_EVAL_DATA_PATH)
    build_parser.add_argument(
        "--skip-image-check",
        action="store_true",
        help="Lewati verifikasi checksum hanya jika gambar asli sengaja tidak tersedia.",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    if args.command == "ocr":
        images = discover_receipt_images(args.image_dir)
        if not images:
            print(
                "Belum ada gambar nota. Tambahkan JPEG, PNG, atau WebP ke "
                f"{args.image_dir}/train, validation, atau evaluation."
            )
            return
        result = prepare_receipt_annotations(
            args.image_dir,
            args.annotation_dir,
            args.reference_date,
            overwrite=args.overwrite,
        )
        print(
            f"Draft dibuat: {len(result['created'])}; "
            f"dilewati: {len(result['skipped'])}; gagal: {len(result['errors'])}."
        )
        for error in result["errors"]:
            print(f"- {error['image']}: {error['error']}")
        if result["errors"]:
            raise SystemExit(1)
        print(
            f"Periksa output di {args.annotation_dir}, lalu ubah "
            "annotation_status menjadi verified."
        )
        return

    result = build_real_receipt_datasets(
        args.annotation_dir,
        args.image_dir,
        {
            "train": args.train_output,
            "validation": args.validation_output,
            "evaluation": args.eval_output,
        },
        verify_images=not args.skip_image_check,
    )
    counts = result["counts"]
    print(
        "Dataset nyata dibuat: "
        f"train={counts['train']}, validation={counts['validation']}, "
        f"evaluation={counts['evaluation']}; pending={result['pending']}."
    )


if __name__ == "__main__":
    try:
        main()
    except ReceiptDatasetPreparationError as exc:
        raise SystemExit(f"Dataset nota gagal dibuat: {exc}") from None
