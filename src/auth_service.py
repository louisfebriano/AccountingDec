"""Integrasi Supabase Auth tanpa mengekspos session token ke JavaScript."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from . import config


class AuthConfigurationError(RuntimeError):
    """Konfigurasi Supabase Auth belum lengkap."""


class AuthServiceError(RuntimeError):
    """Supabase Auth menolak atau gagal memproses permintaan."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AuthenticatedUser:
    """Identitas minimum pengguna yang sudah diverifikasi Supabase."""

    id: str
    email: str | None


def auth_is_configured() -> bool:
    """Periksa konfigurasi Auth tanpa melakukan request jaringan."""
    return bool(config.SUPABASE_URL and config.SUPABASE_PUBLISHABLE_KEY)


def _headers(access_token: str | None = None) -> dict[str, str]:
    if not auth_is_configured():
        raise AuthConfigurationError(
            "SUPABASE_URL dan SUPABASE_PUBLISHABLE_KEY belum dikonfigurasi."
        )
    headers = {
        "apikey": config.SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _safe_auth_error(response: httpx.Response, operation: str) -> AuthServiceError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    code = str(payload.get("error_code") or payload.get("code") or "").lower()
    message = str(payload.get("msg") or payload.get("message") or "").lower()
    combined = f"{code} {message}"

    if "invalid_credentials" in combined or "invalid login" in combined:
        return AuthServiceError("Email atau password salah.", 401)
    if "email_not_confirmed" in combined or "email not confirmed" in combined:
        return AuthServiceError("Email belum dikonfirmasi.", 401)
    if "already" in combined or "user_exists" in combined:
        return AuthServiceError("Email sudah terdaftar.", 409)
    if "weak_password" in combined or "password" in combined and response.status_code == 422:
        return AuthServiceError("Password belum memenuhi ketentuan keamanan.", 422)
    if response.status_code == 429:
        return AuthServiceError("Terlalu banyak percobaan. Coba kembali nanti.", 429)
    if response.status_code in {400, 401, 403, 422}:
        fallback = "Registrasi gagal." if operation == "register" else "Autentikasi gagal."
        return AuthServiceError(fallback, response.status_code)
    return AuthServiceError("Layanan autentikasi tidak dapat dijangkau.", 503)


async def _request(
    method: str,
    path: str,
    *,
    operation: str,
    json: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Kirim request Auth dengan timeout dan pesan error yang sudah disanitasi."""
    url = f"{config.SUPABASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method,
                url,
                headers=_headers(access_token),
                json=json,
            )
    except AuthConfigurationError:
        raise
    except httpx.HTTPError as exc:
        raise AuthServiceError(
            "Layanan autentikasi tidak dapat dijangkau.", 503
        ) from exc
    if not response.is_success:
        raise _safe_auth_error(response, operation)
    if response.status_code == 204 or not response.content:
        return {}
    try:
        payload = response.json()
    except ValueError as exc:
        raise AuthServiceError("Respons autentikasi tidak dapat dibaca.", 503) from exc
    if not isinstance(payload, dict):
        raise AuthServiceError("Respons autentikasi tidak valid.", 503)
    return payload


async def register(email: str, password: str) -> dict[str, Any]:
    """Daftarkan pengguna melalui Supabase Auth."""
    return await _request(
        "POST",
        "/auth/v1/signup",
        operation="register",
        json={"email": email, "password": password},
    )


async def login(email: str, password: str) -> dict[str, Any]:
    """Buat session password Supabase."""
    return await _request(
        "POST",
        "/auth/v1/token?grant_type=password",
        operation="login",
        json={"email": email, "password": password},
    )


async def refresh(refresh_token: str) -> dict[str, Any]:
    """Perbarui access token memakai refresh token HttpOnly."""
    return await _request(
        "POST",
        "/auth/v1/token?grant_type=refresh_token",
        operation="refresh",
        json={"refresh_token": refresh_token},
    )


async def get_user(access_token: str) -> AuthenticatedUser:
    """Validasi access token ke Supabase dan kembalikan identitas minimum."""
    payload = await _request(
        "GET",
        "/auth/v1/user",
        operation="user",
        access_token=access_token,
    )
    user_id = str(payload.get("id") or "").strip()
    if not user_id:
        raise AuthServiceError("Sesi pengguna tidak valid.", 401)
    email = str(payload.get("email") or "").strip() or None
    return AuthenticatedUser(id=user_id, email=email)


async def logout(access_token: str) -> None:
    """Cabut session Supabase yang sedang aktif."""
    await _request(
        "POST",
        "/auth/v1/logout",
        operation="logout",
        access_token=access_token,
    )
