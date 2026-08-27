"""Schema ketat untuk keluaran Soft Prompt Nota."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, field_validator


ReceiptNumber = StrictInt | StrictFloat


class ReceiptItemSchema(BaseModel):
    """Satu rincian barang yang benar-benar didukung teks OCR."""

    model_config = ConfigDict(extra="forbid", strict=True)

    item_name: str
    quantity: ReceiptNumber | None
    unit: str | None
    unit_price: StrictInt | None
    line_total: StrictInt | None

    @field_validator("item_name")
    @classmethod
    def validate_item_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("item_name tidak boleh kosong")
        return value

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: ReceiptNumber | None) -> ReceiptNumber | None:
        if value is not None and value <= 0:
            raise ValueError("quantity harus lebih besar dari nol")
        return value

    @field_validator("unit_price", "line_total")
    @classmethod
    def validate_item_amount(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("nominal item tidak boleh negatif")
        return value


class ReceiptExtractionSchema(BaseModel):
    """Kontrak lengkap satu nota pembelian hasil inference Llama."""

    model_config = ConfigDict(extra="forbid", strict=True)

    merchant_name: str | None
    receipt_number: str | None
    date: str | None
    items: list[ReceiptItemSchema]
    subtotal: StrictInt | None
    discount: StrictInt | None
    tax: StrictInt | None
    service_charge: StrictInt | None
    total: StrictInt | None
    transaction_type: Literal["expense"]

    @field_validator("merchant_name", "receipt_number")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError) as exc:
            raise ValueError("date harus berformat YYYY-MM-DD atau null") from exc

    @field_validator("items")
    @classmethod
    def validate_items(cls, value: list[ReceiptItemSchema]) -> list[ReceiptItemSchema]:
        if len(value) > 50:
            raise ValueError("items maksimal 50 baris")
        return value

    @field_validator("subtotal", "discount", "tax", "service_charge", "total")
    @classmethod
    def validate_amount(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("nominal nota tidak boleh negatif")
        return value


RECEIPT_SCHEMA_FIELDS = tuple(ReceiptExtractionSchema.model_fields)

