import io
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from PIL import Image
import app as mod

UID = '11111111-1111-4111-8111-111111111111'
CID = '33333333-3333-4333-8333-333333333333'
HEADERS = {'Authorization': 'Bearer test-token'}

class Query:
    def __init__(self, rows=None, fail=False):
        self.data = rows or []
        self.fail = fail
        self.calls = []
    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return method
    def execute(self):
        if self.fail:
            raise RuntimeError('offline')
        return SimpleNamespace(data=self.data)

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(mod, 'redis_cache', None)
    monkeypatch.setattr(mod, 'cache_retry_after', 0.0)
    monkeypatch.setattr(mod, 'supabase_admin', None)
    monkeypatch.setattr(mod, 'ENABLE_DEMO_DATA', False)
    monkeypatch.setattr(mod, 'ADMIN_EMAIL_CONFIG', '')
    monkeypatch.setattr(mod, 'supabase_auth', SimpleNamespace(auth=SimpleNamespace(get_user=lambda token: SimpleNamespace(user=SimpleNamespace(id=UID,email='cat@example.com',app_metadata={},user_metadata={})))) )
    mod.app.config['TESTING'] = True
    mod.limiter.reset()
    return mod.app.test_client()

@pytest.mark.parametrize('path',['/login','/register','/forgot-password','/reset-password','/upload','/profile','/admin','/leaderboard'])
def test_page_templates_render(client,path):
    assert client.get(path).status_code in (200,503)

@pytest.mark.parametrize('path',['/api/cats/not-a-uuid','/api/unknown'])
def test_missing_api_routes_use_json(client,path):
    result=client.get(path)
    assert result.status_code==404
    assert result.is_json

def test_health_probe_checks_database(client,monkeypatch):
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _: Query(fail=True)))
    assert client.get('/healthz').status_code==503
    assert client.get('/livez').status_code==200

def test_unavailable_feed_does_not_pretend_to_be_empty(client):
    r=client.get('/')
    assert r.status_code==503
    assert b'The cats will be back soon' in r.data

def test_pagination_and_search_reach_old_cats(client,monkeypatch):
    monkeypatch.setattr(mod,'ENABLE_DEMO_DATA',True)
    cats=[dict(mod.MOCK_CATS[0],id=str(i),name=f'Cat {i}',created_at=f'2026-08-{i+1:02d}T00:00:00Z') for i in range(30)]
    monkeypatch.setattr(mod,'MOCK_CATS',cats)
    first=client.get('/').data.decode()
    second=client.get('/?page=2').data.decode()
    assert first.count('class="cat-card feed-card"')==24
    assert second.count('class="cat-card feed-card"')==6
    result=client.get('/?q=Cat+0').data.decode()
    assert result.count('class="cat-card feed-card"')==1
    assert 'data-cat-name="Cat 0"' in result

def test_leaderboard_is_limited_to_ten_cats(client,monkeypatch):
    monkeypatch.setattr(mod,'ENABLE_DEMO_DATA',True)
    cats=[dict(mod.MOCK_CATS[0],id=str(i),name=f'Leader {i}',likes_count=100-i) for i in range(12)]
    monkeypatch.setattr(mod,'MOCK_CATS',cats)
    result=client.get('/leaderboard').data.decode()
    assert result.count('data-cat-modal-id=')==10
    assert 'Leader 9' in result
    assert 'Leader 10' not in result

def test_stored_name_cannot_escape_event_handler(client,monkeypatch):
    monkeypatch.setattr(mod,'ENABLE_DEMO_DATA',True)
    monkeypatch.setattr(mod,'MOCK_CATS',[dict(mod.MOCK_CATS[0],user_name="O'Hara');alert(1);//")])
    result=client.get('/').data.decode()
    assert 'onerror="handleAvatarError(this, this.alt)"' in result
    assert "onerror=\"handleAvatarError(this, 'O" not in result

def test_signup_does_not_reuse_shared_auth_session(client,monkeypatch):
    shared=mod.supabase_auth
    signup=Mock(return_value=SimpleNamespace(user=SimpleNamespace(id=UID,identities=[{}]),session=None))
    factory=Mock(return_value=SimpleNamespace(auth=SimpleNamespace(sign_up=signup)))
    monkeypatch.setattr(mod,'create_client',factory)
    r=client.post('/api/auth/register',json={'email':'cat@example.com','password':'valid-password'})
    assert r.status_code==201
    assert r.json['requires_email_confirmation']
    assert mod.supabase_auth is shared
    assert factory.call_args.kwargs['options'].persist_session is False

def test_duplicate_signup_identity_is_not_false_success(client,monkeypatch):
    monkeypatch.setattr(mod,'create_client',lambda *a,**k: SimpleNamespace(auth=SimpleNamespace(sign_up=lambda _:SimpleNamespace(user=SimpleNamespace(identities=[]),session=None))))
    assert client.post('/api/auth/register',json={'email':'cat@example.com','password':'valid-password'}).status_code==409

def test_email_search_escapes_wildcards(client,monkeypatch):
    query=Query()
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:query))
    monkeypatch.setattr(mod,'create_client',lambda *a,**k: SimpleNamespace(auth=SimpleNamespace(sign_up=lambda _:SimpleNamespace(user=SimpleNamespace(identities=[{}]),session=None))))
    r=client.post('/api/auth/register',json={'email':'a_b%tag@example.com','password':'valid-password'})
    assert r.status_code==201
    assert ('ilike',('email',r'a\_b\%tag@example.com'),{}) in query.calls

def test_missing_cat_is_404(client,monkeypatch):
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:Query()))
    assert client.get(f'/api/cats/{CID}').status_code==404

@pytest.mark.parametrize('method,path', [('get','/api/user/favorites'), ('get','/api/user/favorite-ids'), ('put',f'/api/cats/{CID}/favorite'), ('delete',f'/api/cats/{CID}/favorite')])
def test_favorites_require_auth(client, method, path):
    assert getattr(client,method)(path).status_code == 401

def test_save_uses_authenticated_owner_and_upserts_once(client,monkeypatch):
    cat_query = Query([{'id':CID}])
    favorite_query = Query()
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda table: cat_query if table=='cats' else favorite_query))
    response = client.put(f'/api/cats/{CID}/favorite',json={'user_id':'attacker-supplied'},headers=HEADERS)
    assert response.status_code == 200 and response.json['saved'] is True
    upsert = next(call for call in favorite_query.calls if call[0]=='upsert')
    assert upsert[1] == ({'user_id':UID,'cat_id':CID},)
    assert upsert[2] == {'on_conflict':'user_id,cat_id','ignore_duplicates':True}
    assert response.headers['Cache-Control']=='no-store'

def test_unsave_is_private_and_idempotent(client,monkeypatch):
    query = Query()
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:query))
    for _ in range(2):
        result=client.delete(f'/api/cats/{CID}/favorite',headers=HEADERS)
        assert result.status_code==200 and result.json['saved'] is False
    assert ('eq',('user_id',UID),{}) in query.calls
    assert ('eq',('cat_id',CID),{}) in query.calls

def test_missing_cat_cannot_be_saved(client,monkeypatch):
    query=Query()
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:query))
    assert client.put(f'/api/cats/{CID}/favorite',headers=HEADERS).status_code==404
    assert not any(call[0]=='upsert' for call in query.calls)

def test_favorites_failure_is_not_an_empty_success(client,monkeypatch):
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:Query(fail=True)))
    for url in ('/api/user/favorites','/api/user/favorite-ids'):
        assert client.get(url,headers=HEADERS).status_code==503

def test_favorites_paginate_and_ignore_requested_other_user(client,monkeypatch):
    rows=[{'cat_id':str(i),'cats':dict(mod.MOCK_CATS[0],id=str(i))} for i in range(25)]
    query=Query(rows)
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:query))
    result=client.get('/api/user/favorites?page=2&user_id=someone-else',headers=HEADERS)
    assert result.status_code==200
    assert len(result.json['cats'])==24 and result.json['has_next']
    assert ('range',(24,48),{}) in query.calls
    assert ('eq',('user_id',UID),{}) in query.calls
    assert 'email' not in result.json

def test_public_profile_never_includes_favorites(client,monkeypatch):
    tables=[]
    def table(name):
        tables.append(name)
        return Query([{'id':UID,'display_name':'Cat Lover'}] if name=='profiles' else [])
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=table))
    result=client.get(f'/api/user/{UID}/profile')
    assert result.status_code==200 and 'favorites' not in result.json
    assert 'favorites' not in tables

def test_edit_other_users_cat_is_forbidden(client,monkeypatch):
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:Query([{'id':CID,'user_id':'someone-else'}])))
    assert client.put(f'/api/cats/{CID}',json={'name':'stolen'},headers=HEADERS).status_code==403

def test_upload_rolls_back_storage_after_database_failure(client,monkeypatch):
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:Query()))
    monkeypatch.setattr(mod,'safe_db_insert',lambda *a:None)
    monkeypatch.setattr(mod,'upload_file_to_storage',lambda *a:'https://example.com/cat.webp')
    cleanup=Mock();monkeypatch.setattr(mod,'delete_file_from_storage',cleanup)
    output=io.BytesIO();Image.new('RGB',(40,40)).save(output,format='PNG');output.seek(0)
    r=client.post('/api/cats/upload',headers=HEADERS,data={'name':'Cat','file':(output,'cat.png')})
    assert r.status_code==503
    cleanup.assert_called_once()
    assert cleanup.call_args.kwargs['allowed_prefix']==f'{UID}/'

def test_empty_profile_update_result_is_failure(client,monkeypatch):
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=lambda _:Query()))
    assert client.put('/api/user/profile',headers=HEADERS,json={'display_name':'New name'}).status_code==503

def test_truncated_image_is_rejected():
    output=io.BytesIO();Image.new('RGB',(400,400)).save(output,format='JPEG')
    valid,_=mod.validate_image_file(output.getvalue()[:-100],'cat.jpg')
    assert not valid

def test_huge_image_is_rejected_without_crashing():
    with patch.object(mod.Image,'open',side_effect=Image.DecompressionBombError('too large')):
        valid,_=mod.validate_image_file(b'0'*20,'cat.png')
    assert not valid

def test_avatar_animation_is_normalized():
    output=io.BytesIO();a=Image.new('RGB',(40,40),'red');b=Image.new('RGB',(40,40),'blue')
    a.save(output,format='GIF',save_all=True,append_images=[b])
    _,extension,mime=mod.optimize_image_file(output.getvalue(),avatar=True)
    assert (extension,mime)==('webp','image/webp')

def test_backend_email_update_cannot_skip_confirmation(client):
    assert client.put('/api/user/email',headers=HEADERS,json={'email':'new@example.com'}).status_code==409
