import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src import prepare_receipt_dataset


def parsed_receipt():
    return {
        "ocr_raw_text": "TOKO BERKAH\nBeras 1 kg 10.000\nTOTAL 10.000",
        "ocr_text": "TOKO BERKAH\nBeras 1 kg 10.000\nTOTAL 10.000",
        "ocr_model_text": "TOKO BERKAH\nBeras\n1 kg 10.000\nTOTAL 10.000",
        "ocr_diagnostics": {"passes": 1, "selected_pass": 0, "scores": [55.0]},
        "date": "2026-08-20",
        "receipt": {
            "merchant_name": "TOKO BERKAH",
            "receipt_number": None,
            "items": [
                {
                    "item_name": "Beras",
                    "quantity": 1,
                    "unit": "kg",
                    "unit_price": 10000,
                    "line_total": 10000,
                    "confidence": 0.97,
                }
            ],
            "subtotal": 10000,
            "discount": 0,
            "tax": 0,
            "service_charge": 0,
            "total": 10000,
            "confidence": 0.96,
            "warnings": ["Periksa quantity."],
        },
    }


class PrepareReceiptDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image_dir = self.root / "image"
        self.annotation_dir = self.root / "annotations"
        self.image_path = self.image_dir / "train" / "nota-1.jpg"
        self.image_path.parent.mkdir(parents=True)
        self.image_path.write_bytes(b"fake-image-content")

    def tearDown(self):
        self.temporary.cleanup()

    def _prepare(self):
        with (
            patch.object(prepare_receipt_dataset, "validate_receipt_image") as validator,
            patch.object(
                prepare_receipt_dataset,
                "extract_receipt",
                return_value=parsed_receipt(),
            ) as extractor,
        ):
            result = prepare_receipt_dataset.prepare_receipt_annotations(
                self.image_dir,
                self.annotation_dir,
                date(2026, 8, 31),
            )
        validator.assert_called_once_with(self.image_path, "JPEG")
        extractor.assert_called_once_with(self.image_path)
        return result

    def test_discovers_supported_images_and_assigns_splits(self):
        direct = self.image_dir / "langsung.png"
        direct.write_bytes(b"png")
        evaluation = self.image_dir / "evaluation" / "nota.webp"
        evaluation.parent.mkdir(parents=True)
        evaluation.write_bytes(b"webp")
        (self.image_dir / "abaikan.txt").write_text("x", encoding="utf-8")

        discovered = prepare_receipt_dataset.discover_receipt_images(self.image_dir)

        self.assertEqual(
            [(split, path.relative_to(self.image_dir).as_posix()) for split, path in discovered],
            [
                ("evaluation", "evaluation/nota.webp"),
                ("train", "langsung.png"),
                ("train", "train/nota-1.jpg"),
            ],
        )

    def test_ocr_creates_pending_annotation_and_does_not_overwrite_it(self):
        result = self._prepare()

        self.assertEqual(len(result["created"]), 1)
        self.assertEqual(result["errors"], [])
        annotation_path = result["created"][0]
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        self.assertEqual(annotation["annotation_status"], "pending_review")
        self.assertEqual(annotation["source_image"], "train/nota-1.jpg")
        self.assertEqual(annotation["output"]["items"][0]["item_name"], "Beras")
        self.assertNotIn("confidence", annotation["output"]["items"][0])
        self.assertIn("Periksa quantity.", annotation["annotation_notes"])

        annotation["output"]["merchant_name"] = "KOREKSI MANUAL"
        annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
        with patch.object(prepare_receipt_dataset, "extract_receipt") as extractor:
            second = prepare_receipt_dataset.prepare_receipt_annotations(
                self.image_dir,
                self.annotation_dir,
                date(2026, 8, 31),
            )
        extractor.assert_not_called()
        self.assertEqual(second["skipped"], [annotation_path])
        preserved = json.loads(annotation_path.read_text(encoding="utf-8"))
        self.assertEqual(preserved["output"]["merchant_name"], "KOREKSI MANUAL")

    def test_build_compiles_only_verified_annotation_to_real_jsonl(self):
        annotation_path = self._prepare()["created"][0]
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        annotation["annotation_status"] = "verified"
        annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
        outputs = {
            split: self.root / f"receipt-real-{split}.jsonl"
            for split in prepare_receipt_dataset.RECEIPT_SPLITS
        }

        result = prepare_receipt_dataset.build_real_receipt_datasets(
            self.annotation_dir,
            self.image_dir,
            outputs,
        )

        self.assertEqual(result["counts"], {"train": 1, "validation": 0, "evaluation": 0})
        row = json.loads(outputs["train"].read_text(encoding="utf-8"))
        self.assertEqual(row["input"], annotation["ocr"]["text"])
        self.assertEqual(row["data_origin"], "real")
        self.assertEqual(row["output"]["total"], 10000)
        self.assertEqual(outputs["validation"].read_text(encoding="utf-8"), "")
        self.assertEqual(outputs["evaluation"].read_text(encoding="utf-8"), "")

    def test_build_rejects_when_only_pending_annotations_exist(self):
        self._prepare()
        outputs = {
            split: self.root / f"{split}.jsonl"
            for split in prepare_receipt_dataset.RECEIPT_SPLITS
        }

        with self.assertRaisesRegex(
            prepare_receipt_dataset.ReceiptDatasetPreparationError,
            "Belum ada anotasi verified",
        ):
            prepare_receipt_dataset.build_real_receipt_datasets(
                self.annotation_dir,
                self.image_dir,
                outputs,
            )

    def test_build_rejects_changed_source_image(self):
        annotation_path = self._prepare()["created"][0]
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        annotation["annotation_status"] = "verified"
        annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
        self.image_path.write_bytes(b"changed-image")
        outputs = {
            split: self.root / f"{split}.jsonl"
            for split in prepare_receipt_dataset.RECEIPT_SPLITS
        }

        with self.assertRaisesRegex(
            prepare_receipt_dataset.ReceiptDatasetPreparationError,
            "isi gambar berubah",
        ):
            prepare_receipt_dataset.build_real_receipt_datasets(
                self.annotation_dir,
                self.image_dir,
                outputs,
            )


if __name__ == "__main__":
    unittest.main()
