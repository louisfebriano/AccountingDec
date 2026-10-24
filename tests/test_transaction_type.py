import unittest

from src.transaction_type import classify_transaction_type


class TransactionTypeClassifierTests(unittest.TestCase):
    def test_expense_examples(self):
        examples = (
            "Beli tepung 2 karung 250rb",
            "Restok minyak goreng 5 liter 90rb",
            "Ristok galon Aqua 15 botol 52.000",
            "Bayar listrik toko 300rb",
            "Kemarin stok bakso 3 bungkus totalnya 60rb",
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
            "Tanggal 27 Juni kemarin, masuk uang 600 ribu",
            "Kemarin masuk duit 250 ribu",
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
            "Modal usaha 5 juta",
        )

        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "unknown")

    def test_stock_restock_is_expense_but_stock_depletion_is_not(self):
        # "stok <barang>" berarti membeli/restock stok = pengeluaran.
        restock = (
            "Stok masuk 10 karung",
            "Stock gas LPG 2 tabung 120rb",
            "Stok telur 2 tray 60k kemarin",
        )
        for text in restock:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "expense")

        # Laporan penjualan yang menyebut kondisi stok tetap pemasukan,
        # bukan pengeluaran.
        daily_income = (
            "Stok habis, semua dagangan laku 300rb",
            "Stok masih banyak, yang laku barusan 150rb",
            "Stok sudah habis, jualan tadi laku 200rb",
            "Kemarin jualan laku 150rb, stok tinggal sedikit",
        )
        for text in daily_income:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "income")

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

    def test_cash_in_and_cash_out_verbs_determine_direction(self):
        # Pemilik usaha mencatat arus kasnya sendiri: "masuk" adalah pemasukan dan
        # "keluar" adalah pengeluaran, termasuk saat nominal mengapit kata kerja.
        income = (
            "masuk 300rb dari pelanggan",
            "dapet 150rb kemarin",
            "terima 250rb dari Bu Ani",
            "tadi ada yang order 2 gelas es teh",
            "terima pesanan 10 kotak kue 250rb",
            "orderan masuk 120rb",
        )
        for text in income:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "income")

        expense = (
            "keluar 25 ribu tadi pagi",
            "uang keluar 75rb buat bahan",
            "bayar 75rb buat listrik",
            "bayar wifi 300rb",
            "bayar 200rb untuk gaji karyawan",
            "bayar 50 ribu ke supplier",
        )
        for text in expense:
            with self.subTest(text=text):
                self.assertEqual(classify_transaction_type(text), "expense")

    def test_quantity_is_not_mistaken_for_cash_flow(self):
        # Kuantitas bukan nominal, jadi "masuk/keluar" tidak boleh aktif hanya
        # karena ada angka seperti "10 karung".
        self.assertEqual(classify_transaction_type("Stok masuk 10 karung"), "expense")
        self.assertEqual(classify_transaction_type("Barang keluar gudang"), "unknown")

    def test_owner_side_order_is_not_income(self):
        # Pesanan oleh pemilik ke supplier bukan pemasukan; hanya pesanan yang
        # datang ke usaha yang dihitung sebagai pemasukan.
        self.assertEqual(classify_transaction_type("Saya order bahan 200rb"), "unknown")

    def test_customer_payment_stays_income_despite_payment_word(self):
        self.assertEqual(
            classify_transaction_type("Pelanggan bayar pesanan 150rb"), "income"
        )
        self.assertEqual(classify_transaction_type("Pelanggan bayar 150rb"), "income")


if __name__ == "__main__":
    unittest.main()
