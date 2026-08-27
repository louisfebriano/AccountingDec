import tempfile
import unittest
from pathlib import Path

from src.generate_receipt_synthetic_data import (
    generate_and_write,
    generate_dataset,
)
from src.train_receipt import load_receipt_jsonl, validate_receipt_splits


class ReceiptSyntheticDatasetTests(unittest.TestCase):
    def test_generator_is_deterministic_and_schema_valid(self):
        first = generate_dataset("train", 12, 42)
        second = generate_dataset("train", 12, 42)

        self.assertEqual(first, second)
        self.assertTrue(all(row["data_origin"] == "synthetic" for row in first))
        self.assertTrue(any(len(row["output"]["items"]) > 1 for row in first))

    def test_splits_use_distinct_receipts_templates_and_ocr(self):
        train = generate_dataset("train", 20, 42)
        validation = generate_dataset("validation", 8, 43)
        evaluation = generate_dataset("evaluation", 8, 44)

        validate_receipt_splits(train, validation, evaluation)
        self.assertTrue(
            {row["template_id"] for row in train}.isdisjoint(
                {row["template_id"] for row in validation + evaluation}
            )
        )

    def test_generated_files_can_be_loaded_by_training_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = generate_and_write(
                train_count=16,
                validation_count=6,
                evaluation_count=6,
                seed=42,
                output_dir=directory,
            )

            self.assertEqual(len(load_receipt_jsonl(paths["train"])), 16)
            self.assertEqual(len(load_receipt_jsonl(paths["validation"])), 6)
            self.assertEqual(len(load_receipt_jsonl(paths["evaluation"])), 6)
            self.assertEqual(
                set(Path(directory).glob("receipt-*.jsonl")),
                set(paths.values()),
            )


if __name__ == "__main__":
    unittest.main()
