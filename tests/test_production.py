import base64
import json
import os
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from tests.support import isolated_app


application = isolated_app()
USER_ID = "00000000-0000-4000-8000-000000000001"
CAT_ID = "00000000-0000-4000-8000-000000000002"


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.user = SimpleNamespace(id=USER_ID, email="admin@example.test", app_metadata={"role": "admin"})
        self.auth = Mock()
        self.auth.auth.get_user.return_value = SimpleNamespace(user=self.user)
        self.patches = [patch.object(application, "supabase_auth", self.auth),
                        patch.object(application, "supabase_admin", None)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.headers = {"Authorization": "Bearer valid-test-token"}

    def test_invalid_admin_pagination_is_bad_request(self):
        database = Mock()
        with patch.object(application, "supabase_admin", database):
            for collection in ("cats", "users", "comments"):
                for query in ("page=abc", "page=0", "page=10001", "limit=0", "limit=101", "limit=NaN"):
                    with self.subTest(collection=collection, query=query):
                        response = self.client.get(f"/api/admin/{collection}?{query}", headers=self.headers)
                        self.assertEqual(response.status_code, 400)
        database.table.assert_not_called()

    def test_admin_database_outage_is_not_empty_success(self):
        for path in ("cats", "users", "comments", "overview"):
            response = self.client.get(f"/api/admin/{path}", headers=self.headers)
            self.assertEqual(response.status_code, 503)

    def test_non_admin_cannot_read_admin_data(self):
        self.user.app_metadata = {}
        response = self.client.get("/api/admin/users", headers=self.headers)
        self.assertEqual(response.status_code, 403)

    def test_admin_counts_use_database_aggregate(self):
        database = Mock()
        expected = {"total_cats": 2001, "total_likes": 8004, "total_users": 1050, "total_comments": 3200}
        database.rpc.return_value.execute.return_value = SimpleNamespace(data=[expected])
        with patch.object(application, "supabase_admin", database):
            response = self.client.get("/api/admin/overview", headers=self.headers)
        self.assertEqual(response.json, expected)
        database.rpc.assert_called_once_with("admin_overview_counts")
        database.table.assert_not_called()

    def test_admin_query_failure_returns_sanitized_unavailable(self):
        database = Mock()
        database.table.side_effect = RuntimeError("sensitive connection details")
        with patch.object(application, "supabase_admin", database):
            response = self.client.get("/api/admin/users", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("sensitive", response.get_data(as_text=True))

    def test_admin_users_fetches_page_counts_in_one_batch(self):
        database = Mock()
        query = database.table.return_value
        query.select.return_value = query
        query.order.return_value = query
        query.range.return_value = query
        query.execute.return_value = SimpleNamespace(data=[{"id": USER_ID, "display_name": "Cat"}], count=1)
        database.rpc.return_value.execute.return_value = SimpleNamespace(data=[{"user_id": USER_ID, "cats_count": 12, "total_likes": 25}])
        with patch.object(application, "supabase_admin", database):
            response = self.client.get("/api/admin/users", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["users"][0]["cats_count"], 12)
        self.assertEqual(response.json["users"][0]["total_likes"], 25)
        database.rpc.assert_called_once_with("admin_user_counts", {"p_user_ids": [USER_ID]})

    def test_duplicate_signup_exception_matches_confirmation_response(self):
        signup = Mock()
        signup.auth.sign_up.side_effect = RuntimeError("User already registered")
        with patch.object(application, "create_client", return_value=signup):
            response = self.client.post("/api/auth/register", json={"email": "member@example.test", "password": "strong-password-123"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json["requires_email_confirmation"])
        self.assertNotIn("already", response.get_data(as_text=True))
        signup.auth.close.assert_called_once_with()

    def test_search_quotes_filter_grammar(self):
        literal = application.postgrest_search_literal('a,b),role.eq.admin("\\%_*')
        self.assertTrue(literal.startswith('"%') and literal.endswith('%"'))
        # Decode PostgREST's quoted value; punctuation stays inside one literal.
        decoded = json.loads(literal)
        self.assertEqual(decoded, '%a,b),role.eq.admin("\\\\\\%\\_*%')

    def test_profile_invalidation_changes_generation(self):
        with patch.object(application, "cache_delete") as delete, patch.object(application, "bump_cache_counter") as bump:
            application.invalidate_profile_cache(USER_ID)
        delete.assert_called_once_with(application.make_cache_key("identity", USER_ID))
        bump.assert_called_once_with(f"profile:{USER_ID}")

    def test_profile_database_failure_does_not_cache_partial_success(self):
        database = Mock()
        database.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[{"display_name": "Cat"}])
        with patch.object(application, "supabase_admin", database), patch.object(application, "fetch_all_rows", side_effect=RuntimeError("offline")), patch.object(application, "cache_set") as cache:
            response = self.client.get(f"/api/user/{USER_ID}/profile")
        self.assertEqual(response.status_code, 503)
        cache.assert_not_called()

    def test_auth_outage_preserves_session_semantics(self):
        self.auth.auth.get_user.side_effect = ConnectionError("offline")
        response = self.client.get("/api/user/my-cats", headers=self.headers)
        self.assertEqual(response.status_code, 503)

    def test_invalid_auth_returns_unauthorized(self):
        error = RuntimeError("invalid JWT")
        error.status = 401
        self.auth.auth.get_user.side_effect = error
        response = self.client.get("/api/user/my-cats", headers=self.headers)
        self.assertEqual(response.status_code, 401)

    def test_admin_email_must_be_confirmed(self):
        self.user.app_metadata = {}
        with patch.object(application, "ADMIN_EMAIL_CONFIG", self.user.email):
            self.assertFalse(application.is_admin_user(self.user))
            self.user.email_confirmed_at = "2026-09-05T00:00:00Z"
            self.assertTrue(application.is_admin_user(self.user))

    def test_google_signin_cannot_authorize_stale_mismatched_identity(self):
        user = SimpleNamespace(email="new@example.test", identities=[
            {"provider": "google", "identity_data": {"email": "old@example.test"}, "last_sign_in_at": "2026-09-04T00:00:00Z"},
            {"provider": "google", "identity_data": {"email": "new@example.test"}, "last_sign_in_at": "2026-09-05T00:00:00Z"},
        ])
        with patch.object(application, "_jwt_primary_auth_method", return_value="oauth"):
            self.assertFalse(application.google_oauth_matches_current_email(user, "verified-token"))

    def test_oversized_upload_returns_413(self):
        with patch.object(application, "supabase_admin", Mock()), patch.object(application, "get_canonical_user_identity", return_value=(USER_ID, "Cat", "https://example.test/avatar.webp")), patch.dict(application.app.config, {"MAX_CONTENT_LENGTH": 100}):
            response = self.client.post("/api/cats/upload", headers=self.headers, data={"file": (BytesIO(b"x" * 200), "cat.png")})
        self.assertEqual(response.status_code, 413)

    def test_static_image_optimization_bounds_dimensions(self):
        source = BytesIO()
        Image.new("RGB", (2200, 1000), "white").save(source, "PNG")
        payload = source.getvalue()
        self.assertTrue(application.validate_image_file(payload, "cat.png")[0])
        optimized, extension, content_type = application.optimize_image_file(payload)
        with Image.open(BytesIO(optimized)) as result:
            self.assertEqual(result.width, 2048)
        self.assertEqual((extension, content_type), ("webp", "image/webp"))

    def test_api_is_not_exposed_to_cross_origin_browsers(self):
        response = self.client.options("/api/auth/login", headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"})
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_sensitive_responses_are_not_cached(self):
        response = self.client.get("/api/user/my-cats")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_untrusted_host_is_rejected(self):
        with patch.dict(application.app.config, {"TRUSTED_HOSTS": ["cats.example.test"]}):
            self.assertEqual(self.client.get("/livez", base_url="https://evil.example.test").status_code, 400)
            self.assertEqual(self.client.get("/livez", base_url="https://cats.example.test").status_code, 200)

    def test_readiness_checks_shared_limiter(self):
        backend = Mock()
        backend.storage.check.return_value = False
        with patch.object(application, "supabase_admin", Mock()), patch.object(application, "IS_PRODUCTION", True), patch.object(application, "limiter", backend):
            self.assertEqual(self.client.get("/healthz").status_code, 503)
        self.assertEqual(self.client.get("/livez").status_code, 200)


class ConfigurationTests(unittest.TestCase):
    def test_production_rejects_default_secret_and_local_rate_limits(self):
        with patch.object(application, "IS_PRODUCTION", True), patch.dict(os.environ, {"SECRET_KEY": "generate-a-random-32-char-string-here"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY.*shared Redis"):
                application.validate_production_configuration()

    def test_production_rejects_service_key_in_browser_config(self):
        payload = base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
        with patch.object(application, "IS_PRODUCTION", True), patch.object(application, "SUPABASE_ANON_KEY", "header." + payload + ".signature"):
            with self.assertRaisesRegex(RuntimeError, "privileged service-role"):
                application.validate_production_configuration()


if __name__ == "__main__":
    unittest.main()
