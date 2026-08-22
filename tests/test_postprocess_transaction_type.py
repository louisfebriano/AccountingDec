import json
import unittest
from datetime import date

from src.postprocess import parse_and_validate


class PostprocessTransactionTypeTests(unittest.TestCase):
    def setUp(self):
        self.raw_transaction = json.dumps(
            {
                "item_name": "Tepung terigu",
                "quantity": 2,
                "unit": "karung",
                "total_price": 250000,
                "date": None,
            }
        )

    def test_old_model_output_without_transaction_type_is_supported(self):
        result = parse_and_validate(
            self.raw_transaction,
            user_input="Beli tepung terigu 2 karung total 250rb",
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["transaction_type"], "expense")

    def test_sale_fallback_extracts_quantity_before_item_without_inventing_unit(self):
        result = parse_and_validate(
            self.raw_transaction,
            user_input="3 bakmi laku terjual 60 ribu",
            reference_date=date(2026, 8, 21),
            transaction_type="income",
        )

        self.assertEqual(result["data"]["item_name"], "Bakmi")
        self.assertEqual(result["data"]["quantity"], 3)
        self.assertIsNone(result["data"]["unit"])
        self.assertEqual(result["data"]["total_price"], 60000)

    def test_sale_fallback_keeps_explicit_unit(self):
        result = parse_and_validate(
            self.raw_transaction,
            user_input="3 porsi bakmi laku terjual 60 ribu",
            reference_date=date(2026, 8, 21),
            transaction_type="income",
        )

        self.assertEqual(result["data"]["item_name"], "Bakmi")
        self.assertEqual(result["data"]["quantity"], 3)
        self.assertEqual(result["data"]["unit"], "porsi")

    def test_sale_fallback_supports_terjual_before_quantity(self):
        result = parse_and_validate(
            self.raw_transaction,
            user_input="terjual 5 es teh 25 ribu",
            reference_date=date(2026, 8, 21),
            transaction_type="income",
        )

        self.assertEqual(result["data"]["item_name"], "Es teh")
        self.assertEqual(result["data"]["quantity"], 5)
        self.assertIsNone(result["data"]["unit"])
        self.assertEqual(result["data"]["total_price"], 25000)

    def test_sale_fallback_supports_other_clear_word_orders(self):
        cases = (
            ("jual bakmi 3 porsi 60 ribu", "Bakmi", 3, "porsi", 60000),
            ("bakmi laku 3 porsi total 60 ribu", "Bakmi", 3, "porsi", 60000),
            ("pelanggan beli 2 bakmi 40 ribu", "Bakmi", 2, None, 40000),
            ("hari ini 10 nasi goreng laku 200 ribu", "Nasi goreng", 10, None, 200000),
            ("jual bakmi 3 porsi 60000", "Bakmi", 3, "porsi", 60000),
            ("terjual 5 es teh 25000", "Es teh", 5, None, 25000),
        )

        for text, item_name, quantity, unit, total_price in cases:
            with self.subTest(text=text):
                result = parse_and_validate(
                    self.raw_transaction,
                    user_input=text,
                    reference_date=date(2026, 8, 21),
                    transaction_type="income",
                )

                self.assertEqual(result["data"]["item_name"], item_name)
                self.assertEqual(result["data"]["quantity"], quantity)
                self.assertEqual(result["data"]["unit"], unit)
                self.assertEqual(result["data"]["total_price"], total_price)

    def test_default_transaction_type_is_unknown(self):
        result = parse_and_validate(
            self.raw_transaction,
            reference_date=date(2026, 8, 21),
        )

        self.assertEqual(result["data"]["transaction_type"], "unknown")
        self.assertIsNone(result["data"]["item_name"])
        self.assertIsNone(result["data"]["quantity"])
        self.assertIsNone(result["data"]["unit"])

    def test_rule_based_value_overrides_model_value(self):
        raw_with_model_type = json.dumps(
            {
                "item_name": "Tepung terigu",
                "quantity": 2,
                "unit": "karung",
                "total_price": 250000,
                "date": None,
                "transaction_type": "income",
            }
        )

        result = parse_and_validate(
            raw_with_model_type,
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertEqual(result["data"]["transaction_type"], "expense")

    def test_unmentioned_item_quantity_and_unit_are_always_null(self):
        hallucinated_output = json.dumps(
            {
                "item_name": "Tepung terigu",
                "quantity": 2,
                "unit": "karung",
                "total_price": 250000,
                "date": None,
            }
        )

        result = parse_and_validate(
            hallucinated_output,
            user_input="Bayar tagihan toko total 250rb",
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertIsNone(result["data"]["item_name"])
        self.assertIsNone(result["data"]["quantity"])
        self.assertIsNone(result["data"]["unit"])

    def test_only_unmentioned_optional_fields_are_nulled(self):
        result = parse_and_validate(
            self.raw_transaction,
            user_input="Beli tepung terigu total 250rb",
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertEqual(result["data"]["item_name"], "Tepung terigu")
        self.assertIsNone(result["data"]["quantity"])
        self.assertIsNone(result["data"]["unit"])

    def test_quantity_and_unit_can_exist_without_item_name(self):
        result = parse_and_validate(
            self.raw_transaction,
            user_input="Beli 2 karung total 250rb",
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertIsNone(result["data"]["item_name"])
        self.assertEqual(result["data"]["quantity"], 2)
        self.assertEqual(result["data"]["unit"], "karung")

    def test_item_size_is_not_invented_as_quantity_or_unit(self):
        product_size_output = json.dumps(
            {
                "item_name": "Gas 3kg",
                "quantity": 3,
                "unit": "kg",
                "total_price": 40000,
                "date": None,
            }
        )

        result = parse_and_validate(
            product_size_output,
            user_input="Beli gas 3kg total 40rb",
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertEqual(result["data"]["item_name"], "Gas 3kg")
        self.assertIsNone(result["data"]["quantity"])
        self.assertIsNone(result["data"]["unit"])

    def test_missing_optional_keys_default_to_null(self):
        result = parse_and_validate(
            '{"total_price":250000,"date":null}',
            user_input="Bayar tagihan toko total 250rb",
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertTrue(result["success"])
        self.assertIsNone(result["data"]["item_name"])
        self.assertIsNone(result["data"]["quantity"])
        self.assertIsNone(result["data"]["unit"])

    def test_date_number_is_not_treated_as_quantity(self):
        output_with_hallucinated_quantity = json.dumps(
            {
                "item_name": "Listrik toko",
                "quantity": 2,
                "unit": "bulan",
                "total_price": 300000,
                "date": "2026-08-02",
            }
        )

        result = parse_and_validate(
            output_with_hallucinated_quantity,
            user_input="Tanggal 2 Agustus bayar listrik toko 300rb",
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertEqual(result["data"]["item_name"], "Listrik toko")
        self.assertIsNone(result["data"]["quantity"])
        self.assertIsNone(result["data"]["unit"])

    def test_decimal_quantity_and_abbreviated_unit_remain_grounded(self):
        decimal_output = json.dumps(
            {
                "item_name": "Minyak goreng",
                "quantity": 1.5,
                "unit": "liter",
                "total_price": 30000,
                "date": None,
            }
        )

        result = parse_and_validate(
            decimal_output,
            user_input="Beli minyak goreng 1,5 ltr total 30rb",
            reference_date=date(2026, 8, 21),
            transaction_type="expense",
        )

        self.assertEqual(result["data"]["item_name"], "Minyak goreng")
        self.assertEqual(result["data"]["quantity"], 1.5)
        self.assertEqual(result["data"]["unit"], "liter")


if __name__ == "__main__":
    unittest.main()
