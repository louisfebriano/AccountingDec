"""
Load base model (Llama 3.1) dan setup PEFT Prompt Tuning.
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import (
    PromptTuningConfig,
    PromptTuningInit,
    TaskType,
    get_peft_model,
    PeftModel,
)

from . import config


def load_tokenizer():
    tokenizer = AutoTokenizer.from_pretrained(
        config.BASE_MODEL_NAME, token=config.HF_TOKEN
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def load_base_model():
    quant_config = None
    if config.USE_4BIT:
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    model = AutoModelForCausalLM.from_pretrained(
        config.BASE_MODEL_NAME,
        token=config.HF_TOKEN,
        quantization_config=quant_config,
        device_map={"": 0},  # paksa semua ke GPU 0, hindari auto-offload ke CPU
    )
    return model


def load_model_for_training():
    """Base model dibekukan (frozen), hanya soft prompt (virtual tokens) yang dilatih."""
    model = load_base_model()
    model.enable_input_require_grads()  # perlu untuk gradient checkpointing + base model frozen

    peft_config = PromptTuningConfig(
        task_type=TaskType.CAUSAL_LM,
        prompt_tuning_init=PromptTuningInit.TEXT,
        num_virtual_tokens=config.NUM_VIRTUAL_TOKENS,
        prompt_tuning_init_text=config.PROMPT_TUNING_INIT_TEXT,
        tokenizer_name_or_path=config.BASE_MODEL_NAME,
    )

    peft_model = get_peft_model(model, peft_config)
    peft_model.print_trainable_parameters()
    return peft_model


def load_model_for_inference(adapter_path: str = None):
    """Load base model + soft prompt adapter hasil training untuk inference."""
    model = load_base_model()
    adapter_path = adapter_path or config.ADAPTER_OUTPUT_DIR
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()
    return model