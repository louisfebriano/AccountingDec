import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src import receipt_service


class ReceiptServiceTests(unittest.TestCase):
    def tearDown(self):
        receipt_service._ocr_model = None

    def test_paddle_output_keeps_text_confidence_and_box(self):
        box = [[0, 0], [100, 0], [100, 20], [0, 20]]
        result = receipt_service.normalize_paddle_result([
            [
                [box, ("TOKO MAKMUR", 0.96)],
                [box, ("TOTAL 25.000", 0.91)],
            ]
        ])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "TOKO MAKMUR")
        self.assertEqual(result[1]["confidence"], 0.91)
        self.assertEqual(result[0]["box"], box)

    def test_model_is_loaded_lazily_and_cached_once(self):
        instance = object()
        constructor = Mock(return_value=instance)
        fake_module = types.SimpleNamespace(PaddleOCR=constructor)
        with patch.dict(sys.modules, {"paddleocr": fake_module}):
            first = receipt_service.get_receipt_ocr_model()
            second = receipt_service.get_receipt_ocr_model()
        self.assertIs(first, instance)
        self.assertIs(second, instance)
        constructor.assert_called_once()

    def test_best_ocr_pass_prefers_structured_high_confidence_lines(self):
        collapsed = [
            {
                "text": "NOTA semua teks melebur menjadi satu blok yang sangat panjang " * 5,
                "confidence": 0.5,
                "box": [],
            }
        ]
        structured = [
            {"text": "TOKO MAKMUR", "confidence": 0.92, "box": []},
            {"text": "NAMA BARANG HARGA JUMLAH", "confidence": 0.90, "box": []},
            {"text": "1 kg Melon Rp 10.000", "confidence": 0.88, "box": []},
            {"text": "TOTAL Rp 10.000", "confidence": 0.94, "box": []},
        ]
        selected, index, scores = receipt_service.select_best_ocr_lines(
            [collapsed, structured]
        )
        self.assertEqual(index, 1)
        self.assertEqual(selected, structured)
        self.assertGreater(scores[1], scores[0])

    def test_preprocessed_file_is_deleted_after_success(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            processed_path = Path(handle.name)
        model = Mock()
        model.ocr.return_value = []
        with (
            patch.object(receipt_service, "preprocess_receipt_image", return_value=processed_path),
            patch.object(receipt_service, "get_receipt_ocr_model", return_value=model),
        ):
            result = receipt_service.extract_receipt(Path("unused.jpg"))
        self.assertEqual(result["ocr_text"], "")
        self.assertEqual(result["ocr_model_text"], "")
        self.assertFalse(processed_path.exists())

    def test_preprocessed_file_is_deleted_after_ocr_failure(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            processed_path = Path(handle.name)
        model = Mock()
        model.ocr.side_effect = RuntimeError("decoder internals")
        with (
            patch.object(receipt_service, "preprocess_receipt_image", return_value=processed_path),
            patch.object(receipt_service, "get_receipt_ocr_model", return_value=model),
        ):
            with self.assertRaises(receipt_service.ReceiptOcrUnavailableError):
                receipt_service.extract_receipt(Path("unused.jpg"))
        self.assertFalse(processed_path.exists())

    def test_all_multipass_files_are_deleted_and_best_result_is_used(self):
        handles = [
            tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            for _index in range(2)
        ]
        for handle in handles:
            handle.close()
        processed_path, threshold_path = (Path(handle.name) for handle in handles)
        box = [[0, 0], [100, 0], [100, 20], [0, 20]]
        model = Mock()
        model.ocr.side_effect = [
            [[[box, ("teks melebur " * 30, 0.4)]]],
            [[
                [box, ("TOKO MAKMUR", 0.95)],
                [box, ("NAMA BARANG HARGA JUMLAH", 0.93)],
                [box, ("1 kg Melon Rp 10.000", 0.92)],
                [box, ("TOTAL Rp 10.000", 0.96)],
            ]],
        ]
        with (
            patch.object(receipt_service, "preprocess_receipt_image", return_value=processed_path),
            patch.object(receipt_service, "create_threshold_receipt_variant", return_value=threshold_path),
            patch.object(receipt_service, "get_receipt_ocr_model", return_value=model),
        ):
            result = receipt_service.extract_receipt(Path("unused.jpg"))
        self.assertEqual(result["ocr_diagnostics"]["selected_pass"], 1)
        self.assertIn("Melon", result["ocr_text"])
        self.assertIn("Melon", result["ocr_model_text"])
        self.assertFalse(processed_path.exists())
        self.assertFalse(threshold_path.exists())


if __name__ == "__main__":
    unittest.main()
