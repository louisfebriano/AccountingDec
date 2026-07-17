"""
API untuk ekstraksi transaksi UMKM.

Jalankan: uvicorn src.api:app --reload --port 8000
"""

from fastapi import FastAPI
from pydantic import BaseModel

from .inference import extract_transaction

app = FastAPI(title="UMKM Transaksi Extraction API")


class ExtractRequest(BaseModel):
    text: str


@app.on_event("startup")
def warmup():
    # load model sekali saja saat server start, biar request pertama tidak lambat
    from .inference import get_pipeline
    get_pipeline()


@app.post("/extract")
def extract(req: ExtractRequest):
    result = extract_transaction(req.text)
    return result


@app.get("/health")
def health():
    return {"status": "ok"}
