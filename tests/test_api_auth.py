import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src import api
from src.auth_service import AuthServiceError, AuthenticatedUser


USER_ID = "11111111-1111-4111-8111-111111111111"


def session_payload():
    return {
        "access_token": "access-secret-token",
        "refresh_token": "refresh-secret-token",
        "expires_in": 3600,
        "user": {"id": USER_ID, "email": "user@example.com"},
    }


class FakeAuditRepository:
    def __init__(self):
        self.events = []

    def record(self, **values):
        self.events.append(values)


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.audit = FakeAuditRepository()
        self.configured_patch = patch.object(
            api, "database_is_configured", return_value=True
        )
        self.audit_patch = patch.object(
            api, "get_audit_log_repository", return_value=self.audit
        )
        self.configured_patch.start()
        self.audit_patch.start()

    def tearDown(self):
        self.client.cookies.clear()
        self.audit_patch.stop()
        self.configured_patch.stop()
        api.app.dependency_overrides.clear()

    def test_login_sets_httponly_cookies_and_audits_without_secrets(self):
        with patch.object(
            api, "login_supabase_user", new=AsyncMock(return_value=session_payload())
        ):
            response = self.client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "password-kuat"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["authenticated"])
        self.assertNotIn("access_token", response.text)
        self.assertNotIn("refresh_token", response.text)
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn(api.config.AUTH_ACCESS_COOKIE_NAME, set_cookie)
        event = self.audit.events[-1]
        self.assertEqual(event["event_type"], "auth.login")
        self.assertEqual(event["user_id"], USER_ID)
        self.assertEqual(event["metadata"]["method"], "login")
        self.assertEqual(
            event["metadata"]["input"],
            {"email": "user@example.com"},
        )
        self.assertNotIn("password", str(event["metadata"]).lower())
        self.assertNotIn("token", str(event["metadata"]).lower())

    def test_register_can_require_email_confirmation(self):
        payload = {
            "user": {"id": USER_ID, "email": "baru@example.com"},
            "access_token": None,
            "refresh_token": None,
        }
        with patch.object(
            api, "register_supabase_user", new=AsyncMock(return_value=payload)
        ):
            response = self.client.post(
                "/auth/register",
                json={"email": "baru@example.com", "password": "password-kuat"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["authenticated"])
        self.assertTrue(response.json()["data"]["requires_email_confirmation"])

    def test_register_accepts_top_level_supabase_user_response(self):
        payload = {"id": USER_ID, "email": "baru@example.com"}
        with patch.object(
            api, "register_supabase_user", new=AsyncMock(return_value=payload)
        ):
            response = self.client.post(
                "/auth/register",
                json={"email": "baru@example.com", "password": "password-kuat"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["user"]["id"], USER_ID)
        self.assertFalse(data["authenticated"])
        self.assertTrue(data["requires_email_confirmation"])

    def test_failed_login_is_audited_without_user_id(self):
        with patch.object(
            api,
            "login_supabase_user",
            new=AsyncMock(side_effect=AuthServiceError("Email atau password salah.", 401)),
        ):
            response = self.client.post(
                "/auth/login",
                json={"email": "user@example.com", "password": "password-salah"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.audit.events[-1]["status"], "failure")
        self.assertIsNone(self.audit.events[-1]["user_id"])
        self.assertEqual(
            self.audit.events[-1]["metadata"]["error_message"],
            "Email atau password salah.",
        )

    def test_rate_limit_error_message_is_saved_in_audit_metadata(self):
        with patch.object(
            api,
            "register_supabase_user",
            new=AsyncMock(
                side_effect=AuthServiceError(
                    "Terlalu banyak percobaan. Coba kembali nanti.",
                    429,
                )
            ),
        ):
            response = self.client.post(
                "/auth/register",
                json={"email": "user@example.com", "password": "password-kuat"},
            )

        self.assertEqual(response.status_code, 429)
        event = self.audit.events[-1]
        self.assertEqual(event["status"], "failure")
        self.assertEqual(
            event["metadata"]["error_message"],
            "Terlalu banyak percobaan. Coba kembali nanti.",
        )
        self.assertNotIn("password", str(event["metadata"]).lower())

    def test_protected_endpoint_requires_login(self):
        response = self.client.get("/transactions")
        self.assertEqual(response.status_code, 401)
        self.assertIn("login", response.json()["detail"].lower())

        extraction = self.client.post(
            "/extract",
            json={"text": "beli beras 1 kg 10000", "reference_date": "2026-08-29"},
        )
        self.assertEqual(extraction.status_code, 401)

    def test_me_validates_cookie_and_returns_no_token(self):
        self.client.cookies.set(api.config.AUTH_ACCESS_COOKIE_NAME, "secret-token")
        user = AuthenticatedUser(id=USER_ID, email="user@example.com")
        with patch.object(
            api, "get_supabase_user", new=AsyncMock(return_value=user)
        ):
            response = self.client.get("/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["user"]["id"], USER_ID)
        self.assertNotIn("secret-token", response.text)


if __name__ == "__main__":
    unittest.main()
