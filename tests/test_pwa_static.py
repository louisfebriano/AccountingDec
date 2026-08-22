import struct
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src import api


client = TestClient(api.app)


class PwaStaticTests(unittest.TestCase):
    def test_home_manifest_and_service_worker_are_accessible(self):
        home = client.get("/")
        manifest = client.get("/manifest.webmanifest")
        worker = client.get("/sw.js")

        self.assertEqual(home.status_code, 200)
        self.assertIn("CatatKas", home.text)
        self.assertIn("Louis Febriano", home.text)
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.json()["display"], "standalone")
        self.assertEqual(worker.status_code, 200)
        self.assertIn("catatkas-shell-v3", worker.text)

    def test_pwa_icons_have_expected_png_dimensions(self):
        expected = {
            "/icons/icon-192.png": (192, 192),
            "/icons/icon-512.png": (512, 512),
            "/icons/icon-maskable-512.png": (512, 512),
        }
        for path, dimensions in expected.items():
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", response.content[16:24]), dimensions)

    def test_existing_api_routes_keep_priority_over_static_mount(self):
        extraction = {
            "success": True,
            "input": "pemasukan hari ini 300 ribu",
            "data": {
                "item_name": None,
                "quantity": None,
                "unit": None,
                "total_price": 300000,
                "date": "2026-08-22",
                "transaction_type": "income",
            },
            "error": None,
            "raw_output": None,
            "out_of_context": False,
        }
        with patch.object(api, "extract_transaction", return_value=extraction):
            response = client.post(
                "/extract",
                json={
                    "text": "pemasukan hari ini 300 ribu",
                    "reference_date": "2026-08-22",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["transaction_type"], "income")
        self.assertEqual(client.get("/health").json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
