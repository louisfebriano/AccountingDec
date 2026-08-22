"""
Evaluasi model pada data eval (idealnya data primer asli dari UMKM).

Metrik yang dihitung:
- JSON validity rate: persentase output yang berhasil diparse jadi JSON valid + lolos schema
- Exact match accuracy: persentase prediksi yang SELURUH field-nya sama persis dengan ground truth
- Field-level precision/recall/F1: per field (item_name, quantity, unit, total_price, date)
- Akurasi transaction_type: hanya untuk contoh yang memiliki label income/expense/unknown

Jalankan:
  python -m src.evaluate --data data/processed/eval.jsonl --adapter adapters/soft-prompt-transaksi

Untuk data eval yang ground truth-nya mengandung tanggal relatif (kemarin/besok/dll)
ATAU kalimat yang sama sekali tidak menyebut tanggal (date: null di file jsonl),
WAJIB set --reference-date sesuai asumsi "hari ini" saat data itu dibuat, contoh:
  python -m src.evaluate --data data/processed/eval.jsonl --reference-date 2026-07-18

Kenapa null di-handle di sini (bukan di-hardcode di file jsonl): sistem selalu
mengisi field "date" dengan reference_date kalau kalimat tidak menyebut tanggal sama
sekali (lihat postprocess.py). Jadi ground truth "date: null" di file jsonl artinya
"seharusnya sama dengan reference_date", dan itu di-resolve di sini, satu tempat,
supaya file eval tidak perlu di-edit ulang tiap kali reference_date berubah.
"""

import argparse
import json
from datetime import date

from .inference import extract_transaction

FIELDS = ["item_name", "quantity", "unit", "total_price", "date"]
TRANSACTION_TYPES = ("income", "expense", "unknown")


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


def resolve_ground_truth_date(ground_truth: dict, reference_date: date) -> dict:
    """
    Kalau ground_truth["date"] masih null, artinya kalimat itu memang tidak menyebut
    tanggal sama sekali -> sistem otomatis mengisi reference_date (lihat postprocess.py).
    Jadi ground truth-nya di-resolve jadi reference_date juga sebelum dibandingkan.
    """
    resolved = dict(ground_truth)
    if resolved.get("date") is None:
        resolved["date"] = reference_date.isoformat()
    return resolved


def evaluate(data_path: str, adapter_path: str = None, reference_date: date = None):
    dataset = load_jsonl(data_path)
    reference_date = reference_date or date.today()

    n_total = len(dataset)
    n_valid_json = 0
    n_exact_match = 0
    n_transaction_type_labeled = 0
    n_transaction_type_correct = 0
    transaction_type_total = {value: 0 for value in TRANSACTION_TYPES}
    transaction_type_correct = {value: 0 for value in TRANSACTION_TYPES}

    # akumulasi TP/FP/FN per field, dihitung sebagai "match" vs "tidak match"
    field_correct = {f: 0 for f in FIELDS}
    field_total = {f: 0 for f in FIELDS}

    results_log = []

    for example in dataset:
        user_input = example["input"]
        ground_truth = resolve_ground_truth_date(example["output"], reference_date)
        ground_truth_type = normalize(ground_truth.get("transaction_type"))
        has_transaction_type_label = ground_truth_type in TRANSACTION_TYPES
        if has_transaction_type_label:
            n_transaction_type_labeled += 1
            transaction_type_total[ground_truth_type] += 1

        result = extract_transaction(
            user_input, adapter_path=adapter_path, reference_date=reference_date
        )

        row = {
            "input": user_input,
            "ground_truth": ground_truth,
            "transaction_type_labeled": has_transaction_type_label,
        }

        if not result["success"]:
            row["prediction"] = None
            row["valid_json"] = False
            row["exact_match"] = False
            if has_transaction_type_label:
                row["transaction_type_match"] = False
            results_log.append(row)
            continue

        n_valid_json += 1
        prediction = result["data"]
        row["prediction"] = prediction
        row["valid_json"] = True

        if has_transaction_type_label:
            predicted_type = normalize(prediction.get("transaction_type"))
            type_match = predicted_type == ground_truth_type
            row["transaction_type_match"] = type_match
            if type_match:
                n_transaction_type_correct += 1
                transaction_type_correct[ground_truth_type] += 1

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
    print("-" * 60)
    print(f"Label transaction_type    : {n_transaction_type_labeled}/{n_total}")
    if n_transaction_type_labeled:
        type_accuracy = n_transaction_type_correct / n_transaction_type_labeled * 100
        print(
            "Akurasi transaction_type  : "
            f"{n_transaction_type_correct}/{n_transaction_type_labeled} "
            f"({type_accuracy:.1f}%)"
        )
    else:
        print("Akurasi transaction_type  : N/A (tidak ada label)")
    for transaction_type in TRANSACTION_TYPES:
        total = transaction_type_total[transaction_type]
        correct = transaction_type_correct[transaction_type]
        accuracy = (correct / total * 100) if total else 0.0
        print(f"  {transaction_type:<15}: {correct}/{total} ({accuracy:.1f}%)")
    print("=" * 60)

    return {
        "n_total": n_total,
        "json_validity_rate": n_valid_json / n_total if n_total else 0,
        "exact_match_accuracy": n_exact_match / n_total if n_total else 0,
        "field_accuracy": {
            f: (field_correct[f] / field_total[f] if field_total[f] else 0) for f in FIELDS
        },
        "transaction_type_evaluation": {
            "labeled_examples": n_transaction_type_labeled,
            "correct": n_transaction_type_correct,
            "accuracy": (
                n_transaction_type_correct / n_transaction_type_labeled
                if n_transaction_type_labeled
                else None
            ),
            "per_type": {
                transaction_type: {
                    "total": transaction_type_total[transaction_type],
                    "correct": transaction_type_correct[transaction_type],
                    "accuracy": (
                        transaction_type_correct[transaction_type]
                        / transaction_type_total[transaction_type]
                        if transaction_type_total[transaction_type]
                        else None
                    ),
                }
                for transaction_type in TRANSACTION_TYPES
            },
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
        help="Format YYYY-MM-DD. Dipakai buat resolve tanggal relatif (kemarin/besok/dll) "
        "DAN buat isi ground truth yang date-nya null (kalimat tanpa keterangan tanggal). "
        "Kalau tidak diisi, default ke tanggal hari ini di komputer kamu.",
    )
    args = parser.parse_args()

    ref_date = date.fromisoformat(args.reference_date) if args.reference_date else None
    summary = evaluate(args.data, args.adapter, reference_date=ref_date)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nDetail hasil tersimpan di: {args.output}")
