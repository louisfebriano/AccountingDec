"""
Pipeline inference: input kalimat kasual -> output JSON terstruktur.
"""

import torch
from . import config
from .model_utils import load_tokenizer, load_model_for_inference
from .prompt_utils import build_inference_prompt
from .postprocess import parse_and_validate

_tokenizer = None
_model = None


def get_pipeline(adapter_path: str = None):
    """Load model+tokenizer sekali saja (cache), dipanggil dari API."""
    global _tokenizer, _model
    if _model is None:
        _tokenizer = load_tokenizer()
        _model = load_model_for_inference(adapter_path)
    return _tokenizer, _model


def extract_transaction(user_input: str, adapter_path: str = None) -> dict:
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

    result = parse_and_validate(raw_output)
    result["raw_output"] = raw_output
    return result