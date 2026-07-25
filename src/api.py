"""
uvicorn src.api:app --reload --port 8000
"""

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .inference import extract_transaction

app = FastAPI(title="UMKM Transaksi Extraction API")


class ExtractRequest(BaseModel):
    text: str
    reference_date: Optional[str] = None


@app.on_event("startup")
def warmup():
    from .inference import get_pipeline
    get_pipeline()


@app.post("/extract")
def extract(req: ExtractRequest):
    reference_date = date.fromisoformat(req.reference_date) if req.reference_date else None
    result = extract_transaction(req.text, reference_date=reference_date)

    if result.get("out_of_context"):
        raise HTTPException(status_code=422, detail=result["error"])

    return result


@app.get("/health")
def health():
    return {"status": "ok"}