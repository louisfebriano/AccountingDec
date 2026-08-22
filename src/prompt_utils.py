"""
Konstruksi prompt template (few-shot) untuk task ekstraksi transaksi.
"""

INSTRUCTION = (
    "Kamu adalah asisten pencatat transaksi UMKM. "
    "Ekstrak informasi dari kalimat kasual menjadi JSON dengan field: "
    "item_name, quantity, unit, total_price, date. "
    "Jika informasi tidak ada, isi dengan null. Jawab HANYA dengan JSON, tanpa teks lain."
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


def build_inference_prompt(user_input: str) -> str:
    """
    Prompt polos (TANPA few-shot examples) yang dipakai baik saat training maupun inference.
    Instruksi/pola task sudah "tertanam" di soft prompt (virtual tokens) hasil training,
    jadi prompt di sini harus PERSIS sama strukturnya dengan yang dipakai di train.py.
    """
    return f"Kalimat: {user_input}\nJSON:"


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