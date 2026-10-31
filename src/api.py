"""
uvicorn src.api:app --reload --port 8000
"""

import hmac
import logging
import re
import tempfile
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from . import ai_proxy, config
from .ai_proxy import AIServiceTimeoutError, AIServiceUnavailableError
from .audio_service import transcribe_audio
from .audit_service import AuditSchemaError, get_audit_log_repository
from .auth_service import (
    AuthConfigurationError,
    AuthServiceError,
    AuthenticatedUser,
    auth_is_configured,
    get_user as get_supabase_user,
    login as login_supabase_user,
    logout as logout_supabase_user,
    refresh as refresh_supabase_session,
    register as register_supabase_user,
)
from .number_utils import normalize_voice_transaction_text
from .receipt_service import (
    InvalidReceiptImageError,
    ReceiptOcrUnavailableError,
    extract_receipt,
    validate_receipt_image,
)
from .receipt_inference import (
    ReceiptInferenceError,
    extract_receipt_with_llama,
)
from .receipt_validation import fallback_validation, validate_receipt_semantics
from .database import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    database_is_configured,
)
from .transaction_repository import (
    DatabaseSchemaError,
    TransactionConflictError,
    TransactionNotFoundError,
    get_transaction_repository,
)
from .transaction_schema import TransactionCreate, TransactionImport, TransactionUpdate
from .voice_log import log_voice_event
from .voice_normalization import correct_voice_transcript_with_llama

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
_AUDIT_OCR_TEXT_LIMIT = 20_000
RECEIPT_EXTENSION_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
RECEIPT_CONTENT_TYPE_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}

app = FastAPI(title="CatatKas API")
PWA_DIR = Path(__file__).resolve().parent.parent / "pwa"


class ExtractRequest(BaseModel):
    text: str
    reference_date: Optional[str] = None


class AuthCredentials(BaseModel):
    """Email dan password hanya digunakan selama request autentikasi."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


def _safe_audit_error_message(detail: object, status_code: int) -> str:
    """Bentuk pesan audit ringkas tanpa menyalin body atau detail validasi."""
    if isinstance(detail, str) and detail.strip():
        return detail.strip()[:500]
    if status_code == 422:
        return "Request tidak valid."
    return f"Request gagal dengan status HTTP {status_code}."


def _merge_audit_metadata(request: Request | None, **values: object) -> None:
    """Gabungkan metadata audit tanpa menghapus identitas dari dependency auth."""
    if request is None:
        return
    metadata = dict(getattr(request.state, "audit_metadata", {}) or {})
    metadata.update(values)
    request.state.audit_metadata = metadata


def _limited_audit_text(value: object, limit: int = _AUDIT_OCR_TEXT_LIMIT) -> tuple[str, bool]:
    """Batasi teks audit besar dan tandai jika isinya dipotong."""
    text = str(value or "")
    return text[:limit], len(text) > limit


@app.exception_handler(StarletteHTTPException)
async def audited_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    """Simpan pesan HTTP yang aman agar dapat dipakai audit middleware."""
    request.state.audit_error_message = _safe_audit_error_message(
        exc.detail,
        exc.status_code,
    )
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def audited_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """Audit kegagalan validasi tanpa menyalin nilai input pengguna."""
    request.state.audit_error_message = "Request tidak valid."
    return await request_validation_exception_handler(request, exc)


def _auth_http_error(exc: Exception) -> HTTPException:
    """Petakan kegagalan Supabase Auth ke pesan API yang aman."""
    if isinstance(exc, AuthConfigurationError):
        return HTTPException(
            status_code=503,
            detail="Supabase Auth belum dikonfigurasi pada server.",
        )
    if isinstance(exc, AuthServiceError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    return HTTPException(
        status_code=503,
        detail="Layanan autentikasi tidak dapat dijangkau.",
    )


def _cookie_samesite() -> str:
    return (
        config.AUTH_COOKIE_SAMESITE
        if config.AUTH_COOKIE_SAMESITE in {"lax", "strict", "none"}
        else "lax"
    )


def _set_session_cookies(response: Response, session: dict) -> None:
    """Simpan session Supabase pada cookie HttpOnly first-party."""
    access_token = str(session.get("access_token") or "")
    refresh_token = str(session.get("refresh_token") or "")
    if not access_token or not refresh_token:
        return
    try:
        access_max_age = max(int(session.get("expires_in") or 3600), 60)
    except (TypeError, ValueError):
        access_max_age = 3600
    common = {
        "httponly": True,
        "secure": config.AUTH_COOKIE_SECURE,
        "samesite": _cookie_samesite(),
        "path": "/",
    }
    response.set_cookie(
        config.AUTH_ACCESS_COOKIE_NAME,
        access_token,
        max_age=access_max_age,
        **common,
    )
    response.set_cookie(
        config.AUTH_REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=max(config.AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS, 3600),
        **common,
    )


def _clear_session_cookies(response: Response) -> None:
    """Hapus kedua cookie session untuk logout lokal yang deterministik."""
    common = {
        "httponly": True,
        "secure": config.AUTH_COOKIE_SECURE,
        "samesite": _cookie_samesite(),
        "path": "/",
    }
    response.delete_cookie(config.AUTH_ACCESS_COOKIE_NAME, **common)
    response.delete_cookie(config.AUTH_REFRESH_COOKIE_NAME, **common)


async def require_authenticated_user(request: Request) -> AuthenticatedUser:
    """Validasi cookie access token dan pasang user_id untuk audit middleware."""
    # Layanan AI di laptop menerima request dari server publik (Render) yang sudah
    # memvalidasi session Supabase. Token ini hanya aktif bila diisi pada laptop.
    internal_token = request.headers.get(ai_proxy.INTERNAL_TOKEN_HEADER)
    expected_token = config.AI_TRUST_INTERNAL_TOKEN
    if (
        expected_token
        and internal_token
        and hmac.compare_digest(internal_token, expected_token)
    ):
        return AuthenticatedUser(id="ai-internal-service", email=None)

    access_token = request.cookies.get(config.AUTH_ACCESS_COOKIE_NAME)
    if not access_token:
        raise HTTPException(status_code=401, detail="Silakan login terlebih dahulu.")
    try:
        user = await get_supabase_user(access_token)
    except (AuthConfigurationError, AuthServiceError) as exc:
        raise _auth_http_error(exc) from None
    request.state.audit_user_id = user.id
    request.state.audit_metadata = {"user_email": user.email}
    return user


def _should_audit(path: str) -> bool:
    """Audit fitur backend tanpa membanjiri tabel dengan aset CSS/JS/icon."""
    return path.startswith(("/auth", "/transactions", "/extract", "/health"))


def _write_audit_log(**values) -> None:
    """Tulis audit tanpa membuat fitur utama gagal jika log bermasalah."""
    try:
        get_audit_log_repository().record(**values)
    except (AuditSchemaError, DatabaseNotConfiguredError, DatabaseUnavailableError):
        logger.exception("Audit log CatatKas gagal disimpan")


def _append_background_task(response: Response, task: BackgroundTask) -> None:
    """Tambahkan tugas audit tanpa menimpa background task milik respons."""
    if response.background is None:
        response.background = task
        return
    response.background = BackgroundTasks([response.background, task])


@app.middleware("http")
async def audit_backend_request(request: Request, call_next):
    """Catat hasil seluruh fitur backend ke satu tabel audit_logs."""
    started_at = time.perf_counter()
    response = await call_next(request)
    if not (
        config.AUDIT_LOG_ENABLED
        and database_is_configured()
        and _should_audit(request.url.path)
    ):
        return response

    route = request.scope.get("route")
    event_type = getattr(route, "name", None) or (
        f"{request.method.lower()}:{request.url.path}"
    )
    metadata = dict(getattr(request.state, "audit_metadata", {}) or {})
    metadata.update(
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        query_parameter_names=sorted(request.query_params.keys()),
    )
    if response.status_code >= 400:
        metadata["error_message"] = getattr(
            request.state,
            "audit_error_message",
            f"Request gagal dengan status HTTP {response.status_code}.",
        )
    _append_background_task(
        response,
        BackgroundTask(
            _write_audit_log,
            event_type=event_type,
            status="success" if response.status_code < 400 else "failure",
            user_id=getattr(request.state, "audit_user_id", None),
            entity_type=getattr(request.state, "audit_entity_type", None),
            entity_id=getattr(request.state, "audit_entity_id", None),
            http_method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            metadata=metadata,
        ),
    )
    return response


def _receipt_response_data(
    semantic_data: dict,
    rule_result: dict,
    validation: dict,
) -> dict:
    """Bangun hasil nota minimum untuk diedit pengguna sebelum disimpan."""
    receipt = {
        "merchant_name": semantic_data.get("merchant_name"),
        "total": semantic_data.get("total"),
        "items": semantic_data.get("items") or [],
        "warnings": validation["warnings"],
    }
    return {
        "item_name": None,
        "quantity": None,
        "unit": None,
        "total_price": semantic_data.get("total"),
        "date": semantic_data.get("date"),
        "transaction_type": "expense",
        "receipt": receipt,
    }


def _fallback_receipt_response_data(rule_result: dict, validation: dict) -> dict:
    """Bangun respons kompatibel dengan penanda fallback yang tidak ambigu."""
    parsed_receipt = rule_result["receipt"]
    receipt = {
        "merchant_name": parsed_receipt.get("merchant_name"),
        "total": parsed_receipt.get("total"),
        "items": parsed_receipt.get("items") or [],
        "warnings": validation["warnings"],
    }
    return {
        "item_name": None,
        "quantity": None,
        "unit": None,
        "total_price": receipt.get("total"),
        "date": rule_result.get("date"),
        "transaction_type": "expense",
        "receipt": receipt,
    }


def extract_transaction(user_input: str, adapter_path: str = None, reference_date=None) -> dict:
    """Delegasikan ekstraksi ke pipeline Llama yang sudah ada secara lazy."""
    from .inference import extract_transaction as run_extraction

    return run_extraction(
        user_input,
        adapter_path=adapter_path,
        reference_date=reference_date,
    )


async def _relay_ai_response(call) -> JSONResponse:
    """Teruskan respons layanan AI lokal apa adanya agar kontrak PWA tidak berubah."""
    try:
        result = await call
    except AIServiceTimeoutError:
        logger.warning("Layanan AI lokal tidak merespons tepat waktu")
        raise HTTPException(
            status_code=504,
            detail="Layanan AI di perangkat lokal tidak merespons tepat waktu. Coba lagi.",
        ) from None
    except AIServiceUnavailableError:
        logger.warning("Layanan AI lokal tidak dapat dijangkau")
        raise HTTPException(
            status_code=503,
            detail="Layanan AI di perangkat lokal sedang tidak aktif. Nyalakan lalu coba lagi.",
        ) from None
    if result.status_code in {401, 403}:
        # 401 dari laptop berarti token internal tidak cocok, bukan session pengguna
        # berakhir. Teruskan sebagai 503 agar PWA tidak mencoba refresh berulang.
        logger.error(
            "Layanan AI lokal menolak token internal (HTTP %s)",
            result.status_code,
        )
        raise HTTPException(
            status_code=503,
            detail="Layanan AI menolak permintaan server. Periksa konfigurasi token deployment.",
        )
    return JSONResponse(status_code=result.status_code, content=dict(result.payload))


def _database_http_error(exc: Exception) -> HTTPException:
    """Petakan error database ke respons aman tanpa connection string/stack trace."""
    if isinstance(exc, DatabaseNotConfiguredError):
        return HTTPException(
            status_code=503,
            detail="Database Supabase belum dikonfigurasi pada server.",
        )
    if isinstance(exc, TransactionNotFoundError):
        return HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")
    if isinstance(exc, TransactionConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DatabaseSchemaError):
        logger.error("Schema database CatatKas tidak kompatibel: %s", exc)
        return HTTPException(
            status_code=500,
            detail="Schema tabel Supabase belum sesuai dengan CatatKas.",
        )
    logger.exception("Operasi database Supabase gagal")
    return HTTPException(
        status_code=503,
        detail="Database Supabase tidak dapat dijangkau. Silakan coba lagi.",
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
        logger.warning("File sementara tidak dapat dihapus: %s", path)


def _resolve_receipt_upload(file: UploadFile) -> tuple[str, str]:
    """Validasi kecocokan ekstensi dan MIME type gambar nota."""
    extension = Path(file.filename or "").suffix.lower()
    extension_format = RECEIPT_EXTENSION_FORMATS.get(extension)
    content_format = RECEIPT_CONTENT_TYPE_FORMATS.get(
        (file.content_type or "").lower()
    )
    if extension_format is None or content_format is None:
        raise HTTPException(
            status_code=415,
            detail="Format nota tidak didukung. Gunakan JPEG, PNG, atau WebP.",
        )
    if extension_format != content_format:
        raise HTTPException(
            status_code=415,
            detail="Ekstensi dan MIME type gambar nota tidak sesuai.",
        )
    return extension, extension_format


async def _save_receipt_upload(file: UploadFile, suffix: str) -> Path:
    """Simpan upload nota secara terbatas ke nama file sementara acak."""
    temp_path: Optional[Path] = None
    total_size = 0
    try:
        with tempfile.NamedTemporaryFile(
            prefix="catatkas-receipt-",
            suffix=suffix,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > config.RECEIPT_MAX_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Ukuran foto nota maksimal "
                            f"{config.RECEIPT_MAX_SIZE_MB} MB"
                        ),
                    )
                temp_file.write(chunk)
    except BaseException:
        if temp_path is not None:
            _delete_temp_file(temp_path)
        raise

    if total_size == 0:
        if temp_path is not None:
            _delete_temp_file(temp_path)
        raise HTTPException(status_code=400, detail="File foto nota kosong")
    if temp_path is None:
        raise HTTPException(status_code=500, detail="Foto nota gagal diproses")
    return temp_path


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
    if not config.MODEL_WARMUP_ON_STARTUP:
        logger.info("Warmup Llama dinonaktifkan; model dimuat saat ekstraksi pertama.")
        return
    from .inference import get_pipeline
    get_pipeline()


@app.on_event("startup")
def warn_auto_login():
    """Ingatkan operator bahwa akun demo dapat dipakai tanpa login."""
    if not config.AUTO_LOGIN_ENABLED:
        return
    logger.warning(
        "AUTO_LOGIN_ENABLED aktif: akun demo %s dapat dipakai tanpa login. "
        "Matikan opsi ini pada deployment produksi.",
        config.AUTO_LOGIN_EMAIL,
    )


@app.post("/auth/register", name="auth.register")
async def register_user(
    credentials: AuthCredentials,
    request: Request,
    response: Response,
):
    """Daftarkan akun Supabase dan buat cookie jika konfirmasi email tidak wajib."""
    request.state.audit_metadata = {
        "user_email": str(credentials.email),
        "method": "register",
        "input": {"email": str(credentials.email)},
    }
    try:
        session = await register_supabase_user(
            str(credentials.email), credentials.password
        )
    except (AuthConfigurationError, AuthServiceError) as exc:
        raise _auth_http_error(exc) from None
    # REST Supabase mengembalikan UserSchema langsung ketika konfirmasi email aktif,
    # tetapi mengembalikan AccessTokenResponse.user ketika auto-confirm aktif.
    user_payload = session.get("user") or (session if session.get("id") else {})
    user_id = str(user_payload.get("id") or "").strip() or None
    if not user_id:
        raise HTTPException(status_code=503, detail="Respons registrasi tidak valid.")
    if user_id:
        request.state.audit_user_id = user_id
    authenticated = bool(session.get("access_token") and session.get("refresh_token"))
    if authenticated:
        _set_session_cookies(response, session)
    return {
        "success": True,
        "data": {
            "user": {
                "id": user_id,
                "email": user_payload.get("email") or str(credentials.email),
            },
            "authenticated": authenticated,
            "requires_email_confirmation": not authenticated,
        },
        "error": None,
    }


@app.post("/auth/login", name="auth.login")
async def login_user(
    credentials: AuthCredentials,
    request: Request,
    response: Response,
):
    """Login Supabase dan simpan token hanya dalam cookie HttpOnly."""
    request.state.audit_metadata = {
        "user_email": str(credentials.email),
        "method": "login",
        "input": {"email": str(credentials.email)},
    }
    try:
        session = await login_supabase_user(str(credentials.email), credentials.password)
    except (AuthConfigurationError, AuthServiceError) as exc:
        raise _auth_http_error(exc) from None
    user_payload = session.get("user") or {}
    user_id = str(user_payload.get("id") or "").strip()
    if (
        not user_id
        or not session.get("access_token")
        or not session.get("refresh_token")
    ):
        raise HTTPException(status_code=503, detail="Session login tidak valid.")
    request.state.audit_user_id = user_id
    _set_session_cookies(response, session)
    return {
        "success": True,
        "data": {
            "user": {"id": user_id, "email": user_payload.get("email")},
            "authenticated": True,
        },
        "error": None,
    }


@app.post("/auth/auto-login", name="auth.auto-login")
async def auto_login_user(request: Request, response: Response):
    """Login otomatis dengan akun demo bila diaktifkan pada konfigurasi server."""
    if not config.AUTO_LOGIN_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Login otomatis tidak diaktifkan pada server ini.",
        )
    email = config.AUTO_LOGIN_EMAIL
    password = config.AUTO_LOGIN_PASSWORD
    if not email or not password:
        raise HTTPException(
            status_code=503,
            detail="Kredensial login otomatis belum lengkap.",
        )
    request.state.audit_metadata = {
        "user_email": email,
        "method": "auto_login",
        "input": {"email": email},
    }
    try:
        session = await login_supabase_user(email, password)
    except (AuthConfigurationError, AuthServiceError) as exc:
        raise _auth_http_error(exc) from None
    user_payload = session.get("user") or {}
    user_id = str(user_payload.get("id") or "").strip()
    if (
        not user_id
        or not session.get("access_token")
        or not session.get("refresh_token")
    ):
        raise HTTPException(status_code=503, detail="Session login otomatis tidak valid.")
    request.state.audit_user_id = user_id
    _set_session_cookies(response, session)
    return {
        "success": True,
        "data": {
            "user": {"id": user_id, "email": user_payload.get("email") or email},
            "authenticated": True,
            "auto_login": True,
        },
        "error": None,
    }


@app.post("/auth/refresh", name="auth.refresh")
async def refresh_user_session(request: Request, response: Response):
    """Perbarui session tanpa mengekspos refresh token ke frontend."""
    refresh_token = request.cookies.get(config.AUTH_REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Session login telah berakhir.")
    try:
        session = await refresh_supabase_session(refresh_token)
    except (AuthConfigurationError, AuthServiceError) as exc:
        _clear_session_cookies(response)
        raise _auth_http_error(exc) from None
    user_payload = session.get("user") or {}
    user_id = str(user_payload.get("id") or "").strip() or None
    if (
        not user_id
        or not session.get("access_token")
        or not session.get("refresh_token")
    ):
        _clear_session_cookies(response)
        raise HTTPException(status_code=503, detail="Session login tidak valid.")
    if user_id:
        request.state.audit_user_id = user_id
        request.state.audit_metadata = {"user_email": user_payload.get("email")}
    _set_session_cookies(response, session)
    return {
        "success": True,
        "data": {
            "user": {"id": user_id, "email": user_payload.get("email")},
            "authenticated": True,
        },
        "error": None,
    }


@app.get("/auth/me", name="auth.me")
async def current_user(user: AuthenticatedUser = Depends(require_authenticated_user)):
    """Kembalikan identitas session aktif tanpa token."""
    return {
        "success": True,
        "data": {"user": {"id": user.id, "email": user.email}},
        "error": None,
    }


@app.post("/auth/logout", name="auth.logout")
async def logout_user(request: Request, response: Response):
    """Cabut session Supabase dan selalu hapus cookie lokal."""
    access_token = request.cookies.get(config.AUTH_ACCESS_COOKIE_NAME)
    try:
        if access_token:
            try:
                user = await get_supabase_user(access_token)
                request.state.audit_user_id = user.id
                request.state.audit_metadata = {"user_email": user.email}
            except (AuthConfigurationError, AuthServiceError):
                pass
            await logout_supabase_user(access_token)
    except (AuthConfigurationError, AuthServiceError) as exc:
        logger.warning("Logout remote gagal: %s", exc)
    finally:
        _clear_session_cookies(response)
    return {"success": True, "data": {"logged_out": True}, "error": None}


@app.post("/extract", name="extract.text")
async def extract(
    req: ExtractRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    request: Request = None,
):
    _merge_audit_metadata(
        request,
        method="text",
        input={"text": req.text, "reference_date": req.reference_date},
    )
    if ai_proxy.ai_service_is_configured():
        return await _relay_ai_response(
            ai_proxy.extract_text(req.text, req.reference_date)
        )

    reference_date = date.fromisoformat(req.reference_date) if req.reference_date else None
    result = await run_in_threadpool(
        extract_transaction,
        req.text,
        reference_date=reference_date,
    )

    if result.get("out_of_context"):
        raise HTTPException(status_code=422, detail=result["error"])

    return result


@app.post("/extract/audio", name="extract.audio")
async def extract_audio(
    file: UploadFile = File(...),
    reference_date: Optional[str] = Form(None),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    request: Request = None,
):
    """Transkripsikan satu rekaman dan ekstrak satu transaksi terstruktur."""
    audit_input = {
        "reference_date": reference_date,
        "audio": {
            "content_type": file.content_type,
        },
    }
    _merge_audit_metadata(request, method="voice", input=audit_input)
    parsed_reference_date = _parse_reference_date(reference_date)
    suffix = _resolve_audio_suffix(file)
    audit_input["audio"]["format"] = suffix.removeprefix(".")
    temp_path: Optional[Path] = None
    request_id = uuid.uuid4().hex[:8]
    # request_id yang sama dipakai pada console, logs/voice.log, dan audit_logs
    # sehingga satu pemrosesan suara dapat ditelusuri dari berkas ke database.
    _merge_audit_metadata(
        request,
        method="voice",
        request_id=request_id,
        input=audit_input,
    )

    try:
        temp_path = await _save_upload_to_temp(file, suffix)
        audit_input["audio"]["size_bytes"] = temp_path.stat().st_size
        log_voice_event(
            request_id,
            "received",
            user_id=getattr(user, "id", None),
            audio_format=suffix.removeprefix("."),
            content_type=file.content_type,
            size_bytes=audit_input["audio"]["size_bytes"],
        )
        if ai_proxy.ai_service_is_configured():
            return await _relay_ai_response(
                ai_proxy.extract_audio(
                    temp_path.read_bytes(),
                    f"audio{suffix}",
                    file.content_type or "application/octet-stream",
                    reference_date,
                )
            )
        transcript = await run_in_threadpool(transcribe_audio, temp_path)
        transcript = transcript.strip()
        audit_input["transcript"] = transcript
        _merge_audit_metadata(request, method="voice", input=audit_input)
        logger.info("[voice:%s] transcript=%r", request_id, transcript)
        log_voice_event(request_id, "transcript", transcript=transcript)
        if not transcript:
            log_voice_event(request_id, "empty_transcript")
            raise HTTPException(
                status_code=422,
                detail="Tidak ditemukan ucapan yang dapat dikenali pada audio",
            )

        llama_corrected_text = transcript
        normalization_method = "rule_based"
        if config.VOICE_LLM_NORMALIZATION_ENABLED:
            try:
                llama_corrected_text = await run_in_threadpool(
                    correct_voice_transcript_with_llama,
                    transcript,
                )
                normalization_method = "llama_3.2_base_and_rule_based"
            except Exception as exc:
                normalization_method = "rule_based_fallback"
                logger.exception(
                    "[voice:%s] Koreksi typo Llama gagal; memakai fallback",
                    request_id,
                )
                log_voice_event(
                    request_id,
                    "normalization_fallback",
                    error_type=type(exc).__name__,
                    error=str(exc)[:500],
                )

        normalized_text = normalize_voice_transaction_text(llama_corrected_text)
        audit_input["llama_corrected_text"] = llama_corrected_text
        audit_input["normalized_text"] = normalized_text
        audit_input["normalization_method"] = normalization_method
        _merge_audit_metadata(request, method="voice", input=audit_input)
        logger.info(
            "[voice:%s] llama_corrected_text=%r method=%s",
            request_id,
            llama_corrected_text,
            normalization_method,
        )
        logger.info("[voice:%s] normalized_text=%r", request_id, normalized_text)
        log_voice_event(
            request_id,
            "normalized",
            llama_corrected_text=llama_corrected_text,
            normalized_text=normalized_text,
            normalization_method=normalization_method,
        )
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
        log_voice_event(
            request_id,
            "extraction",
            success=bool(result.get("success", False)),
            out_of_context=bool(result.get("out_of_context", False)),
            data=result.get("data"),
            error=result.get("error"),
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
    except HTTPException as exc:
        log_voice_event(
            request_id,
            "rejected",
            status_code=exc.status_code,
            error=exc.detail,
        )
        raise
    except Exception as exc:
        logger.exception("Pemrosesan input audio gagal")
        log_voice_event(
            request_id,
            "error",
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
        raise HTTPException(
            status_code=500,
            detail="Audio gagal diproses. Silakan coba lagi.",
        ) from None
    finally:
        if temp_path is not None:
            _delete_temp_file(temp_path)


@app.post("/extract/receipt", name="extract.receipt")
async def extract_receipt_endpoint(
    file: UploadFile = File(...),
    reference_date: Optional[str] = Form(None),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    request: Request = None,
):
    """Baca satu foto nota dan kembalikan kandidat untuk konfirmasi pengguna."""
    audit_input = {
        "reference_date": reference_date,
        "image": {"content_type": file.content_type},
    }
    _merge_audit_metadata(request, method="receipt", input=audit_input)
    parsed_reference_date = _parse_reference_date(reference_date)
    effective_reference_date = parsed_reference_date or date.today()
    suffix, expected_format = _resolve_receipt_upload(file)
    audit_input["image"]["format"] = expected_format
    temp_path: Optional[Path] = None
    request_id = uuid.uuid4().hex[:8]

    try:
        temp_path = await _save_receipt_upload(file, suffix)
        audit_input["image"]["size_bytes"] = temp_path.stat().st_size
        if ai_proxy.ai_service_is_configured():
            return await _relay_ai_response(
                ai_proxy.extract_receipt(
                    temp_path.read_bytes(),
                    f"nota{suffix}",
                    file.content_type or "application/octet-stream",
                    reference_date,
                )
            )
        await run_in_threadpool(
            validate_receipt_image,
            temp_path,
            expected_format,
        )
        parsed = await run_in_threadpool(extract_receipt, temp_path)
        full_ocr_text = str(parsed.get("ocr_text") or "")
        compact_ocr_text = str(parsed.get("ocr_model_text") or full_ocr_text)
        model_ocr_text = (
            compact_ocr_text
            if config.RECEIPT_OCR_COMPACT_FOR_MODEL
            else full_ocr_text
        )
        parsed["ocr_model_text"] = model_ocr_text
        ocr_text, ocr_text_truncated = _limited_audit_text(full_ocr_text)
        audit_model_text, audit_model_text_truncated = _limited_audit_text(
            model_ocr_text
        )
        audit_input.update(
            ocr_text=ocr_text,
            ocr_text_truncated=ocr_text_truncated,
            ocr_model_text=audit_model_text,
            ocr_model_text_truncated=audit_model_text_truncated,
            ocr_compacted=model_ocr_text != full_ocr_text,
        )
        _merge_audit_metadata(request, method="receipt", input=audit_input)
        if not parsed.get("ocr_text") or parsed.get("receipt") is None:
            raise HTTPException(
                status_code=422,
                detail="Tidak ditemukan teks nota yang dapat dibaca.",
            )

        rule_receipt = parsed["receipt"]
        ocr_diagnostics = parsed.get("ocr_diagnostics") or {}
        logger.info(
            "[receipt:%s] ocr_passes=%s selected_pass=%s scores=%s",
            request_id,
            ocr_diagnostics.get("passes"),
            ocr_diagnostics.get("selected_pass"),
            ocr_diagnostics.get("scores"),
        )
        logger.info(
            "[receipt:%s] rule_parser has_merchant=%s items=%d has_total=%s has_date=%s",
            request_id,
            rule_receipt.get("merchant_name") is not None,
            len(rule_receipt.get("items") or []),
            rule_receipt.get("total") is not None,
            parsed.get("date") is not None,
        )
        logger.info(
            "[receipt:%s] ocr_chars=%d model_ocr_chars=%d compacted=%s",
            request_id,
            len(full_ocr_text),
            len(model_ocr_text),
            model_ocr_text != full_ocr_text,
        )

        extraction_method = "llama_soft_prompt_receipt"
        if config.RECEIPT_LLM_ENABLED:
            try:
                semantic_result = await run_in_threadpool(
                    extract_receipt_with_llama,
                    model_ocr_text,
                    effective_reference_date,
                    parsed,
                )
                semantic_data = semantic_result["data"]
                validation = validate_receipt_semantics(
                    semantic_data,
                    parsed,
                    parsed["ocr_text"],
                )
                response_data = _receipt_response_data(
                    semantic_data,
                    parsed,
                    validation,
                )
                logger.debug(
                    "[receipt:%s] llama_raw_output=%r",
                    request_id,
                    semantic_result.get("raw_output"),
                )
            except ReceiptInferenceError as exc:
                if not config.RECEIPT_RULE_FALLBACK_ENABLED:
                    logger.error(
                        "[receipt:%s] Soft Prompt Nota tidak tersedia: %s",
                        request_id,
                        exc,
                    )
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Soft Prompt Nota belum tersedia atau menghasilkan output "
                            "yang tidak valid."
                        ),
                    ) from None
                extraction_method = "rule_based_fallback"
                validation = fallback_validation(
                    parsed,
                    f"Fallback rule-based digunakan: {exc}",
                )
                response_data = _fallback_receipt_response_data(parsed, validation)
                logger.warning(
                    "[receipt:%s] extraction_method=%s reason=%s",
                    request_id,
                    extraction_method,
                    exc,
                )
        else:
            extraction_method = "rule_based_disabled"
            validation = fallback_validation(
                parsed,
                "Soft Prompt Nota dinonaktifkan melalui konfigurasi server.",
            )
            response_data = _fallback_receipt_response_data(parsed, validation)

        logger.info(
            "[receipt:%s] extraction_method=%s validation=%s warnings=%d",
            request_id,
            extraction_method,
            validation["status"],
            len(validation["warnings"]),
        )
        return {
            "success": True,
            "source": "receipt",
            "requires_confirmation": True,
            "data": response_data,
            "ocr_text": parsed["ocr_text"],
            "ocr_model_text": model_ocr_text,
            "extraction_method": extraction_method,
            "validation": {
                "status": validation["status"],
                "warnings": validation["warnings"],
            },
            "error": None,
        }
    except HTTPException:
        raise
    except InvalidReceiptImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except ReceiptOcrUnavailableError:
        logger.exception("Layanan OCR nota tidak tersedia")
        raise HTTPException(
            status_code=500,
            detail="Layanan OCR nota belum tersedia. Periksa instalasi server.",
        ) from None
    except Exception:
        logger.exception("Pemrosesan foto nota gagal")
        raise HTTPException(
            status_code=500,
            detail="Foto nota gagal diproses. Silakan coba lagi.",
        ) from None
    finally:
        await file.close()
        if temp_path is not None:
            _delete_temp_file(temp_path)


@app.get("/health", name="health.api")
def health():
    return {"status": "ok"}


@app.get("/health/database", name="health.database")
def database_health():
    """Periksa konfigurasi dan koneksi Supabase tanpa membuka rahasia koneksi."""
    if not database_is_configured():
        raise HTTPException(
            status_code=503,
            detail="Database Supabase belum dikonfigurasi pada server.",
        )
    try:
        get_transaction_repository().check_connection()
    except (
        DatabaseNotConfiguredError,
        DatabaseSchemaError,
        DatabaseUnavailableError,
    ) as exc:
        raise _database_http_error(exc) from None
    return {"status": "ok", "database": "connected"}


@app.get("/health/auth", name="health.auth")
def auth_health():
    """Periksa kelengkapan konfigurasi Supabase Auth tanpa mengirim key."""
    if not auth_is_configured():
        raise HTTPException(
            status_code=503,
            detail="Supabase Auth belum dikonfigurasi pada server.",
        )
    return {"status": "ok", "auth": "configured"}


@app.get("/transactions", name="transaction.list")
def list_transactions(
    request: Request,
    limit: int = Query(default=500, ge=1, le=500),
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Ambil riwayat transaksi dari Supabase, termasuk rincian nota."""
    try:
        records = get_transaction_repository().list(user.id, limit=limit)
    except (
        DatabaseNotConfiguredError,
        DatabaseSchemaError,
        DatabaseUnavailableError,
    ) as exc:
        raise _database_http_error(exc) from None
    _merge_audit_metadata(
        request,
        method="list",
        input={"limit": limit},
        record_count=len(records),
    )
    return {"success": True, "data": records, "error": None}


@app.get("/transactions/{transaction_id}", name="transaction.get")
def get_transaction(
    transaction_id: uuid.UUID,
    request: Request,
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Ambil satu detail transaksi berdasarkan UUID."""
    try:
        record = get_transaction_repository().get(str(transaction_id), user.id)
    except (
        DatabaseNotConfiguredError,
        DatabaseSchemaError,
        DatabaseUnavailableError,
        TransactionNotFoundError,
    ) as exc:
        raise _database_http_error(exc) from None
    request.state.audit_entity_type = "transaction"
    request.state.audit_entity_id = str(transaction_id)
    _merge_audit_metadata(
        request,
        method="detail",
        input={"transaction_id": str(transaction_id)},
    )
    return {"success": True, "data": record, "error": None}


@app.post("/transactions", status_code=201, name="transaction.create")
def create_transaction_record(
    payload: TransactionCreate,
    request: Request,
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Simpan satu transaksi terkonfirmasi ke Supabase."""
    try:
        record = get_transaction_repository().create(payload, user.id)
    except (
        DatabaseNotConfiguredError,
        DatabaseSchemaError,
        DatabaseUnavailableError,
    ) as exc:
        raise _database_http_error(exc) from None
    request.state.audit_entity_type = "transaction"
    request.state.audit_entity_id = record["id"]
    _merge_audit_metadata(
        request,
        source=payload.source,
        method=payload.source,
        input=payload.model_dump(mode="json"),
    )
    return {"success": True, "data": record, "error": None}


@app.post("/transactions/import", name="transaction.import")
def import_local_transactions(
    payload: TransactionImport,
    request: Request,
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Migrasikan maksimal 50 transaksi lokal jika database masih kosong."""
    try:
        records = get_transaction_repository().import_if_empty(
            payload.transactions, user.id
        )
    except (
        DatabaseNotConfiguredError,
        DatabaseSchemaError,
        DatabaseUnavailableError,
    ) as exc:
        raise _database_http_error(exc) from None
    _merge_audit_metadata(
        request,
        method="import",
        input={
            "transactions": [
                transaction.model_dump(mode="json")
                for transaction in payload.transactions
            ]
        },
        requested_count=len(payload.transactions),
        result_count=len(records),
    )
    return {"success": True, "data": records, "error": None}


@app.put("/transactions/{transaction_id}", name="transaction.update")
def update_transaction_record(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    request: Request,
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Perbarui transaksi tanpa menghapus receipt items yang sudah tersimpan."""
    try:
        record = get_transaction_repository().update(
            str(transaction_id), payload, user.id
        )
    except (
        DatabaseNotConfiguredError,
        DatabaseSchemaError,
        DatabaseUnavailableError,
        TransactionConflictError,
        TransactionNotFoundError,
    ) as exc:
        raise _database_http_error(exc) from None
    request.state.audit_entity_type = "transaction"
    request.state.audit_entity_id = str(transaction_id)
    _merge_audit_metadata(
        request,
        method="edit",
        input={
            "transaction_id": str(transaction_id),
            "changes": payload.model_dump(
                mode="json",
                exclude_unset=True,
            ),
        },
        updated_fields=sorted(payload.model_fields_set),
    )
    return {"success": True, "data": record, "error": None}


@app.delete("/transactions/{transaction_id}", name="transaction.delete")
def delete_transaction_record(
    transaction_id: uuid.UUID,
    request: Request,
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Hapus transaksi dan seluruh rincian notanya secara atomik."""
    try:
        get_transaction_repository().delete(str(transaction_id), user.id)
    except (
        DatabaseNotConfiguredError,
        DatabaseSchemaError,
        DatabaseUnavailableError,
        TransactionNotFoundError,
    ) as exc:
        raise _database_http_error(exc) from None
    request.state.audit_entity_type = "transaction"
    request.state.audit_entity_id = str(transaction_id)
    _merge_audit_metadata(
        request,
        method="delete",
        input={"transaction_id": str(transaction_id)},
    )
    return {
        "success": True,
        "data": {"id": str(transaction_id)},
        "error": None,
    }


@app.delete("/transactions", name="transaction.clear")
def clear_transaction_records(
    request: Request,
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Hapus seluruh riwayat CatatKas dari Supabase."""
    try:
        deleted = get_transaction_repository().clear(user.id)
    except (
        DatabaseNotConfiguredError,
        DatabaseSchemaError,
        DatabaseUnavailableError,
    ) as exc:
        raise _database_http_error(exc) from None
    _merge_audit_metadata(
        request,
        method="clear",
        input={"scope": "all_user_transactions"},
        deleted_count=deleted,
    )
    return {
        "success": True,
        "data": {"deleted": deleted},
        "error": None,
    }


# Mount terakhir agar route API di atas tetap memiliki prioritas dan tidak tertutup
# fallback HTML milik PWA.
app.mount("/", StaticFiles(directory=PWA_DIR, html=True), name="pwa")
