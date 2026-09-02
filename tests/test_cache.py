import json
from types import SimpleNamespace
from pathlib import Path

import app as mod
from test_flows import Query, client, UID, CID, HEADERS


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}
        self.calls = 0
    def get(self, key):
        self.calls += 1
        return self.data.get(key)
    def setex(self, key, ttl, value):
        self.data[key] = value
        self.ttls[key] = ttl
    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
    def incr(self, key):
        self.data[key] = str(int(self.data.get(key, 0)) + 1)


def test_redis_roundtrip_ttl_and_typed_objects(client,monkeypatch):
    cache=FakeRedis()
    monkeypatch.setattr(mod,'redis_cache',cache)
    mod.cache_set('object',{'name':'Cat'},45)
    assert mod.cache_get_dict('object')=={'name':'Cat'}
    assert cache.ttls['object']==45
    mod.cache_set('array',[1,2],15)
    assert mod.cache_get_dict('array') is None


def test_cache_failure_skips_repeated_requests(client,monkeypatch):
    class BrokenRedis:
        calls=0
        def get(self,_):
            self.calls+=1
            raise ConnectionError('offline')
    cache=BrokenRedis()
    monkeypatch.setattr(mod,'redis_cache',cache)
    assert mod.cache_get('a') is None
    assert mod.cache_get('b') is None
    assert cache.calls==1


def test_repeated_cat_read_avoids_second_database_query(client,monkeypatch):
    cache=FakeRedis()
    query=Query([dict(mod.MOCK_CATS[0],id=CID)])
    calls=[]
    def table(name):
        calls.append(name)
        return query
    monkeypatch.setattr(mod,'redis_cache',cache)
    monkeypatch.setattr(mod,'supabase_admin',SimpleNamespace(table=table))
    assert client.get(f'/api/cats/{CID}').status_code==200
    assert client.get(f'/api/cats/{CID}').status_code==200
    assert calls==['cats']


def test_content_invalidation_removes_cache_and_changes_feed_generation(client,monkeypatch):
    cache=FakeRedis()
    monkeypatch.setattr(mod,'redis_cache',cache)
    for kind,identity in [('cat',CID),('profile',UID),('identity',UID)]:
        mod.cache_set(mod.make_cache_key(kind,identity),{'stale':True},45)
    old=mod.cache_counter_value('cats')
    mod.invalidate_cat_content(cat_id=CID,user_id=UID)
    assert mod.cache_counter_value('cats')==old+1
    for kind,identity in [('cat',CID),('profile',UID),('identity',UID)]:
        assert mod.cache_get(mod.make_cache_key(kind,identity)) is None


def test_favorites_migration_is_private_and_cascades():
    sql=(Path(__file__).resolve().parents[1]/'migrations/20260902_favorites.sql').read_text()
    assert 'PRIMARY KEY (user_id, cat_id)' in sql
    assert sql.count('ON DELETE CASCADE')==2
    assert 'ENABLE ROW LEVEL SECURITY' in sql
    assert 'FROM PUBLIC, anon, authenticated' in sql
    assert 'TO service_role' in sql
