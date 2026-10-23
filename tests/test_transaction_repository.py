import unittest
from datetime import date, datetime

try:
    from sqlalchemy import (
        Column,
        Date,
        DateTime,
        ForeignKey,
        Integer,
        MetaData,
        Numeric,
        String,
        Table,
        Text,
        create_engine,
        func,
        select,
    )
except ImportError:  # pragma: no cover - dependency error is clearer in setup
    raise unittest.SkipTest("SQLAlchemy belum terpasang")

from src.transaction_repository import (
    DatabaseSchemaError,
    TransactionConflictError,
    TransactionNotFoundError,
    TransactionRepository,
    _date_only,
)
from src.transaction_schema import TransactionCreate, TransactionUpdate


USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"


def build_engine(
    *,
    wrong_receipt_item_foreign_key=False,
    with_category=True,
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    Table(
        "transactions",
        metadata,
        Column("id", String, primary_key=True),
        Column("user_id", String, nullable=False),
        Column("source", String, nullable=False),
        Column("transaction_type", String, nullable=False),
        Column("item_name", String),
        Column("quantity", Numeric(14, 3)),
        Column("unit", String),
        Column("total_price", Integer, nullable=False),
        Column("transaction_date", Date, nullable=False),
        *(
            [Column("category", String(50))]
            if with_category
            else []
        ),
        Column("original_text", Text),
        Column("transcript", Text),
        Column("normalized_text", Text),
        Column("note", Text),
        Column("reference_date", Date),
        Column("extraction_method", String),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True)),
    )
    Table(
        "receipts",
        metadata,
        Column("id", String, primary_key=True),
        Column(
            "transaction_id",
            String,
            ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("merchant_name", String),
        Column("receipt_number", String),
        Column("subtotal", Integer),
        Column("discount", Integer),
        Column("tax", Integer),
        Column("service_charge", Integer),
        Column("total", Integer),
        Column("confidence", Numeric(5, 4)),
        Column("created_at", DateTime(timezone=True)),
    )
    Table(
        "receipt_items",
        metadata,
        Column(
            "id",
            String,
            *(
                [ForeignKey("receipts.id")]
                if wrong_receipt_item_foreign_key
                else []
            ),
            primary_key=True,
        ),
        Column(
            "receipt_id",
            String,
            *(
                []
                if wrong_receipt_item_foreign_key
                else [ForeignKey("receipts.id", ondelete="CASCADE")]
            ),
            nullable=False,
        ),
        Column("line_number", Integer),
        Column("item_name", String, nullable=False),
        Column("quantity", Numeric(14, 3)),
        Column("unit", String),
        Column("unit_price", Integer),
        Column("line_total", Integer),
        Column("confidence", Numeric(5, 4)),
        Column("created_at", DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    return engine


def manual_payload(total=125_000, category="Bahan baku"):
    return TransactionCreate(
        source="manual",
        transaction_type="expense",
        item_name="Gas LPG",
        quantity=3,
        unit="tabung",
        total_price=total,
        date=date(2026, 8, 23),
        note="Belanja warung",
        category=category,
    )


class TransactionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = build_engine()
        self.repository = TransactionRepository(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_manual_crud(self):
        created = self.repository.create(manual_payload(), USER_A)
        self.assertEqual(created["user_id"], USER_A)
        self.assertEqual(created["item_name"], "Gas LPG")
        self.assertEqual(created["total_price"], 125_000)
        self.assertEqual(created["category"], "Bahan baku")
        self.assertIsNone(created["receipt"])

        records = self.repository.list(USER_A)
        self.assertEqual([item["id"] for item in records], [created["id"]])

        updated = self.repository.update(
            created["id"],
            TransactionUpdate(total_price=130_000, note="Harga diperbarui"),
            USER_A,
        )
        self.assertEqual(updated["total_price"], 130_000)
        self.assertEqual(updated["note"], "Harga diperbarui")
        self.assertEqual(updated["category"], "Bahan baku")

        self.repository.delete(created["id"], USER_A)
        self.assertEqual(self.repository.list(USER_A), [])

    def test_category_can_be_set_replaced_and_cleared(self):
        created = self.repository.create(
            manual_payload(category="Operasional"), USER_A
        )
        self.assertEqual(created["category"], "Operasional")

        replaced = self.repository.update(
            created["id"], TransactionUpdate(category="Sewa"), USER_A
        )
        self.assertEqual(replaced["category"], "Sewa")

        cleared = self.repository.update(
            created["id"], TransactionUpdate(category=None), USER_A
        )
        self.assertIsNone(cleared["category"])

        without_category = self.repository.create(
            manual_payload(category=None), USER_B
        )
        self.assertIsNone(without_category["category"])

    def test_missing_category_column_reports_migration_file(self):
        engine = build_engine(with_category=False)
        repository = TransactionRepository(engine)
        try:
            with self.assertRaisesRegex(
                DatabaseSchemaError,
                r"field: category.*sql/add_transaction_category\.sql",
            ):
                repository.create(manual_payload(), USER_A)
        finally:
            engine.dispose()

    def test_timestamp_transaction_date_is_serialized_as_date_only(self):
        self.assertEqual(
            _date_only(datetime(2026, 8, 29, 0, 0, 0)),
            date(2026, 8, 29),
        )

    def test_wrong_receipt_item_foreign_key_is_reported_before_insert(self):
        engine = build_engine(wrong_receipt_item_foreign_key=True)
        repository = TransactionRepository(engine)
        try:
            with self.assertRaisesRegex(
                DatabaseSchemaError,
                r"receipt_items\.receipt_id.*receipts\.id",
            ):
                repository.create(manual_payload(), USER_A)
        finally:
            engine.dispose()
        self.assertEqual(
            _date_only("2026-08-29T00:00:00+00:00"),
            date(2026, 8, 29),
        )

    def test_receipt_items_are_nested_and_deleted_atomically(self):
        payload = TransactionCreate.model_validate(
            {
                "source": "receipt",
                "transaction_type": "expense",
                "item_name": None,
                "quantity": None,
                "unit": None,
                "total_price": 62_000,
                "date": "2026-08-24",
                "extraction_method": "llama_soft_prompt_receipt",
                "receipt": {
                    "merchant_name": "Toko Makmur",
                    "total": 62_000,
                    "items": [
                        {
                            "item_name": "Beras",
                            "quantity": 4,
                            "unit": "kg",
                            "unit_price": 12_500,
                            "line_total": 50_000,
                        },
                        {
                            "item_name": "Minyak Goreng",
                            "quantity": 1,
                            "unit": "botol",
                            "unit_price": 12_000,
                            "line_total": 12_000,
                        },
                    ],
                },
            }
        )
        created = self.repository.create(payload, USER_A)
        self.assertEqual(created["receipt"]["merchant_name"], "Toko Makmur")
        self.assertEqual(len(created["receipt"]["items"]), 2)

        updated = self.repository.update(
            created["id"], TransactionUpdate(total_price=63_000), USER_A
        )
        self.assertEqual(updated["receipt"]["total"], 63_000)
        self.assertEqual(len(updated["receipt"]["items"]), 2)

        self.repository.delete(created["id"], USER_A)
        tables = self.repository._tables()
        with self.engine.connect() as connection:
            receipt_count = connection.execute(
                select(func.count()).select_from(tables.receipts)
            ).scalar_one()
            item_count = connection.execute(
                select(func.count()).select_from(tables.receipt_items)
            ).scalar_one()
        self.assertEqual(receipt_count, 0)
        self.assertEqual(item_count, 0)

    def test_import_only_runs_when_database_is_empty(self):
        first = self.repository.import_if_empty([manual_payload()], USER_A)
        second = self.repository.import_if_empty(
            [manual_payload(total=999_000)], USER_A
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["total_price"], 125_000)

    def test_receipt_cannot_be_changed_to_income(self):
        payload = TransactionCreate.model_validate(
            {
                "source": "receipt",
                "transaction_type": "expense",
                "total_price": 20_000,
                "date": "2026-08-24",
                "receipt": {"total": 20_000, "items": []},
            }
        )
        created = self.repository.create(payload, USER_A)

        with self.assertRaises(TransactionConflictError):
            self.repository.update(
                created["id"],
                TransactionUpdate(transaction_type="income"),
                USER_A,
            )

    def test_users_cannot_read_update_or_delete_each_others_transactions(self):
        created = self.repository.create(manual_payload(), USER_A)

        self.assertEqual(self.repository.list(USER_B), [])
        with self.assertRaises(TransactionNotFoundError):
            self.repository.get(created["id"], USER_B)
        with self.assertRaises(TransactionNotFoundError):
            self.repository.update(
                created["id"], TransactionUpdate(total_price=10_000), USER_B
            )
        with self.assertRaises(TransactionNotFoundError):
            self.repository.delete(created["id"], USER_B)

        self.assertEqual(self.repository.get(created["id"], USER_A)["total_price"], 125_000)


if __name__ == "__main__":
    unittest.main()
