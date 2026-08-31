import unittest
from unittest.mock import patch

from src import train_receipt


def receipt_output(**overrides):
    output = {
        "merchant_name": "TOKO BERKAH",
        "receipt_number": None,
        "date": "2026-08-26",
        "items": [],
        "subtotal": 53000,
        "discount": 0,
        "tax": 0,
        "service_charge": 0,
        "total": 53000,
        "transaction_type": "expense",
    }
    output.update(overrides)
    return output


def row(text="TOKO BERKAH\nTOTAL 53.000", **overrides):
    value = {
        "input": text,
        "reference_date": "2026-08-26",
        "output": receipt_output(),
    }
    value.update(overrides)
    return value


class FakeTokenizer:
    eos_token = "<eos>"

    def __init__(self):
        self.text = None
        self.kwargs = None

    def __call__(self, text, **kwargs):
        self.text = text
        self.kwargs = kwargs
        return {"input_ids": [1, 2, 3]}


class LongFakeTokenizer(FakeTokenizer):
    def __call__(self, text, **kwargs):
        super().__call__(text, **kwargs)
        return {"input_ids": list(range(9))}


class FakeCuda:
    def __init__(self, free_gib=6.0, total_gib=6.0, bf16=True):
        self.free_gib = free_gib
        self.total_gib = total_gib
        self.bf16 = bf16
        self.cache_cleared = False

    def is_available(self):
        return True

    def is_bf16_supported(self):
        return self.bf16

    def empty_cache(self):
        self.cache_cleared = True

    def mem_get_info(self):
        gib = 1024**3
        return int(self.free_gib * gib), int(self.total_gib * gib)


class FakeTorch:
    def __init__(self, **kwargs):
        self.cuda = FakeCuda(**kwargs)


class ReceiptTrainingDataTests(unittest.TestCase):
    def test_valid_row_preserves_ocr_line_breaks(self):
        prepared = train_receipt.validate_receipt_training_row(row())
        self.assertEqual(prepared["input"], "TOKO BERKAH\nTOTAL 53.000")
        self.assertEqual(prepared["output"]["transaction_type"], "expense")

    def test_invalid_target_is_rejected_without_autocorrection(self):
        missing = receipt_output()
        missing.pop("date")
        cases = (
            row(output=missing),
            row(output=receipt_output(total="53000")),
            row(output=receipt_output(transaction_type="income")),
            row(extra_field=True),
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                train_receipt.validate_receipt_training_row(value)

    def test_data_origin_is_optional_but_strict_when_provided(self):
        prepared = train_receipt.validate_receipt_training_row(
            row(data_origin="synthetic")
        )
        self.assertEqual(prepared["data_origin"], "synthetic")
        with self.assertRaises(ValueError):
            train_receipt.validate_receipt_training_row(row(data_origin="unknown"))

    def test_overlap_checks_text_receipt_id_and_template(self):
        with self.assertRaises(ValueError):
            train_receipt.assert_no_receipt_dataset_overlap(
                [row(receipt_id="receipt-1")],
                [row(text="foto lain", receipt_id="receipt-1")],
                "train",
                "validation",
            )
        with self.assertRaises(ValueError):
            train_receipt.assert_no_receipt_dataset_overlap(
                [row(template_id="template-a")],
                [row(text="foto lain", template_id="template-a")],
                "train",
                "evaluation",
            )
        with self.assertRaises(ValueError):
            train_receipt.assert_no_receipt_dataset_overlap(
                [row()],
                [row()],
                "train",
                "evaluation",
            )

    def test_training_uses_same_receipt_prompt(self):
        tokenizer = FakeTokenizer()
        tokenized = train_receipt.format_receipt_example(
            train_receipt.validate_receipt_training_row(row()),
            tokenizer,
        )
        self.assertIn("SOURCE: receipt_ocr", tokenizer.text)
        self.assertIn("TOKO BERKAH\nTOTAL 53.000", tokenizer.text)
        self.assertFalse(tokenizer.kwargs["padding"])
        self.assertFalse(tokenizer.kwargs["truncation"])
        self.assertEqual(tokenized["labels"], tokenized["input_ids"])

    def test_training_compacts_ocr_without_dropping_transaction_fields(self):
        tokenizer = FakeTokenizer()
        example = row(
            text=(
                "TOKO BERKAH\n"
                "Jl. Contoh No. 10\n"
                "NPWP 01.234.567.8-999.000\n"
                "Beras 1 kg Rp 10.000\n"
                "TOTAL Rp 10.000\n"
                "Terima kasih"
            ),
            output=receipt_output(
                items=[
                    {
                        "item_name": "Beras",
                        "quantity": 1,
                        "unit": "kg",
                        "unit_price": 10000,
                        "line_total": 10000,
                    }
                ],
                subtotal=10000,
                total=10000,
            ),
        )

        train_receipt.format_receipt_example(
            train_receipt.validate_receipt_training_row(example),
            tokenizer,
        )

        self.assertIn("TOKO BERKAH", tokenizer.text)
        self.assertIn("Beras\n1 kg Rp 10.000", tokenizer.text)
        self.assertIn("TOTAL Rp 10.000", tokenizer.text)
        self.assertNotIn("Jl. Contoh", tokenizer.text)
        self.assertNotIn("NPWP", tokenizer.text)
        self.assertNotIn("Terima kasih", tokenizer.text)

    def test_training_restores_integer_quantity_after_arrow_coercion(self):
        tokenizer = FakeTokenizer()
        example = row(
            output=receipt_output(
                items=[
                    {
                        "item_name": "Beras",
                        "quantity": 4000.0,
                        "unit": "kg",
                        "unit_price": 12500,
                        "line_total": 50000000,
                    },
                    {
                        "item_name": "Gula",
                        "quantity": 1.5,
                        "unit": "kg",
                        "unit_price": 16000,
                        "line_total": 24000,
                    },
                ]
            ),
        )

        train_receipt.format_receipt_example(
            train_receipt.validate_receipt_training_row(example),
            tokenizer,
        )

        self.assertIn('"quantity": 4000', tokenizer.text)
        self.assertNotIn('"quantity": 4000.0', tokenizer.text)
        self.assertIn('"quantity": 1.5', tokenizer.text)

    def test_training_rejects_overlong_example_without_truncating_target(self):
        with patch.object(train_receipt.config, "RECEIPT_MAX_SEQ_LENGTH", 8):
            with self.assertRaisesRegex(ValueError, "tidak dipotong diam-diam"):
                train_receipt.format_receipt_example(
                    train_receipt.validate_receipt_training_row(row()),
                    LongFakeTokenizer(),
                )

    def test_low_vram_preflight_and_precision_selection(self):
        enough = FakeTorch(free_gib=5.5, total_gib=6.0, bf16=True)
        self.assertEqual(
            train_receipt.ensure_receipt_training_memory(enough),
            (5.5, 6.0),
        )
        self.assertTrue(enough.cuda.cache_cleared)
        self.assertEqual(
            train_receipt.receipt_training_precision(enough),
            (True, False),
        )

        insufficient = FakeTorch(free_gib=2.0, total_gib=6.0, bf16=False)
        with patch.object(train_receipt.config, "RECEIPT_MIN_FREE_GPU_GB", 5.0):
            with self.assertRaisesRegex(RuntimeError, "Hentikan server API"):
                train_receipt.ensure_receipt_training_memory(insufficient)
        self.assertEqual(
            train_receipt.receipt_training_precision(insufficient),
            (False, True),
        )


if __name__ == "__main__":
    unittest.main()
