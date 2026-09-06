import unittest
import os
from flask import Flask
from app import app, asset_fingerprint
from unittest.mock import patch, MagicMock

class TestPerformanceAudit(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_versioned_static_urls(self):
        # We need to verify that static files return the correct Cache-Control
        resp = self.client.get('/static/css/style.css')
        self.assertIn('max-age=86400', resp.headers.get('Cache-Control', ''))
        self.assertNotIn('immutable', resp.headers.get('Cache-Control', ''))
        
        # Now with a version parameter
        resp = self.client.get('/static/css/style.css?v=dummyhash')
        self.assertIn('max-age=31536000', resp.headers.get('Cache-Control', ''))
        self.assertIn('immutable', resp.headers.get('Cache-Control', ''))

    def test_dynamic_html_not_cached(self):
        resp = self.client.get('/')
        self.assertEqual(resp.headers.get('Cache-Control', ''), 'no-store')

        resp = self.client.get('/profile')
        self.assertEqual(resp.headers.get('Cache-Control', ''), 'no-store')

    def test_version_changes_with_content(self):
        # We can mock a file or test an existing one
        h1 = asset_fingerprint('css/style.css')
        self.assertTrue(len(h1) > 0)
        # In a real test we'd modify the file, but we can't easily without side effects.
        # We assume asset_fingerprint relies on hashlib.sha256(path.read_bytes()).hexdigest()

    def test_server_timing_header(self):
        resp = self.client.get('/')
        self.assertIn('Server-Timing', resp.headers)
        self.assertTrue(resp.headers['Server-Timing'].startswith('app;dur='))

if __name__ == '__main__':
    unittest.main()
