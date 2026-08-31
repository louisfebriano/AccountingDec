import unittest
from unittest.mock import patch

from src import inference
from src.voice_normalization import correct_voice_transcript_with_llama


class VoiceNormalizationTests(unittest.TestCase):
    def test_llama_correction_keeps_numbers_and_returns_corrected_text(self):
        original = "beli tepung 4 karong 44 ribu"
        corrected = "beli tepung 4 karung 44 ribu"
        with (
            patch.object(inference, "generate_with_base_model", return_value=corrected) as generate,
            patch("src.voice_normalization.config.VOICE_LLM_NORMALIZATION_ENABLED", True),
        ):
            result = correct_voice_transcript_with_llama(original)

        self.assertEqual(result, corrected)
        messages = generate.call_args.args[0]
        self.assertEqual(messages[-1]["content"], original)
        self.assertIn("Jangan mengubah angka", messages[0]["content"])

    def test_changed_numbers_are_rejected(self):
        original = "beli tepung 4 karong 44 ribu"
        with (
            patch.object(
                inference,
                "generate_with_base_model",
                return_value="beli tepung 5 karung 45 ribu",
            ),
            patch("src.voice_normalization.config.VOICE_LLM_NORMALIZATION_ENABLED", True),
        ):
            result = correct_voice_transcript_with_llama(original)

        self.assertEqual(result, original)

    def test_disabled_correction_does_not_load_llama(self):
        with (
            patch.object(inference, "generate_with_base_model") as generate,
            patch("src.voice_normalization.config.VOICE_LLM_NORMALIZATION_ENABLED", False),
        ):
            result = correct_voice_transcript_with_llama("beli tepung 4 karong")

        self.assertEqual(result, "beli tepung 4 karong")
        generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
