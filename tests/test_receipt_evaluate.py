import json
import unittest

from src.evaluate_receipt import evaluate_receipt_predictions
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


if __name__ == "__main__":
    unittest.main()

