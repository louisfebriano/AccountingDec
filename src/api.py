"""
uvicorn src.api:app --reload --port 8000
"""

import logging
import re
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.staticfiles import StaticFiles

from . import config
from .audio_service import transcribe_audio
from .number_utils import normalize_indonesian_numbers

# Pakai logger Uvicorn agar log INFO aplikasi tampil pada terminal API secara default.
logger = logging.getLogger("uvicorn.error")

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}
AUDIO_CONTENT_TYPE_SUFFIXES = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "video/mp4": ".m4a",
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/ogg": ".ogg",
    "application/ogg": ".ogg",
}
_REFERENCE_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

app = FastAPI(title="CatatKas API")
PWA_DIR = Path(__file__).resolve().parent.parent / "pwa"


class ExtractRequest(BaseModel):
    text: str
    reference_date: Optional[str] = None


def extract_transaction(user_input: str, adapter_path: str = None, reference_date=None) -> dict:
    """Delegasikan ekstraksi ke pipeline Llama yang sudah ada secara lazy."""
    from .inference import extract_transaction as run_extraction

    return run_extraction(
        user_input,
        adapter_path=adapter_path,
        reference_date=reference_date,
    )


def _parse_reference_date(value: Optional[str]) -> Optional[date]:
    """Validasi tanggal referensi form dengan format YYYY-MM-DD."""
    if value is None or value == "":
        return None
    if not _REFERENCE_DATE_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail="reference_date harus menggunakan format YYYY-MM-DD",
        )
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="reference_date bukan tanggal yang valid",
        ) from None


def _resolve_audio_suffix(file: UploadFile) -> str:
    """Validasi format upload tanpa memakai nama pengguna sebagai path."""
    extension = Path(file.filename or "").suffix.lower()
    if extension in SUPPORTED_AUDIO_EXTENSIONS:
        return extension

    suffix = AUDIO_CONTENT_TYPE_SUFFIXES.get((file.content_type or "").lower())
    if suffix:
        return suffix
    raise HTTPException(
        status_code=415,
        detail="Format audio tidak didukung. Gunakan WAV, MP3, M4A, WEBM, atau OGG.",
    )


def _delete_temp_file(path: Path) -> None:
    """Hapus file audio sementara tanpa menutupi hasil request."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("File audio sementara tidak dapat dihapus: %s", path)


async def _save_upload_to_temp(file: UploadFile, suffix: str) -> Path:
    """Salin upload terbatas ukuran ke file sementara bernama acak."""
    temp_path: Optional[Path] = None
    total_size = 0
    try:
        with tempfile.NamedTemporaryFile(
            prefix="umkm-audio-",
            suffix=suffix,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > config.AUDIO_MAX_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Ukuran audio maksimal {config.AUDIO_MAX_SIZE_MB} MB",
                    )
                temp_file.write(chunk)
    except BaseException:
        if temp_path is not None:
            _delete_temp_file(temp_path)
        raise

    if total_size == 0:
        if temp_path is not None:
            _delete_temp_file(temp_path)
        raise HTTPException(status_code=400, detail="File audio kosong")

    if temp_path is None:
        raise HTTPException(status_code=500, detail="Audio gagal diproses")
    return temp_path


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


@app.post("/extract/audio")
async def extract_audio(
    file: UploadFile = File(...),
    reference_date: Optional[str] = Form(None),
):
    """Transkripsikan satu rekaman dan ekstrak satu transaksi terstruktur."""
    parsed_reference_date = _parse_reference_date(reference_date)
    suffix = _resolve_audio_suffix(file)
    temp_path: Optional[Path] = None
    request_id = uuid.uuid4().hex[:8]

    try:
        temp_path = await _save_upload_to_temp(file, suffix)
        transcript = await run_in_threadpool(transcribe_audio, temp_path)
        transcript = transcript.strip()
        logger.info("[voice:%s] transcript=%r", request_id, transcript)
        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="Tidak ditemukan ucapan yang dapat dikenali pada audio",
            )

        normalized_text = normalize_indonesian_numbers(transcript)
        logger.info("[voice:%s] normalized_text=%r", request_id, normalized_text)
        result = await run_in_threadpool(
            extract_transaction,
            normalized_text,
            reference_date=parsed_reference_date,
        )
        logger.info(
            "[voice:%s] extraction success=%s out_of_context=%s data=%r error=%r",
            request_id,
            result.get("success", False),
            result.get("out_of_context", False),
            result.get("data"),
            result.get("error"),
        )

        if result.get("out_of_context"):
            raise HTTPException(status_code=422, detail=result["error"])

        return {
            "success": result.get("success", False),
            "source": "voice",
            "transcript": transcript,
            "normalized_text": normalized_text,
            "data": result.get("data"),
            "error": result.get("error"),
            "out_of_context": result.get("out_of_context", False),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Pemrosesan input audio gagal")
        raise HTTPException(
            status_code=500,
            detail="Audio gagal diproses. Silakan coba lagi.",
        ) from None
    finally:
        if temp_path is not None:
            _delete_temp_file(temp_path)


@app.get("/health")
def health():
    return {"status": "ok"}


# Mount terakhir agar route API di atas tetap memiliki prioritas dan tidak tertutup
# fallback HTML milik PWA.
app.mount("/", StaticFiles(directory=PWA_DIR, html=True), name="pwa")
