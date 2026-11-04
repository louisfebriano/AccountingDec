"""
Pipeline inference: input kalimat kasual -> output JSON terstruktur.
"""

import json
import warnings
from datetime import date
from threading import Lock, RLock

from . import config
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
_pipeline_lock = Lock()
_generation_lock = RLock()

TRANSACTION_ADAPTER_NAME = "default"
RECEIPT_ADAPTER_NAME = "receipt"

UNKNOWN_TRANSACTION_TYPE_ERROR = (
    "Jenis transaksi tidak dapat ditentukan. Gunakan konteks pemasukan "
    "atau pengeluaran yang lebih jelas."
)
GENERATION_STOP_STRINGS = [".Kalimat:", "\n\n", "\nKalimat", "Kalimat:"]
# Soft Prompt Nota kadang mengulang penanda prompt setelah objek JSON selesai.
# JSON satu baris tidak pernah memuat newline mentah, jadi penanda ini aman
# dipakai sebagai batas berhenti tanpa memotong output yang sah.
RECEIPT_GENERATION_STOP_STRINGS = [
    "\nJSON",
    "\nINSTRUCTION:",
    "\nREFERENCE_DATE:",
    "\nOCR_TEXT:",
]


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
        with _pipeline_lock:
            if _model is None:
                # Import berat (torch/transformers/peft) sengaja dilakukan di sini agar
                # server tanpa GPU tetap bisa mengimpor src.api untuk mode proxy AI.
                from .model_utils import load_model_for_inference, load_tokenizer

                _tokenizer = load_tokenizer()
                _model = load_model_for_inference(adapter_path)
    return _tokenizer, _model


def _ensure_adapter_loaded(model, adapter_name: str, adapter_path: str | None) -> None:
    """Muat adapter tambahan satu kali pada PeftModel yang sama."""
    peft_config = getattr(model, "peft_config", {})
    if adapter_name in peft_config:
        return
    if adapter_name == TRANSACTION_ADAPTER_NAME:
        return
    if not adapter_path:
        raise RuntimeError(f"Path adapter {adapter_name} tidak diberikan.")
    load_adapter = getattr(model, "load_adapter", None)
    if load_adapter is None:
        raise RuntimeError("Model aktif tidak mendukung multi-adapter PEFT.")
    load_adapter(adapter_path, adapter_name=adapter_name)


def generate_with_adapter(
    prompt: str,
    *,
    adapter_name: str,
    adapter_path: str | None = None,
    transaction_adapter_path: str | None = None,
    max_new_tokens: int | None = None,
    stop_strings: list[str] | None = None,
) -> str:
    """Pilih adapter dan generate secara atomik agar request tidak tertukar."""
    import torch

    with _generation_lock:
        tokenizer, model = get_pipeline(transaction_adapter_path)
        _ensure_adapter_loaded(model, adapter_name, adapter_path)
        set_adapter = getattr(model, "set_adapter", None)
        if set_adapter is not None:
            set_adapter(adapter_name, inference_mode=True)
        elif adapter_name != TRANSACTION_ADAPTER_NAME:
            raise RuntimeError("Model aktif tidak dapat memilih adapter nota.")

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        generation_options = {
            "max_new_tokens": max_new_tokens or config.MAX_NEW_TOKENS,
            "do_sample": False,
        }
        if stop_strings:
            generation_options.update(
                tokenizer=tokenizer,
                stop_strings=stop_strings,
            )

        with torch.no_grad():
            output_ids = model.generate(**inputs, **generation_options)

        raw_output = tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        for stop in stop_strings or []:
            if raw_output.endswith(stop):
                raw_output = raw_output[: -len(stop)]
                break
        return raw_output.strip()


def generate_with_base_model(
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int,
    transaction_adapter_path: str | None = None,
) -> str:
    """Generate chat Llama dasar tanpa Soft Prompt pada model cache yang sama."""
    import torch

    with _generation_lock:
        tokenizer, model = get_pipeline(transaction_adapter_path)
        disable_adapter = getattr(model, "disable_adapter", None)
        if not callable(disable_adapter):
            raise RuntimeError("Model aktif tidak mendukung inferensi tanpa adapter.")

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with disable_adapter(), torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        return tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        ).strip()


def extract_transaction(user_input: str, adapter_path: str = None, reference_date=None) -> dict:
    """Ubah satu kalimat kasual menjadi satu transaksi terstruktur.

    Urutan pengecekan, dari yang paling murah ke yang paling mahal:

    1. Konteks: kalimat harus memuat angka dan kata transaksi/pola harga.
    2. Arah transaksi: classifier rule-based menentukan income/expense. Nilai
       ``unknown`` langsung menghentikan pipeline sehingga model tidak dimuat.
    3. Pemasukan umum tanpa rincian barang diselesaikan tanpa model.
    4. Prompt dikirim ke Llama + Soft Prompt transaksi.
    5. Output model dirapikan dan divalidasi oleh ``parse_and_validate``.

    Return ``{"success", "input", "data", "error", "raw_output", "out_of_context"}``.
    """
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

    effective_reference_date = reference_date or date.today()
    prompt = build_inference_prompt(user_input, effective_reference_date)
    raw_output = generate_with_adapter(
        prompt,
        adapter_name=TRANSACTION_ADAPTER_NAME,
        transaction_adapter_path=adapter_path,
        max_new_tokens=config.MAX_NEW_TOKENS,
        stop_strings=GENERATION_STOP_STRINGS,
    )

    result = parse_and_validate(
        raw_output,
        user_input=user_input,
        reference_date=effective_reference_date,
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
