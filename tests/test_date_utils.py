import unittest
from datetime import date

from src.date_utils import resolve_date


class DateUtilsTests(unittest.TestCase):
    def setUp(self):
        self.reference_date = date(2026, 8, 25)

    def test_explicit_date_wins_over_kemarin(self):
        resolved = resolve_date(
            "tanggal 27 juni kemarin, masuk uang 600 ribu",
            self.reference_date,
        )
        self.assertEqual(resolved, "2026-06-27")

    def test_hari_minggu_kemarin_means_previous_sunday(self):
        resolved = resolve_date(
            "hari minggu kemarin beli gas 3kg 3 tabung 60 ribu",
            self.reference_date,
        )
        self.assertEqual(resolved, "2026-08-23")

    def test_same_weekday_means_previous_week(self):
        self.assertEqual(
            resolve_date("hari selasa kemarin bayar listrik 100 ribu", self.reference_date),
            "2026-08-18",
        )

    def test_minggu_kemarin_without_hari_keeps_week_ago_meaning(self):
        self.assertEqual(
            resolve_date("minggu kemarin beli gas 60 ribu", self.reference_date),
            "2026-08-18",
        )


if __name__ == "__main__":
    unittest.main()
