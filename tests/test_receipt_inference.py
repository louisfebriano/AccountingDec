import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src import config, receipt_inference
from src.prompt_utils import RECEIPT_PROMPT_FORMAT, build_receipt_prompt


def receipt_payload(**overrides):
    payload = {
        "merchant_name": "TOKO BERKAH",
        "receipt_number": None,
        "date": "2026-08-26",
        "items": [
            {
                "item_name": "Beras",
                "quantity": 2,
                "unit": "kg",
                "unit_price": 15000,
                "line_total": 30000,
            }
        ],
        "subtotal": 30000,
        "discount": 0,
        "tax": 0,
        "service_charge": 0,
        "total": 30000,
        "transaction_type": "expense",
    }
    payload.update(overrides)
    return payload


def write_adapter_contract(path):
    Path(path, "adapter_config.json").write_text(
        json.dumps({
            "peft_type": "PROMPT_TUNING",
            "base_model_name_or_path": config.BASE_MODEL_NAME,
        }),
        encoding="utf-8",
    )
    Path(path, config.SOFT_PROMPT_CONTRACT_FILENAME).write_text(
        json.dumps({
            "contract_version": config.RECEIPT_SOFT_PROMPT_CONTRACT_VERSION,
            "base_model": config.BASE_MODEL_NAME,
            "fields": list(receipt_inference.RECEIPT_SCHEMA_FIELDS),
            "prompt_format": RECEIPT_PROMPT_FORMAT,
        }),
        encoding="utf-8",
    )


class ReceiptInferenceTests(unittest.TestCase):
    def test_receipt_prompt_preserves_line_breaks_and_contract(self):
        prompt = build_receipt_prompt(
            "TOKO BERKAH\n2 Beras 30.000\nTOTAL 30.000",
            date(2026, 8, 26),
        )
        self.assertIn("SOURCE: receipt_ocr", prompt)
        self.assertIn("REFERENCE_DATE: 2026-08-26", prompt)
        self.assertIn("TOKO BERKAH\n2 Beras 30.000\nTOTAL 30.000", prompt)
        self.assertTrue(prompt.endswith("\nJSON:"))

    def test_schema_is_strict_and_requires_every_field(self):
        valid = receipt_inference.parse_receipt_model_output(
            json.dumps(receipt_payload())
        )
        self.assertEqual(valid["total"], 30000)
        self.assertEqual(valid["transaction_type"], "expense")

        cases = []
        missing = receipt_payload()
        missing.pop("tax")
        cases.append(missing)
        cases.append(receipt_payload(total="30000"))
        cases.append({**receipt_payload(), "confidence": 0.99})
        cases.append(receipt_payload(transaction_type="income"))
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(receipt_inference.ReceiptOutputValidationError):
                    receipt_inference.parse_receipt_model_output(json.dumps(payload))

        with self.assertRaises(receipt_inference.ReceiptOutputValidationError):
            receipt_inference.parse_receipt_model_output(
                json.dumps(receipt_payload()) + " penjelasan"
            )

    def test_inference_selects_receipt_adapter_without_loading_model_in_test(self):
        raw_output = json.dumps(receipt_payload())
        with tempfile.TemporaryDirectory() as directory:
            write_adapter_contract(directory)
            with (
                patch.object(config, "RECEIPT_ADAPTER_OUTPUT_DIR", directory),
                patch.object(
                    receipt_inference,
                    "generate_with_adapter",
                    return_value=raw_output,
                ) as generate,
            ):
                result = receipt_inference.extract_receipt_with_llama(
                    "TOKO BERKAH\nTOTAL 30.000",
                    date(2026, 8, 26),
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["merchant_name"], "TOKO BERKAH")
        self.assertEqual(result["raw_output"], raw_output)
        self.assertEqual(
            generate.call_args.kwargs["adapter_name"],
            receipt_inference.RECEIPT_ADAPTER_NAME,
        )
        self.assertIn("TOKO BERKAH\nTOTAL 30.000", generate.call_args.args[0])

    def test_missing_adapter_is_explicit_and_stops_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "soft-prompt-nota")
            with (
                patch.object(config, "RECEIPT_ADAPTER_OUTPUT_DIR", missing),
                patch.object(receipt_inference, "generate_with_adapter") as generate,
            ):
                with self.assertRaises(
                    receipt_inference.ReceiptAdapterUnavailableError
                ):
                    receipt_inference.extract_receipt_with_llama(
                        "TOTAL 30.000",
                        date(2026, 8, 26),
                    )
        generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()

