"""Konstruksi prompt untuk training, inference, dan baseline evaluasi."""

from datetime import date
from typing import Any

INSTRUCTION = (
    "Kamu adalah asisten pencatat transaksi UMKM. "
    "Ekstrak informasi dari kalimat kasual menjadi JSON dengan field: "
    "item_name, quantity, unit, total_price, date, transaction_type. "
    "Jika informasi tidak ada, isi dengan null. Jawab HANYA dengan JSON, tanpa teks lain."
)

EXPLICIT_EVALUATION_INSTRUCTION = (
    "Kamu adalah asisten pencatat transaksi UMKM kuliner. Ekstrak tepat satu "
    "transaksi dari kalimat pengguna. Jawab hanya dengan satu objek JSON valid "
    "tanpa markdown atau penjelasan, menggunakan tepat field item_name, quantity, "
    "unit, total_price, date, dan transaction_type. Gunakan null untuk item_name, "
    "quantity, atau unit yang tidak disebutkan. total_price harus berupa angka "
    "rupiah. date wajib berformat YYYY-MM-DD. Gunakan hanya REFERENCE_DATE yang "
    "diberikan, bukan tanggal sistem: selesaikan tanggal relatif terhadapnya dan "
    "salin REFERENCE_DATE persis jika tanggal tidak disebutkan. transaction_type "
    "wajib expense untuk beli, belanja, kulakan, restok, atau biaya; wajib income "
    "untuk jual, terjual, laku, pembayaran pelanggan, atau pemasukan. Nilainya hanya "
    "boleh income atau expense. Periksa kembali date dan transaction_type sebelum "
    "menjawab."
)

FEW_SHOT_EXAMPLES = [
    {
        "input": "Kemarin beli Gas 3kg sebanyak 10 tabung, totalnya 180rb",
        "output": {
            "item_name": "Gas 3kg",
            "quantity": 10,
            "unit": "tabung",
            "total_price": 180000,
            "date": None,
        },
    },
    {
        "input": "Hari Rabu 1 Juli  , restock susu kaleng 1 dus dengan total harga 200k",
        "output": {
            "item_name": "Susu kaleng",
            "quantity": 1,
            "unit": "dus",
            "total_price": 200000,
            "date": "2026-07-01",
        },
    },
]


def build_inference_prompt(user_input: str, reference_date: date) -> str:
    """
    Prompt Soft Prompt enam field yang identik saat training dan inference.

    Reference date menjadi input eksplisit agar adapter dapat mempelajari tanggal relatif
    tanpa bergantung pada tanggal mesin yang menjalankan model.
    """
    return (
        f"REFERENCE_DATE: {reference_date.isoformat()}\n"
        f"Kalimat: {user_input}\nJSON:"
    )


def build_explicit_instruction_prompt(
    tokenizer: Any,
    user_input: str,
    reference_date: date,
) -> str:
    """Bangun baseline standalone melalui chat template resmi tokenizer Llama."""
    messages = [
        {
            "role": "system",
            "content": EXPLICIT_EVALUATION_INSTRUCTION,
        },
        {
            "role": "user",
            "content": (
                f"REFERENCE_DATE: {reference_date.isoformat()}\n"
                f"TRANSACTION_TEXT: {user_input}"
            ),
        },
    ]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


def build_prompt(user_input: str, examples: list = None) -> str:
    """Bangun prompt few-shot lengkap untuk satu input kasual."""
    examples = examples if examples is not None else FEW_SHOT_EXAMPLES

    example_blocks = []
    for ex in examples:
        example_blocks.append(
            f"Kalimat: {ex['input']}\nJSON: {_dict_to_json_str(ex['output'])}"
        )

    prompt = (
        f"{INSTRUCTION}\n\n"
        + "\n\n".join(example_blocks)
        + f"\n\nKalimat: {user_input}\nJSON:"
    )
    return prompt


def _dict_to_json_str(d: dict) -> str:
    import json

    return json.dumps(d, ensure_ascii=False)
