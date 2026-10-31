"""Klien HTTP ke layanan AI CatatKas yang berjalan di laptop via Cloudflare Tunnel.

Modul ini hanya dipakai ketika ``AI_SERVICE_URL`` diisi, yaitu pada server publik
(Render) yang tidak memiliki GPU. Pipeline AI tetap dijalankan oleh kode yang sama
(``src.api``) di laptop, sehingga logika ekstraksi tidak berubah.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from . import config

INTERNAL_TOKEN_HEADER = "X-CatatKas-Internal-Token"


class AIServiceError(RuntimeError):
    """Kegagalan memanggil layanan AI lokal."""


class AIServiceUnavailableError(AIServiceError):
    """Layanan AI lokal tidak dapat dijangkau (mati, tunnel putus, atau salah URL)."""


class AIServiceTimeoutError(AIServiceError):
    """Layanan AI lokal tidak merespons dalam batas waktu."""


@dataclass(frozen=True)
class AIResponse:
    """Respons mentah layanan AI yang diteruskan apa adanya ke klien PWA."""

    status_code: int
    payload: Mapping[str, Any]


def ai_service_is_configured() -> bool:
    """True bila server ini meneruskan ekstraksi ke layanan AI di laptop."""
    return bool(config.AI_SERVICE_URL)


def _endpoint(path: str) -> str:
    return f"{config.AI_SERVICE_URL.rstrip('/')}{path}"


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if config.AI_INTERNAL_TOKEN:
        headers[INTERNAL_TOKEN_HEADER] = config.AI_INTERNAL_TOKEN
    return headers


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=config.AI_CONNECT_TIMEOUT_SECONDS,
        read=config.AI_REQUEST_TIMEOUT_SECONDS,
        write=config.AI_REQUEST_TIMEOUT_SECONDS,
        pool=config.AI_CONNECT_TIMEOUT_SECONDS,
    )


async def _send(path: str, **kwargs: Any) -> AIResponse:
    """Kirim satu request dan ubah kegagalan jaringan menjadi error domain."""
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.post(
                _endpoint(path),
                headers=_headers(),
                **kwargs,
            )
    except httpx.TimeoutException:
        raise AIServiceTimeoutError("Layanan AI lokal tidak merespons tepat waktu.") from None
    except httpx.HTTPError as exc:
        raise AIServiceUnavailableError(
            f"Layanan AI lokal tidak dapat dijangkau ({type(exc).__name__})."
        ) from None

    try:
        payload = response.json()
    except ValueError:
        raise AIServiceUnavailableError(
            "Layanan AI lokal mengirim respons yang tidak dapat dibaca."
        ) from None
    if not isinstance(payload, Mapping):
        raise AIServiceUnavailableError("Respons layanan AI lokal tidak valid.")
    return AIResponse(status_code=response.status_code, payload=payload)


async def extract_text(text: str, reference_date: str | None) -> AIResponse:
    """Teruskan input teks ke pipeline Llama di laptop."""
    return await _send(
        "/extract",
        json={"text": text, "reference_date": reference_date},
    )


async def extract_audio(
    content: bytes,
    filename: str,
    content_type: str,
    reference_date: str | None,
) -> AIResponse:
    """Teruskan satu rekaman suara ke layanan AI lokal."""
    data: dict[str, str] = {}
    if reference_date:
        data["reference_date"] = reference_date
    return await _send(
        "/extract/audio",
        files={"file": (filename, content, content_type)},
        data=data,
    )


async def extract_receipt(
    content: bytes,
    filename: str,
    content_type: str,
    reference_date: str | None,
) -> AIResponse:
    """Teruskan satu foto nota ke layanan AI lokal."""
    data: dict[str, str] = {}
    if reference_date:
        data["reference_date"] = reference_date
    return await _send(
        "/extract/receipt",
        files={"file": (filename, content, content_type)},
        data=data,
    )
