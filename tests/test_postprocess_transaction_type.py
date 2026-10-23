import json
import unittest
from datetime import date

from src.postprocess import parse_and_validate
from src.transaction_type import classify_transaction_type


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

    def test_clear_quantity_and_unit_override_wrong_model_details(self):
        cases = (
            ("restok santan 10bks 50rb", "Santan", 10, "bungkus"),
            ("beli gula 500gram 8rb", "Gula", 500, "gram"),
            ("beli santan 200ml 3rb", "Santan", 200, "ml"),
            ("beli cabai rawit seperempat kilo 9rb", "Cabai rawit", 0.25, "kg"),
            ("beli gas elpiji 3kg 3tbg 60rb", "Gas elpiji 3kg", 3, "tabung"),
        )

        for text, item_name, quantity, unit in cases:
            with self.subTest(text=text):
                raw_output = json.dumps(
                    {
                        "item_name": item_name,
                        "quantity": 1,
                        "unit": "karung",
                        "total_price": 1,
                        "date": None,
                    }
                )
                result = parse_and_validate(
                    raw_output,
                    user_input=text,
                    reference_date=date(2026, 8, 24),
                    transaction_type="expense",
                )

                self.assertEqual(result["data"]["quantity"], quantity)
                self.assertEqual(result["data"]["unit"], unit)

    def test_restock_sentence_with_totalnya_pattern_is_grounded_and_priced(self):
        raw_output = json.dumps(
            {
                "item_name": "Bakso",
                "quantity": 3,
                "unit": "bungkus",
                "total_price": 60000,
                "date": None,
            }
        )

        result = parse_and_validate(
            raw_output,
            user_input="Kemarin stok bakso 3 bungkus totalnya 60rb",
            reference_date=date(2026, 8, 24),
            transaction_type="expense",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["item_name"], "Bakso")
        self.assertEqual(result["data"]["quantity"], 3)
        self.assertEqual(result["data"]["unit"], "bungkus")
        self.assertEqual(result["data"]["total_price"], 60000)
        self.assertEqual(result["data"]["date"], "2026-08-23")

    def test_casual_restock_variations_are_detected_and_grounded(self):
        # Variasi kasual "stok <barang> <jumlah> <satuan> totalnya <harga>".
        # Keluaran model sengaja dibuat salah (quantity=1, unit=pcs, price=99999)
        # untuk membuktikan deteksi dan nilai akhir tidak bergantung pada tebakan
        # model: klasifikasi, harga, tanggal, jumlah, dan satuan semuanya
        # deterministik dari kalimat asli.
        variants = (
            (
                "barusan stok telur 10kg 120rb",
                "Telur", 10, "kg", 120000, "2026-08-24",
            ),
            (
                "kmrn stok gas 2 tabung totalnya 90rb",
                "Gas", 2, "tabung", 90000, "2026-08-23",
            ),
            (
                "tadi stok ayam 5kg abis 55rb",
                "Ayam", 5, "kg", 55000, "2026-08-24",
            ),
            (
                "ngisi stok bakso 3 bungkus totalnya 60rb",
                "Bakso", 3, "bungkus", 60000, "2026-08-24",
            ),
            (
                "kemarin stok minyak goreng 5ltr 60rb",
                "Minyak goreng", 5, "liter", 60000, "2026-08-23",
            ),
            (
                "stok saus sambal 15btl 75rb tadi sore",
                "Saus sambal", 15, "botol", 75000, "2026-08-24",
            ),
            (
                "beli stok terigu 5kg totalnya 45rb kemarin",
                "Terigu", 5, "kg", 45000, "2026-08-23",
            ),
            (
                "ambil stok beras 2 karung seharga 200rb",
                "Beras", 2, "karung", 200000, "2026-08-24",
            ),
            (
                "tadi pagi stok kopi 2krg 160rb",
                "Kopi", 2, "karung", 160000, "2026-08-24",
            ),
            (
                "stok gula pasir 2 karung seharga 150k kemarin",
                "Gula pasir", 2, "karung", 150000, "2026-08-23",
            ),
        )

        for text, item, quantity, unit, price, expected_date in variants:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "expense")

                raw_output = json.dumps(
                    {
                        "item_name": item,
                        "quantity": 1,
                        "unit": "pcs",
                        "total_price": 99999,
                        "date": None,
                    }
                )
                result = parse_and_validate(
                    raw_output,
                    user_input=text,
                    reference_date=date(2026, 8, 24),
                    transaction_type="expense",
                )

                self.assertTrue(result["success"])
                self.assertEqual(result["data"]["item_name"], item)
                self.assertEqual(result["data"]["quantity"], quantity)
                self.assertEqual(result["data"]["unit"], unit)
                self.assertEqual(result["data"]["total_price"], price)
                self.assertEqual(result["data"]["date"], expected_date)

    def test_outer_package_is_selected_in_both_word_orders(self):
        cases = (
            ("beli kecap 2dus isi 24btl 130rb", 2, "dus"),
            ("beli kecap isi 24 botol 1dus totalnya 130rb", 1, "dus"),
            ("beli telur 1papan isi 30 55rb", 1, "papan"),
        )

        for text, quantity, unit in cases:
            with self.subTest(text=text):
                raw_output = json.dumps(
                    {
                        "item_name": "Kecap" if "kecap" in text else "Telur",
                        "quantity": 24,
                        "unit": "botol",
                        "total_price": 1,
                        "date": None,
                    }
                )
                result = parse_and_validate(
                    raw_output,
                    user_input=text,
                    reference_date=date(2026, 8, 24),
                    transaction_type="expense",
                )

                self.assertEqual(result["data"]["quantity"], quantity)
                self.assertEqual(result["data"]["unit"], unit)

    def test_short_relative_date_is_resolved_deterministically(self):
        result = parse_and_validate(
            self.raw_transaction,
            user_input="kmrn beli tepung terigu 2 karung 250rb",
            reference_date=date(2026, 8, 24),
            transaction_type="expense",
        )

        self.assertEqual(result["data"]["date"], "2026-08-23")

    def test_undated_transaction_uses_reference_date_not_model_date(self):
        raw_output = json.dumps(
            {
                "item_name": "Daging ayam giling",
                "quantity": 2,
                "unit": "kg",
                "total_price": 50000,
                "date": "2024-01-01",
            }
        )

        result = parse_and_validate(
            raw_output,
            user_input="beli daging ayam giling 2kg 50rb buat bakso",
            reference_date=date(2026, 8, 29),
            transaction_type="expense",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["item_name"], "Daging ayam giling")
        self.assertEqual(result["data"]["quantity"], 2)
        self.assertEqual(result["data"]["unit"], "kg")
        self.assertEqual(result["data"]["total_price"], 50000)
        self.assertEqual(result["data"]["date"], "2026-08-29")

    def test_unstated_price_is_not_invented_by_model(self):
        raw_output = json.dumps(
            {
                "item_name": "Terigu",
                "quantity": 5,
                "unit": "kg",
                "total_price": 15000,
                "date": None,
            }
        )

        result = parse_and_validate(
            raw_output,
            user_input="beli terigu 5kg",
            reference_date=date(2026, 8, 24),
            transaction_type="expense",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["item_name"], "Terigu")
        self.assertEqual(result["data"]["quantity"], 5)
        self.assertEqual(result["data"]["unit"], "kg")
        # Harga tebakan model tidak dapat ditelusuri ke kalimat pengguna, jadi
        # nominal dibiarkan kosong sampai pengguna mengisinya di popup konfirmasi.
        self.assertIsNone(result["data"]["total_price"])

    def test_explicit_price_still_overrides_model_value(self):
        raw_output = json.dumps(
            {
                "item_name": "Tepung terigu",
                "quantity": 5,
                "unit": "kg",
                "total_price": 999999,
                "date": None,
            }
        )

        result = parse_and_validate(
            raw_output,
            user_input="beli terigu 5kg total 150rb",
            reference_date=date(2026, 8, 24),
            transaction_type="expense",
        )

        self.assertEqual(result["data"]["total_price"], 150000)


if __name__ == "__main__":
    unittest.main()
