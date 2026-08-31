import unittest

try:
    from sqlalchemy import (
        JSON,
        Column,
        DateTime,
        Integer,
        MetaData,
        String,
        Table,
        create_engine,
        select,
    )
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("SQLAlchemy belum terpasang")

from src.audit_service import AuditLogRepository


class AuditLogRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        metadata = MetaData()
        self.table = Table(
            "audit_logs",
            metadata,
            Column("id", String, primary_key=True),
            Column("user_id", String),
            Column("event_type", String, nullable=False),
            Column("entity_type", String),
            Column("entity_id", String),
            Column("status", String, nullable=False),
            Column("http_method", String),
            Column("path", String),
            Column("status_code", Integer),
            Column("ip_address", String),
            Column("user_agent", String),
            Column("metadata", JSON, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False),
        )
        metadata.create_all(self.engine)
        self.repository = AuditLogRepository(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_one_generic_table_accepts_transaction_and_auth_metadata(self):
        self.repository.record(
            event_type="transactions.create",
            status="success",
            user_id="11111111-1111-4111-8111-111111111111",
            entity_type="transaction",
            entity_id="transaction-id",
            http_method="POST",
            path="/transactions",
            status_code=201,
            metadata={"source": "voice", "fields": ["total_price", "date"]},
        )
        self.repository.record(
            event_type="auth.login",
            status="failure",
            metadata={"user_email": "user@example.com"},
        )

        with self.engine.connect() as connection:
            rows = connection.execute(
                select(self.table).order_by(self.table.c.created_at)
            ).mappings().all()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["metadata"]["source"], "voice")
        self.assertEqual(rows[1]["event_type"], "auth.login")
        self.assertNotIn("password", rows[1]["metadata"])


if __name__ == "__main__":
    unittest.main()
