import unittest

from src.number_utils import normalize_indonesian_numbers


class NormalizeIndonesianNumbersTests(unittest.TestCase):
    def test_normalizes_supported_number_scales(self):
        cases = {
            "dua": "2",
            "sepuluh": "10",
            "sebelas": "11",
            "dua belas": "12",
            "dua puluh": "20",
            "dua ratus lima puluh": "250",
            "sembilan puluh ribu": "90000",
            "seratus delapan puluh ribu": "180000",
            "dua ratus lima puluh ribu": "250000",
            "satu juta": "1000000",
            "satu juta lima ratus ribu": "1500000",
        }

        for raw_text, expected in cases.items():
            with self.subTest(raw_text=raw_text):
                self.assertEqual(normalize_indonesian_numbers(raw_text), expected)

    def test_normalizes_voice_transaction_sentence(self):
        transcript = (
            "Kemarin beli tepung terigu dua karung total "
            "dua ratus lima puluh ribu"
        )

        self.assertEqual(
            normalize_indonesian_numbers(transcript),
            "Kemarin beli tepung terigu 2 karung total 250000",
        )

    def test_normalizes_simple_fraction_when_followed_by_measurement_unit(self):
        self.assertEqual(
            normalize_indonesian_numbers(
                "beli setengah kilo dan seperempat liter"
            ),
            "beli 0.5 kilo dan 0.25 liter",
        )

    def test_keeps_spoken_decimal_and_ambiguous_fraction_unchanged(self):
        self.assertEqual(
            normalize_indonesian_numbers("harga dua koma lima juta dan tambah setengah"),
            "harga dua koma lima juta dan tambah setengah",
        )


if __name__ == "__main__":
    unittest.main()
