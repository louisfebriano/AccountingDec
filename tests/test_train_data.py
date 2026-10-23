import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.train import (
    TRAINING_FIELDS,
    assert_no_exact_input_overlap,
    balance_training_rows,
    build_training_reference_dates,
    load_training_rows,
    prepare_training_example,
    prepare_training_rows,
    split_training_rows,
    validate_curated_annotations,
)


REFERENCE_DATE = date(2026, 8, 24)


class TrainingDataTests(unittest.TestCase):
    def test_optional_augmentation_is_appended_without_loading_model(self):
        base_row = {"input": "base", "output": {"item_name": "Beras"}}
        augmentation_row = {"input": "augmentasi", "output": {"item_name": "Kopi"}}

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            base_path = root / "base.jsonl"
            augmentation_path = root / "augmentation.jsonl"
            base_path.write_text(json.dumps(base_row) + "\n", encoding="utf-8")
            augmentation_path.write_text(
                json.dumps(augmentation_row) + "\n",
                encoding="utf-8",
            )

            rows = load_training_rows(str(base_path), str(augmentation_path))

        self.assertEqual(rows, [base_row, augmentation_row])

    def test_missing_augmentation_keeps_base_data(self):
        base_row = {"input": "base", "output": {"item_name": "Beras"}}

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            base_path = root / "base.jsonl"
            base_path.write_text(json.dumps(base_row) + "\n", encoding="utf-8")

            rows = load_training_rows(
                str(base_path),
                str(root / "missing.jsonl"),
            )

        self.assertEqual(rows, [base_row])

    def test_null_source_date_is_resolved_against_reference_date(self):
        example = {
            "input": "Kemarin beli beras 2kg 30rb",
            "output": {
                "item_name": "Beras",
                "quantity": 2,
                "unit": "kg",
                "total_price": 30000,
                "date": None,
                "transaction_type": "expense",
            },
        }

        prepared = prepare_training_example(example, REFERENCE_DATE)

        self.assertEqual(tuple(prepared["output"]), TRAINING_FIELDS)
        self.assertEqual(prepared["output"]["date"], "2026-08-23")
        self.assertEqual(prepared["output"]["transaction_type"], "expense")

    def test_missing_source_date_defaults_to_reference_date(self):
        example = {
            "input": "Jual 3 porsi bakmi total 60rb",
            "output": {
                "item_name": "Bakmi",
                "quantity": 3,
                "unit": "porsi",
                "total_price": 60000,
                "transaction_type": "income",
            },
        }

        prepared = prepare_training_example(example, REFERENCE_DATE)

        self.assertEqual(prepared["output"]["date"], "2026-08-24")
        self.assertEqual(prepared["output"]["transaction_type"], "income")

    def test_source_row_without_valid_transaction_type_is_excluded(self):
        valid = {
            "input": "Beli beras 2kg 30rb",
            "output": {
                "item_name": "Beras",
                "total_price": 30000,
                "transaction_type": "expense",
            },
        }
        missing_type = {
            "input": "Beras 2kg 30rb",
            "output": {"item_name": "Beras", "total_price": 30000},
        }
        unknown_type = {
            "input": "Beras 2kg 30rb lagi",
            "output": {
                "item_name": "Beras",
                "total_price": 30000,
                "transaction_type": "unknown",
            },
        }

        prepared, excluded = prepare_training_rows(
            [valid, missing_type, unknown_type],
            REFERENCE_DATE,
        )

        self.assertEqual(len(prepared), 1)
        self.assertEqual(excluded, ["Beras 2kg 30rb", "Beras 2kg 30rb lagi"])
        self.assertEqual(prepared[0]["output"]["transaction_type"], "expense")

    def test_training_rows_rotate_reference_dates_instead_of_memorizing_one(self):
        rows = [
            {
                "input": f"Beli barang {index} 10rb",
                "output": {
                    "item_name": f"Barang {index}",
                    "total_price": 10000,
                    "transaction_type": "expense",
                },
            }
            for index in range(4)
        ]
        reference_dates = build_training_reference_dates(REFERENCE_DATE, 2, 7)

        prepared, excluded = prepare_training_rows(rows, reference_dates)

        self.assertEqual(excluded, [])
        self.assertEqual(
            [row["reference_date"] for row in prepared],
            ["2026-08-24", "2026-08-17", "2026-08-24", "2026-08-17"],
        )
        self.assertEqual(
            [row["output"]["date"] for row in prepared],
            ["2026-08-24", "2026-08-17", "2026-08-24", "2026-08-17"],
        )

    def test_stratified_split_and_balancing_keep_both_classes(self):
        rows = []
        for transaction_type, verb in (("income", "Jual"), ("expense", "Beli")):
            for index in range(10):
                rows.append(
                    {
                        "input": f"{verb} barang {index} 10rb",
                        "output": {"transaction_type": transaction_type},
                    }
                )

        train_rows, validation_rows = split_training_rows(rows, 0.2, 42)
        balanced_rows = balance_training_rows(
            [
                row
                for row in train_rows
                if not (
                    row["output"]["transaction_type"] == "income"
                    and row["input"].endswith("9 10rb")
                )
            ],
            42,
        )

        self.assertEqual(len(validation_rows), 4)
        self.assertEqual(
            {row["output"]["transaction_type"] for row in validation_rows},
            {"income", "expense"},
        )
        balanced_counts = {
            transaction_type: sum(
                row["output"]["transaction_type"] == transaction_type
                for row in balanced_rows
            )
            for transaction_type in ("income", "expense")
        }
        self.assertEqual(balanced_counts["income"], balanced_counts["expense"])

    def test_bundled_validation_is_balanced_consistent_and_held_out(self):
        project_root = Path(__file__).resolve().parents[1]
        validation_rows = load_training_rows(
            str(project_root / "data" / "processed" / "validation-six-fields.jsonl")
        )
        prepared, excluded = prepare_training_rows(validation_rows, REFERENCE_DATE)

        validate_curated_annotations(validation_rows, prepared)
        self.assertEqual(excluded, [])
        self.assertEqual(len(prepared), 24)
        self.assertEqual(
            {
                transaction_type: sum(
                    row["output"]["transaction_type"] == transaction_type
                    for row in prepared
                )
                for transaction_type in ("income", "expense")
            },
            {"income": 12, "expense": 12},
        )

        augmentation_rows = load_training_rows(
            str(project_root / "data" / "processed" / "train-augmentation.jsonl")
        )
        evaluation_rows = load_training_rows(
            str(project_root / "data" / "processed" / "eval-six-fields.jsonl")
        )
        assert_no_exact_input_overlap(
            augmentation_rows,
            prepared,
            "augmentation",
            "validation",
        )
        assert_no_exact_input_overlap(
            prepared,
            evaluation_rows,
            "validation",
            "evaluation",
        )

    def test_inconsistent_curated_validation_annotation_is_rejected(self):
        source = {
            "input": "Kemarin jual 2 porsi bakmi 40rb",
            "output": {
                "item_name": "Bakmi",
                "quantity": 2,
                "unit": "porsi",
                "total_price": 40000,
                "date": "2026-08-24",
                "transaction_type": "income",
            },
        }
        prepared, _ = prepare_training_rows([source], REFERENCE_DATE)

        with self.assertRaises(ValueError):
            validate_curated_annotations([source], prepared)


if __name__ == "__main__":
    unittest.main()
