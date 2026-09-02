from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from itsdangerous import URLSafeTimedSerializer
import pytest
import app as mod
from test_flows import client, Query, UID, CID, HEADERS
from test_cache import FakeRedis

COMMENT = '44444444-4444-4444-8444-444444444444'
OTHER = '22222222-2222-4222-8222-222222222222'


def fake_auth(monkeypatch, *, uid=UID, providers=('email', 'google')):
    user = SimpleNamespace(id=uid, email='cat@example.com')
    auth = SimpleNamespace(
        sign_in_with_password=Mock(return_value=SimpleNamespace(user=user, session=SimpleNamespace(access_token='access', refresh_token='refresh'))),
        update_user=Mock(return_value=SimpleNamespace(user=user)),
        sign_out=Mock(), reset_password_email=Mock(),
        get_user_identities=Mock(return_value=SimpleNamespace(identities=[SimpleNamespace(provider=p, identity_id=p) for p in providers])),
        unlink_identity=Mock(),
    )
    monkeypatch.setattr(mod, 'SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setattr(mod, 'SUPABASE_ANON_KEY', 'public-test-placeholder')
    monkeypatch.setattr(mod, 'new_auth_client', lambda: SimpleNamespace(auth=auth))
    return auth


def test_google_hidden_until_provider_enabled(client, monkeypatch):
    assert b'Continue with Google' not in client.get('/login').data
    monkeypatch.setattr(mod, 'GOOGLE_AUTH_ENABLED', True)
    assert b'Continue with Google' in client.get('/login').data
    assert client.get('/api/auth/options').json == {'google_enabled': True}
    assert client.get('/auth/callback').status_code == 200


def test_password_login_returns_only_session_tokens_and_no_store(client, monkeypatch):
    auth = fake_auth(monkeypatch)
    response = client.post('/api/auth/login', json={'email': 'CAT@example.com', 'password': 'password'})
    assert response.json == {'access_token': 'access', 'refresh_token': 'refresh'}
    assert response.headers['Cache-Control'] == 'no-store'
    auth.sign_in_with_password.assert_called_once_with({'email': 'cat@example.com', 'password': 'password'})


def test_login_is_rate_limited_even_when_password_fails(client, monkeypatch):
    auth = fake_auth(monkeypatch)
    auth.sign_in_with_password.side_effect = ValueError('secret provider diagnostic')
    for _ in range(10):
        response = client.post('/api/auth/login', json={'email': 'cat@example.com', 'password': 'wrong'})
        assert response.status_code == 401 and b'secret provider' not in response.data
    assert client.post('/api/auth/login', json={'email': 'cat@example.com', 'password': 'wrong'}).status_code == 429


def test_reset_has_generic_response_and_fixed_redirect(client, monkeypatch):
    auth = fake_auth(monkeypatch)
    result = client.post('/api/auth/password-reset', json={'email': 'cat@example.com', 'redirect_to': 'https://evil.invalid'})
    assert result.status_code == 200 and 'If an account exists' in result.json['message']
    assert auth.reset_password_email.call_args.args[1]['redirect_to'] == 'http://localhost:5000/reset-password'


def test_google_bootstrap_uses_verified_id_and_never_overwrites_profile(client, monkeypatch):
    query = Query()
    monkeypatch.setattr(mod, 'supabase_admin', SimpleNamespace(table=lambda _: query))
    result = client.post('/api/auth/bootstrap', headers=HEADERS, json={'id':OTHER, 'role':'admin', 'display_name':'Spoof'})
    assert result.status_code == 200
    call = next(c for c in query.calls if c[0] == 'upsert')
    assert call[1][0]['id'] == UID and call[1][0]['role'] == 'user'
    assert call[2] == {'on_conflict':'id','ignore_duplicates': True}


@pytest.mark.parametrize('action', ['email', 'password', 'unlink_google'])
def test_security_changes_require_matching_reauthentication(client, monkeypatch, action):
    auth = fake_auth(monkeypatch, uid=OTHER)
    result = client.put('/api/user/security', headers=HEADERS, json={'action':action, 'value':'new@example.com' if action=='email' else 'new-password', 'current_password':'password'})
    assert result.status_code == 401
    auth.update_user.assert_not_called()
    auth.unlink_identity.assert_not_called()


def test_email_change_uses_user_confirmation_flow(client, monkeypatch):
    auth = fake_auth(monkeypatch)
    result = client.put('/api/user/security', headers=HEADERS, json={'action':'email','value':'new@example.com','current_password':'password'})
    assert result.json['requires_confirmation'] is True
    auth.update_user.assert_called_once_with({'email':'new@example.com'}, {'email_redirect_to':'http://localhost:5000/profile?email_confirmed=1'})
    auth.sign_out.assert_called_once_with({'scope':'local'})


@pytest.mark.parametrize('providers,expected', [(('google',),409), (('email','google'),200)])
def test_google_cannot_be_disconnected_without_password_identity(client, monkeypatch, providers, expected):
    auth = fake_auth(monkeypatch, providers=providers)
    result = client.put('/api/user/security', headers=HEADERS, json={'action':'unlink_google','current_password':'password'})
    assert result.status_code == expected
    assert auth.unlink_identity.call_count == (1 if expected == 200 else 0)


@pytest.mark.parametrize('method,owner,admin,expected', [('put',UID,False,200), ('put',OTHER,False,403), ('delete',OTHER,False,403), ('delete',OTHER,True,200)])
def test_comment_mutations_enforce_ownership(client, monkeypatch, method, owner, admin, expected):
    query=Query([{'id':COMMENT,'user_id':owner,'cat_id':CID}])
    rpc = Mock(return_value=SimpleNamespace(execute=lambda: SimpleNamespace(data=[{'status':'updated','cat_id':CID,'comment':'Edited','updated_at':'2026-09-02T10:00:00Z'}])))
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:query, rpc=rpc))
    monkeypatch.setattr(mod,'is_admin_user',lambda _:admin)
    cache=FakeRedis();monkeypatch.setattr(mod,'redis_cache',cache)
    result=getattr(client,method)(f'/api/comments/{COMMENT}',headers=HEADERS,json={'comment':'Edited'})
    assert result.status_code==expected
    writes=[c for c in query.calls if c[0] in {'update','delete'}]
    assert len(writes)==(1 if expected==200 and method=='delete' else 0)
    assert rpc.call_count==(1 if expected==200 and method=='put' else 0)
    if expected==200: assert mod.cache_counter_value(f'comments:{CID}')==1


def test_comments_page_uses_cursor_and_does_not_expose_email(client, monkeypatch):
    stamp=datetime(2026,9,1,tzinfo=timezone.utc)
    rows=[{'id':f'00000000-0000-4000-8000-{i:012d}','cat_id':CID,'created_at':(stamp+timedelta(seconds=i)).isoformat(),'comment':str(i),'user_email':'private@example.com'} for i in range(240)]
    monkeypatch.setattr(mod,'ENABLE_DEMO_DATA',True)
    monkeypatch.setattr(mod,'MOCK_COMMENTS',rows)
    seen=[];cursor=''
    while True:
        result=client.get(f'/api/cats/{CID}/comments',query_string={'cursor':cursor}).json
        assert all('user_email' not in c for c in result['comments'])
        assert len(result['comments']) <=30
        seen.extend(c['id'] for c in result['comments'])
        cursor=result['next_cursor']
        if not cursor:break
    assert len(set(seen))==len(seen)==240
    assert client.get(f'/api/cats/{CID}/comments?cursor=tampered').status_code==400


def test_cursor_is_bound_to_one_cat(client,monkeypatch):
    cursor=URLSafeTimedSerializer(mod.app.config['SECRET_KEY'],salt='comments-page').dumps({'cat':OTHER,'id':COMMENT,'created_at':'2026-09-01T00:00:00+00:00'})
    assert client.get(f'/api/cats/{CID}/comments',query_string={'cursor':cursor}).status_code==400


def test_comment_query_is_bounded_and_tie_broken(client,monkeypatch):
    query=Query([])
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:query))
    assert client.get(f'/api/cats/{CID}/comments').status_code==200
    assert ('limit',(31,),{}) in query.calls
    assert ('order',('id',),{}) in query.calls


def test_reply_notifies_actual_target_and_different_owner_once(client,monkeypatch):
    parent={'id':COMMENT,'cat_id':CID,'user_id':OTHER,'user_name':'Other','parent_id':None}
    queries={'cats':Query([{'id':CID,'user_id':'owner','name':'Cat'}]),'profiles':Query([])}
    def table(name):
        if name=='comments':
            q=Query([parent])
            def execute():
                return SimpleNamespace(data=[] if any(c[0]=='gte' for c in q.calls) else q.data)
            q.execute=execute
            return q
        return queries[name]
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=table))
    monkeypatch.setattr(mod,'safe_db_insert',Mock(return_value=True))
    notify=Mock();monkeypatch.setattr(mod,'push_notification',notify)
    result=client.post(f'/api/cats/{CID}/comments',headers=HEADERS,json={'comment':'Hello','parent_id':COMMENT,'reply_to_name':'Spoof'})
    assert result.status_code==201
    assert result.json['comment']['reply_to_name']=='Other'
    assert [c.kwargs['user_id'] for c in notify.call_args_list]==[OTHER,'owner']


@pytest.mark.parametrize('header,expected', [({},403), ({'X-Vercel-IP-Country':'US'},403), ({'X-Vercel-IP-Country':'UZ'},200), ({'Accept-Language':'uz'},403)])
def test_country_guard_uses_only_trusted_geo_input(client,monkeypatch,header,expected):
    monkeypatch.setattr(mod,'COUNTRY_ACCESS_ENABLED',True)
    monkeypatch.setattr(mod,'ALLOWED_COUNTRIES',frozenset({'UZ'}))
    result=client.get('/login',headers=header)
    assert result.status_code==expected
    assert client.get('/livez').status_code==200


@pytest.mark.parametrize('path', ['/app.py','/.env','/.git/config','/migrations/20260902_roadmap.sql','/emails/reset_password.html'])
def test_private_sources_are_not_served(client,path):
    assert client.get(path).status_code==404


def test_attribution_change_invalidates_comments_and_feeds(client,monkeypatch):
    cache=FakeRedis();monkeypatch.setattr(mod,'redis_cache',cache)
    mod.invalidate_attribution(UID)
    assert mod.cache_counter_value('attribution')==1
    assert mod.cache_counter_value('cats')==1
