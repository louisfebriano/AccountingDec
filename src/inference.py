"""
Pipeline inference: input kalimat kasual -> output JSON terstruktur.
"""

import warnings
import torch
from . import config
from .model_utils import load_tokenizer, load_model_for_inference
from .prompt_utils import build_inference_prompt
from .postprocess import parse_and_validate
from .validation import validate_transaction_context

# Warning ini harmless: PEFT prompt tuning memang nggak pakai position_ids
# (virtual token nggak punya posisi asli dalam sequence), jadi aman di-suppress.
warnings.filterwarnings(
    "ignore", message="Position ids are not supported for parameter efficient tuning*"
)

_tokenizer = None
_model = None


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
            "data": None,
            "error": f"Input di luar konteks transaksi: {reason}",
            "out_of_context": True,
        }

    tokenizer, model = get_pipeline(adapter_path)

    prompt = build_inference_prompt(user_input)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=config.MAX_NEW_TOKENS,
            do_sample=False,
            tokenizer=tokenizer,
            stop_strings=["\n\n", "\nKalimat"],
        )

    raw_output = tokenizer.decode(
        output_ids[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )

    result = parse_and_validate(raw_output, user_input=user_input, reference_date=reference_date)
    result["raw_output"] = raw_output
    result["out_of_context"] = False
    return result