import io
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The test runner should set Supabase env vars to empty strings before import.
import app as app_module


class FakeAuthAPI:
    def get_user(self, token):
        if token != "valid-test-token":
            raise ValueError("invalid token")
        return SimpleNamespace(
            user=SimpleNamespace(
                id="11111111-1111-4111-8111-111111111111",
                email="user@example.com",
                user_metadata={},
                app_metadata={},
            )
        )


class FakeAuthClient:
    def __init__(self):
        self.auth = FakeAuthAPI()


class CatRankSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_auth = app_module.supabase_auth
        self.original_admin = app_module.supabase_admin
        self.original_demo = app_module.ENABLE_DEMO_DATA
        self.original_admin_email_config = app_module.ADMIN_EMAIL_CONFIG
        app_module.supabase_auth = FakeAuthClient()
        app_module.supabase_admin = None
        app_module.ENABLE_DEMO_DATA = False
        app_module.ADMIN_EMAIL_CONFIG = ""
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.supabase_auth = self.original_auth
        app_module.supabase_admin = self.original_admin
        app_module.ENABLE_DEMO_DATA = self.original_demo
        app_module.ADMIN_EMAIL_CONFIG = self.original_admin_email_config

    def test_missing_bearer_token_is_rejected(self):
        response = self.client.get("/api/user/liked-cats")
        self.assertEqual(response.status_code, 401)

    def test_invalid_bearer_token_never_falls_back_to_admin(self):
        response = self.client.get(
            "/api/user/liked-cats",
            headers={"Authorization": "Bearer definitely-invalid"},
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_token_reaches_route_but_missing_database_is_not_fake_success(self):
        response = self.client.get(
            "/api/user/liked-cats",
            headers={"Authorization": "Bearer valid-test-token"},
        )
        self.assertEqual(response.status_code, 503)

    def test_user_metadata_role_cannot_grant_admin(self):
        user = SimpleNamespace(
            email="user@example.com",
            user_metadata={"role": "admin"},
            app_metadata={},
        )
        self.assertFalse(app_module.is_admin_user(user))

    def test_server_controlled_app_metadata_can_grant_admin(self):
        user = SimpleNamespace(
            email="user@example.com",
            user_metadata={},
            app_metadata={"role": "admin"},
        )
        self.assertTrue(app_module.is_admin_user(user))

    def test_security_headers_are_present(self):
        response = self.client.get("/")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertTrue(response.headers.get("X-Request-ID"))

    def test_malicious_image_url_is_rejected(self):
        url = app_module.sanitize_image_url('https://example.com/" onerror="alert(1)')
        self.assertTrue(url.startswith("https://api.dicebear.com/"))

    def test_avatar_seed_is_url_encoded(self):
        url = app_module.generate_default_avatar('name&x="bad"')
        self.assertNotIn('name&x=', url)
        self.assertIn('%26', url)

    def test_real_image_is_verified_and_optimized(self):
        src = io.BytesIO()
        Image.new("RGB", (900, 700), (255, 255, 255)).save(src, format="JPEG")
        raw = src.getvalue()
        valid, error = app_module.validate_image_file(raw, "cat.jpg")
        self.assertTrue(valid, error)

        optimized, ext, mime = app_module.optimize_image_file(raw, avatar=True)
        self.assertEqual(ext, "webp")
        self.assertEqual(mime, "image/webp")
        with Image.open(io.BytesIO(optimized)) as img:
            self.assertLessEqual(max(img.size), 512)

    def test_fake_image_is_rejected(self):
        valid, _ = app_module.validate_image_file(b"not-an-image-at-all", "cat.jpg")
        self.assertFalse(valid)

    def test_canonical_identity_prefers_profile_over_editable_user_metadata(self):
        class FakeQuery:
            def select(self, *_args, **_kwargs): return self
            def eq(self, *_args, **_kwargs): return self
            def limit(self, *_args, **_kwargs): return self
            def execute(self):
                return SimpleNamespace(data=[{
                    "display_name": "Canonical Name",
                    "avatar_url": "https://example.com/canonical.webp",
                }])

        class FakeAdmin:
            def table(self, _name): return FakeQuery()

        app_module.supabase_admin = FakeAdmin()
        user = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            email="user@example.com",
            user_metadata={
                "display_name": "Spoofed Name",
                "avatar_url": "https://evil.example/spoof.webp",
            },
        )
        user_id, name, avatar = app_module.get_canonical_user_identity(user)
        self.assertEqual(user_id, user.id)
        self.assertEqual(name, "Canonical Name")
        self.assertEqual(avatar, "https://example.com/canonical.webp")

    def test_admin_template_does_not_render_rows_with_raw_innerhtml(self):
        root = os.path.dirname(os.path.dirname(__file__))
        source = open(os.path.join(root, "templates", "admin.html"), encoding="utf-8").read()
        self.assertNotIn("tbody.innerHTML", source)
        self.assertIn("textContent", source)

    def test_toast_message_is_rendered_as_text_not_html(self):
        root = os.path.dirname(os.path.dirname(__file__))
        source = open(os.path.join(root, "static", "js", "toast.js"), encoding="utf-8").read()
        self.assertIn('messageWrap.textContent = String(message ?? "")', source)
        self.assertNotIn('<div class="flex-grow">${message}</div>', source)

    def test_likes_count_is_not_manually_editable_by_cat_update_api(self):
        root = os.path.dirname(os.path.dirname(__file__))
        source = open(os.path.join(root, "app.py"), encoding="utf-8").read()
        self.assertNotIn('updates["likes_count"]', source)

    def test_migration_revokes_direct_browser_table_writes(self):
        root = os.path.dirname(os.path.dirname(__file__))
        sql = open(os.path.join(root, "supabase_migration.sql"), encoding="utf-8").read()
        for table in ("profiles", "cats", "likes", "comments", "notifications"):
            self.assertIn(f"REVOKE ALL ON TABLE public.{table} FROM anon, authenticated;", sql)
        self.assertNotIn('CREATE POLICY "Allow authenticated insert on cats"', sql)
        self.assertNotIn('CREATE POLICY "Allow authenticated insert on comments"', sql)
        self.assertIn("REVOKE INSERT, UPDATE, DELETE ON storage.objects FROM anon, authenticated;", sql)


    def test_migration_backfills_existing_auth_users(self):
        sql = (PROJECT_ROOT / "supabase_migration.sql").read_text(encoding="utf-8")
        self.assertIn("FROM auth.users u", sql)
        self.assertIn("ON CONFLICT (id) DO NOTHING", sql)

    def test_regular_profile_api_rejects_direct_avatar_urls(self):
        source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('if "avatar_url" in data:', source)
        self.assertIn("Avatar URLs cannot be set directly", source)
        profile_js = (PROJECT_ROOT / "templates" / "profile.html").read_text(encoding="utf-8")
        self.assertIn("reset_avatar: isResetAvatarChosen", profile_js)

    def test_storage_cleanup_requires_managed_origin_and_prefix(self):
        source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("allowed_prefix: Optional[str] = None", source)
        self.assertIn("parsed.netloc == supabase_origin.netloc", source)
        self.assertIn("not key.startswith(allowed_prefix)", source)

    def test_auth_metadata_cannot_resync_canonical_profile(self):
        sql = (PROJECT_ROOT / "supabase_migration.sql").read_text(encoding="utf-8")
        self.assertIn("AFTER INSERT ON auth.users", sql)
        self.assertNotIn("AFTER INSERT OR UPDATE ON auth.users", sql)
        self.assertIn("AFTER UPDATE OF email ON auth.users", sql)
        self.assertIn("CREATE OR REPLACE FUNCTION public.sync_profile_email", sql)
        self.assertIn("avatar_url, role", sql)
        creation_function = sql.split("CREATE OR REPLACE FUNCTION public.handle_new_user()", 1)[1].split("$$ LANGUAGE", 1)[0]
        self.assertRegex(creation_function, r"NULL,\s*'user'")
        self.assertNotIn("raw_user_meta_data->>'avatar_url'", creation_function)

    def test_atomic_like_rpc_is_service_role_only(self):
        sql = (PROJECT_ROOT / "supabase_migration.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE FUNCTION public.toggle_cat_like", sql)
        self.assertIn("FOR UPDATE", sql)
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.toggle_cat_like(UUID, UUID) TO service_role",
            sql,
        )
        self.assertIn(
            "REVOKE ALL ON FUNCTION public.toggle_cat_like(UUID, UUID) FROM PUBLIC, anon, authenticated",
            sql,
        )

    def test_security_headers_include_csp(self):
        source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('response.headers["Content-Security-Policy"]', source)
        self.assertIn("object-src 'none'", source)
        self.assertIn("frame-ancestors 'none'", source)



if __name__ == "__main__":
    unittest.main()
