import smtplib
import time
import unittest
from unittest.mock import Mock, patch

from itsdangerous import URLSafeTimedSerializer
from redis.exceptions import ConnectionError

import contact
from tests.support import isolated_app

application = isolated_app()


class ContactTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.store = Mock()
        self.store.set.return_value = True
        self.config = patch.dict(application.app.config, {
            'CONTACT_EMAIL_ENABLED': True, 'CONTACT_EMAIL': 'support@example.test',
            'CONTACT_SMTP_FROM': 'sender@example.test', 'CONTACT_SMTP_HOST': 'smtp.example.test',
            'CONTACT_SMTP_PORT': 587, 'CONTACT_SMTP_USERNAME': 'smtp-user',
            'CONTACT_SMTP_PASSWORD': 'smtp-secret-test', 'CONTACT_SMTP_USE_TLS': True,
            'CONTACT_SMTP_USE_SSL': False, 'TELEGRAM_URL': 'https://t.me/test_fixture',
            'DISCORD_URL': 'https://discord.gg/test_fixture',
        })
        self.config.start()
        self.addCleanup(self.config.stop)
        store_patch = patch.object(application, 'redis_cache', self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)
        self.smtp = patch('contact.smtplib.SMTP').start()
        self.addCleanup(patch.stopall)
        self.mail = self.smtp.return_value.__enter__.return_value

    def payload(self, client=None, age=3):
        client = client or self.client
        client.get('/contact')
        with client.session_transaction() as state:
            csrf = state['contact_csrf']
        serializer = URLSafeTimedSerializer(application.app.secret_key, salt='contact-form-v1')
        token = serializer.dumps({'csrf': csrf, 'nonce': 'nonce-' + str(time.time_ns()), 'issued': time.time() - age})
        return dict(name='Cat Person', email='person@example.test', subject='A question', message='Hello, CatRank!', contact_token=token)

    def test_disabled_form_and_empty_links_still_render(self):
        with patch.dict(application.app.config, CONTACT_EMAIL_ENABLED=False, TELEGRAM_URL='', DISCORD_URL='', CONTACT_EMAIL=''):
            response = self.client.get('/contact')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Email sending is temporarily unavailable', response.data)
            self.assertNotIn(b'id="contact-form"', response.data)
            self.assertNotIn(b'href="mailto:', response.data)
            self.assertNotIn('Set-Cookie', response.headers)
            self.assertEqual(self.client.post('/contact').status_code, 503)
        self.mail.send_message.assert_not_called()

    def test_links_are_safe_and_credentials_are_not_rendered(self):
        response = self.client.get('/contact')
        self.assertIn(b'rel="noopener noreferrer"', response.data)
        self.assertIn(b'mailto:support%40example.test', response.data)
        self.assertNotIn(b'smtp-secret-test', response.data)
        self.assertNotIn(b'smtp-user', response.data)
        for value in ('javascript:alert(1)', 'https://user:pass@example.test', 'https://example.test\n', '//example.test', 'https://x:99999'):
            self.assertEqual(contact.public_link(value), '')

    def test_sends_plain_text_with_fixed_headers_and_redirects(self):
        data = self.payload()
        data['message'] = '<script>alert(1)</script>\nA normal newline.'
        response = self.client.post('/contact', data=data)
        self.assertEqual(response.status_code, 303)
        self.mail.starttls.assert_called_once()
        self.mail.login.assert_called_once_with('smtp-user', 'smtp-secret-test')
        message = self.mail.send_message.call_args.args[0]
        self.assertEqual(message['To'], 'support@example.test')
        self.assertEqual(message['From'], 'sender@example.test')
        self.assertEqual(message['Reply-To'], data['email'])
        self.assertEqual(message.get_content_type(), 'text/plain')
        self.assertIn('<script>', message.get_content())
        self.assertIn(b'accepted by our email service', self.client.get('/contact').data)
        self.assertNotIn(b'accepted by our email service', self.client.get('/contact').data)

    def test_accepted_mail_is_not_reported_failed_when_smtp_quit_fails(self):
        self.smtp.return_value.__exit__.side_effect = smtplib.SMTPResponseException(421, b'Closing connection')
        response = self.client.post('/contact', data=self.payload())
        self.assertEqual(response.status_code, 303)
        self.mail.send_message.assert_called_once()
        self.assertIn(b'accepted by our email service', self.client.get('/contact').data)

    def test_duplicate_submission_does_not_send_twice(self):
        self.store.set.side_effect = [True, False]
        data = self.payload()
        self.assertEqual(self.client.post('/contact', data=data).status_code, 303)
        self.assertEqual(self.client.post('/contact', data=data).status_code, 409)
        self.mail.send_message.assert_called_once()
        self.assertEqual(self.store.set.call_args.kwargs, {'nx': True, 'ex': 3600})

    def test_csrf_cannot_be_reused_by_another_browser(self):
        data = self.payload()
        self.assertEqual(application.app.test_client().post('/contact', data=data).status_code, 400)
        data['contact_token'] += 'tampered'
        self.assertEqual(self.client.post('/contact', data=data).status_code, 400)
        self.mail.send_message.assert_not_called()

    def test_expired_token_is_rejected(self):
        with patch('itsdangerous.timed.time.time', return_value=time.time() - 4000):
            data = self.payload()
        self.assertEqual(self.client.post('/contact', data=data).status_code, 400)
        self.mail.send_message.assert_not_called()

    def test_honeypot_and_instant_submission_are_rejected(self):
        data = self.payload(age=0)
        self.assertEqual(self.client.post('/contact', data=data).status_code, 400)
        data = self.payload()
        data['website'] = 'spam'
        self.assertEqual(self.client.post('/contact', data=data).status_code, 400)
        self.mail.send_message.assert_not_called()

    def test_validation_rejects_lengths_controls_and_header_injection(self):
        for field, value in [('name', ''), ('name', 'x' * 81), ('subject', 'x' * 121), ('message', 'x' * 5001), ('message', '\x00'), ('email', 'x@y'), ('email', 'a@example.test,b@example.test'), ('email', 'a@example.test\r\nBcc:evil@example.test'), ('subject', 'hello\r\nBcc:evil@example.test'), ('name', 'Name\n')]:
            with self.subTest(field=field, value=value[:40]):
                data = self.payload()
                data[field] = value
                self.assertEqual(self.client.post('/contact', data=data).status_code, 400)
        self.mail.send_message.assert_not_called()

    def test_invalid_values_are_escaped_and_preserved(self):
        data = self.payload()
        data.update(name='\"><script>alert(1)</script>', email='invalid')
        result = self.client.post('/contact', data=data)
        self.assertIn(b'&lt;script&gt;', result.data)
        self.assertNotIn(b'<script>alert(1)</script>', result.data)
        self.assertIn(b'aria-invalid="true"', result.data)

    def test_storage_outage_prevents_mail(self):
        self.store.set.side_effect = ConnectionError('internal endpoint secret')
        response = self.client.post('/contact', data=self.payload())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'internal endpoint', response.data)
        self.mail.send_message.assert_not_called()

    def test_full_length_unicode_message_and_oversized_request(self):
        data = self.payload()
        data['message'] = '🐱' * 5000
        self.assertEqual(self.client.post('/contact', data=data).status_code, 303)
        data['message'] = 'x' * (65 * 1024)
        self.assertEqual(self.client.post('/contact', data=data).status_code, 413)
        self.mail.send_message.assert_called_once()

    def test_smtp_failure_never_reports_success(self):
        self.mail.send_message.side_effect = smtplib.SMTPException('secret provider response')
        response = self.client.post('/contact', data=self.payload())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'secret provider', response.data)
        self.assertIn(b'could not confirm delivery', response.data)
        self.assertNotIn(b'accepted by our email service', response.data)

    def test_missing_or_unsafe_smtp_configuration_disables_form(self):
        for cfg in ({'CONTACT_SMTP_HOST': ''}, {'CONTACT_SMTP_PORT': 0}, {'CONTACT_SMTP_USE_TLS': False}, {'CONTACT_SMTP_USE_SSL': True}, {'CONTACT_SMTP_FROM': 'bad'}, {'CONTACT_SMTP_PASSWORD': ''}):
            with self.subTest(cfg=cfg), patch.dict(application.app.config, cfg):
                self.assertNotIn(b'id="contact-form"', self.client.get('/contact').data)

    def test_implicit_tls_provider(self):
        with patch.dict(application.app.config, CONTACT_SMTP_USE_SSL=True, CONTACT_SMTP_USE_TLS=False, CONTACT_SMTP_PORT=465), patch('contact.smtplib.SMTP_SSL') as smtp_ssl:
            self.assertEqual(self.client.post('/contact', data=self.payload()).status_code, 303)
            self.assertEqual(smtp_ssl.call_args.kwargs['timeout'], 10)
            self.assertTrue(smtp_ssl.call_args.kwargs['context'].check_hostname)
            smtp_ssl.return_value.__enter__.return_value.starttls.assert_not_called()

    def test_rate_limit_and_spoofed_forwarding_headers(self):
        application.limiter.enabled = True
        application.limiter.reset()
        self.addCleanup(setattr, application.limiter, 'enabled', False)
        for number in range(3):
            response = self.client.post('/contact', headers={'X-Forwarded-For': f'192.0.2.{number}', 'CF-Connecting-IP': f'192.0.2.{number}'})
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response.headers)
        self.assertIn(b'CatRank', response.data)
        self.mail.send_message.assert_not_called()


class PublicPolishTests(unittest.TestCase):
    def test_metadata_uses_configured_origin_and_sitemap_is_public_only(self):
        with patch.object(application, 'PUBLIC_SITE_URL', 'https://catrank.example'), patch.object(application, 'ENABLE_DEMO_DATA', True):
            client = application.app.test_client()
            for path in ('/', '/leaderboard', '/contact'):
                response = client.get(path)
                self.assertIn(f'rel="canonical" href="https://catrank.example{path}"'.encode(), response.data)
                self.assertIn(b'property="og:title"', response.data)
            body = client.get('/sitemap.xml').get_data(as_text=True)
            self.assertEqual(body.count('<url>'), 3)
            self.assertNotIn('/profile', body)
            self.assertIn(b'Sitemap: https://catrank.example/sitemap.xml', client.get('/robots.txt').data)
            self.assertIn(b'noindex, nofollow', client.get('/profile').data)
            self.assertIn(b'noindex, nofollow', client.get('/missing').data)

    def test_pages_and_static_cache_headers(self):
        client = application.app.test_client()
        for path in ('/contact', '/login', '/register', '/forgot-password', '/set-password', '/reset-password', '/upload', '/profile', '/user/00000000-0000-4000-8000-000000000001', '/livez'):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(client.get('/missing').status_code, 404)
        with client.get('/static/js/main.js') as response:
            self.assertEqual(response.headers['Cache-Control'], 'public, max-age=86400')
        fingerprint = application.asset_fingerprint('js/main.js')
        self.assertIn(f'js/main.js?v={fingerprint}'.encode(), client.get('/contact').data)
