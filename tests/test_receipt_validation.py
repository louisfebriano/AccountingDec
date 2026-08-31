import unittest

from src.receipt_validation import fallback_validation, validate_receipt_semantics


def semantic_receipt(**overrides):
    value = {
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
    value.update(overrides)
    return value


def rule_result():
    return {
        "date": "2026-08-26",
        "total_candidates": [30000],
        "receipt": {
            "merchant_name": "TOKO BERKAH",
            "items": [{"item_name": "Beras", "line_total": 30000}],
            "warnings": [],
        },
    }


class ReceiptSemanticValidationTests(unittest.TestCase):
    def test_retail_ppn_after_dpp_is_treated_as_included_tax(self):
        item = {
            "item_name": "RDL PAPAYA135G",
            "quantity": 1,
            "unit": None,
            "unit_price": 52900,
            "line_total": 52900,
        }
        llama = semantic_receipt(
            merchant_name="ALFAMART",
            date=None,
            items=[item],
            subtotal=52900,
            discount=2000,
            tax=5242,
            total=50900,
        )
        parsed = {
            "date": None,
            "total_candidates": [50900],
            "receipt": {
                "merchant_name": "ALFAMART",
                "items": [item],
                "warnings": [],
            },
        }

        result = validate_receipt_semantics(
            llama,
            parsed,
            "ALFAMART\nRDL PAPAYA135G 1 52,900 52,900\n"
            "TOTAL BELANJA 50,900\nPPN DPP: 47,657 PPN: 5,242",
        )

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["warnings"], [])

    def test_consistent_result_is_valid(self):
        result = validate_receipt_semantics(
            semantic_receipt(),
            rule_result(),
            "TOKO BERKAH\nBeras 2 kg 15.000\nTOTAL 30.000",
        )
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["warnings"], [])

    def test_mismatches_are_reported_without_overwriting_llama(self):
        llama = semantic_receipt(
            merchant_name="TOKO HALUSINASI",
            date="2026-08-25",
            subtotal=40000,
            total=50000,
            items=[{
                "item_name": "Barang Gaib",
                "quantity": 2,
                "unit": "kg",
                "unit_price": 15000,
                "line_total": 20000,
            }],
        )
        result = validate_receipt_semantics(
            llama,
            rule_result(),
            "TOKO BERKAH\nBeras 2 kg 15.000\nTOTAL 30.000",
        )
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertGreaterEqual(len(result["warnings"]), 5)
        self.assertEqual(result["audit"]["llama"]["total"], 50000)
        self.assertEqual(
            result["audit"]["rule_based"]["total_candidates"],
            [30000],
        )

    def test_fallback_is_always_explicit(self):
        result = fallback_validation(rule_result(), "Adapter nota belum tersedia.")
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIn("Adapter nota belum tersedia.", result["warnings"])
        self.assertIsNone(result["audit"]["llama"])

    def test_missing_model_values_are_compared_with_rule_candidates(self):
        llama = semantic_receipt(date=None, total=None, items=[])
        result = validate_receipt_semantics(
            llama,
            rule_result(),
            "TOKO BERKAH\nBeras 2 kg 15.000\nTOTAL 30.000",
        )
        combined = " ".join(result["warnings"])
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIn("Total hasil model kosong", combined)
        self.assertIn("Tanggal hasil model berbeda", combined)
        self.assertIn("Jumlah item hasil model berbeda", combined)


if __name__ == "__main__":
    unittest.main()
