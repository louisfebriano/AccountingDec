"""Koneksi PostgreSQL Supabase yang dibuat secara lazy dan aman untuk FastAPI."""

from __future__ import annotations

from threading import Lock
from typing import Any

from . import config


class DatabaseNotConfiguredError(RuntimeError):
    """Connection string database belum tersedia pada environment server."""


class DatabaseUnavailableError(RuntimeError):
    """Database sudah dikonfigurasi tetapi koneksi atau query gagal."""


_engine: Any = None
_engine_lock = Lock()


def database_is_configured() -> bool:
    """Kembalikan True tanpa membuka koneksi bila DATABASE_URL sudah diisi."""
    return bool(config.DATABASE_URL)


def _sqlalchemy_url(value: str) -> str:
    """Gunakan driver psycopg 3 untuk connection string PostgreSQL Supabase."""
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://") :]
    return value


def get_database_engine() -> Any:
    """Buat dan cache satu SQLAlchemy engine; koneksi fisik tetap lazy."""
    global _engine
    if not database_is_configured():
        raise DatabaseNotConfiguredError(
            "DATABASE_URL belum dikonfigurasi pada server."
        )
    if config.DATABASE_POOL_MODE not in {"direct", "session", "transaction"}:
        raise DatabaseNotConfiguredError(
            "DATABASE_POOL_MODE harus direct, session, atau transaction."
        )

    if _engine is None:
        with _engine_lock:
            if _engine is None:
                try:
                    from sqlalchemy import create_engine
                    from sqlalchemy.pool import NullPool
                except ImportError as exc:
                    raise DatabaseUnavailableError(
                        "Dependensi SQLAlchemy dan psycopg belum terpasang."
                    ) from exc

                connect_args: dict[str, Any] = {
                    "connect_timeout": config.DATABASE_CONNECT_TIMEOUT_SECONDS,
                    "sslmode": "require",
                }
                engine_options: dict[str, Any] = {
                    "pool_pre_ping": True,
                    "connect_args": connect_args,
                }
                if config.DATABASE_POOL_MODE == "transaction":
                    # Supavisor transaction mode tidak mendukung prepared statement
                    # dan sudah melakukan pooling di sisi server.
                    connect_args["prepare_threshold"] = None
                    engine_options["poolclass"] = NullPool
                else:
                    engine_options.update(
                        pool_size=max(config.DATABASE_POOL_SIZE, 1),
                        max_overflow=max(config.DATABASE_MAX_OVERFLOW, 0),
                        pool_recycle=300,
                    )
                try:
                    _engine = create_engine(
                        _sqlalchemy_url(config.DATABASE_URL),
                        **engine_options,
                    )
                except Exception as exc:
                    raise DatabaseUnavailableError(
                        "Konfigurasi koneksi database tidak valid."
                    ) from exc
    return _engine


def dispose_database_engine() -> None:
    """Lepaskan pool koneksi; terutama digunakan oleh test dan shutdown server."""
    global _engine
    with _engine_lock:
        engine, _engine = _engine, None
    if engine is not None:
        engine.dispose()

