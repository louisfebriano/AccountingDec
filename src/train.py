"""
Training soft prompt tuning.

Format data (JSONL), tiap baris:
{"input": "kalimat kasual", "output": {"item_name": ..., "quantity": ..., "unit": ..., "total_price": ..., "date": ...}}

Jalankan: python -m src.train
"""

import json
from datasets import Dataset
from transformers import TrainingArguments, Trainer, DataCollatorForLanguageModeling

from . import config
from .model_utils import load_tokenizer, load_model_for_training
from .prompt_utils import build_inference_prompt, _dict_to_json_str


def load_jsonl(path: str) -> list:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def format_example(example: dict, tokenizer):
    """Gabungkan prompt (tanpa few-shot examples, karena konteksnya sudah ada di soft prompt) + target JSON."""
    prompt = build_inference_prompt(example["input"])
    target = _dict_to_json_str(example["output"])
    full_text = f"{prompt} {target}{tokenizer.eos_token}"

    tokenized = tokenizer(
        full_text,
        truncation=True,
        max_length=config.MAX_SEQ_LENGTH,
        padding="max_length",
    )
    tokenized["labels"] = tokenized["input_ids"].copy()
    return tokenized


def main():
    tokenizer = load_tokenizer()
    model = load_model_for_training()

    train_raw = load_jsonl(config.TRAIN_DATA_PATH)
    train_dataset = Dataset.from_list(train_raw)
    train_dataset = train_dataset.map(
        lambda ex: format_example(ex, tokenizer), remove_columns=train_dataset.column_names
    )

    eval_dataset = None
    try:
        eval_raw = load_jsonl(config.EVAL_DATA_PATH)
        eval_dataset = Dataset.from_list(eval_raw)
        eval_dataset = eval_dataset.map(
            lambda ex: format_example(ex, tokenizer), remove_columns=eval_dataset.column_names
        )
    except FileNotFoundError:
        print("Eval data tidak ditemukan, lanjut tanpa evaluasi selama training.")

    training_args = TrainingArguments(
        output_dir="checkpoints",
        num_train_epochs=config.NUM_EPOCHS,
        per_device_train_batch_size=config.BATCH_SIZE,
        gradient_accumulation_steps=4,  # simulasikan batch lebih besar tanpa nambah VRAM
        gradient_checkpointing=True,
        learning_rate=config.LEARNING_RATE,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if eval_dataset else "no",
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    trainer.train()
    model.save_pretrained(config.ADAPTER_OUTPUT_DIR)
    tokenizer.save_pretrained(config.ADAPTER_OUTPUT_DIR)
    print(f"Soft prompt adapter tersimpan di: {config.ADAPTER_OUTPUT_DIR}")


if __name__ == "__main__":
    main()