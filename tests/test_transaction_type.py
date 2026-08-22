import unittest

from src.transaction_type import classify_transaction_type


class TransactionTypeClassifierTests(unittest.TestCase):
    def test_expense_examples(self):
        examples = (
            "Beli tepung 2 karung 250rb",
            "Restok minyak goreng 5 liter 90rb",
            "Bayar listrik toko 300rb",
        )

        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "expense")

    def test_income_examples(self):
        examples = (
            "Jual nasi goreng 10 porsi 200rb",
            "Terjual es teh 15 gelas 75rb",
            "Pelanggan bayar pesanan 150rb",
            "Pelanggan beli 2 bakmi 40rb",
            "Pemasukkan hari ini 3 juta rupiah",
            "Duit masuk 300 ribu",
            "Penghasilan hari ini 1 juta",
            "Omzet hari ini 3 juta",
            "Income hari ini 400 ribu",
        )

        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "income")

    def test_ambiguous_or_directionless_examples_are_unknown(self):
        examples = (
            "Transfer 500rb",
            "Catat beras 2 karung seharga 100rb",
            "Stok masuk 10 karung",
            "Modal usaha 5 juta",
        )

        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "unknown")

    def test_conflicting_strong_signals_are_unknown(self):
        self.assertEqual(
            classify_transaction_type("Beli tepung lalu jual kembali total 300rb"),
            "unknown",
        )

    def test_purchase_actor_changes_direction(self):
        self.assertEqual(
            classify_transaction_type("Pelanggan beli 2 bakmi 40rb"),
            "income",
        )
        self.assertEqual(
            classify_transaction_type("Saya beli 2 bakmi 40rb"),
            "expense",
        )

    def test_matching_is_case_insensitive_and_punctuation_tolerant(self):
        self.assertEqual(
            classify_transaction_type("PELANGGAN, BAYAR pesanan nasi kotak 300rb!"),
            "income",
        )
        self.assertEqual(
            classify_transaction_type("BAYAR: LISTRIK toko 300rb."),
            "expense",
        )

    def test_keyword_matching_uses_word_boundaries(self):
        self.assertEqual(
            classify_transaction_type("Penjual makanan mencatat barang 200rb"),
            "unknown",
        )


if __name__ == "__main__":
    unittest.main()
