import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from src import inference


class FakeInputIds:
    shape = (1, 1)


class FakeInputs(dict):
    def __init__(self):
        super().__init__(input_ids=FakeInputIds())

    def to(self, _device):
        return self


class FakeTokenizer:
    def __call__(self, _prompt, return_tensors):
        assert return_tensors == "pt"
        return FakeInputs()

    def decode(self, _tokens, **_kwargs):
        return "{}"


class AdapterAwareModel:
    device = "cpu"

    def __init__(self):
        self.peft_config = {inference.TRANSACTION_ADAPTER_NAME: object()}
        self.active_adapter = inference.TRANSACTION_ADAPTER_NAME
        self.load_calls = []
        self.generate_records = []

    def load_adapter(self, path, adapter_name):
        self.load_calls.append((path, adapter_name))
        self.peft_config[adapter_name] = object()

    def set_adapter(self, adapter_name, inference_mode=False):
        if not inference_mode:
            raise AssertionError("Adapter inference harus tetap frozen")
        self.active_adapter = adapter_name

    def generate(self, **_kwargs):
        before = self.active_adapter
        time.sleep(0.01)
        after = self.active_adapter
        self.generate_records.append((before, after))
        return [[1, 2]]


class ModelAdapterRoutingTests(unittest.TestCase):
    def test_requests_share_one_model_and_never_swap_active_adapter(self):
        model = AdapterAwareModel()
        tokenizer = FakeTokenizer()

        def run(adapter_name):
            return inference.generate_with_adapter(
                "prompt",
                adapter_name=adapter_name,
                adapter_path="adapters/soft-prompt-nota",
            )

        adapter_names = [
            inference.RECEIPT_ADAPTER_NAME,
            inference.TRANSACTION_ADAPTER_NAME,
            inference.RECEIPT_ADAPTER_NAME,
            inference.TRANSACTION_ADAPTER_NAME,
        ]
        with patch.object(inference, "get_pipeline", return_value=(tokenizer, model)) as pipeline:
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(run, adapter_names))

        self.assertEqual(pipeline.call_count, 4)
        self.assertEqual(
            model.load_calls,
            [("adapters/soft-prompt-nota", inference.RECEIPT_ADAPTER_NAME)],
        )
        self.assertEqual(len(model.generate_records), 4)
        self.assertTrue(all(before == after for before, after in model.generate_records))
        self.assertEqual(
            {before for before, _after in model.generate_records},
            {inference.TRANSACTION_ADAPTER_NAME, inference.RECEIPT_ADAPTER_NAME},
        )


if __name__ == "__main__":
    unittest.main()
