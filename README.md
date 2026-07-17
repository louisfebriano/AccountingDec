# Information Extraction Transaksi UMKM Kuliner (Soft Prompt Tuning, Llama 3.1)

## Setup

1. Request akses model di HuggingFace: https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct
2. Login: `huggingface-cli login` (atau isi `HF_TOKEN` di file `.env`, copy dari `.env.example`)
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Cek GPU terbaca:
   ```
   python -c "import torch; print(torch.cuda.is_available())"
   ```

## Struktur

```
skripsi/
├── data/
│   ├── raw/           # data mentah (form/WA dari UMKM asli - dipakai buat evaluasi akhir)
│   └── processed/     # data sintetis siap latih (JSONL) - dipakai buat soft prompt tuning
├── adapters/           # hasil training soft prompt tersimpan di sini
├── src/
│   ├── config.py       # semua setting model & training
│   ├── prompt_utils.py # template few-shot prompt
│   ├── model_utils.py  # load model + setup PEFT prompt tuning
│   ├── train.py        # script training
│   ├── inference.py    # pipeline inference
│   ├── postprocess.py  # validasi JSON output (pydantic)
│   └── api.py           # FastAPI endpoint
└── requirements.txt
```

## Training

1. Siapkan data sintetis di `data/processed/train.jsonl` (format lihat contoh yang sudah ada)
2. Jalankan:
   ```
   python -m src.train
   ```
3. Adapter (soft prompt) hasil training tersimpan di `adapters/soft-prompt-transaksi/`

## Jalankan API

```
uvicorn src.api:app --reload --port 8000
```

Test:
```
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "Kemarin beli Gas 3kg sebanyak 10 tabung, totalnya 180rb"}'
```

## Catatan GPU

Model 8B dengan 4-bit quantization (`USE_4BIT=True` di config) butuh sekitar 6-8GB VRAM untuk inference/training soft prompt (base model dibekukan, cuma virtual token embeddings yang dilatih — jauh lebih ringan dibanding full fine-tuning).
