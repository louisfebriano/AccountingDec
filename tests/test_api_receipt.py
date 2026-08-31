import io
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException, Request
from starlette.datastructures import Headers, UploadFile

from src import api
from src.receipt_inference import ReceiptAdapterUnavailableError
from src.receipt_service import InvalidReceiptImageError


def make_upload(
    content=b"image-bytes",
    filename="nota.jpg",
    content_type="image/jpeg",
):
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def parsed_receipt():
    return {
        "ocr_text": (
            "TOKO MAKMUR\nJl. Contoh No. 10\nTOTAL 180.000\n26/08/2026"
        ),
        "ocr_model_text": "TOKO MAKMUR\nTOTAL 180.000\n26/08/2026",
        "date": "2026-08-26",
        "total_candidates": [180000],
        "receipt": {
            "merchant_name": "TOKO MAKMUR",
            "receipt_number": None,
            "subtotal": None,
            "discount": None,
            "tax": None,
            "service_charge": None,
            "total": 180000,
            "items": [],
            "confidence": 0.95,
            "warnings": [],
        },
    }


def semantic_receipt(total=180000):
    return {
        "success": True,
        "raw_output": "{\"total\":180000}",
        "adapter_name": "receipt",
        "data": {
            "merchant_name": "TOKO MAKMUR",
            "receipt_number": None,
            "date": "2026-08-26",
            "items": [],
            "subtotal": None,
            "discount": None,
            "tax": None,
            "service_charge": None,
            "total": total,
            "transaction_type": "expense",
        },
    }


class ReceiptEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_receipt_input_and_ocr_text_are_added_to_audit_metadata(self):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/extract/receipt",
                "headers": [],
            }
        )
        with (
            patch.object(api, "validate_receipt_image"),
            patch.object(api, "extract_receipt", return_value=parsed_receipt()),
            patch.object(
                api,
                "extract_receipt_with_llama",
                return_value=semantic_receipt(),
            ),
        ):
            await api.extract_receipt_endpoint(
                make_upload(),
                "2026-08-26",
                request=request,
            )

        metadata = request.state.audit_metadata
        self.assertEqual(metadata["method"], "receipt")
        self.assertEqual(metadata["input"]["ocr_text"], parsed_receipt()["ocr_text"])
        self.assertFalse(metadata["input"]["ocr_text_truncated"])
        self.assertEqual(
            metadata["input"]["ocr_model_text"],
            parsed_receipt()["ocr_model_text"],
        )
        self.assertTrue(metadata["input"]["ocr_compacted"])
        self.assertEqual(metadata["input"]["image"]["format"], "JPEG")
        self.assertGreater(metadata["input"]["image"]["size_bytes"], 0)

    async def test_accepts_jpeg_png_and_webp(self):
        cases = (
            ("nota.jpg", "image/jpeg", "JPEG"),
            ("nota.png", "image/png", "PNG"),
            ("nota.webp", "image/webp", "WEBP"),
        )
        for filename, content_type, expected_format in cases:
            with self.subTest(filename=filename):
                captured_paths = []

                def validate(path, image_format):
                    captured_paths.append(Path(path))
                    self.assertEqual(image_format, expected_format)
                    self.assertTrue(Path(path).exists())

                with (
                    patch.object(api, "validate_receipt_image", side_effect=validate),
                    patch.object(api, "extract_receipt", return_value=parsed_receipt()),
                    patch.object(
                        api,
                        "extract_receipt_with_llama",
                        return_value=semantic_receipt(),
                    ) as semantic,
                ):
                    response = await api.extract_receipt_endpoint(
                        make_upload(filename=filename, content_type=content_type),
                        "2026-08-26",
                    )

                self.assertTrue(response["success"])
                self.assertTrue(response["requires_confirmation"])
                self.assertEqual(response["data"]["transaction_type"], "expense")
                self.assertEqual(response["data"]["total_price"], 180000)
                self.assertNotIn("total_candidates", response)
                for unused_field in (
                    "receipt_number",
                    "subtotal",
                    "discount",
                    "tax",
                    "service_charge",
                ):
                    self.assertNotIn(unused_field, response["data"]["receipt"])
                self.assertEqual(
                    response["extraction_method"],
                    "llama_soft_prompt_receipt",
                )
                self.assertEqual(response["validation"]["status"], "valid")
                semantic.assert_called_once_with(
                    parsed_receipt()["ocr_model_text"],
                    api.date(2026, 8, 26),
                    parsed_receipt(),
                )
                self.assertEqual(
                    response["ocr_model_text"],
                    parsed_receipt()["ocr_model_text"],
                )
                self.assertFalse(captured_paths[0].exists())

    async def test_can_disable_model_ocr_compaction(self):
        with (
            patch.object(api, "validate_receipt_image"),
            patch.object(api, "extract_receipt", return_value=parsed_receipt()),
            patch.object(api.config, "RECEIPT_OCR_COMPACT_FOR_MODEL", False),
            patch.object(
                api,
                "extract_receipt_with_llama",
                return_value=semantic_receipt(),
            ) as semantic,
        ):
            response = await api.extract_receipt_endpoint(
                make_upload(),
                "2026-08-26",
            )

        semantic.assert_called_once()
        model_text, reference_date, parsed_input = semantic.call_args.args
        self.assertEqual(model_text, parsed_receipt()["ocr_text"])
        self.assertEqual(reference_date, api.date(2026, 8, 26))
        self.assertEqual(parsed_input["ocr_model_text"], parsed_receipt()["ocr_text"])
        self.assertEqual(response["ocr_model_text"], parsed_receipt()["ocr_text"])

    async def test_llama_result_is_primary_and_rule_difference_requires_confirmation(self):
        with (
            patch.object(api, "validate_receipt_image"),
            patch.object(api, "extract_receipt", return_value=parsed_receipt()),
            patch.object(
                api,
                "extract_receipt_with_llama",
                return_value=semantic_receipt(total=175000),
            ),
        ):
            response = await api.extract_receipt_endpoint(
                make_upload(),
                "2026-08-26",
            )

        self.assertEqual(response["data"]["total_price"], 175000)
        self.assertEqual(response["data"]["receipt"]["total"], 175000)
        self.assertEqual(response["validation"]["status"], "needs_confirmation")
        self.assertTrue(any(
            "kandidat total" in warning
            for warning in response["validation"]["warnings"]
        ))

    async def test_missing_receipt_adapter_uses_explicit_fallback(self):
        with (
            patch.object(api, "validate_receipt_image"),
            patch.object(api, "extract_receipt", return_value=parsed_receipt()),
            patch.object(
                api,
                "extract_receipt_with_llama",
                side_effect=ReceiptAdapterUnavailableError("adapter belum dilatih"),
            ),
            patch.object(api.config, "RECEIPT_RULE_FALLBACK_ENABLED", True),
            self.assertLogs(api.logger, level="WARNING"),
        ):
            response = await api.extract_receipt_endpoint(make_upload(), None)

        self.assertTrue(response["success"])
        self.assertEqual(response["extraction_method"], "rule_based_fallback")
        self.assertEqual(response["validation"]["status"], "needs_confirmation")
        self.assertTrue(any(
            "Fallback rule-based" in warning
            for warning in response["validation"]["warnings"]
        ))

    async def test_missing_receipt_adapter_without_fallback_returns_503_and_cleans_temp(self):
        captured = []

        def extract(path):
            captured.append(Path(path))
            return parsed_receipt()

        with (
            patch.object(api, "validate_receipt_image"),
            patch.object(api, "extract_receipt", side_effect=extract),
            patch.object(
                api,
                "extract_receipt_with_llama",
                side_effect=ReceiptAdapterUnavailableError("private adapter path"),
            ),
            patch.object(api.config, "RECEIPT_RULE_FALLBACK_ENABLED", False),
            self.assertLogs(api.logger, level="ERROR"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_receipt_endpoint(make_upload(), None)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("private", raised.exception.detail)
        self.assertFalse(captured[0].exists())

    async def test_rejects_empty_unsupported_oversized_and_mismatched_files(self):
        with self.assertRaises(HTTPException) as empty:
            await api.extract_receipt_endpoint(make_upload(content=b""), None)
        self.assertEqual(empty.exception.status_code, 400)

        with self.assertRaises(HTTPException) as unsupported:
            await api.extract_receipt_endpoint(
                make_upload(filename="nota.gif", content_type="image/gif"), None
            )
        self.assertEqual(unsupported.exception.status_code, 415)

        with self.assertRaises(HTTPException) as mismatched:
            await api.extract_receipt_endpoint(
                make_upload(filename="nota.png", content_type="image/jpeg"), None
            )
        self.assertEqual(mismatched.exception.status_code, 415)

        with patch.object(api.config, "RECEIPT_MAX_SIZE_BYTES", 3):
            with self.assertRaises(HTTPException) as oversized:
                await api.extract_receipt_endpoint(make_upload(content=b"1234"), None)
        self.assertEqual(oversized.exception.status_code, 413)

    async def test_rejects_invalid_reference_date_before_ocr(self):
        extract = Mock()
        with patch.object(api, "extract_receipt", extract):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_receipt_endpoint(make_upload(), "26-08-2026")
        self.assertEqual(raised.exception.status_code, 400)
        extract.assert_not_called()

    async def test_corrupt_image_returns_400_and_deletes_temp_file(self):
        captured = []

        def reject(path, _expected):
            captured.append(Path(path))
            raise InvalidReceiptImageError("File bukan gambar yang valid atau sudah rusak.")

        with patch.object(api, "validate_receipt_image", side_effect=reject):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_receipt_endpoint(make_upload(), None)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertFalse(captured[0].exists())

    async def test_empty_ocr_returns_422_and_deletes_temp_file(self):
        captured = []

        def extract(path):
            captured.append(Path(path))
            return {"ocr_text": "", "receipt": None, "total_candidates": []}

        with (
            patch.object(api, "validate_receipt_image"),
            patch.object(api, "extract_receipt", side_effect=extract),
        ):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_receipt_endpoint(make_upload(), None)
        self.assertEqual(raised.exception.status_code, 422)
        self.assertFalse(captured[0].exists())

    async def test_internal_failure_hides_details_and_deletes_temp_file(self):
        captured = []

        def fail(path):
            captured.append(Path(path))
            raise RuntimeError("private OCR stack detail")

        with (
            patch.object(api, "validate_receipt_image"),
            patch.object(api, "extract_receipt", side_effect=fail),
            self.assertLogs(api.logger, level="ERROR"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_receipt_endpoint(make_upload(), None)
        self.assertEqual(raised.exception.status_code, 500)
        self.assertNotIn("private", raised.exception.detail)
        self.assertFalse(captured[0].exists())


if __name__ == "__main__":
    unittest.main()
