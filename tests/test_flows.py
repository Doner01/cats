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
