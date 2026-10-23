import unittest
import uuid
from datetime import date, datetime, timezone
from unittest.mock import patch

from fastapi import Request
from fastapi.testclient import TestClient

from src import api
from src.auth_service import AuthenticatedUser
from src.transaction_repository import TransactionNotFoundError


client = TestClient(api.app)
TEST_USER = AuthenticatedUser(
    id="11111111-1111-4111-8111-111111111111",
    email="user@example.com",
)


def authenticated_test_user(request: Request):
    request.state.audit_user_id = TEST_USER.id
    request.state.audit_metadata = {"user_email": TEST_USER.email}
    return TEST_USER


def transaction_record(transaction_id=None):
    return {
        "id": transaction_id or str(uuid.uuid4()),
        "user_id": TEST_USER.id,
        "source": "manual",
        "transaction_type": "income",
        "item_name": None,
        "quantity": None,
        "unit": None,
        "total_price": 600_000,
        "date": date(2026, 8, 27),
        "original_text": None,
        "transcript": None,
        "normalized_text": None,
        "note": "Modal masuk",
        "category": "Modal usaha",
        "reference_date": None,
        "extraction_method": None,
        "receipt": None,
        "created_at": datetime(2026, 8, 27, tzinfo=timezone.utc),
        "updated_at": None,
    }


class FakeRepository:
    def __init__(self):
        self.record = transaction_record()
        self.created = None
        self.updated = None
        self.deleted = None

    def check_connection(self):
        return None

    def list(self, user_id, limit=500):
        assert user_id == TEST_USER.id
        return [self.record][:limit]

    def get(self, transaction_id, user_id):
        assert user_id == TEST_USER.id
        if transaction_id != self.record["id"]:
            raise TransactionNotFoundError()
        return self.record

    def create(self, payload, user_id):
        assert user_id == TEST_USER.id
        self.created = payload
        return self.record

    def import_if_empty(self, payloads, user_id):
        assert user_id == TEST_USER.id
        return [self.record] if payloads else []

    def update(self, transaction_id, payload, user_id):
        assert user_id == TEST_USER.id
        self.updated = (transaction_id, payload)
        return {**self.record, "total_price": payload.total_price}

    def delete(self, transaction_id, user_id):
        assert user_id == TEST_USER.id
        self.deleted = transaction_id

    def clear(self, user_id):
        assert user_id == TEST_USER.id
        return 1


class FakeAuditRepository:
    def __init__(self):
        self.events = []

    def record(self, **values):
        self.events.append(values)


class TransactionApiTests(unittest.TestCase):
    def setUp(self):
        api.app.dependency_overrides[api.require_authenticated_user] = authenticated_test_user
        self.audit_patch = patch.object(api.config, "AUDIT_LOG_ENABLED", False)
        self.audit_patch.start()
        self.repository = FakeRepository()
        self.repository_patch = patch.object(
            api, "get_transaction_repository", return_value=self.repository
        )
        self.repository_patch.start()

    def tearDown(self):
        self.repository_patch.stop()
        self.audit_patch.stop()
        api.app.dependency_overrides.pop(api.require_authenticated_user, None)

    def test_database_health_does_not_expose_connection_string(self):
        with patch.object(api, "database_is_configured", return_value=True):
            response = client.get("/health/database")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "connected"})

    def test_unconfigured_database_returns_safe_503(self):
        with patch.object(api, "database_is_configured", return_value=False):
            response = client.get("/health/database")

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("postgres", response.text.lower())

    def test_create_list_update_and_delete(self):
        payload = {
            "source": "manual",
            "transaction_type": "income",
            "item_name": None,
            "quantity": None,
            "unit": None,
            "total_price": 600000,
            "date": "2026-08-27",
            "note": "Modal masuk",
            "receipt": None,
        }
        created = client.post("/transactions", json=payload)
        listed = client.get("/transactions")
        updated = client.put(
            f"/transactions/{self.repository.record['id']}",
            json={"total_price": 650000},
        )
        deleted = client.delete(f"/transactions/{self.repository.record['id']}")

        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["success"])
        self.assertEqual(listed.json()["data"][0]["total_price"], 600000)
        self.assertEqual(updated.json()["data"]["total_price"], 650000)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.repository.deleted, self.repository.record["id"])

    def test_category_is_saved_and_updated(self):
        payload = {
            "source": "manual",
            "transaction_type": "expense",
            "total_price": 125000,
            "date": "2026-08-27",
            "category": "  bahan baku  ",
        }
        created = client.post("/transactions", json=payload)
        updated = client.put(
            f"/transactions/{self.repository.record['id']}",
            json={"category": None},
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.repository.created.category, "bahan baku")
        self.assertIsNone(self.repository.updated[1].category)
        self.assertEqual(updated.status_code, 200)

    def test_category_longer_than_fifty_characters_is_rejected(self):
        response = client.post(
            "/transactions",
            json={
                "source": "manual",
                "transaction_type": "expense",
                "total_price": 50000,
                "date": "2026-08-27",
                "category": "x" * 51,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_unknown_transaction_type_is_rejected(self):
        response = client.post(
            "/transactions",
            json={
                "source": "manual",
                "transaction_type": "unknown",
                "total_price": 500000,
                "date": "2026-08-27",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_transaction_create_uses_generic_audit_log_with_user_id(self):
        audit = FakeAuditRepository()
        payload = {
            "source": "manual",
            "transaction_type": "income",
            "total_price": 600000,
            "date": "2026-08-27",
        }
        with (
            patch.object(api.config, "AUDIT_LOG_ENABLED", True),
            patch.object(api, "database_is_configured", return_value=True),
            patch.object(api, "get_audit_log_repository", return_value=audit),
        ):
            response = client.post("/transactions", json=payload)

        self.assertEqual(response.status_code, 201)
        event = audit.events[-1]
        self.assertEqual(event["event_type"], "transaction.create")
        self.assertEqual(event["user_id"], TEST_USER.id)
        self.assertEqual(event["entity_type"], "transaction")
        self.assertEqual(event["metadata"]["source"], "manual")
        self.assertEqual(event["metadata"]["method"], "manual")
        self.assertEqual(event["metadata"]["input"]["total_price"], 600000)
        self.assertEqual(event["metadata"]["input"]["date"], "2026-08-27")


if __name__ == "__main__":
    unittest.main()
