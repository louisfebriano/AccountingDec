"""
Evaluasi model pada data eval (idealnya data primer asli dari UMKM).

Metrik yang dihitung:
- JSON validity rate: persentase output yang berhasil diparse jadi JSON valid + lolos schema
- Exact match accuracy: persentase prediksi yang SELURUH field-nya sama persis dengan ground truth
- Field-level precision/recall/F1: per field (item_name, quantity, unit, total_price, date)

Jalankan:
  python -m src.evaluate --data data/processed/eval.jsonl --adapter adapters/soft-prompt-transaksi

Untuk data eval yang ground truth-nya mengandung tanggal relatif (kemarin/besok/dll),
WAJIB set --reference-date sesuai asumsi tanggal saat data itu dibuat, contoh:
  python -m src.evaluate --data data/processed/eval_relative_date.jsonl --reference-date 2026-07-18
"""

import argparse
import json
from datetime import date

from .inference import extract_transaction

FIELDS = ["item_name", "quantity", "unit", "total_price", "date"]


def load_jsonl(path: str) -> list:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def normalize(value):
    """Normalisasi ringan biar perbandingan lebih adil (case, whitespace, tipe angka)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, (int, float)):
        return float(value)
    return value


def evaluate(data_path: str, adapter_path: str = None, reference_date: date = None):
    dataset = load_jsonl(data_path)

    n_total = len(dataset)
    n_valid_json = 0
    n_exact_match = 0

    # akumulasi TP/FP/FN per field, dihitung sebagai "match" vs "tidak match"
    field_correct = {f: 0 for f in FIELDS}
    field_total = {f: 0 for f in FIELDS}

    results_log = []

    for example in dataset:
        user_input = example["input"]
        ground_truth = example["output"]

        result = extract_transaction(
            user_input, adapter_path=adapter_path, reference_date=reference_date
        )

        row = {"input": user_input, "ground_truth": ground_truth}

        if not result["success"]:
            row["prediction"] = None
            row["valid_json"] = False
            row["exact_match"] = False
            results_log.append(row)
            continue

        n_valid_json += 1
        prediction = result["data"]
        row["prediction"] = prediction
        row["valid_json"] = True

        is_exact_match = True
        for field in FIELDS:
            field_total[field] += 1
            gt_val = normalize(ground_truth.get(field))
            pred_val = normalize(prediction.get(field))
            match = gt_val == pred_val
            if match:
                field_correct[field] += 1
            else:
                is_exact_match = False

        row["exact_match"] = is_exact_match
        if is_exact_match:
            n_exact_match += 1

        results_log.append(row)

    # ---- Summary ----
    print("=" * 60)
    print(f"Total data eval           : {n_total}")
    print(f"JSON validity rate        : {n_valid_json}/{n_total} ({n_valid_json/n_total*100:.1f}%)")
    print(f"Exact match accuracy      : {n_exact_match}/{n_total} ({n_exact_match/n_total*100:.1f}%)")
    print("-" * 60)
    print("Field-level accuracy:")
    for field in FIELDS:
        total = field_total[field]
        correct = field_correct[field]
        acc = (correct / total * 100) if total > 0 else 0.0
        print(f"  {field:<15}: {correct}/{total} ({acc:.1f}%)")
    print("=" * 60)

    return {
        "n_total": n_total,
        "json_validity_rate": n_valid_json / n_total if n_total else 0,
        "exact_match_accuracy": n_exact_match / n_total if n_total else 0,
        "field_accuracy": {
            f: (field_correct[f] / field_total[f] if field_total[f] else 0) for f in FIELDS
        },
        "details": results_log,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/eval.jsonl")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--output", default="eval_results.json")
    parser.add_argument(
        "--reference-date",
        default=None,
        help="Format YYYY-MM-DD. Wajib diisi kalau data eval mengandung tanggal relatif "
        "(kemarin/besok/dll), supaya ground truth bisa dicocokkan dengan benar.",
    )
    args = parser.parse_args()

    ref_date = date.fromisoformat(args.reference_date) if args.reference_date else None
    summary = evaluate(args.data, args.adapter, reference_date=ref_date)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nDetail hasil tersimpan di: {args.output}")