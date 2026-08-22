"""
Pipeline inference: input kalimat kasual -> output JSON terstruktur.
"""

import json
import warnings
import torch
from . import config
from .model_utils import load_tokenizer, load_model_for_inference
from .prompt_utils import build_inference_prompt
from .postprocess import parse_and_validate
from .price_utils import extract_price_from_text
from .transaction_type import (
    classify_transaction_type,
    is_general_income_transaction,
)
from .validation import validate_transaction_context

# Warning ini harmless: PEFT prompt tuning memang nggak pakai position_ids
# (virtual token nggak punya posisi asli dalam sequence), jadi aman di-suppress.
warnings.filterwarnings(
    "ignore", message="Position ids are not supported for parameter efficient tuning*"
)

_tokenizer = None
_model = None

UNKNOWN_TRANSACTION_TYPE_ERROR = (
    "Jenis transaksi tidak dapat ditentukan. Gunakan konteks pemasukan "
    "atau pengeluaran yang lebih jelas."
)


def _extract_general_income(user_input: str, reference_date=None) -> dict:
    """Selesaikan pemasukan umum secara deterministik tanpa memanggil Llama."""
    total_price = extract_price_from_text(user_input)
    if total_price is None:
        return {
            "success": False,
            "input": user_input,
            "data": None,
            "error": "Nominal pemasukan tidak ditemukan atau formatnya tidak dikenali",
            "raw_output": None,
            "out_of_context": False,
        }

    deterministic_output = json.dumps(
        {
            "item_name": None,
            "quantity": None,
            "unit": None,
            "total_price": total_price,
            "date": None,
        }
    )
    result = parse_and_validate(
        deterministic_output,
        user_input=user_input,
        reference_date=reference_date,
        transaction_type="income",
    )
    return {
        "success": result["success"],
        "input": user_input,
        "data": result["data"],
        "error": result["error"],
        "raw_output": deterministic_output,
        "out_of_context": False,
    }


def get_pipeline(adapter_path: str = None):
    """Load model+tokenizer sekali saja (cache), dipanggil dari API."""
    global _tokenizer, _model
    if _model is None:
        _tokenizer = load_tokenizer()
        _model = load_model_for_inference(adapter_path)
    return _tokenizer, _model


def extract_transaction(user_input: str, adapter_path: str = None, reference_date=None) -> dict:
    # Validasi konteks dulu SEBELUM panggil model -- hemat komputasi kalau kalimatnya
    # jelas bukan transaksi, dan responnya lebih cepat + jelas alasannya ke user.
    is_valid, reason = validate_transaction_context(user_input)
    if not is_valid:
        return {
            "success": False,
            "input": user_input,
            "data": None,
            "error": f"Input di luar konteks transaksi: {reason}",
            "raw_output": None,
            "out_of_context": True,
        }

    transaction_type = classify_transaction_type(user_input)
    if transaction_type == "unknown":
        return {
            "success": False,
            "input": user_input,
            "data": None,
            "error": UNKNOWN_TRANSACTION_TYPE_ERROR,
            "raw_output": None,
            "out_of_context": False,
        }

    if is_general_income_transaction(user_input):
        return _extract_general_income(user_input, reference_date=reference_date)

    tokenizer, model = get_pipeline(adapter_path)

    prompt = build_inference_prompt(user_input)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=config.MAX_NEW_TOKENS,
            do_sample=False,
            tokenizer=tokenizer,
            stop_strings=["\n\n", "\nKalimat", "Kalimat:"],
        )

    raw_output = tokenizer.decode(
        output_ids[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )

    # stop_strings berhenti SETELAH string itu selesai di-generate, tapi teksnya sendiri
    # tetap ikut ke output (tidak otomatis dihapus transformers) -- di-strip di sini
    # biar raw_output rapi, murni kosmetik, tidak mempengaruhi hasil parse.
    stop_strings = ["\n\n", "\nKalimat", "Kalimat:"]
    for stop in stop_strings:
        if raw_output.endswith(stop):
            raw_output = raw_output[: -len(stop)]
            break

    result = parse_and_validate(
        raw_output,
        user_input=user_input,
        reference_date=reference_date,
        transaction_type=transaction_type,
    )
    return {
        "success": result["success"],
        "input": user_input,
        "data": result["data"],
        "error": result["error"],
        "raw_output": raw_output,
        "out_of_context": False,
    }
