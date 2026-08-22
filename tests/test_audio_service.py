import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src import audio_service


class AudioServiceTests(unittest.TestCase):
    def setUp(self):
        self.original_model = audio_service._whisper_model
        audio_service._whisper_model = None

    def tearDown(self):
        audio_service._whisper_model = self.original_model

    def test_model_is_loaded_once_and_transcript_segments_are_cleaned(self):
        created_models = []

        class FakeWhisperModel:
            def __init__(self, model_size, device, compute_type):
                created_models.append((model_size, device, compute_type, self))
                self.calls = []

            def transcribe(self, path, language, vad_filter):
                self.calls.append((path, language, vad_filter))
                return iter(
                    [
                        SimpleNamespace(text="  Kemarin beli tepung "),
                        SimpleNamespace(text=" "),
                        SimpleNamespace(text="dua karung.  "),
                    ]
                ), SimpleNamespace()

        fake_module = types.ModuleType("faster_whisper")
        fake_module.WhisperModel = FakeWhisperModel

        with (
            patch.dict(sys.modules, {"faster_whisper": fake_module}),
            patch.multiple(
                audio_service.config,
                WHISPER_MODEL_SIZE="small",
                WHISPER_DEVICE="cpu",
                WHISPER_COMPUTE_TYPE="int8",
                WHISPER_LANGUAGE="id",
                WHISPER_VAD_FILTER=True,
            ),
        ):
            first = audio_service.transcribe_audio(Path("sample.wav"))
            second_model = audio_service.get_whisper_model()

        self.assertEqual(first, "Kemarin beli tepung dua karung.")
        self.assertEqual(len(created_models), 1)
        self.assertIs(second_model, created_models[0][3])
        self.assertEqual(created_models[0][:3], ("small", "cpu", "int8"))
        self.assertEqual(
            second_model.calls,
            [("sample.wav", "id", True)],
        )


if __name__ == "__main__":
    unittest.main()
