import base64
import json
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.support import isolated_app


USER_ID = "00000000-0000-0000-0000-000000000001"
CAT_ID = "00000000-0000-0000-0000-000000000002"


class AuthenticationSecurityTests(unittest.TestCase):
    def setUp(self):
        self.module = isolated_app()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.user = SimpleNamespace(
            id=USER_ID, email="member@example.test", phone="",
            email_confirmed_at="2026-09-01T00:00:00Z", app_metadata={},
            user_metadata={}, identities=[],
        )
        self.auth_service = Mock()
        self.auth_service.auth.get_user.return_value = SimpleNamespace(user=self.user)
        self.admin = Mock()
        self.stack.enter_context(patch.object(self.module, "supabase_auth", self.auth_service))
        self.stack.enter_context(patch.object(self.module, "supabase_admin", self.admin))
        self.stack.enter_context(patch.object(self.module, "SUPABASE_URL", "https://project.example.test"))
        self.stack.enter_context(patch.object(self.module, "SUPABASE_ANON_KEY", "test-anon"))
        self.client = self.module.app.test_client()
        self.headers = {"Authorization": "Bearer test-token"}

    def test_password_login_closes_transport_without_revoking_returned_session(self):
        auth_client = Mock()
        auth_client.auth.sign_in_with_password.return_value = SimpleNamespace(
            user=self.user,
            session=SimpleNamespace(access_token="access", refresh_token="refresh"),
        )
        with patch.object(self.module, "new_auth_client", return_value=auth_client), patch.object(
            self.module, "release_mismatched_google_after_password_login", return_value={"status": "not_needed"}
        ):
            response = self.client.post("/api/auth/login", json={"email": self.user.email, "password": "password123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["refresh_token"], "refresh")
        auth_client.auth.close.assert_called_once_with()
        auth_client.auth.sign_out.assert_not_called()

    def test_failed_login_closes_transport(self):
        auth_client = Mock()
        auth_client.auth.sign_in_with_password.side_effect = RuntimeError("provider failure")
        with patch.object(self.module, "new_auth_client", return_value=auth_client):
            response = self.client.post("/api/auth/login", json={"email": self.user.email, "password": "bad"})
        self.assertEqual(response.status_code, 401)
        auth_client.auth.close.assert_called_once_with()
        self.assertNotIn("provider failure", response.get_data(as_text=True))

    def test_reset_closes_transport_on_success_and_failure(self):
        for fails in (False, True):
            with self.subTest(fails=fails):
                auth_client = Mock()
                if fails:
                    auth_client.auth.reset_password_email.side_effect = RuntimeError("delivery detail")
                with patch.object(self.module, "new_auth_client", return_value=auth_client):
                    response = self.client.post("/api/auth/password-reset", json={"email": self.user.email})
                self.assertEqual(response.status_code, 503 if fails else 200)
                auth_client.auth.close.assert_called_once_with()

    def test_password_proof_revokes_temporary_session_and_closes_transport(self):
        auth_client = Mock()
        auth_client.auth.sign_in_with_password.return_value = SimpleNamespace(user=self.user, session=object())
        with patch.object(self.module, "new_auth_client", return_value=auth_client):
            response = self.client.post("/api/auth/password-proof", json={"password": "password123"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        auth_client.auth.sign_out.assert_called_once_with({"scope": "local"})
        auth_client.auth.close.assert_called_once_with()

    def test_security_change_closes_transport_when_password_is_wrong(self):
        auth_client = Mock()
        auth_client.auth.sign_in_with_password.side_effect = RuntimeError("wrong password")
        with patch.object(self.module, "new_auth_client", return_value=auth_client):
            response = self.client.put("/api/user/security", json={
                "action": "password", "current_password": "wrong", "value": "password123"
            }, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        auth_client.auth.close.assert_called_once_with()
        auth_client.auth.update_user.assert_not_called()

    def test_password_hint_does_not_resubmit_stale_role(self):
        self.user.app_metadata = {"role": "admin", "providers": ["email"]}
        self.module.mark_password_access(self.user)
        self.admin.auth.admin.update_user_by_id.assert_called_once_with(
            USER_ID, {"app_metadata": {"catrank_password_enabled": True}}
        )

    def test_editable_metadata_cannot_grant_admin_access(self):
        self.user.user_metadata = {"role": "admin"}
        self.assertFalse(self.module.is_admin_user(self.user))

    def test_allowlisted_email_requires_verification(self):
        with patch.object(self.module, "ADMIN_EMAIL_CONFIG", self.user.email):
            self.user.email_confirmed_at = None
            self.assertFalse(self.module.is_admin_user(self.user))
            self.user.email_confirmed_at = "2026-09-01T00:00:00Z"
            self.assertTrue(self.module.is_admin_user(self.user))

    def test_new_google_login_cannot_validate_an_old_mismatched_identity(self):
        self.user.identities = [
            {"provider": "google", "identity_data": {"email": "old@example.test"}, "last_sign_in_at": "2026-01-01T00:00:00Z"},
            {"provider": "google", "identity_data": {"email": self.user.email}, "last_sign_in_at": "2026-09-01T00:00:00Z"},
        ]
        payload = base64.urlsafe_b64encode(json.dumps({"amr": [{"method": "oauth", "timestamp": 1}]}).encode()).decode().rstrip("=")
        self.assertFalse(self.module.google_oauth_matches_current_email(self.user, f"header.{payload}.signature"))

    def test_missing_authentication_never_reaches_database(self):
        response = self.client.delete(f"/api/cats/{CAT_ID}")
        self.assertEqual(response.status_code, 401)
        self.admin.table.assert_not_called()
        self.auth_service.auth.get_user.assert_not_called()

    def test_other_users_cat_cannot_be_deleted(self):
        with patch.object(self.module, "get_db_row", return_value={"id": CAT_ID, "user_id": CAT_ID}):
            response = self.client.delete(f"/api/cats/{CAT_ID}", headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.admin.table.return_value.delete.assert_not_called()
