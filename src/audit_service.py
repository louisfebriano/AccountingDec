"""Satu audit log generik untuk seluruh fitur backend CatatKas."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Mapping

from . import config
from .database import DatabaseUnavailableError, get_database_engine


class AuditSchemaError(RuntimeError):
    """Tabel audit_logs belum sesuai kontrak minimum."""


class AuditLogRepository:
    """Tulis event lintas fitur ke satu tabel dengan metadata JSONB."""

    def __init__(self, engine: Any | None = None) -> None:
        self.engine = engine or get_database_engine()
        self._table_cache: Any | None = None
        self._table_lock = Lock()

    def _table(self) -> Any:
        if self._table_cache is None:
            with self._table_lock:
                if self._table_cache is None:
                    try:
                        from sqlalchemy import MetaData, Table

                        table = Table(
                            config.DATABASE_AUDIT_LOGS_TABLE,
                            MetaData(),
                            autoload_with=self.engine,
                        )
                    except Exception as exc:
                        raise DatabaseUnavailableError(
                            "Tabel audit log tidak dapat dibaca."
                        ) from exc
                    required = {
                        "id",
                        "user_id",
                        "event_type",
                        "status",
                        "metadata",
                        "created_at",
                    }
                    missing = sorted(required.difference(table.c.keys()))
                    if missing:
                        raise AuditSchemaError(
                            f"Tabel {table.name} belum memiliki field: {', '.join(missing)}."
                        )
                    self._table_cache = table
        return self._table_cache

    @staticmethod
    def _database_id(column: Any, value: str | None) -> Any:
        if value is None:
            return None
        try:
            if column.type.python_type is uuid.UUID:
                return uuid.UUID(str(value))
        except (AttributeError, NotImplementedError, ValueError):
            return str(value)
        return str(value)

    def record(
        self,
        *,
        event_type: str,
        status: str,
        user_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        http_method: str | None = None,
        path: str | None = None,
        status_code: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Tulis event dengan metadata terpilih; rahasia dan binary tidak diterima."""
        from sqlalchemy import insert

        table = self._table()
        values = {
            "id": self._database_id(table.c.id, str(uuid.uuid4())),
            "user_id": self._database_id(table.c.user_id, user_id),
            "event_type": event_type[:120],
            "entity_type": entity_type[:80] if entity_type else None,
            "entity_id": entity_id[:200] if entity_id else None,
            "status": status[:30],
            "http_method": http_method[:10] if http_method else None,
            "path": path[:500] if path else None,
            "status_code": status_code,
            "ip_address": ip_address,
            "user_agent": user_agent[:500] if user_agent else None,
            "metadata": dict(metadata or {}),
            "created_at": datetime.now(timezone.utc),
        }
        filtered = {key: value for key, value in values.items() if key in table.c}
        try:
            with self.engine.begin() as connection:
                connection.execute(insert(table).values(**filtered))
        except AuditSchemaError:
            raise
        except Exception as exc:
            raise DatabaseUnavailableError("Audit log gagal disimpan.") from exc


_repository: AuditLogRepository | None = None
_repository_lock = Lock()


def get_audit_log_repository() -> AuditLogRepository:
    """Cache satu repository audit per proses."""
    global _repository
    if _repository is None:
        with _repository_lock:
            if _repository is None:
                _repository = AuditLogRepository()
    return _repository


def reset_audit_log_repository() -> None:
    """Reset cache untuk pengujian atau perubahan konfigurasi."""
    global _repository
    with _repository_lock:
        _repository = None
