"""Flask comment delivery with deterministic Supabase/transport failures, no credentials."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import httpx
from postgrest.exceptions import APIError
from tests.support import isolated_app

module = isolated_app()
REAL_NOTIFY = module.push_notification
USER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
CAT = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
PARENT = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
STAMP = '2026-09-06T00:00:00+00:00'


def query(rows):
    q = Mock()
    for name in ('select', 'eq', 'limit', 'order', 'range', 'insert'):
        getattr(q, name).return_value = q
    q.execute.return_value = SimpleNamespace(data=rows)
    return q


class CommentDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.db, self.auth = Mock(), Mock()
        self.auth.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(
            id=USER, email='test@example.test', user_metadata={}, app_metadata={}, identities=[]))
        self.cat = query([{'id': CAT, 'user_id': PARENT, 'name': 'Cat'}])
        self.comments = query([])
        self.db.table.side_effect = lambda name: self.cat if name == 'cats' else self.comments
        self.insert = Mock()
        self.insert.execute.return_value = SimpleNamespace(data=[{'status': 'inserted', 'created_at': STAMP}])
        self.db.rpc.return_value = self.insert
        for p in (patch.object(module, 'supabase_admin', self.db), patch.object(module, 'supabase_auth', self.auth),
                  patch.object(module, 'get_canonical_user_identity', return_value=(USER, 'Tester', '')),
                  patch.object(module, 'sleep'), patch.object(module, 'cache_get_dict', return_value=None)):
            p.start(); self.addCleanup(p.stop)
        self.notify = patch.object(module, 'push_notification').start()
        self.addCleanup(patch.stopall)
        self.client = module.app.test_client()
        self.headers = {'Authorization': 'Bearer private-test-token', 'X-Request-ID': 'comment-test-123'}

    def post(self, **extra):
        return self.client.post(f'/api/cats/{CAT}/comments', headers=self.headers,
                                json={'comment': 'Hello', **extra})

    def test_normal_insert_uses_canonical_owner_and_database_time(self):
        res = self.post(user_id=PARENT)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json['comment']['user_id'], USER)
        self.assertEqual(res.json['comment']['created_at'], STAMP)
        self.assertNotIn('user_email', res.json['comment'])
        self.insert.execute.assert_called_once()
        self.notify.assert_called_once()

    def test_reply_validates_ancestry_and_notifies_immediate_parent_and_owner(self):
        validation = Mock()
        validation.execute.return_value = SimpleNamespace(data=[{'is_valid': True, 'root_id': PARENT, 'reply_to_name': 'Parent'}])
        self.comments.execute.return_value = SimpleNamespace(data=[{'id': PARENT, 'user_id': CAT}])
        self.db.rpc.side_effect = lambda name, args: validation if name == 'validate_comment_reply' else self.insert
        res = self.post(parent_id=PARENT)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json['comment']['parent_id'], PARENT)
        self.assertEqual(res.json['comment']['reply_to_id'], PARENT)
        self.assertEqual(self.notify.call_count, 2)

    def test_missing_rpc_is_safe_503_with_correlated_diagnostics(self):
        self.insert.execute.side_effect = APIError({'code': 'PGRST202', 'message': 'secret-token SQL payload', 'details': '', 'hint': ''})
        with self.assertLogs(module.app.logger, level='WARNING') as logs:
            res = self.post()
        text = '\n'.join(logs.output)
        self.assertEqual(res.status_code, 503)
        for expected in ('comment-test-123', '/api/cats/<cat_id>/comments', 'APIError', 'PGRST202', 'status=503'):
            self.assertIn(expected, text)
        for private in ('secret-token', 'private-test-token', 'SQL payload', 'Traceback'):
            self.assertNotIn(private, text + res.get_data(as_text=True))
        self.insert.execute.assert_called_once()
        self.comments.execute.assert_not_called()

    def test_transport_error_after_commit_reconciles_uuid_without_second_write(self):
        def dropped():
            payload = self.db.rpc.call_args.args[1]['p_comment']
            self.comments.execute.return_value = SimpleNamespace(data=[dict(payload, created_at=STAMP)])
            raise httpx.RemoteProtocolError('Server disconnected')
        self.insert.execute.side_effect = dropped
        res = self.post()
        self.assertEqual(res.status_code, 201)
        self.comments.eq.assert_any_call('id', res.json['comment']['id'])
        self.comments.eq.assert_any_call('user_id', USER)
        self.insert.execute.assert_called_once()
        self.notify.assert_called_once()

    def test_transport_error_before_commit_is_503_and_never_retried(self):
        self.insert.execute.side_effect = httpx.RemoteProtocolError('Server disconnected')
        self.assertEqual(self.post().status_code, 503)
        self.insert.execute.assert_called_once()
        self.notify.assert_not_called()

    def test_failed_reconciliation_has_only_one_read_retry(self):
        self.insert.execute.side_effect = httpx.ReadTimeout('uncertain')
        self.comments.execute.side_effect = httpx.ConnectError('offline')
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.comments.execute.call_count, 2)
        self.insert.execute.assert_called_once()

    def test_read_drop_before_insert_retries_only_read(self):
        good = self.cat.execute.return_value
        self.cat.execute.side_effect = [httpx.RemoteProtocolError('offline'), good]
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.cat.execute.call_count, 2)
        self.insert.execute.assert_called_once()

    def test_database_unavailable_never_attempts_write(self):
        self.cat.execute.side_effect = httpx.ConnectError('offline')
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.cat.execute.call_count, 2)
        self.insert.execute.assert_not_called()

    def test_existing_submission_returns_success_without_new_notification(self):
        self.insert.execute.return_value = SimpleNamespace(data=[{'status': 'existing', 'created_at': STAMP}])
        self.assertEqual(self.post().status_code, 201)
        self.notify.assert_not_called()

    def test_submission_id_is_stable_and_scoped_to_content(self):
        token = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
        first = self.post(submission_id=token).json['comment']['id']
        self.assertEqual(first, self.post(submission_id=token).json['comment']['id'])
        self.assertNotEqual(first, self.post(submission_id=token, comment='Changed').json['comment']['id'])
        self.assertNotEqual(first, token)

    def test_invalid_submission_id_is_rejected_without_write(self):
        self.assertEqual(self.post(submission_id='invalid').status_code, 400)
        self.insert.execute.assert_not_called()

    def test_content_cooldown_remains_429(self):
        self.insert.execute.return_value = SimpleNamespace(data=[{'status': 'duplicate'}])
        self.assertEqual(self.post().status_code, 429)
        self.notify.assert_not_called()

    def test_missing_auth_is_401(self):
        self.headers = {}
        self.assertEqual(self.post().status_code, 401)
        self.insert.execute.assert_not_called()

    def test_auth_permission_failure_is_403(self):
        with patch.object(module, 'google_oauth_matches_current_email', return_value=False):
            self.assertEqual(self.post().status_code, 403)
        self.insert.execute.assert_not_called()

    def test_notification_failure_does_not_report_comment_failure(self):
        self.notify.side_effect = httpx.RemoteProtocolError('private notification body')
        with self.assertLogs(module.app.logger, level='WARNING') as logs:
            self.assertEqual(self.post().status_code, 201)
        self.assertIn('comment_notification_insert', '\n'.join(logs.output))
        self.assertNotIn('private notification body', '\n'.join(logs.output))
        self.notify.assert_called_once()

    def test_supported_read_errors_retry_once(self):
        for cls in module.TRANSIENT_READ_ERRORS:
            with self.subTest(error=cls.__name__):
                read = Mock(side_effect=[cls('offline'), 'ok'])
                self.assertEqual(module.read_once_with_retry(read), 'ok')
                self.assertEqual(read.call_count, 2)

    def test_nontransient_read_error_is_not_retried(self):
        read = Mock(side_effect=ValueError('invalid'))
        with self.assertRaises(ValueError): module.read_once_with_retry(read)
        read.assert_called_once()

    def test_notification_insert_is_not_retried(self):
        with module.app.test_request_context('/api/cats/test/comments', method='POST'):
            self.comments.execute.side_effect = httpx.RemoteProtocolError('offline')
            self.assertIsNone(module.safe_db_insert('notifications', {'id': 'test'}))
        self.comments.execute.assert_called_once()

    def test_comment_notification_ids_are_stable_per_recipient_and_event(self):
        with patch.object(module, 'safe_db_insert') as insert, patch.object(module, 'resolve_user_avatar', return_value=''):
            for _ in range(2):
                REAL_NOTIFY(PARENT, USER, 'Tester', '', 'comment', CAT, 'Hello', comment_id=CAT)
            first, second = [call.args[1]['id'] for call in insert.call_args_list]
            self.assertEqual(first, second)
            REAL_NOTIFY(PARENT, USER, 'Tester', '', 'reply', CAT, 'Hello', comment_id=CAT)
            self.assertNotEqual(first, insert.call_args.args[1]['id'])

    def test_write_error_reconciles_without_retry(self):
        self.insert.execute.side_effect = httpx.WriteError('uncertain write')
        self.assertEqual(self.post().status_code, 503)
        self.insert.execute.assert_called_once()
        self.comments.execute.assert_called_once()

    def test_favorite_and_like_reads_retry_once_and_keep_503_on_exhaustion(self):
        for endpoint in ('favorite-ids', 'liked-cats'):
            for recover in (True, False):
                with self.subTest(endpoint=endpoint, recover=recover):
                    self.comments.execute.reset_mock()
                    self.comments.execute.side_effect = [httpx.RemoteProtocolError('simulated'),
                        SimpleNamespace(data=[]) if recover else httpx.RemoteProtocolError('simulated')]
                    res = self.client.get('/api/user/' + endpoint, headers=self.headers)
                    self.assertEqual(res.status_code, 200 if recover else 503)
                    self.assertEqual(self.comments.execute.call_count, 2)
                    self.comments.insert.assert_not_called()

    def test_profile_read_recovers_from_one_remote_disconnect(self):
        profile = query([])
        profile.execute.side_effect = [httpx.RemoteProtocolError('simulated'), SimpleNamespace(data=[{
            'id': USER, 'display_name': 'Tester', 'avatar_url': '', 'bio': ''}])]
        self.cat.execute.return_value = SimpleNamespace(data=[])
        self.db.table.side_effect = lambda name: profile if name == 'profiles' else self.cat
        res = self.client.get(f'/api/user/{USER}/profile')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(profile.execute.call_count, 2)
