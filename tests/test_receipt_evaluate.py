import json
import unittest
from unittest.mock import patch

from src import evaluate_receipt
from src.evaluate_receipt import collect_model_predictions, evaluate_receipt_predictions
from src.receipt_inference import ReceiptOutputValidationError
from tests.test_receipt_training import receipt_output


class ReceiptEvaluationTests(unittest.TestCase):
    def test_perfect_prediction_scores_one(self):
        output = receipt_output(items=[{
            "item_name": "Beras",
            "quantity": 2,
            "unit": "kg",
            "unit_price": 15000,
            "line_total": 30000,
        }])
        report = evaluate_receipt_predictions(
            [{"output": output}],
            [{"raw_output": json.dumps(output)}],
        )
        for field in (
            "json_validity_rate",
            "field_level_accuracy",
            "merchant_name_accuracy",
            "date_accuracy",
            "total_price_accuracy",
            "item_name_precision",
            "item_name_recall",
            "item_name_f1",
            "quantity_accuracy",
            "unit_accuracy",
            "unit_price_accuracy",
            "line_total_accuracy",
            "exact_transaction_match",
        ):
            self.assertEqual(report[field], 1.0, field)

    def test_invalid_json_is_counted_not_fabricated(self):
        output = receipt_output(items=[{
            "item_name": "Beras",
            "quantity": 2,
            "unit": "kg",
            "unit_price": 15000,
            "line_total": 30000,
        }])
        report = evaluate_receipt_predictions(
            [{"output": output}],
            [{"raw_output": "bukan json"}],
        )
        self.assertEqual(report["json_validity_rate"], 0.0)
        self.assertEqual(report["exact_transaction_match"], 0.0)
        self.assertEqual(report["item_name_recall"], 0.0)


class CollectModelPredictionsTests(unittest.TestCase):
    def test_invalid_model_output_is_recorded_instead_of_aborting_run(self):
        rows = [
            {"input": "NOTA A", "reference_date": "2026-08-31"},
            {"input": "NOTA B", "reference_date": "2026-08-31"},
        ]
        valid_output = json.dumps(receipt_output())
        broken_output = valid_output + " JSON JSON"
        outcomes = [
            ReceiptOutputValidationError(
                "Soft Prompt Nota tidak menghasilkan JSON valid.",
                broken_output,
            ),
            {"raw_output": valid_output},
        ]

        def fake_extract(ocr_text, reference_date):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with patch.object(evaluate_receipt, "extract_receipt_with_llama", fake_extract):
            predictions = collect_model_predictions(rows)

        self.assertEqual(
            predictions,
            [{"raw_output": broken_output}, {"raw_output": valid_output}],
        )
        report = evaluate_receipt_predictions(
            [{"output": receipt_output()}, {"output": receipt_output()}],
            predictions,
        )
        self.assertEqual(report["json_validity_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()

