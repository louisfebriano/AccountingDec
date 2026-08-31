"""Repository PostgreSQL untuk transaksi, nota, dan rincian barang CatatKas."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any, Iterable, Mapping

from . import config
from .database import DatabaseUnavailableError, get_database_engine
from .transaction_schema import TransactionCreate, TransactionUpdate


class DatabaseSchemaError(RuntimeError):
    """Tabel Supabase tidak sesuai kontrak minimal CatatKas."""


class TransactionNotFoundError(LookupError):
    """Transaksi dengan ID yang diberikan tidak ditemukan."""


class TransactionConflictError(ValueError):
    """Perubahan melanggar kontrak sumber transaksi yang sudah tersimpan."""


@dataclass(frozen=True)
class DatabaseTables:
    """Tabel hasil reflection agar kode mengikuti schema Supabase yang sudah dibuat."""

    transactions: Any
    receipts: Any
    receipt_items: Any
    transaction_date_column: str


def _required_columns(table: Any, names: Iterable[str]) -> None:
    missing = [name for name in names if name not in table.c]
    if missing:
        raise DatabaseSchemaError(
            f"Tabel {table.name} belum memiliki field: {', '.join(missing)}."
        )


def _required_foreign_key(
    table: Any,
    local_column: str,
    target_table: str,
    target_column: str,
) -> None:
    """Pastikan relasi database memakai kolom lokal dan target yang benar."""
    for foreign_key in table.foreign_keys:
        try:
            if (
                foreign_key.parent.name == local_column
                and foreign_key.column.table.name == target_table
                and foreign_key.column.name == target_column
            ):
                return
        except Exception:
            continue
    raise DatabaseSchemaError(
        f"Foreign key {table.name}.{local_column} harus mengarah ke "
        f"{target_table}.{target_column}. Jalankan migrasi "
        "sql/fix_receipt_relationships.sql."
    )


def _filtered_values(table: Any, values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if key in table.c
    }


def _database_id(column: Any, value: str) -> Any:
    """Gunakan UUID object hanya bila dialect column memang memintanya."""
    try:
        if column.type.python_type is uuid.UUID:
            return uuid.UUID(str(value))
    except (AttributeError, NotImplementedError):
        pass
    return str(value)


def _date_only(value: Any) -> date:
    """Normalisasi DATE/TIMESTAMP database menjadi tanggal transaksi."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            pass
    raise DatabaseSchemaError("Nilai transaction_date bukan tanggal yang valid.")


class TransactionRepository:
    """CRUD atomik yang tidak menyimpan audio, foto, raw OCR, atau raw output model."""

    def __init__(self, engine: Any | None = None) -> None:
        self.engine = engine or get_database_engine()
        self._tables_cache: DatabaseTables | None = None
        self._tables_lock = Lock()

    def _tables(self) -> DatabaseTables:
        if self._tables_cache is None:
            with self._tables_lock:
                if self._tables_cache is None:
                    try:
                        from sqlalchemy import MetaData, Table

                        metadata = MetaData()
                        transactions = Table(
                            config.DATABASE_TRANSACTIONS_TABLE,
                            metadata,
                            autoload_with=self.engine,
                        )
                        receipts = Table(
                            config.DATABASE_RECEIPTS_TABLE,
                            metadata,
                            autoload_with=self.engine,
                        )
                        receipt_items = Table(
                            config.DATABASE_RECEIPT_ITEMS_TABLE,
                            metadata,
                            autoload_with=self.engine,
                        )
                    except DatabaseSchemaError:
                        raise
                    except Exception as exc:
                        raise DatabaseUnavailableError(
                            "Tabel transaksi Supabase tidak dapat dibaca."
                        ) from exc

                    date_column = (
                        "transaction_date"
                        if "transaction_date" in transactions.c
                        else "date"
                        if "date" in transactions.c
                        else ""
                    )
                    if not date_column:
                        raise DatabaseSchemaError(
                            "Tabel transactions memerlukan transaction_date atau date."
                        )
                    _required_columns(
                        transactions,
                        (
                            "id",
                            "user_id",
                            "source",
                            "transaction_type",
                            "item_name",
                            "quantity",
                            "unit",
                            "total_price",
                            "created_at",
                        ),
                    )
                    _required_columns(receipts, ("id", "transaction_id"))
                    _required_columns(
                        receipt_items,
                        ("id", "receipt_id", "item_name"),
                    )
                    _required_foreign_key(
                        receipts,
                        "transaction_id",
                        transactions.name,
                        "id",
                    )
                    _required_foreign_key(
                        receipt_items,
                        "receipt_id",
                        receipts.name,
                        "id",
                    )
                    self._tables_cache = DatabaseTables(
                        transactions,
                        receipts,
                        receipt_items,
                        date_column,
                    )
        return self._tables_cache

    def check_connection(self) -> None:
        """Verifikasi koneksi dan ketiga tabel tanpa memodifikasi data."""
        from sqlalchemy import text

        self._tables()
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            raise DatabaseUnavailableError("Supabase tidak dapat dijangkau.") from exc

    def _transaction_values(
        self,
        payload: TransactionCreate,
        transaction_id: str,
        user_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        tables = self._tables()
        values = payload.model_dump(exclude={"receipt", "date"})
        values.update(
            id=_database_id(tables.transactions.c.id, transaction_id),
            user_id=_database_id(tables.transactions.c.user_id, user_id),
            **{tables.transaction_date_column: payload.date},
            created_at=now,
            updated_at=None,
        )
        return _filtered_values(tables.transactions, values)

    def _insert_receipt(
        self,
        connection: Any,
        transaction_id: str,
        payload: TransactionCreate,
        now: datetime,
    ) -> None:
        if payload.receipt is None:
            return
        from sqlalchemy import insert

        tables = self._tables()
        receipt_id = str(uuid.uuid4())
        receipt_values = payload.receipt.model_dump(exclude={"items"})
        receipt_values.update(
            id=_database_id(tables.receipts.c.id, receipt_id),
            transaction_id=_database_id(
                tables.receipts.c.transaction_id,
                transaction_id,
            ),
            created_at=now,
        )
        connection.execute(
            insert(tables.receipts).values(
                **_filtered_values(tables.receipts, receipt_values)
            )
        )
        for line_number, item in enumerate(payload.receipt.items, start=1):
            item_values = item.model_dump()
            item_values.update(
                id=_database_id(tables.receipt_items.c.id, str(uuid.uuid4())),
                receipt_id=_database_id(
                    tables.receipt_items.c.receipt_id,
                    receipt_id,
                ),
                line_number=line_number,
                created_at=now,
            )
            connection.execute(
                insert(tables.receipt_items).values(
                    **_filtered_values(tables.receipt_items, item_values)
                )
            )

    def _insert(
        self,
        connection: Any,
        payload: TransactionCreate,
        user_id: str,
    ) -> str:
        from sqlalchemy import insert

        transaction_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        tables = self._tables()
        connection.execute(
            insert(tables.transactions).values(
                **self._transaction_values(payload, transaction_id, user_id, now)
            )
        )
        self._insert_receipt(connection, transaction_id, payload, now)
        return transaction_id

    def create(self, payload: TransactionCreate, user_id: str) -> dict[str, Any]:
        """Simpan transaksi beserta nota dan items dalam satu commit."""
        try:
            with self.engine.begin() as connection:
                transaction_id = self._insert(connection, payload, user_id)
                return self._get(connection, transaction_id, user_id)
        except (DatabaseSchemaError, TransactionNotFoundError):
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(
                "Transaksi gagal disimpan ke Supabase."
            ) from exc

    def import_if_empty(
        self,
        payloads: list[TransactionCreate],
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Migrasikan localStorage sekali dan atomik hanya saat tabel masih kosong."""
        from sqlalchemy import func, select

        tables = self._tables()
        try:
            with self.engine.begin() as connection:
                total = connection.execute(
                    select(func.count())
                    .select_from(tables.transactions)
                    .where(
                        tables.transactions.c.user_id
                        == _database_id(tables.transactions.c.user_id, user_id)
                    )
                ).scalar_one()
                if total:
                    return self._list(connection, user_id, limit=500)
                ids = [
                    self._insert(connection, payload, user_id) for payload in payloads
                ]
                return [self._get(connection, value, user_id) for value in ids]
        except (DatabaseSchemaError, TransactionNotFoundError):
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(
                "Riwayat lokal gagal dimigrasikan ke Supabase."
            ) from exc

    def _related_receipts(
        self,
        connection: Any,
        transaction_ids: list[Any],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        from sqlalchemy import select

        if not transaction_ids:
            return {}, {}
        tables = self._tables()
        receipt_rows = connection.execute(
            select(tables.receipts).where(
                tables.receipts.c.transaction_id.in_(transaction_ids)
            )
        ).mappings().all()
        receipt_by_transaction = {
            str(row["transaction_id"]): dict(row)
            for row in receipt_rows
        }
        receipt_ids = [row["id"] for row in receipt_rows]
        items_by_receipt: dict[str, list[dict[str, Any]]] = {}
        if receipt_ids:
            order = (
                tables.receipt_items.c.line_number
                if "line_number" in tables.receipt_items.c
                else tables.receipt_items.c.id
            )
            item_rows = connection.execute(
                select(tables.receipt_items)
                .where(tables.receipt_items.c.receipt_id.in_(receipt_ids))
                .order_by(order)
            ).mappings().all()
            for row in item_rows:
                values = dict(row)
                items_by_receipt.setdefault(str(row["receipt_id"]), []).append(values)
        return receipt_by_transaction, items_by_receipt

    @staticmethod
    def _optional_value(row: Mapping[str, Any], name: str) -> Any:
        return row[name] if name in row else None

    def _serialize_transaction(
        self,
        row: Mapping[str, Any],
        receipt_by_transaction: Mapping[str, Mapping[str, Any]],
        items_by_receipt: Mapping[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        tables = self._tables()
        transaction_id = str(row["id"])
        receipt_row = receipt_by_transaction.get(transaction_id)
        receipt: dict[str, Any] | None = None
        if receipt_row is not None:
            receipt_id = str(receipt_row["id"])
            receipt = {
                "merchant_name": self._optional_value(receipt_row, "merchant_name"),
                "receipt_number": self._optional_value(receipt_row, "receipt_number"),
                "subtotal": self._optional_value(receipt_row, "subtotal"),
                "discount": self._optional_value(receipt_row, "discount"),
                "tax": self._optional_value(receipt_row, "tax"),
                "service_charge": self._optional_value(receipt_row, "service_charge"),
                "total": self._optional_value(receipt_row, "total"),
                "confidence": self._optional_value(receipt_row, "confidence"),
                "items": [
                    {
                        "item_name": item["item_name"],
                        "quantity": self._optional_value(item, "quantity"),
                        "unit": self._optional_value(item, "unit"),
                        "unit_price": self._optional_value(item, "unit_price"),
                        "line_total": self._optional_value(item, "line_total"),
                        "confidence": self._optional_value(item, "confidence"),
                    }
                    for item in items_by_receipt.get(receipt_id, [])
                ],
            }
        created_at = self._optional_value(row, "created_at")
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        return {
            "id": transaction_id,
            "user_id": str(row["user_id"]),
            "source": row["source"],
            "transaction_type": row["transaction_type"],
            "item_name": self._optional_value(row, "item_name"),
            "quantity": self._optional_value(row, "quantity"),
            "unit": self._optional_value(row, "unit"),
            "total_price": row["total_price"],
            "date": _date_only(row[tables.transaction_date_column]),
            "original_text": self._optional_value(row, "original_text"),
            "transcript": self._optional_value(row, "transcript"),
            "normalized_text": self._optional_value(row, "normalized_text"),
            "note": self._optional_value(row, "note"),
            "reference_date": self._optional_value(row, "reference_date"),
            "extraction_method": self._optional_value(row, "extraction_method"),
            "receipt": receipt,
            "created_at": created_at,
            "updated_at": self._optional_value(row, "updated_at"),
        }

    def _list(
        self,
        connection: Any,
        user_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import desc, select

        tables = self._tables()
        order_columns = [desc(tables.transactions.c[tables.transaction_date_column])]
        if "created_at" in tables.transactions.c:
            order_columns.append(desc(tables.transactions.c.created_at))
        rows = connection.execute(
            select(tables.transactions)
            .where(
                tables.transactions.c.user_id
                == _database_id(tables.transactions.c.user_id, user_id)
            )
            .order_by(*order_columns)
            .limit(max(1, min(limit, 500)))
        ).mappings().all()
        ids = [row["id"] for row in rows]
        receipts, items = self._related_receipts(connection, ids)
        return [self._serialize_transaction(row, receipts, items) for row in rows]

    def list(self, user_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        """Ambil riwayat terbaru beserta nested receipt items."""
        try:
            with self.engine.connect() as connection:
                return self._list(connection, user_id, limit=limit)
        except DatabaseSchemaError:
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(
                "Riwayat transaksi gagal dibaca dari Supabase."
            ) from exc

    def _get(
        self,
        connection: Any,
        transaction_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        from sqlalchemy import select

        tables = self._tables()
        identifier = _database_id(tables.transactions.c.id, transaction_id)
        row = connection.execute(
            select(tables.transactions).where(
                tables.transactions.c.id == identifier,
                tables.transactions.c.user_id
                == _database_id(tables.transactions.c.user_id, user_id),
            )
        ).mappings().one_or_none()
        if row is None:
            raise TransactionNotFoundError("Transaksi tidak ditemukan.")
        receipts, items = self._related_receipts(connection, [row["id"]])
        return self._serialize_transaction(row, receipts, items)

    def get(self, transaction_id: str, user_id: str) -> dict[str, Any]:
        try:
            with self.engine.connect() as connection:
                return self._get(connection, transaction_id, user_id)
        except (DatabaseSchemaError, TransactionNotFoundError):
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(
                "Detail transaksi gagal dibaca dari Supabase."
            ) from exc

    def update(
        self,
        transaction_id: str,
        payload: TransactionUpdate,
        user_id: str,
    ) -> dict[str, Any]:
        """Perbarui field transaksi induk dan pertahankan rincian nota."""
        from sqlalchemy import select, update

        tables = self._tables()
        identifier = _database_id(tables.transactions.c.id, transaction_id)
        owner_identifier = _database_id(tables.transactions.c.user_id, user_id)
        changes = payload.model_dump(exclude_unset=True, exclude={"date"})
        if "date" in payload.model_fields_set:
            changes[tables.transaction_date_column] = payload.date
        changes["updated_at"] = datetime.now(timezone.utc)
        changes = _filtered_values(tables.transactions, changes)
        try:
            with self.engine.begin() as connection:
                owned = connection.execute(
                    select(tables.transactions.c.id).where(
                        tables.transactions.c.id == identifier,
                        tables.transactions.c.user_id == owner_identifier,
                    )
                ).first()
                if owned is None:
                    raise TransactionNotFoundError("Transaksi tidak ditemukan.")
                if payload.transaction_type == "income":
                    receipt_exists = connection.execute(
                        select(tables.receipts.c.id).where(
                            tables.receipts.c.transaction_id == identifier
                        )
                    ).first()
                    if receipt_exists is not None:
                        raise TransactionConflictError(
                            "Transaksi nota harus tetap berjenis expense."
                        )
                result = connection.execute(
                    update(tables.transactions)
                    .where(
                        tables.transactions.c.id == identifier,
                        tables.transactions.c.user_id == owner_identifier,
                    )
                    .values(**changes)
                )
                if result.rowcount == 0:
                    raise TransactionNotFoundError("Transaksi tidak ditemukan.")
                if payload.total_price is not None and "total" in tables.receipts.c:
                    connection.execute(
                        update(tables.receipts)
                        .where(tables.receipts.c.transaction_id == identifier)
                        .values(total=payload.total_price)
                    )
                return self._get(connection, transaction_id, user_id)
        except (
            DatabaseSchemaError,
            TransactionConflictError,
            TransactionNotFoundError,
        ):
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(
                "Transaksi gagal diperbarui di Supabase."
            ) from exc

    def _delete_related(self, connection: Any, transaction_ids: list[Any]) -> None:
        from sqlalchemy import delete, select

        if not transaction_ids:
            return
        tables = self._tables()
        receipt_ids = connection.execute(
            select(tables.receipts.c.id).where(
                tables.receipts.c.transaction_id.in_(transaction_ids)
            )
        ).scalars().all()
        if receipt_ids:
            connection.execute(
                delete(tables.receipt_items).where(
                    tables.receipt_items.c.receipt_id.in_(receipt_ids)
                )
            )
        connection.execute(
            delete(tables.receipts).where(
                tables.receipts.c.transaction_id.in_(transaction_ids)
            )
        )

    def delete(self, transaction_id: str, user_id: str) -> None:
        """Hapus transaksi serta detail nota secara atomik."""
        from sqlalchemy import delete, select

        tables = self._tables()
        identifier = _database_id(tables.transactions.c.id, transaction_id)
        owner_identifier = _database_id(tables.transactions.c.user_id, user_id)
        try:
            with self.engine.begin() as connection:
                owned = connection.execute(
                    select(tables.transactions.c.id).where(
                        tables.transactions.c.id == identifier,
                        tables.transactions.c.user_id == owner_identifier,
                    )
                ).first()
                if owned is None:
                    raise TransactionNotFoundError("Transaksi tidak ditemukan.")
                self._delete_related(connection, [identifier])
                result = connection.execute(
                    delete(tables.transactions).where(
                        tables.transactions.c.id == identifier,
                        tables.transactions.c.user_id == owner_identifier,
                    )
                )
                if result.rowcount == 0:
                    raise TransactionNotFoundError("Transaksi tidak ditemukan.")
        except (DatabaseSchemaError, TransactionNotFoundError):
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(
                "Transaksi gagal dihapus dari Supabase."
            ) from exc

    def clear(self, user_id: str) -> int:
        """Hapus semua riwayat transaksi aplikasi dan kembalikan jumlahnya."""
        from sqlalchemy import delete, select

        tables = self._tables()
        try:
            with self.engine.begin() as connection:
                ids = connection.execute(
                    select(tables.transactions.c.id).where(
                        tables.transactions.c.user_id
                        == _database_id(tables.transactions.c.user_id, user_id)
                    )
                ).scalars().all()
                self._delete_related(connection, list(ids))
                if ids:
                    connection.execute(
                        delete(tables.transactions).where(
                            tables.transactions.c.user_id
                            == _database_id(
                                tables.transactions.c.user_id, user_id
                            )
                        )
                    )
                return len(ids)
        except DatabaseSchemaError:
            raise
        except Exception as exc:
            raise DatabaseUnavailableError(
                "Riwayat transaksi gagal dihapus dari Supabase."
            ) from exc


_repository: TransactionRepository | None = None
_repository_lock = Lock()


def get_transaction_repository() -> TransactionRepository:
    """Buat satu repository per proses setelah DATABASE_URL tersedia."""
    global _repository
    if _repository is None:
        with _repository_lock:
            if _repository is None:
                _repository = TransactionRepository()
    return _repository


def reset_transaction_repository() -> None:
    """Reset cache repository untuk test atau pergantian konfigurasi."""
    global _repository
    with _repository_lock:
        _repository = None
