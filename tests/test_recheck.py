"""Regression cases found during the second deployment review."""
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from redis.exceptions import ConnectionError as RedisConnectionError
from tests.support import isolated_app

module = isolated_app()
USER_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
CAT_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'


def query_mock(*rows):
    query = Mock()
    for method in ('select', 'eq', 'limit', 'upsert', 'update', 'is_', 'range'):
        getattr(query, method).return_value = query
    query.execute.side_effect = [SimpleNamespace(data=row) for row in rows]
    return query


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=USER_ID, email='member@example.test', phone='',
                                    user_metadata={}, app_metadata={'role': 'admin'}, identities=[])
        self.auth = Mock()
        self.auth.auth.get_user.return_value = SimpleNamespace(user=self.user)
        self.database = Mock()
        for change in (patch.object(module, 'supabase_auth', self.auth),
                       patch.object(module, 'supabase_admin', self.database)):
            change.start()
            self.addCleanup(change.stop)
        self.client = module.app.test_client()
        self.headers = {'Authorization': 'Bearer test-token'}

    def test_mixed_case_uuid_cannot_bypass_admin_self_delete_protection(self):
        response = self.client.delete(f'/api/admin/users/{USER_ID.upper()}/force-delete', headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.database.auth.admin.delete_user.assert_not_called()

    def test_bootstrap_conflict_keeps_the_profile_created_by_another_request(self):
        query = query_mock([], [], [{'id': USER_ID}])
        self.database.table.return_value = query
        module.ensure_auth_profile(self.user)
        self.assertEqual(query.upsert.call_args.kwargs, {'on_conflict': 'id', 'ignore_duplicates': True})
        self.assertEqual(query.update.call_args.args[0], {'email': self.user.email})
        query.insert.assert_not_called()

    def test_bootstrap_read_outage_does_not_attempt_an_insert(self):
        query = query_mock()
        query.execute.side_effect = RuntimeError('database offline')
        self.database.table.return_value = query
        response = self.client.post('/api/auth/bootstrap', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        query.upsert.assert_not_called()

    def test_avatar_repair_uses_compare_and_set_and_skips_stale_metadata(self):
        query = query_mock([{'id': USER_ID, 'avatar_url': None}], [], [{'id': USER_ID}])
        self.database.table.return_value = query
        with patch.object(module, '_google_avatar_from_user', return_value='https://example.test/google.webp'):
            module.ensure_auth_profile(self.user)
        query.is_.assert_called_once_with('avatar_url', 'null')
        self.database.auth.admin.update_user_by_id.assert_not_called()

    def test_failed_contact_write_does_not_claim_profile_is_ready(self):
        query = query_mock([{'id': USER_ID, 'avatar_url': None}], [])
        self.database.table.return_value = query
        response = self.client.post('/api/auth/bootstrap', headers=self.headers)
        self.assertEqual(response.status_code, 503)

    def test_oversized_json_keeps_413_for_mutation_routes(self):
        row = {'id': CAT_ID, 'user_id': USER_ID, 'cat_id': CAT_ID,
               'created_at': datetime.now(timezone.utc).isoformat()}
        cases = [('put', f'/api/cats/{CAT_ID}'), ('post', f'/api/cats/{CAT_ID}/comments'),
                 ('put', '/api/user/profile'), ('put', f'/api/admin/users/{USER_ID}/profile'),
                 ('put', f'/api/comments/{CAT_ID}')]
        with patch.dict(module.app.config, {'MAX_CONTENT_LENGTH': 100}), patch.object(module, 'get_db_row', return_value=row), patch.object(module, 'get_canonical_user_identity', return_value=(USER_ID, 'Cat', '')):
            for method, url in cases:
                with self.subTest(url=url):
                    result = getattr(self.client, method)(url, headers=self.headers, json={'comment': 'x' * 1000})
                    self.assertEqual(result.status_code, 413)

    def test_comments_containing_only_control_characters_are_rejected(self):
        row = {'id': CAT_ID, 'user_id': USER_ID, 'cat_id': CAT_ID}
        with patch.object(module, 'get_db_row', return_value=row):
            response = self.client.put(f'/api/comments/{CAT_ID}', headers=self.headers, json={'comment': '\x00\x01'})
        self.assertEqual(response.status_code, 400)
        self.database.rpc.assert_not_called()

    def test_duplicate_comment_rpc_result_does_not_send_notifications(self):
        self.database.rpc.return_value.execute.return_value = SimpleNamespace(data=[{'status': 'duplicate'}])
        with patch.object(module, 'get_db_row', return_value={'id': CAT_ID, 'user_id': USER_ID}), patch.object(module, 'get_canonical_user_identity', return_value=(USER_ID, 'Cat', '')), patch.object(module, 'push_notification') as notify:
            response = self.client.post(f'/api/cats/{CAT_ID}/comments', headers=self.headers, json={'comment': 'Hello'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.database.rpc.call_args.args[0], 'insert_comment_once')
        notify.assert_not_called()

    def test_comment_response_uses_database_creation_time(self):
        stamp = '2026-09-05T08:00:00+00:00'
        self.database.rpc.return_value.execute.return_value = SimpleNamespace(data=[{'status': 'inserted', 'created_at': stamp}])
        with patch.object(module, 'get_db_row', return_value={'id': CAT_ID, 'user_id': USER_ID}), patch.object(module, 'get_canonical_user_identity', return_value=(USER_ID, 'Cat', '')):
            response = self.client.post(f'/api/cats/{CAT_ID}/comments', headers=self.headers, json={'comment': 'Hello'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json['comment']['created_at'], stamp)
        self.assertNotIn('user_email', response.json['comment'])

    def test_fetch_all_rows_rejects_truncation(self):
        query = query_mock([{'id': n} for n in range(4)])
        with self.assertRaisesRegex(RuntimeError, 'row limit'):
            module.fetch_all_rows(lambda: query, max_rows=3)

    def test_fetch_all_rows_accepts_exact_limit(self):
        query = query_mock([{'id': n} for n in range(3)])
        self.assertEqual(len(module.fetch_all_rows(lambda: query, max_rows=3)), 3)
        query.range.assert_called_once_with(0, 3)

    def test_account_deletion_aborts_before_destroying_data_if_enumeration_is_incomplete(self):
        with patch.object(module, 'fetch_all_rows', side_effect=RuntimeError('row limit')):
            response = self.client.delete(f'/api/admin/users/{CAT_ID}/force-delete', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.database.auth.admin.delete_user.assert_not_called()

    def test_cat_deletion_invalidates_comments(self):
        row = {'id': CAT_ID, 'user_id': USER_ID, 'image_url': ''}
        with patch.object(module, 'get_db_row', return_value=row), patch.object(module, 'invalidate_comments') as invalidate:
            response = self.client.delete(f'/api/cats/{CAT_ID}', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        invalidate.assert_called_once_with(CAT_ID)

    def test_rate_limit_storage_outage_fails_closed(self):
        with patch.object(module.limiter, 'enabled', True), patch.object(module.limiter, '_in_memory_fallback_enabled', False), patch.object(module.limiter.limiter, 'hit', side_effect=RedisConnectionError('offline')):
            response = self.client.post('/api/auth/login', json={'email': self.user.email, 'password': 'password123'})
        self.assertEqual(response.status_code, 503)

    def test_missing_auth_user_returns_profile_not_found(self):
        query = query_mock([])
        self.database.table.return_value = query
        error = RuntimeError('user not found')
        error.status = 404
        self.database.auth.admin.get_user_by_id.side_effect = error
        with patch.object(module, 'fetch_all_rows', return_value=[]):
            response = self.client.get(f'/api/user/{USER_ID}/profile')
        self.assertEqual(response.status_code, 404)

    def test_wrong_password_still_returns_401(self):
        auth = Mock()
        error = RuntimeError('invalid credentials')
        error.status = 400
        auth.auth.sign_in_with_password.side_effect = error
        with patch.object(module, 'new_auth_client', return_value=auth), patch.object(module, 'SUPABASE_URL', 'https://example.test'), patch.object(module, 'SUPABASE_ANON_KEY', 'test-public'):
            response = self.client.post('/api/auth/login', json={'email': self.user.email, 'password': 'wrong'})
        self.assertEqual(response.status_code, 401)
        auth.auth.close.assert_called_once_with()


class OriginValidationTests(unittest.TestCase):
    def test_bad_origins_fail_during_configuration(self):
        for name, value in [('PUBLIC_SITE_URL', 'https://:443'), ('PUBLIC_SITE_URL', 'https://example.test:invalid'),
                            ('SUPABASE_URL', 'https://user:password@example.test'), ('SUPABASE_URL', 'https://example.test/path'),
                            ('RATE_LIMIT_STORAGE_URI', 'redis://')]:
            with self.subTest(name=name, value=value), patch.multiple(module, IS_PRODUCTION=True,
                    PUBLIC_SITE_URL='https://cats.example.test', SUPABASE_URL='https://db.example.test',
                    SUPABASE_ANON_KEY='test-public', SUPABASE_SERVICE_KEY='test-service',
                    RATE_LIMIT_STORAGE_URI='redis://cache.example.test'), patch.object(module, name, value), patch.dict(os.environ, {'SECRET_KEY': 'test-signing-key-' * 4}, clear=True):
                with self.assertRaisesRegex(RuntimeError, name):
                    module.validate_production_configuration()
