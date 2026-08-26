import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src import evaluate as evaluate_module
from src.date_utils import resolve_date
from src.prompt_utils import (
    build_explicit_instruction_prompt,
    build_inference_prompt,
)
from src.transaction_type import classify_transaction_type


REFERENCE_DATE = date(2026, 8, 24)


def complete_target(**overrides):
    target = {
        "item_name": "Bakmi",
        "quantity": 3,
        "unit": "porsi",
        "total_price": 60000,
        "date": "2026-08-24",
        "transaction_type": "income",
    }
    target.update(overrides)
    return target


def metrics_for(target, prediction=None, valid_json=True):
    dataset = [{"input": "3 bakmi laku 60 ribu", "output": target}]
    results = [
        {
            "valid_json": valid_json,
            "prediction": prediction,
            "raw_output": None,
            "error": None,
        }
    ]
    return evaluate_module.evaluate_configuration(dataset, results)


class EvaluationMetricTests(unittest.TestCase):
    def test_all_fields_correct(self):
        target = complete_target()
        metrics = metrics_for(target, dict(target))

        self.assertEqual(metrics["counts"]["tp"], 6)
        self.assertEqual(metrics["counts"]["fp"], 0)
        self.assertEqual(metrics["counts"]["fn"], 0)
        self.assertEqual(metrics["precision"], 100.0)
        self.assertEqual(metrics["recall"], 100.0)
        self.assertEqual(metrics["f1_score"], 100.0)
        self.assertEqual(metrics["overall_field_accuracy"], 100.0)

    def test_one_wrong_non_null_field_adds_fp_and_fn(self):
        target = complete_target()
        prediction = {**target, "item_name": "Ayam"}
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["counts"]["tp"], 5)
        self.assertEqual(metrics["counts"]["fp"], 1)
        self.assertEqual(metrics["counts"]["fn"], 1)
        self.assertAlmostEqual(metrics["overall_field_accuracy"], 5 / 6 * 100)

    def test_target_null_and_prediction_null_is_field_correct_without_counts(self):
        target = complete_target(item_name=None, quantity=None, unit=None)
        prediction = dict(target)
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["counts"]["tp"], 3)
        self.assertEqual(metrics["counts"]["fp"], 0)
        self.assertEqual(metrics["counts"]["fn"], 0)
        self.assertEqual(metrics["field_accuracy"]["item_name"], 100.0)

    def test_target_null_and_prediction_filled_adds_fp(self):
        target = complete_target(item_name=None)
        prediction = {**target, "item_name": "Duit"}
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["counts"]["tp"], 5)
        self.assertEqual(metrics["counts"]["fp"], 1)
        self.assertEqual(metrics["counts"]["fn"], 0)
        self.assertEqual(metrics["field_accuracy"]["item_name"], 0.0)

    def test_target_value_and_prediction_null_adds_fn(self):
        target = complete_target()
        prediction = {**target, "item_name": None}
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["counts"]["tp"], 5)
        self.assertEqual(metrics["counts"]["fp"], 0)
        self.assertEqual(metrics["counts"]["fn"], 1)

    def test_missing_prediction_field_is_wrong_and_adds_fn_for_non_null_target(self):
        target = complete_target()
        prediction = dict(target)
        del prediction["quantity"]
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["counts"]["fn"], 1)
        self.assertEqual(metrics["field_accuracy"]["quantity"], 0.0)

    def test_missing_prediction_field_is_wrong_even_when_target_is_null(self):
        target = complete_target(item_name=None)
        prediction = dict(target)
        del prediction["item_name"]
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["counts"]["tp"], 5)
        self.assertEqual(metrics["counts"]["fp"], 0)
        self.assertEqual(metrics["counts"]["fn"], 0)
        self.assertEqual(metrics["field_accuracy"]["item_name"], 0.0)
        self.assertAlmostEqual(metrics["overall_field_accuracy"], 5 / 6 * 100)

    def test_invalid_json_adds_fn_for_every_non_null_target_field(self):
        target = complete_target(unit=None)
        metrics = metrics_for(target, prediction=None, valid_json=False)

        self.assertEqual(metrics["counts"]["valid_json"], 0)
        self.assertEqual(metrics["counts"]["invalid_json"], 1)
        self.assertEqual(metrics["counts"]["fn"], 5)
        self.assertEqual(metrics["overall_field_accuracy"], 0.0)

    def test_wrong_price_adds_fp_and_fn(self):
        target = complete_target()
        metrics = metrics_for(target, {**target, "total_price": 50000})

        self.assertEqual(metrics["counts"]["fp"], 1)
        self.assertEqual(metrics["counts"]["fn"], 1)
        self.assertEqual(metrics["field_accuracy"]["total_price"], 0.0)

    def test_wrong_transaction_type_adds_fp_and_fn(self):
        target = complete_target()
        metrics = metrics_for(target, {**target, "transaction_type": "expense"})

        self.assertEqual(metrics["counts"]["fp"], 1)
        self.assertEqual(metrics["counts"]["fn"], 1)
        self.assertEqual(metrics["field_accuracy"]["transaction_type"], 0.0)

    def test_zero_denominators_return_zero_not_nan(self):
        target = {field: None for field in evaluate_module.FIELDS}
        metrics = metrics_for(target, dict(target))

        self.assertEqual(metrics["precision"], 0.0)
        self.assertEqual(metrics["recall"], 0.0)
        self.assertEqual(metrics["f1_score"], 0.0)
        self.assertEqual(metrics["overall_field_accuracy"], 100.0)

    def test_required_aggregate_income_example_formula(self):
        target = complete_target(
            item_name=None,
            quantity=None,
            unit=None,
            total_price=300000,
        )
        prediction = {**target, "item_name": "duit"}
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["counts"]["tp"], 3)
        self.assertEqual(metrics["counts"]["fp"], 1)
        self.assertEqual(metrics["counts"]["fn"], 0)
        self.assertEqual(metrics["precision"], 75.0)
        self.assertEqual(metrics["recall"], 100.0)
        self.assertAlmostEqual(metrics["f1_score"], 85.71428571428571)
        self.assertAlmostEqual(metrics["overall_field_accuracy"], 83.33333333333334)

    def test_light_normalization_only(self):
        target = complete_target(quantity=3, total_price=60000)
        prediction = {
            **target,
            "item_name": "  BAKMI  ",
            "quantity": "3.0",
            "total_price": "60000",
            "transaction_type": "INCOME",
        }
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["overall_field_accuracy"], 100.0)


class EvaluationPipelineTests(unittest.TestCase):
    def test_bundled_six_field_dataset_passes_preflight(self):
        project_root = Path(__file__).resolve().parents[1]
        dataset = evaluate_module.load_jsonl(
            project_root / "data" / "processed" / "eval-six-fields.jsonl"
        )

        evaluate_module.validate_evaluation_dataset(dataset)

        self.assertEqual(len(dataset), 52)
        normalized_inputs = {
            " ".join(row["input"].casefold().split()) for row in dataset
        }
        self.assertEqual(len(normalized_inputs), len(dataset))
        type_counts = {
            transaction_type: sum(
                row["output"]["transaction_type"] == transaction_type
                for row in dataset
            )
            for transaction_type in ("income", "expense")
        }
        self.assertEqual(type_counts, {"income": 13, "expense": 39})
        self.assertTrue(
            all(
                classify_transaction_type(row["input"])
                == row["output"]["transaction_type"]
                for row in dataset
            )
        )
        self.assertTrue(all(row["output"]["date"] is not None for row in dataset))
        self.assertTrue(
            all(
                (resolve_date(row["input"], REFERENCE_DATE) or REFERENCE_DATE.isoformat())
                == row["output"]["date"]
                for row in dataset
            )
        )
        dates_by_input = {row["input"]: row["output"]["date"] for row in dataset}
        self.assertEqual(
            dates_by_input["Tanggal 10 Juli restock telur 2 tray total 60k"],
            "2026-07-10",
        )
        self.assertEqual(
            dates_by_input["kmrn restok saus sambal 15btl 75rb"],
            "2026-08-23",
        )
        self.assertEqual(
            dates_by_input["Barusan beli beras pandan wangi 5kg total 78rb"],
            "2026-08-24",
        )
        targets_by_input = {row["input"]: row["output"] for row in dataset}
        self.assertIsNone(targets_by_input["beli galon aqua 70rb"]["quantity"])
        self.assertIsNone(targets_by_input["beli galon aqua 70rb"]["unit"])
        self.assertIsNone(targets_by_input["beli telur 45500"]["quantity"])
        self.assertIsNone(targets_by_input["beli telur 45500"]["unit"])

        augmentation = evaluate_module.load_jsonl(
            project_root / "data" / "processed" / "train-augmentation.jsonl"
        )
        augmentation_inputs = {
            " ".join(row["input"].casefold().split()) for row in augmentation
        }
        self.assertTrue(normalized_inputs.isdisjoint(augmentation_inputs))

    def test_explicit_instruction_uses_chat_template_and_fixed_reference_date(self):
        class RecordingTokenizer:
            def __init__(self):
                self.messages = None
                self.options = None

            def apply_chat_template(self, messages, **options):
                self.messages = messages
                self.options = options
                return "rendered chat prompt"

        tokenizer = RecordingTokenizer()
        prompt = build_explicit_instruction_prompt(
            tokenizer,
            "Beli beras 5kg 65rb",
            REFERENCE_DATE,
        )

        self.assertEqual(prompt, "rendered chat prompt")
        self.assertEqual([message["role"] for message in tokenizer.messages], ["system", "user"])
        self.assertIn("transaction_type", tokenizer.messages[0]["content"])
        self.assertIn("expense untuk beli", tokenizer.messages[0]["content"])
        self.assertEqual(
            tokenizer.messages[1]["content"],
            "REFERENCE_DATE: 2026-08-24\nTRANSACTION_TEXT: Beli beras 5kg 65rb",
        )
        self.assertEqual(
            tokenizer.options,
            {"tokenize": False, "add_generation_prompt": True},
        )

    def test_soft_prompt_receives_same_fixed_reference_date_contract(self):
        prompt = build_inference_prompt("Kemarin jual 2 porsi bakmi", REFERENCE_DATE)

        self.assertEqual(
            prompt,
            "REFERENCE_DATE: 2026-08-24\n"
            "Kalimat: Kemarin jual 2 porsi bakmi\nJSON:",
        )

    def test_postprocessing_preserves_all_ideal_evaluation_and_validation_targets(self):
        project_root = Path(__file__).resolve().parents[1]
        dataset = []
        for filename in (
            "eval-six-fields.jsonl",
            "validation-six-fields.jsonl",
        ):
            dataset.extend(
                evaluate_module.load_jsonl(
                    project_root / "data" / "processed" / filename
                )
            )

        for row in dataset:
            with self.subTest(user_input=row["input"]):
                parsed = evaluate_module.apply_system_postprocessing(
                    json.dumps(row["output"]),
                    row["input"],
                    REFERENCE_DATE,
                )

                self.assertTrue(parsed["valid_json"], parsed["error"])
                self.assertEqual(parsed["prediction"], row["output"])

    def test_raw_json_requires_the_entire_output_to_be_an_object(self):
        valid = evaluate_module.parse_raw_json('{"item_name": "Bakmi"}')
        commentary = evaluate_module.parse_raw_json(
            'Hasil: {"item_name": "Bakmi"}'
        )
        trailing = evaluate_module.parse_raw_json(
            '{"item_name": "Bakmi"}\nKalimat:'
        )
        array = evaluate_module.parse_raw_json("[]")

        self.assertTrue(valid["valid_json"])
        self.assertFalse(commentary["valid_json"])
        self.assertFalse(trailing["valid_json"])
        self.assertFalse(array["valid_json"])

    def test_four_configurations_reuse_two_raw_output_sources(self):
        target = complete_target(unit=None)
        dataset = [
            {
                "input": "3 bakmi laku terjual 60 ribu",
                "output": target,
            }
        ]
        raw = json.dumps(target)
        raw_outputs = {
            "base_explicit": [{"raw_output": raw, "error": None}],
            "soft_prompt": [{"raw_output": raw, "error": None}],
        }

        with (
            patch.object(
                evaluate_module,
                "parse_raw_json",
                wraps=evaluate_module.parse_raw_json,
            ) as raw_parser,
            patch.object(
                evaluate_module,
                "apply_system_postprocessing",
                wraps=evaluate_module.apply_system_postprocessing,
            ) as postprocessor,
        ):
            results = evaluate_module.evaluate_from_raw_outputs(
                dataset,
                raw_outputs,
                REFERENCE_DATE,
            )

        self.assertEqual(set(results), set(evaluate_module.CONFIGURATIONS))
        self.assertEqual(len(results), 4)
        self.assertEqual(raw_parser.call_count, 2)
        self.assertEqual(postprocessor.call_count, 2)
        groups = [
            definition["experiment_group"]
            for definition in evaluate_module.CONFIGURATIONS.values()
        ]
        self.assertEqual(groups, ["main_comparison"] * 4)
        labels = [
            definition["label"]
            for definition in evaluate_module.CONFIGURATIONS.values()
        ]
        self.assertTrue(all("Minimal Prompt" not in label for label in labels))
        for metrics in results.values():
            self.assertEqual(metrics["counts"]["total_examples"], 1)
            self.assertEqual(metrics["counts"]["total_fields"], 6)

    def test_collection_loads_two_models_and_runs_two_prompt_passes(self):
        dataset = [{"input": "Beli bakmi 3 porsi 60 ribu", "output": complete_target()}]
        tokenizer = object()
        base_model = object()
        soft_prompt_model = object()
        pass_results = [
            [{"raw_output": "base explicit", "error": None}],
            [{"raw_output": "soft prompt", "error": None}],
        ]

        with (
            patch("src.model_utils.load_tokenizer", return_value=tokenizer) as load_tokenizer,
            patch("src.model_utils.load_base_model", return_value=base_model) as load_base,
            patch(
                "src.model_utils.load_model_for_inference",
                return_value=soft_prompt_model,
            ) as load_soft_prompt,
            patch.object(
                evaluate_module,
                "_run_inference_pass",
                side_effect=pass_results,
            ) as run_pass,
            patch.object(evaluate_module, "_clear_model_memory"),
        ):
            outputs = evaluate_module.collect_raw_model_outputs(
                dataset,
                "adapter-path",
                42,
                REFERENCE_DATE,
            )

        load_tokenizer.assert_called_once_with()
        load_base.assert_called_once_with()
        load_soft_prompt.assert_called_once_with("adapter-path")
        self.assertEqual(run_pass.call_count, 2)
        self.assertIs(run_pass.call_args_list[0].args[2], base_model)
        self.assertIs(run_pass.call_args_list[1].args[2], soft_prompt_model)
        self.assertEqual(
            [call.args[5] for call in run_pass.call_args_list],
            ["explicit_instruction", "minimal"],
        )
        self.assertEqual(
            set(outputs),
            {"base_explicit", "soft_prompt"},
        )

    def test_missing_target_field_fails_preflight_instead_of_being_fabricated(self):
        dataset = [
            {
                "input": "Beli bakmi 3 porsi 60 ribu",
                "output": {
                    key: value
                    for key, value in complete_target().items()
                    if key != "transaction_type"
                },
            }
        ]

        with self.assertRaises(evaluate_module.DatasetValidationError) as context:
            evaluate_module.validate_evaluation_dataset(dataset)

        self.assertIn("transaction_type", str(context.exception))

    def test_unknown_transaction_type_is_rejected_as_evaluation_target(self):
        dataset = [
            {
                "input": "catat transaksi 60 ribu",
                "output": complete_target(transaction_type="unknown"),
            }
        ]

        with self.assertRaises(evaluate_module.DatasetValidationError) as context:
            evaluate_module.validate_evaluation_dataset(dataset)

        self.assertIn("income atau expense", str(context.exception))

    def test_old_adapter_contract_is_rejected_before_model_evaluation(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            with self.assertRaises(evaluate_module.ModelEvaluationError) as context:
                evaluate_module.validate_soft_prompt_contract(temp_directory)

        self.assertIn("python -m src.train", str(context.exception))

    def test_six_field_adapter_contract_is_accepted(self):
        contract = {
            "contract_version": evaluate_module.config.SOFT_PROMPT_CONTRACT_VERSION,
            "fields": list(evaluate_module.FIELDS),
        }
        with tempfile.TemporaryDirectory() as temp_directory:
            contract_path = (
                Path(temp_directory)
                / evaluate_module.config.SOFT_PROMPT_CONTRACT_FILENAME
            )
            contract_path.write_text(json.dumps(contract), encoding="utf-8")

            loaded = evaluate_module.validate_soft_prompt_contract(temp_directory)

        self.assertEqual(loaded, contract)

    def test_target_null_date_is_not_changed_to_reference_date(self):
        target = complete_target(date=None)
        prediction = complete_target(date="2026-08-24")
        metrics = metrics_for(target, prediction)

        self.assertEqual(metrics["field_accuracy"]["date"], 0.0)
        self.assertEqual(metrics["counts"]["fp"], 1)

    def test_evaluate_writes_auditable_report_without_loading_models_when_raw_is_injected(self):
        target = complete_target(unit=None)
        row = {
            "input": "3 bakmi laku terjual 60 ribu",
            "output": target,
        }
        raw = json.dumps(target)
        raw_outputs = {
            "base_explicit": [{"raw_output": raw, "error": None}],
            "soft_prompt": [{"raw_output": raw, "error": None}],
        }

        with tempfile.TemporaryDirectory() as temp_directory:
            data_path = Path(temp_directory) / "eval.jsonl"
            output_path = Path(temp_directory) / "results" / "evaluation_report.json"
            data_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

            with (
                patch.object(
                    evaluate_module,
                    "collect_raw_model_outputs",
                    side_effect=AssertionError("model tidak boleh dimuat"),
                ),
                redirect_stdout(io.StringIO()),
            ):
                report = evaluate_module.evaluate(
                    str(data_path),
                    reference_date=REFERENCE_DATE,
                    output_path=str(output_path),
                    training_path=None,
                    raw_outputs_by_model=raw_outputs,
                )

            saved_report = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "completed")
        self.assertEqual(
            saved_report["evaluation_settings"]["fields"],
            list(evaluate_module.FIELDS),
        )
        self.assertEqual(
            set(saved_report["configurations"]),
            set(evaluate_module.CONFIGURATIONS),
        )
        self.assertEqual(
            saved_report["raw_model_outputs"]["base_explicit"][0]["raw_output"],
            raw,
        )
        self.assertEqual(saved_report["evaluation_settings"]["raw_inference_passes"], 2)
        self.assertEqual(saved_report["evaluation_settings"]["model_loads"], 2)
        self.assertEqual(
            saved_report["configurations"]["llama"]["counts"]["total_examples"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
