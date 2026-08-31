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

# ---- Supabase PostgreSQL ----
# Simpan connection string hanya di .env. Untuk FastAPI yang hidup terus-menerus,
# gunakan direct connection atau Supavisor session mode. Transaction mode memakai
# NullPool dan menonaktifkan prepared statements di src.database.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DATABASE_POOL_MODE = os.getenv("DATABASE_POOL_MODE", "session").strip().lower()
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "5"))
DATABASE_CONNECT_TIMEOUT_SECONDS = int(
    os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "10")
)
DATABASE_TRANSACTIONS_TABLE = os.getenv(
    "DATABASE_TRANSACTIONS_TABLE", "transactions"
).strip()
DATABASE_RECEIPTS_TABLE = os.getenv("DATABASE_RECEIPTS_TABLE", "receipts").strip()
DATABASE_RECEIPT_ITEMS_TABLE = os.getenv(
    "DATABASE_RECEIPT_ITEMS_TABLE", "receipt_items"
).strip()
DATABASE_AUDIT_LOGS_TABLE = os.getenv(
    "DATABASE_AUDIT_LOGS_TABLE", "audit_logs"
).strip()

# ---- Supabase Auth ----
# Publishable/anon key digunakan hanya untuk endpoint Auth Supabase. Session token
# disimpan oleh FastAPI pada cookie HttpOnly dan tidak tersedia bagi JavaScript.
SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    os.getenv("NEXT_PUBLIC_SUPABASE_URL", ""),
).strip().rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.getenv(
    "SUPABASE_PUBLISHABLE_KEY",
    os.getenv(
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        os.getenv("SUPABASE_ANON_KEY", ""),
    ),
).strip()
AUTH_ACCESS_COOKIE_NAME = os.getenv(
    "AUTH_ACCESS_COOKIE_NAME", "catatkas_access_token"
).strip()
AUTH_REFRESH_COOKIE_NAME = os.getenv(
    "AUTH_REFRESH_COOKIE_NAME", "catatkas_refresh_token"
).strip()
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {
    "1", "true", "yes", "on"
}
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS = int(
    os.getenv("AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS", "2592000")
)
AUDIT_LOG_ENABLED = os.getenv("AUDIT_LOG_ENABLED", "true").lower() in {
    "1", "true", "yes", "on"
}

# ---- Soft Prompt Tuning (PEFT) ----
NUM_VIRTUAL_TOKENS = 20
PROMPT_TUNING_INIT_TEXT = (
    "Ekstrak informasi transaksi dari kalimat kasual UMKM menjadi JSON terstruktur."
)
ADAPTER_OUTPUT_DIR = "adapters/soft-prompt-transaksi"
SOFT_PROMPT_CONTRACT_VERSION = 2
SOFT_PROMPT_CONTRACT_FILENAME = "catatkas_contract.json"

# ---- Training ----
TRAIN_DATA_PATH = "data/processed/train.jsonl"
TRAIN_AUGMENTATION_DATA_PATH = "data/processed/train-augmentation.jsonl"
TRAIN_VALIDATION_DATA_PATH = os.getenv(
    "TRAIN_VALIDATION_DATA_PATH",
    "data/processed/validation-six-fields.jsonl",
)
EVAL_DATA_PATH = "data/processed/eval-six-fields.jsonl"
TRAIN_REFERENCE_DATE = os.getenv("TRAIN_REFERENCE_DATE", "2026-08-24")
TRAIN_REFERENCE_DATE_VARIANTS = int(os.getenv("TRAIN_REFERENCE_DATE_VARIANTS", "4"))
TRAIN_REFERENCE_DATE_STEP_DAYS = int(
    os.getenv("TRAIN_REFERENCE_DATE_STEP_DAYS", "7")
)
TRAIN_VALIDATION_RATIO = float(os.getenv("TRAIN_VALIDATION_RATIO", "0.1"))
TRAIN_SEED = int(os.getenv("TRAIN_SEED", "42"))
BALANCE_TRANSACTION_TYPES = os.getenv(
    "BALANCE_TRANSACTION_TYPES", "true"
).lower() in {"1", "true", "yes", "on"}
NUM_EPOCHS = 10
LEARNING_RATE = 3e-3
BATCH_SIZE = 1
MAX_SEQ_LENGTH = 256

# ---- Inference ----
MAX_NEW_TOKENS = 256
MODEL_WARMUP_ON_STARTUP = os.getenv("MODEL_WARMUP_ON_STARTUP", "false").lower() in {
    "1", "true", "yes", "on"
}

# ---- Speech-to-text (faster-whisper) ----
# Whisper sengaja berjalan di CPU secara default agar tidak berebut VRAM dengan Llama.
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "id")
WHISPER_VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "true").lower() in {
    "1", "true", "yes", "on",
}

# Batas request audio. Nilai environment variable dinyatakan dalam MB.
AUDIO_MAX_SIZE_MB = int(os.getenv("AUDIO_MAX_SIZE_MB", "10"))
AUDIO_MAX_SIZE_BYTES = AUDIO_MAX_SIZE_MB * 1024 * 1024
VOICE_LLM_NORMALIZATION_ENABLED = os.getenv(
    "VOICE_LLM_NORMALIZATION_ENABLED",
    "true",
).lower() in {"1", "true", "yes", "on"}
VOICE_LLM_NORMALIZATION_MAX_NEW_TOKENS = int(
    os.getenv("VOICE_LLM_NORMALIZATION_MAX_NEW_TOKENS", "96")
)

# ---- Receipt OCR (PaddleOCR) ----
# OCR nota dimuat secara lazy. Paket CPU digunakan agar tidak mengambil VRAM Llama.
RECEIPT_MAX_SIZE_MB = int(os.getenv("RECEIPT_MAX_SIZE_MB", "10"))
RECEIPT_MAX_SIZE_BYTES = RECEIPT_MAX_SIZE_MB * 1024 * 1024
RECEIPT_OCR_LANGUAGE = os.getenv("RECEIPT_OCR_LANGUAGE", "id")
RECEIPT_MIN_CONFIDENCE = float(os.getenv("RECEIPT_MIN_CONFIDENCE", "0.50"))
RECEIPT_MAX_IMAGE_DIMENSION = int(
    os.getenv("RECEIPT_MAX_IMAGE_DIMENSION", "2400")
)
RECEIPT_OCR_TARGET_LONG_EDGE = int(
    os.getenv("RECEIPT_OCR_TARGET_LONG_EDGE", "2000")
)
RECEIPT_MAX_IMAGE_PIXELS = int(os.getenv("RECEIPT_MAX_IMAGE_PIXELS", "25000000"))
RECEIPT_OCR_MULTIPASS = os.getenv("RECEIPT_OCR_MULTIPASS", "true").lower() in {
    "1", "true", "yes", "on",
}
RECEIPT_OCR_COMPACT_FOR_MODEL = os.getenv(
    "RECEIPT_OCR_COMPACT_FOR_MODEL",
    "true",
).lower() in {"1", "true", "yes", "on"}
RECEIPT_OCR_DET_BOX_THRESHOLD = float(
    os.getenv("RECEIPT_OCR_DET_BOX_THRESHOLD", "0.30")
)
RECEIPT_OCR_DROP_SCORE = float(os.getenv("RECEIPT_OCR_DROP_SCORE", "0.25"))

# ---- Receipt Soft Prompt (Llama + OCR text) ----
# Adapter nota terpisah dari adapter transaksi dan dimuat lazy pada base model yang sama.
RECEIPT_ADAPTER_OUTPUT_DIR = os.getenv(
    "RECEIPT_ADAPTER_OUTPUT_DIR",
    "adapters/soft-prompt-nota",
)
RECEIPT_TRAIN_DATA_PATH = os.getenv(
    "RECEIPT_TRAIN_DATA_PATH",
    "data/processed/receipt-train.jsonl",
)
RECEIPT_VALIDATION_DATA_PATH = os.getenv(
    "RECEIPT_VALIDATION_DATA_PATH",
    "data/processed/receipt-validation.jsonl",
)
RECEIPT_EVAL_DATA_PATH = os.getenv(
    "RECEIPT_EVAL_DATA_PATH",
    "data/processed/receipt-eval.jsonl",
)
RECEIPT_SOFT_PROMPT_CONTRACT_VERSION = int(
    os.getenv("RECEIPT_SOFT_PROMPT_CONTRACT_VERSION", "1")
)
RECEIPT_LLM_ENABLED = os.getenv("RECEIPT_LLM_ENABLED", "true").lower() in {
    "1", "true", "yes", "on",
}
RECEIPT_RULE_FALLBACK_ENABLED = os.getenv(
    "RECEIPT_RULE_FALLBACK_ENABLED",
    "true",
).lower() in {"1", "true", "yes", "on"}
RECEIPT_PROMPT_TUNING_INIT_TEXT = os.getenv(
    "RECEIPT_PROMPT_TUNING_INIT_TEXT",
    "Ekstrak teks OCR nota UMKM menjadi satu JSON nota terstruktur tanpa mengarang data.",
)
RECEIPT_MAX_SEQ_LENGTH = int(os.getenv("RECEIPT_MAX_SEQ_LENGTH", "768"))
RECEIPT_MAX_NEW_TOKENS = int(os.getenv("RECEIPT_MAX_NEW_TOKENS", "768"))
RECEIPT_TRAIN_BATCH_SIZE = int(os.getenv("RECEIPT_TRAIN_BATCH_SIZE", "1"))
RECEIPT_GRADIENT_ACCUMULATION_STEPS = int(
    os.getenv("RECEIPT_GRADIENT_ACCUMULATION_STEPS", "8")
)
RECEIPT_MIN_FREE_GPU_GB = float(os.getenv("RECEIPT_MIN_FREE_GPU_GB", "4.5"))
