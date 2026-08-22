import io
import unittest
from contextlib import redirect_stdout
from datetime import date
from unittest.mock import patch

from src import evaluate as evaluate_module


def transaction_data(transaction_type="expense"):
    return {
        "item_name": "Tepung",
        "quantity": 2,
        "unit": "karung",
        "total_price": 250000,
        "date": "2026-08-21",
        "transaction_type": transaction_type,
    }


class EvaluateTransactionTypeTests(unittest.TestCase):
    def test_old_dataset_without_type_label_keeps_five_field_metrics(self):
        old_dataset = [
            {
                "input": "Beli tepung 2 karung 250rb",
                "output": {
                    "item_name": "Tepung",
                    "quantity": 2,
                    "unit": "karung",
                    "total_price": 250000,
                    "date": None,
                },
            }
        ]
        extraction_result = {
            "success": True,
            "data": transaction_data("expense"),
        }

        with (
            patch.object(evaluate_module, "load_jsonl", return_value=old_dataset),
            patch.object(
                evaluate_module,
                "extract_transaction",
                return_value=extraction_result,
            ),
            redirect_stdout(io.StringIO()),
        ):
            summary = evaluate_module.evaluate(
                "unused.jsonl",
                reference_date=date(2026, 8, 21),
            )

        self.assertEqual(summary["exact_match_accuracy"], 1.0)
        self.assertEqual(set(summary["field_accuracy"]), set(evaluate_module.FIELDS))
        self.assertEqual(
            summary["transaction_type_evaluation"]["labeled_examples"],
            0,
        )
        self.assertIsNone(summary["transaction_type_evaluation"]["accuracy"])

    def test_type_accuracy_uses_only_labeled_examples(self):
        labeled_dataset = [
            {
                "input": "Jual nasi 10 porsi 200rb",
                "output": {
                    **transaction_data("income"),
                    "transaction_type": "income",
                },
            }
        ]
        extraction_result = {
            "success": True,
            "data": {
                **transaction_data("income"),
                "transaction_type": "income",
            },
        }

        with (
            patch.object(evaluate_module, "load_jsonl", return_value=labeled_dataset),
            patch.object(
                evaluate_module,
                "extract_transaction",
                return_value=extraction_result,
            ),
            redirect_stdout(io.StringIO()),
        ):
            summary = evaluate_module.evaluate(
                "unused.jsonl",
                reference_date=date(2026, 8, 21),
            )

        type_evaluation = summary["transaction_type_evaluation"]
        self.assertEqual(type_evaluation["labeled_examples"], 1)
        self.assertEqual(type_evaluation["accuracy"], 1.0)
        self.assertEqual(type_evaluation["per_type"]["income"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
