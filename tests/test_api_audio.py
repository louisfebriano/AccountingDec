import io
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from src import api


def make_upload(
    content: bytes = b"fake-audio",
    filename: str = "transaction.wav",
    content_type: str = "audio/wav",
) -> UploadFile:
    """Buat UploadFile in-memory tanpa membutuhkan berkas audio nyata."""
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def successful_extraction(text, adapter_path=None, reference_date=None):
    """Mock hasil pipeline Llama untuk jalur sukses endpoint."""
    return {
        "success": True,
        "input": text,
        "data": {
            "item_name": "Tepung terigu",
            "quantity": 2,
            "unit": "karung",
            "total_price": 250000,
            "date": "2026-08-20",
            "transaction_type": "expense",
        },
        "error": None,
        "raw_output": "{}",
        "out_of_context": False,
    }


class ExtractAudioEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_empty_audio_file(self):
        transcribe = Mock()

        with patch.object(api, "transcribe_audio", transcribe):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_audio(make_upload(content=b""), None)

        self.assertEqual(raised.exception.status_code, 400)
        transcribe.assert_not_called()

    async def test_rejects_unsupported_audio_format(self):
        transcribe = Mock()

        with patch.object(api, "transcribe_audio", transcribe):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_audio(
                    make_upload(filename="notes.txt", content_type="text/plain"),
                    None,
                )

        self.assertEqual(raised.exception.status_code, 415)
        transcribe.assert_not_called()

    async def test_rejects_empty_transcript(self):
        extract = Mock()

        with (
            patch.object(api, "transcribe_audio", return_value="   "),
            patch.object(api, "extract_transaction", extract),
        ):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_audio(make_upload(), None)

        self.assertEqual(raised.exception.status_code, 422)
        extract.assert_not_called()

    async def test_rejects_invalid_reference_date(self):
        transcribe = Mock()

        with patch.object(api, "transcribe_audio", transcribe):
            with self.assertRaises(HTTPException) as raised:
                await api.extract_audio(make_upload(), "21-08-2026")

        self.assertEqual(raised.exception.status_code, 400)
        transcribe.assert_not_called()

    async def test_success_path_normalizes_text_and_deletes_temp_file(self):
        captured_paths = []

        def transcribe(temp_path):
            captured_paths.append(Path(temp_path))
            self.assertTrue(Path(temp_path).is_file())
            return (
                "Kemarin beli tepung terigu dua karung total "
                "dua ratus lima puluh ribu"
            )

        extract = Mock(side_effect=successful_extraction)
        with (
            patch.object(api, "transcribe_audio", side_effect=transcribe),
            patch.object(api, "extract_transaction", extract),
        ):
            with self.assertLogs(api.logger, level="INFO") as captured_logs:
                response = await api.extract_audio(make_upload(), "2026-08-21")

        self.assertEqual(response["success"], True)
        self.assertEqual(response["source"], "voice")
        self.assertEqual(
            response["normalized_text"],
            "Kemarin beli tepung terigu 2 karung total 250000",
        )
        self.assertEqual(response["data"]["total_price"], 250000)
        self.assertEqual(response["data"]["transaction_type"], "expense")
        extract.assert_called_once_with(
            "Kemarin beli tepung terigu 2 karung total 250000",
            reference_date=date(2026, 8, 21),
        )
        self.assertEqual(len(captured_paths), 1)
        self.assertFalse(captured_paths[0].exists())
        log_output = "\n".join(captured_logs.output)
        self.assertIn("transcript=", log_output)
        self.assertIn("normalized_text=", log_output)
        self.assertIn("extraction success=True out_of_context=False", log_output)

    async def test_income_voice_input_returns_transaction_type(self):
        def classify_extraction(text, adapter_path=None, reference_date=None):
            result = successful_extraction(text, adapter_path, reference_date)
            result["data"] = dict(result["data"])
            result["data"]["item_name"] = "Nasi goreng"
            result["data"]["transaction_type"] = "income"
            return result

        with (
            patch.object(
                api,
                "transcribe_audio",
                return_value="Jual nasi goreng sepuluh porsi total dua ratus ribu",
            ),
            patch.object(
                api,
                "extract_transaction",
                side_effect=classify_extraction,
            ) as extract,
            self.assertLogs(api.logger, level="INFO"),
        ):
            response = await api.extract_audio(make_upload(), "2026-08-21")

        self.assertEqual(response["data"]["transaction_type"], "income")
        extract.assert_called_once_with(
            "Jual nasi goreng 10 porsi total 200000",
            reference_date=date(2026, 8, 21),
        )

    async def test_general_income_voice_uses_deterministic_pipeline(self):
        from src import inference

        with (
            patch.object(
                api,
                "transcribe_audio",
                return_value="pemasukan hari ini tiga juta rupiah",
            ),
            patch.object(inference, "get_pipeline") as pipeline,
            self.assertLogs(api.logger, level="INFO"),
        ):
            response = await api.extract_audio(make_upload(), "2026-08-21")

        self.assertEqual(response["normalized_text"], "pemasukan hari ini 3000000 rupiah")
        self.assertEqual(response["data"]["transaction_type"], "income")
        self.assertEqual(response["data"]["total_price"], 3000000)
        self.assertIsNone(response["data"]["item_name"])
        self.assertIsNone(response["data"]["quantity"])
        self.assertIsNone(response["data"]["unit"])
        pipeline.assert_not_called()

    async def test_unknown_voice_transaction_returns_error_before_model(self):
        from src import inference

        with (
            patch.object(
                api,
                "transcribe_audio",
                return_value="transfer lima ratus ribu",
            ),
            patch.object(inference, "get_pipeline") as pipeline,
            self.assertLogs(api.logger, level="INFO") as captured_logs,
        ):
            response = await api.extract_audio(make_upload(), "2026-08-21")

        self.assertFalse(response["success"])
        self.assertEqual(response["source"], "voice")
        self.assertEqual(response["normalized_text"], "transfer 500000")
        self.assertIsNone(response["data"])
        self.assertEqual(
            response["error"],
            inference.UNKNOWN_TRANSACTION_TYPE_ERROR,
        )
        self.assertFalse(response["out_of_context"])
        self.assertIn(
            "extraction success=False out_of_context=False",
            "\n".join(captured_logs.output),
        )
        pipeline.assert_not_called()

    async def test_out_of_context_matches_text_endpoint_handling(self):
        out_of_context = {
            "success": False,
            "data": None,
            "error": "Input di luar konteks transaksi: Tidak ditemukan angka",
            "out_of_context": True,
        }

        with (
            patch.object(api, "transcribe_audio", return_value="ceritakan cuaca hari ini"),
            patch.object(api, "extract_transaction", return_value=out_of_context),
        ):
            with self.assertLogs(api.logger, level="INFO") as captured_logs:
                with self.assertRaises(HTTPException) as raised:
                    await api.extract_audio(make_upload(), None)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.detail, out_of_context["error"])
        log_output = "\n".join(captured_logs.output)
        self.assertIn("normalized_text='ceritakan cuaca hari ini'", log_output)
        self.assertIn("extraction success=False out_of_context=True", log_output)

    async def test_temp_file_is_deleted_when_transcription_fails(self):
        captured_paths = []

        def fail_transcription(temp_path):
            captured_paths.append(Path(temp_path))
            self.assertTrue(Path(temp_path).is_file())
            raise RuntimeError("internal decoder detail")

        with patch.object(api, "transcribe_audio", side_effect=fail_transcription):
            with self.assertLogs(api.logger, level="ERROR"):
                with self.assertRaises(HTTPException) as raised:
                    await api.extract_audio(make_upload(), None)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertNotIn("decoder", raised.exception.detail)
        self.assertEqual(len(captured_paths), 1)
        self.assertFalse(captured_paths[0].exists())


class LegacyTextEndpointTests(unittest.TestCase):
    def test_extract_text_keeps_original_input_unchanged(self):
        result = successful_extraction("beli dua karung total 250000")

        with patch.object(api, "extract_transaction", return_value=result) as extract:
            response = api.extract(
                api.ExtractRequest(
                    text="beli dua karung total 250000",
                    reference_date="2026-08-21",
                )
            )

        self.assertIs(response, result)
        self.assertEqual(
            set(response["data"]),
            {
                "item_name",
                "quantity",
                "unit",
                "total_price",
                "date",
                "transaction_type",
            },
        )
        extract.assert_called_once_with(
            "beli dua karung total 250000",
            reference_date=date(2026, 8, 21),
        )

    def test_unknown_text_transaction_returns_error_before_model(self):
        from src import inference

        with patch.object(inference, "get_pipeline") as pipeline:
            response = api.extract(
                api.ExtractRequest(
                    text="Transfer 500rb",
                    reference_date="2026-08-21",
                )
            )

        self.assertFalse(response["success"])
        self.assertIsNone(response["data"])
        self.assertEqual(
            response["error"],
            inference.UNKNOWN_TRANSACTION_TYPE_ERROR,
        )
        self.assertFalse(response["out_of_context"])
        pipeline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
