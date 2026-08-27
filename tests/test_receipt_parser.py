import unittest

from src.receipt_parser import (
    extract_rupiah_values,
    parse_receipt,
    parse_receipt_date,
    parse_rupiah,
)


def line(text, confidence=0.95):
    return {"text": text, "confidence": confidence}


class ReceiptParserTests(unittest.TestCase):
    def test_normalizes_common_indonesian_rupiah_formats(self):
        for raw in ("Rp 25.000", "Rp25.000", "25.000", "25,000", "25 000", "25000"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_rupiah(raw), 25000)
        self.assertEqual(extract_rupiah_values("TOTAL 25000"), [25000])

    def test_extracts_supported_dates_without_confusing_time(self):
        expected = "2026-08-26"
        for raw in (
            "26/08/2026",
            "26-08-2026",
            "26.08.2026",
            "2026-08-26",
            "26 Agu 2026",
            "26 Agustus 2026",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(parse_receipt_date(raw), expected)
        self.assertIsNone(parse_receipt_date("Jam 18:30 Telp 08123456789"))

    def test_total_priority_ignores_cash_and_change(self):
        result = parse_receipt([
            line("TOKO MAKMUR"),
            line("TOTAL PEMBAYARAN Rp180.000"),
            line("TUNAI Rp200.000"),
            line("KEMBALIAN Rp20.000"),
            line("26 Agustus 2026"),
        ])
        self.assertEqual(result["receipt"]["total"], 180000)
        self.assertEqual(result["total_candidates"], [180000])
        self.assertEqual(result["date"], "2026-08-26")

    def test_groups_multiline_item_and_reconciles_totals(self):
        result = parse_receipt([
            line("TOKO MAKMUR"),
            line("MINYAK GORENG"),
            line("2 x 20.000"),
            line("40.000"),
            line("BERAS"),
            line("2 kg x 15.000"),
            line("30.000"),
            line("SUBTOTAL 70.000"),
            line("DISKON 5.000"),
            line("PAJAK 10.000"),
            line("SERVICE 5.000"),
            line("GRAND TOTAL 80.000"),
        ])
        receipt = result["receipt"]
        self.assertEqual(len(receipt["items"]), 2)
        self.assertEqual(receipt["items"][0]["item_name"], "MINYAK GORENG")
        self.assertEqual(receipt["items"][0]["line_total"], 40000)
        self.assertEqual(receipt["items"][1]["unit"], "kg")
        self.assertEqual(receipt["subtotal"], 70000)
        self.assertEqual(receipt["total"], 80000)
        self.assertNotIn("Total akhir perlu diperiksa kembali.", receipt["warnings"])

    def test_extracts_tabular_items_and_preserves_ambiguous_values(self):
        result = parse_receipt([
            line("RESTORAN&PEMANCINGAN Karawang, 28-10-2012"),
            line("Banyak NamaBarang Harga Jumlah"),
            line("nya Satuan"),
            line("1 Gurame goreng Rp.65.00"),
            line("1 nasi Putih Rp.12.000"),
            line("Kelapa muda 2p.7.000"),
            line("PERHATIAN: Jumlah Rp Rp.84.000"),
        ])

        items = result["receipt"]["items"]
        self.assertEqual([item["item_name"] for item in items], [
            "Gurame goreng",
            "nasi Putih",
            "Kelapa muda",
        ])
        self.assertEqual(items[0]["quantity"], 1)
        self.assertIsNone(items[0]["unit_price"])
        self.assertEqual(items[1]["unit_price"], 12000)
        self.assertEqual(items[1]["line_total"], 12000)
        self.assertIsNone(items[2]["quantity"])
        self.assertEqual(items[2]["unit_price"], 7000)
        self.assertIsNone(items[2]["line_total"])
        self.assertIn(
            "Sebagian rincian barang tidak lengkap. Periksa quantity dan nominal pada nota.",
            result["receipt"]["warnings"],
        )

    def test_does_not_treat_address_with_price_as_item_without_table(self):
        result = parse_receipt([
            line("TOKO MAKMUR"),
            line("Alamat cabang Rp.12.000"),
            line("TOTAL Rp.12.000"),
        ])
        self.assertEqual(result["receipt"]["items"], [])

    def test_mismatch_and_ambiguous_total_create_warnings_without_mutation(self):
        result = parse_receipt([
            line("SUBTOTAL 100.000"),
            line("PAJAK 10.000"),
            line("TOTAL 125.000"),
            line("GRAND TOTAL 120.000"),
        ])
        receipt = result["receipt"]
        self.assertEqual(receipt["total"], 120000)
        self.assertEqual(result["total_candidates"], [120000, 125000])
        self.assertIn("Beberapa kandidat total ditemukan. Pilih total akhir yang benar.", receipt["warnings"])
        self.assertIn("Total akhir perlu diperiksa kembali.", receipt["warnings"])

    def test_missing_date_and_total_remain_null(self):
        result = parse_receipt([line("TOKO TANPA TOTAL"), line("NASI GORENG")])
        self.assertIsNone(result["date"])
        self.assertIsNone(result["receipt"]["total"])
        self.assertTrue(result["receipt"]["warnings"])

    def test_low_confidence_is_reported(self):
        result = parse_receipt([line("TOTAL 50.000", confidence=0.2)])
        self.assertIn(
            "Keyakinan OCR rendah. Periksa kembali seluruh hasil nota.",
            result["receipt"]["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
