"""Schema API CRUD transaksi CatatKas yang kompatibel dengan data PWA."""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TransactionSource = Literal["manual", "text", "voice", "receipt"]
TransactionType = Literal["income", "expense"]


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class ReceiptItemInput(BaseModel):
    """Satu rincian barang hasil konfirmasi nota."""

    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(min_length=1, max_length=200)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=50)
    unit_price: int | None = Field(default=None, ge=0)
    line_total: int | None = Field(default=None, ge=0)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)

    @field_validator("item_name")
    @classmethod
    def clean_item_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("unit")
    @classmethod
    def clean_unit(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class ReceiptInput(BaseModel):
    """Metadata dan rincian satu nota yang tidak menyimpan foto atau raw OCR."""

    model_config = ConfigDict(extra="ignore")

    merchant_name: str | None = Field(default=None, max_length=200)
    receipt_number: str | None = Field(default=None, max_length=100)
    subtotal: int | None = Field(default=None, ge=0)
    discount: int | None = Field(default=None, ge=0)
    tax: int | None = Field(default=None, ge=0)
    service_charge: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    items: list[ReceiptItemInput] = Field(default_factory=list, max_length=50)

    @field_validator("merchant_name", "receipt_number")
    @classmethod
    def clean_optional_fields(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class TransactionCreate(BaseModel):
    """Payload penyimpanan satu transaksi yang sudah dikonfirmasi pengguna."""

    model_config = ConfigDict(extra="forbid")

    source: TransactionSource
    transaction_type: TransactionType
    item_name: str | None = Field(default=None, max_length=200)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=50)
    total_price: int = Field(gt=0)
    date: Date
    original_text: str | None = Field(default=None, max_length=500)
    transcript: str | None = Field(default=None, max_length=500)
    normalized_text: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)
    reference_date: Date | None = None
    extraction_method: str | None = Field(default=None, max_length=100)
    receipt: ReceiptInput | None = None

    @field_validator(
        "item_name",
        "unit",
        "original_text",
        "transcript",
        "normalized_text",
        "note",
        "extraction_method",
    )
    @classmethod
    def clean_text_fields(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)

    @model_validator(mode="after")
    def validate_source_contract(self) -> "TransactionCreate":
        if self.source == "receipt":
            if self.receipt is None:
                raise ValueError("Transaksi receipt wajib memiliki rincian nota.")
            if self.transaction_type != "expense":
                raise ValueError("Transaksi receipt harus berjenis expense.")
        elif self.receipt is not None:
            raise ValueError("Rincian nota hanya boleh digunakan oleh source receipt.")
        return self


class TransactionUpdate(BaseModel):
    """Field CRUD manual yang dapat diubah tanpa menghapus rincian nota."""

    model_config = ConfigDict(extra="forbid")

    transaction_type: TransactionType | None = None
    item_name: str | None = Field(default=None, max_length=200)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=50)
    total_price: int | None = Field(default=None, gt=0)
    date: Date | None = None
    note: str | None = Field(default=None, max_length=500)

    @field_validator("item_name", "unit", "note")
    @classmethod
    def clean_text_fields(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)

    @model_validator(mode="after")
    def validate_update(self) -> "TransactionUpdate":
        if not self.model_fields_set:
            raise ValueError("Minimal satu field transaksi harus diperbarui.")
        for required in ("transaction_type", "total_price", "date"):
            if required in self.model_fields_set and getattr(self, required) is None:
                raise ValueError(f"{required} tidak boleh null.")
        return self


class TransactionRecord(BaseModel):
    """Representasi transaksi yang dikembalikan ke PWA."""

    model_config = ConfigDict(extra="ignore")

    id: str
    user_id: str
    source: TransactionSource
    transaction_type: TransactionType
    item_name: str | None
    quantity: Decimal | None
    unit: str | None
    total_price: int
    date: Date
    original_text: str | None
    transcript: str | None
    normalized_text: str | None
    note: str | None
    reference_date: Date | None = None
    extraction_method: str | None = None
    receipt: ReceiptInput | None = None
    created_at: datetime
    updated_at: datetime | None


class TransactionImport(BaseModel):
    """Migrasi atomik riwayat localStorage saat database masih kosong."""

    transactions: list[TransactionCreate] = Field(max_length=50)
