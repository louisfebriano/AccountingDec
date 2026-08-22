import unittest
from datetime import date
from unittest.mock import Mock, patch

from src import inference


class FakeInputIds:
    shape = (1, 2)


class FakeInputs(dict):
    def __init__(self):
        super().__init__(input_ids=FakeInputIds())

    def to(self, _device):
        return self


class FakeTokenizer:
    def __init__(self, raw_output='{"item_name":"Tepung","quantity":2}'):
        self.raw_output = raw_output

    def __call__(self, _prompt, return_tensors):
        if return_tensors != "pt":
            raise AssertionError("Unexpected tensor format")
        return FakeInputs()

    def decode(self, _token_ids, **_kwargs):
        return self.raw_output


class FakeModel:
    device = "cpu"

    def generate(self, **_kwargs):
        return [[1, 2, 3]]


class InferenceTransactionTypeTests(unittest.TestCase):
    def test_classifier_result_is_forwarded_to_postprocess(self):
        parsed_result = {
            "success": True,
            "data": {"item_name": "Tepung", "transaction_type": "expense"},
            "error": None,
        }
        parse = Mock(return_value=parsed_result)

        with (
            patch.object(
                inference,
                "get_pipeline",
                return_value=(FakeTokenizer(), FakeModel()),
            ),
            patch.object(inference, "parse_and_validate", parse),
        ):
            result = inference.extract_transaction("Beli tepung 2 karung 250rb")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["transaction_type"], "expense")
        self.assertEqual(parse.call_args.kwargs["transaction_type"], "expense")

    def test_general_income_is_extracted_without_loading_llama(self):
        examples = (
            ("pemasukan hari ini 3 juta rupiah", 3000000),
            ("pemasukkan hari ini 3 juta rupiah", 3000000),
            ("duit masuk 300 ribu", 300000),
            ("uang masuk 300 ribu", 300000),
            ("pendapatan hari ini 2 juta", 2000000),
            ("hasil penjualan hari ini 750 ribu", 750000),
            ("pemasukan hari ini 750.000", 750000),
            ("income hari ini Rp300.000", 300000),
        )

        for text, expected_price in examples:
            with self.subTest(text=text), patch.object(
                inference,
                "get_pipeline",
            ) as pipeline:
                result = inference.extract_transaction(
                    text,
                    reference_date=date(2026, 8, 21),
                )

            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["transaction_type"], "income")
            self.assertEqual(result["data"]["total_price"], expected_price)
            self.assertIsNone(result["data"]["item_name"])
            self.assertIsNone(result["data"]["quantity"])
            self.assertIsNone(result["data"]["unit"])
            pipeline.assert_not_called()

    def test_general_income_resolves_relative_date(self):
        with patch.object(inference, "get_pipeline") as pipeline:
            result = inference.extract_transaction(
                "kemarin duit masuk 300 ribu",
                reference_date=date(2026, 8, 21),
            )

        self.assertEqual(result["data"]["date"], "2026-08-20")
        pipeline.assert_not_called()

    def test_general_income_without_nominal_is_rejected_before_model(self):
        with patch.object(inference, "get_pipeline") as pipeline:
            result = inference.extract_transaction("ada pemasukan hari ini")

        self.assertFalse(result["success"])
        self.assertTrue(result["out_of_context"])
        pipeline.assert_not_called()

    def test_unknown_transaction_type_returns_error_before_model(self):
        examples = (
            "Transfer 500rb",
            "Stok masuk 10 karung",
            "Beli tepung lalu jual kembali total 300rb",
        )

        for text in examples:
            with self.subTest(text=text), patch.object(
                inference,
                "get_pipeline",
            ) as pipeline:
                result = inference.extract_transaction(text)

            self.assertFalse(result["success"])
            self.assertIsNone(result["data"])
            self.assertEqual(
                result["error"],
                inference.UNKNOWN_TRANSACTION_TYPE_ERROR,
            )
            self.assertIsNone(result["raw_output"])
            self.assertFalse(result["out_of_context"])
            pipeline.assert_not_called()

    def test_clear_item_sale_fallback_runs_after_mocked_llama(self):
        raw_output = (
            '{"item_name":"Penjualan","quantity":1,"unit":"porsi",'
            '"total_price":1,"date":null}'
        )
        with patch.object(
            inference,
            "get_pipeline",
            return_value=(FakeTokenizer(raw_output), FakeModel()),
        ):
            result = inference.extract_transaction(
                "3 bakmi laku terjual 60 ribu",
            )

        self.assertEqual(result["data"]["transaction_type"], "income")
        self.assertEqual(result["data"]["item_name"], "Bakmi")
        self.assertEqual(result["data"]["quantity"], 3)
        self.assertIsNone(result["data"]["unit"])
        self.assertEqual(result["data"]["total_price"], 60000)


if __name__ == "__main__":
    unittest.main()
