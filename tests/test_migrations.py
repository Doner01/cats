"""Exercise all migrations against an isolated, disposable local PostgreSQL.

Requires PostgreSQL server tools on PATH. No configured database or .env is used.
The tiny auth/storage schemas stand in for the Supabase-managed schemas.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


TOOLS = ("initdb", "pg_ctl", "psql")


@unittest.skipUnless(all(shutil.which(tool) for tool in TOOLS) and os.geteuid() != 0,
                     "Local PostgreSQL server tools and a non-root user are required")
class MigrationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="catrank-postgres-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)
        cls.data = cls.root / "data"
        subprocess.run(["initdb", "-D", str(cls.data), "-A", "trust", "-U", "catrank_test", "--no-locale", "-E", "UTF8"],
                       check=True, capture_output=True, text=True)
        started = subprocess.run([
            "pg_ctl", "-D", str(cls.data), "-l", str(cls.root / "postgres.log"),
            "-o", f"-F -h '' -k {cls.root} -p 55439", "-w", "start"
        ], capture_output=True, text=True)
        if started.returncode:
            raise RuntimeError((cls.root / "postgres.log").read_text())
        cls.addClassCleanup(lambda: subprocess.run(
            ["pg_ctl", "-D", str(cls.data), "-m", "immediate", "-w", "stop"],
            check=True, capture_output=True, text=True,
        ))
        cls.sql("""
            CREATE ROLE anon;
            CREATE ROLE authenticated;
            CREATE ROLE service_role BYPASSRLS;
            CREATE SCHEMA auth;
            CREATE TABLE auth.users (
                id uuid PRIMARY KEY, email text, phone text,
                raw_user_meta_data jsonb NOT NULL DEFAULT '{}'::jsonb
            );
            CREATE SCHEMA storage;
            CREATE TABLE storage.buckets (
                id text PRIMARY KEY, name text, public boolean,
                file_size_limit bigint, allowed_mime_types text[]
            );
        """)
        cls.migrations = sorted((Path(__file__).resolve().parents[1] / "migrations").glob("*.sql"))
        for migration in cls.migrations:
            cls.sql(migration.read_text())

    @classmethod
    def sql(cls, statement, *, success=True):
        result = subprocess.run([
            "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", str(cls.root),
            "-p", "55439", "-U", "catrank_test", "-d", "postgres",
        ], input=statement, capture_output=True, text=True)
        if success and result.returncode:
            raise AssertionError(result.stderr)
        if not success and not result.returncode:
            raise AssertionError("A forbidden/invalid SQL operation unexpectedly succeeded")
        return result.stdout.strip() if success else result.stderr

    def setUp(self):
        self.owner = str(uuid.uuid4())
        self.actor = str(uuid.uuid4())
        self.cat = str(uuid.uuid4())
        self.sql(f"""
            INSERT INTO auth.users(id, email, raw_user_meta_data) VALUES
                ('{self.owner}', 'owner@example.test', '{{"display_name":"Owner","role":"admin"}}'),
                ('{self.actor}', 'actor@example.test', '{{"display_name":"Actor"}}');
            INSERT INTO public.cats(id, user_id, name, image_url)
                VALUES ('{self.cat}', '{self.owner}', 'Test cat', 'https://images.example.test/cat.webp');
        """)

    def test_migrations_can_be_reapplied(self):
        for migration in self.migrations:
            self.sql(migration.read_text())

    def test_anonymous_and_authenticated_clients_cannot_bypass_backend(self):
        for role in ("anon", "authenticated"):
            for table in ("profiles", "cats", "likes", "comments", "notifications", "favorites", "comment_likes"):
                with self.subTest(role=role, table=table):
                    self.sql(f"SET ROLE {role}; SELECT * FROM public.{table};", success=False)
            for function in (
                f"toggle_cat_like('{self.cat}', '{self.actor}')",
                f"set_comment_like('{uuid.uuid4()}', '{self.actor}', true)",
                f"edit_comment_with_window('{uuid.uuid4()}', '{self.actor}', 'changed', true)",
                "admin_overview_counts()",
            ):
                self.sql(f"SET ROLE {role}; SELECT * FROM public.{function};", success=False)
        self.assertEqual(self.sql(f"SET ROLE service_role; SELECT count(*) FROM public.cats WHERE id='{self.cat}';"), "1")

    def test_profile_bootstrap_does_not_trust_role_metadata(self):
        self.assertEqual(self.sql(f"SELECT display_name || ':' || role FROM public.profiles WHERE id='{self.owner}';"), "Owner:user")
        self.sql(f"UPDATE public.profiles SET display_name='Renamed', avatar_url='https://example.test/avatar.webp' WHERE id='{self.owner}';")
        self.assertEqual(self.sql(f"SELECT user_name || ':' || user_avatar FROM public.cats WHERE id='{self.cat}';"), "Renamed:https://example.test/avatar.webp")

    def test_concurrent_toggles_do_not_duplicate_votes_or_lose_counts(self):
        statement = f"SET ROLE service_role; SELECT * FROM public.toggle_cat_like('{self.cat}', '{self.actor}');"
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.sql(statement), range(20)))
        self.assertEqual(results.count("liked|1"), 10)
        self.assertEqual(results.count("unliked|0"), 10)
        self.assertEqual(self.sql(f"SELECT likes_count FROM public.cats WHERE id='{self.cat}';"), "0")
        self.assertEqual(self.sql(f"SELECT count(*) FROM public.likes WHERE cat_id='{self.cat}';"), "0")

    def test_deleting_voter_updates_count_on_surviving_cat(self):
        self.sql(f"SELECT * FROM public.toggle_cat_like('{self.cat}', '{self.actor}');")
        self.sql(f"DELETE FROM auth.users WHERE id='{self.actor}';")
        self.assertEqual(self.sql(f"SELECT likes_count FROM public.cats WHERE id='{self.cat}';"), "0")

    def test_comment_likes_are_idempotent_and_edit_window_is_enforced(self):
        comment = str(uuid.uuid4())
        self.sql(f"INSERT INTO public.comments(id,cat_id,user_id,comment,created_at) VALUES ('{comment}','{self.cat}','{self.owner}','original',now()-interval '3 minutes');")
        self.assertEqual(self.sql(f"SELECT status FROM public.edit_comment_with_window('{comment}','{self.actor}','changed',false);"), "forbidden")
        self.assertEqual(self.sql(f"SELECT status FROM public.edit_comment_with_window('{comment}','{self.owner}','changed',false);"), "expired")
        self.assertEqual(self.sql(f"SELECT status FROM public.edit_comment_with_window('{comment}','{self.actor}','moderated',true);"), "updated")
        for _ in range(2):
            self.assertEqual(self.sql(f"SELECT likes_count FROM public.set_comment_like('{comment}','{self.actor}',true);"), "1")
        self.assertEqual(self.sql(f"SELECT likes_count FROM public.set_comment_like('{comment}','{self.actor}',false);"), "0")

    def test_cross_cat_comment_replies_are_rejected(self):
        parent = str(uuid.uuid4())
        other_cat = str(uuid.uuid4())
        self.sql(f"""
            INSERT INTO public.comments(id,cat_id,user_id,comment) VALUES ('{parent}','{self.cat}','{self.owner}','parent');
            INSERT INTO public.cats(id,user_id,name,image_url) VALUES ('{other_cat}','{self.owner}','Other','https://example.test/cat.webp');
        """)
        self.sql(f"INSERT INTO public.comments(cat_id,user_id,parent_id,comment) VALUES ('{other_cat}','{self.actor}','{parent}','bad reply');", success=False)

    def test_aggregate_includes_more_than_one_thousand_cats(self):
        before = json.loads(self.sql("SELECT row_to_json(r) FROM public.admin_overview_counts() r;"))
        self.sql(f"""
            INSERT INTO public.cats(user_id,name,image_url,likes_count)
            SELECT '{self.owner}', 'Count test', 'https://example.test/cat.webp', 2
            FROM generate_series(1,1101);
        """)
        after = json.loads(self.sql("SET ROLE service_role; SELECT row_to_json(r) FROM public.admin_overview_counts() r;"))
        self.assertEqual(after["total_cats"] - before["total_cats"], 1101)
        self.assertEqual(after["total_likes"] - before["total_likes"], 2202)

    def test_admin_user_counts_includes_users_with_no_cats(self):
        self.sql(f"SELECT * FROM public.toggle_cat_like('{self.cat}', '{self.actor}');")
        counts = json.loads(self.sql(f"SET ROLE service_role; SELECT json_agg(r) FROM public.admin_user_counts(ARRAY['{self.owner}','{self.actor}']::uuid[]) r;"))
        by_user = {row['user_id']: row for row in counts}
        self.assertEqual(by_user[self.owner]['cats_count'], 1)
        self.assertEqual(by_user[self.owner]['total_likes'], 1)
        self.assertEqual(by_user[self.actor]['cats_count'], 0)
        self.sql(f"SET ROLE authenticated; SELECT * FROM public.admin_user_counts(ARRAY['{self.owner}']::uuid[]);", success=False)

    def test_concurrent_duplicate_comments_insert_once(self):
        def attempt(_):
            payload = json.dumps({'id': str(uuid.uuid4()), 'cat_id': self.cat,
                                  'user_id': self.actor, 'comment': 'Same comment'})
            return self.sql(f"SET ROLE service_role; SELECT status FROM public.insert_comment_once('{payload}'::jsonb);")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(16)))
        self.assertEqual(results.count('inserted'), 1)
        self.assertEqual(results.count('duplicate'), 15)
        self.assertEqual(self.sql(f"SELECT count(*) FROM public.comments WHERE cat_id='{self.cat}';"), '1')

    def test_comment_deduplication_expires_and_is_scoped_to_account(self):
        payload = {'id': str(uuid.uuid4()), 'cat_id': self.cat, 'user_id': self.actor, 'comment': 'Hello'}
        def insert_as(user_id):
            payload.update(id=str(uuid.uuid4()), user_id=user_id)
            return self.sql(f"SELECT status FROM public.insert_comment_once('{json.dumps(payload)}'::jsonb);")
        self.assertEqual(insert_as(self.actor), 'inserted')
        self.assertEqual(insert_as(self.owner), 'inserted')
        self.sql(f"UPDATE public.comments SET created_at=now()-interval '61 seconds' WHERE cat_id='{self.cat}';")
        self.assertEqual(insert_as(self.actor), 'inserted')
        for role in ('anon', 'authenticated'):
            self.sql(f"SET ROLE {role}; SELECT * FROM public.insert_comment_once('{json.dumps(payload)}'::jsonb);", success=False)
