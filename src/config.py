"""
Konfigurasi utama untuk project.
Ubah nilai-nilai di bawah sesuai kebutuhan/hasil eksperimen.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---- Model ----
# Model gated di HuggingFace. Sebelum pakai:
# 1. Request akses di https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct
# 2. huggingface-cli login (pakai token dari https://huggingface.co/settings/tokens)
# Catatan: dipilih varian 3B (bukan 8B) karena disesuaikan dengan VRAM GPU lokal (6GB).
BASE_MODEL_NAME = "meta-llama/Llama-3.2-3B-Instruct"
HF_TOKEN = os.getenv("HF_TOKEN")  # optional kalau sudah login via huggingface-cli

# Quantization (biar muat di GPU lokal, misal 8GB-12GB VRAM)
USE_4BIT = True

# ---- Soft Prompt Tuning (PEFT) ----
NUM_VIRTUAL_TOKENS = 20
PROMPT_TUNING_INIT_TEXT = (
    "Ekstrak informasi transaksi dari kalimat kasual UMKM menjadi JSON terstruktur."
)
ADAPTER_OUTPUT_DIR = "adapters/soft-prompt-transaksi"

# ---- Training ----
TRAIN_DATA_PATH = "data/processed/train.jsonl"
EVAL_DATA_PATH = "data/processed/eval.jsonl"
NUM_EPOCHS = 10
LEARNING_RATE = 3e-3
BATCH_SIZE = 1
MAX_SEQ_LENGTH = 256

# ---- Inference ----
MAX_NEW_TOKENS = 256
