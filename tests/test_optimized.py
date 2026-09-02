import hashlib
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app as mod
from build_vercel import build_static
from test_flows import client, Query, UID, CID, HEADERS

COMMENT = '44444444-4444-4444-8444-444444444444'


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('path', ['/login', '/register'])
def test_phone_ui_and_script_follow_flag(client, monkeypatch, enabled, path):
    monkeypatch.setattr(mod, 'PHONE_AUTH_ENABLED', enabled)
    html = client.get(path).get_data(as_text=True)
    assert ('data-auth-phone-panel=' in html) is enabled
    assert ('/static/js/phone-auth.js?' in html) is enabled
    assert 'data-auth-email-panel=' in html
    assert 'id="reg-bio"' not in html


def test_phone_script_not_loaded_by_unrelated_pages(client, monkeypatch):
    monkeypatch.setattr(mod, 'PHONE_AUTH_ENABLED', True)
    for path in ['/', '/profile', '/leaderboard', '/upload']:
        assert b'/static/js/phone-auth.js' not in client.get(path).data


@pytest.mark.parametrize('path', ['/api/auth/phone/send', '/api/auth/phone/verify'])
def test_disabled_sms_never_calls_provider(client, monkeypatch, path):
    factory = Mock()
    monkeypatch.setattr(mod, 'new_auth_client', factory)
    assert client.post(path, json={'phone': '+998901234567', 'mode': 'login', 'token': '123456'}).status_code == 503
    factory.assert_not_called()


@pytest.mark.parametrize('mode,creates', [('login', False), ('register', True)])
def test_phone_login_never_silently_registers(client, monkeypatch, mode, creates):
    auth = SimpleNamespace(sign_in_with_otp=Mock())
    monkeypatch.setattr(mod, 'PHONE_AUTH_ENABLED', True)
    monkeypatch.setattr(mod, 'new_auth_client', lambda: SimpleNamespace(auth=auth))
    result = client.post('/api/auth/phone/send', json={'phone': '+998 (90) 123-45-67', 'mode': mode, 'display_name': 'Cat Friend'})
    assert result.status_code == 200
    args = auth.sign_in_with_otp.call_args.args[0]
    assert args['phone'] == '+998901234567'
    assert args['options']['should_create_user'] is creates
    assert args['options']['channel'] == 'sms'


@pytest.mark.parametrize('verified_phone,confirmed,expected', [('998901234567', True, 200), ('998901234568', True, 401), ('998901234567', False, 401)])
def test_sms_session_requires_verified_matching_number(client, monkeypatch, verified_phone, confirmed, expected):
    user = SimpleNamespace(id=UID, email=None, phone=verified_phone, phone_confirmed_at='2026-09-02' if confirmed else None, user_metadata={})
    auth = SimpleNamespace(verify_otp=Mock(return_value=SimpleNamespace(user=user, session=SimpleNamespace(access_token='test-access', refresh_token='test-refresh'))))
    query = Query()
    monkeypatch.setattr(mod, 'PHONE_AUTH_ENABLED', True)
    monkeypatch.setattr(mod, 'new_auth_client', lambda: SimpleNamespace(auth=auth))
    monkeypatch.setattr(mod, 'supabase_admin', SimpleNamespace(table=lambda _: query))
    result = client.post('/api/auth/phone/verify', json={'phone': '+998901234567', 'token': '123456'})
    assert result.status_code == expected
    assert result.headers['Cache-Control'] == 'no-store'
    if expected == 200:
        assert set(result.json) == {'access_token', 'refresh_token'}
        profile = next(call for call in query.calls if call[0] == 'upsert')[1][0]
        assert profile['id'] == UID and profile['email'] is None
        assert verified_phone not in str(profile)


@pytest.mark.parametrize('status,expected', [('updated', 200), ('expired', 409), ('forbidden', 403)])
def test_comment_edit_uses_database_window(client, monkeypatch, status, expected):
    query = Query([{'id': COMMENT, 'user_id': UID, 'cat_id': CID}])
    rpc = Mock(return_value=SimpleNamespace(execute=lambda: SimpleNamespace(data=[{'status': status, 'cat_id': CID, 'comment': 'Edited', 'updated_at': '2026-09-02T00:00:00Z'}])))
    monkeypatch.setattr(mod, 'supabase_admin', SimpleNamespace(table=lambda _: query, rpc=rpc))
    response = client.put(f'/api/comments/{COMMENT}', headers=HEADERS, json={'comment': 'Edited', 'p_admin': True, 'created_at': '2099-01-01'})
    assert response.status_code == expected
    assert rpc.call_args.args == ('edit_comment_with_window', {'p_comment_id': COMMENT, 'p_user_id': UID, 'p_comment': 'Edited', 'p_admin': False})
    assert not any(call[0] == 'update' for call in query.calls)


def test_comment_edit_fails_closed_without_window_rpc(client, monkeypatch):
    query = Query([{'id': COMMENT, 'user_id': UID, 'cat_id': CID}])
    monkeypatch.setattr(mod, 'supabase_admin', SimpleNamespace(table=lambda _: query))
    assert client.put(f'/api/comments/{COMMENT}', headers=HEADERS, json={'comment': 'Edited'}).status_code == 503
    assert not any(call[0] == 'update' for call in query.calls)


@pytest.mark.parametrize('method,liked', [('put', True), ('delete', False)])
def test_comment_like_uses_authenticated_identity(client, monkeypatch, method, liked):
    rpc = Mock(return_value=SimpleNamespace(execute=lambda: SimpleNamespace(data=[{'liked': liked, 'likes_count': 4, 'cat_id': CID}])))
    monkeypatch.setattr(mod, 'supabase_admin', SimpleNamespace(rpc=rpc))
    result = getattr(client, method)(f'/api/comments/{COMMENT}/like', headers=HEADERS, json={'user_id': CID})
    assert result.json == {'liked': liked, 'likes_count': 4}
    assert rpc.call_args.args[1] == {'p_comment_id': COMMENT, 'p_user_id': UID, 'p_liked': liked}


def test_comment_like_state_is_account_scoped(client, monkeypatch):
    query = Query([{'comment_id': COMMENT}])
    monkeypatch.setattr(mod, 'supabase_admin', SimpleNamespace(table=lambda _: query))
    result = client.get('/api/user/comment-likes', headers=HEADERS, query_string={'ids': COMMENT, 'user_id': CID})
    assert result.json == {'liked_comment_ids': [COMMENT]}
    assert ('eq', ('user_id', UID), {}) in query.calls
    assert client.get('/api/user/comment-likes', headers=HEADERS, query_string={'ids': ','.join([COMMENT] * 101)}).status_code == 400


def test_asset_hashes_are_cached_and_content_based(tmp_path, monkeypatch):
    (tmp_path / 'static').mkdir()
    asset = tmp_path / 'static/app.js'
    asset.write_text('one')
    monkeypatch.setattr(mod, 'BASE_DIR', tmp_path)
    mod.asset_fingerprint.cache_clear()
    try:
        first = mod.asset_fingerprint('app.js')
        assert first == hashlib.sha256(b'one').hexdigest()[:12]
        assert mod.asset_fingerprint('app.js') == first
        assert mod.asset_fingerprint.cache_info().hits == 1
        asset.write_text('two')
        mod.asset_fingerprint.cache_clear()
        assert mod.asset_fingerprint('app.js') != first
        with pytest.raises(ValueError):
            mod.asset_fingerprint('../requirements.txt')
    finally:
        mod.asset_fingerprint.cache_clear()


def test_storage_initialization_is_lazy_and_thread_safe(client, monkeypatch):
    storage = SimpleNamespace(put_object=Mock())
    factory = Mock(return_value=storage)
    imported = Mock(side_effect=lambda name: SimpleNamespace(client=factory) if name == 'boto3' else SimpleNamespace(Config=lambda **kwargs: kwargs))
    for name in ['R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY']:
        monkeypatch.setattr(mod, name, 'local-test-placeholder')
    monkeypatch.setattr(mod, 'r2_client', None)
    monkeypatch.setattr(mod.importlib, 'import_module', imported)
    client.get('/login')
    imported.assert_not_called()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(item is storage for item in pool.map(lambda _: mod.get_r2_client(), range(8)))
    assert imported.call_count == 2
    factory.assert_called_once()


def test_build_replaces_stale_assets_but_never_publishes_root(tmp_path):
    source = tmp_path / 'static'
    source.mkdir()
    (source / 'app.js').write_text('one')
    (tmp_path / 'app.py').write_text('private source')
    (tmp_path / '.env').write_text('private test config')
    build_static(tmp_path)
    (source / 'app.js').rename(source / 'new.js')
    build_static(tmp_path)
    assert sorted(p.relative_to(tmp_path / 'public').as_posix() for p in (tmp_path / 'public').rglob('*') if p.is_file()) == ['static/new.js']
    assert (tmp_path / '.env').read_text() == 'private test config'


@pytest.mark.parametrize('name', ['.env', 'app.py', 'source.zip'])
def test_build_rejects_nonpublic_files_before_changing_output(tmp_path, name):
    source = tmp_path / 'static'
    source.mkdir()
    (source / 'app.js').write_text('good')
    build_static(tmp_path)
    (source / name).write_text('must not be published')
    with pytest.raises(ValueError):
        build_static(tmp_path)
    assert (tmp_path / 'public/static/app.js').read_text() == 'good'


@pytest.mark.parametrize('target', ['source', 'output'])
def test_build_rejects_symlinks(tmp_path, target):
    (tmp_path / 'static').mkdir()
    (tmp_path / 'static/app.js').write_text('good')
    if target == 'source':
        (tmp_path / 'static/link.js').symlink_to(tmp_path / 'static/app.js')
    else:
        (tmp_path / 'public').symlink_to(tmp_path / 'static', target_is_directory=True)
    with pytest.raises(ValueError):
        build_static(tmp_path)


@pytest.mark.parametrize('path', ['/app.py', '/.env', '/.git/config', '/requirements.txt', '/migrations/20260902_phone_comments.sql', '/templates/base.html'])
def test_server_source_is_not_public(client, path):
    assert client.get(path).status_code == 404


def test_every_stylesheet_local_url_has_a_public_asset():
    root = Path(__file__).resolve().parents[1]
    static = root / 'static'
    for css in static.rglob('*.css'):
        for match in re.finditer(r'url\(\s*[\"\']?([^\)\"\']+)[\"\']?\s*\)', css.read_text()):
            url = match.group(1).strip()
            if url.startswith(('data:', 'http:', 'https:', '#')):
                continue
            clean = url.split('?')[0].split('#')[0]
            target = root / clean.lstrip('/') if clean.startswith('/') else css.parent / clean
            assert target.resolve().is_relative_to(static.resolve())
            assert target.is_file(), f'{css.relative_to(root)} references missing asset {url}'


def test_every_icon_class_has_a_bundled_definition():
    root = Path(__file__).resolve().parents[1]
    css = (root / 'static/vendor/fontawesome/css/all.min.css').read_text()
    sources = list((root / 'templates').glob('*.html')) + list((root / 'static/js').glob('*.js'))
    for source in sources:
        for name in set(re.findall(r'\bfa-[a-z0-9-]+', source.read_text())):
            assert re.search(r'\.' + re.escape(name) + r'[:{,\s]', css), f'Missing icon definition: {name}'
