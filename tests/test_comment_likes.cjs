const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const response = (data, ok = true) => ({ok, json: async () => data});
const deferred = () => {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return {promise, resolve};
};
const flush = () => new Promise(setImmediate);
const session = id => ({user: {id}, access_token: id + '-token'});

function fixture(ids = ['one']) {
    const listeners = new Map();
    const events = [];
    const calls = [];
    const toasts = [];
    const buttons = ids.map(id => {
        const count = {textContent: '4'};
        const icon = {textContent: '♡'};
        const attrs = {'aria-pressed': 'false'};
        return {
            dataset: {commentLikeId: id, commentLikeCount: '4'}, attrs, count, icon,
            disabled: false, classList: {toggle() {}},
            setAttribute: (key, value) => { attrs[key] = value; },
            querySelector: selector => selector.includes('count') ? count : icon,
        };
    });
    const f = {buttons, calls, toasts, events, handler: async url => response(url.startsWith('/api/user/') ? {liked_comment_ids: []} : {liked: true, likes_count: 5})};
    const context = vm.createContext({
        console, URL, Map, Set, Array, Promise, Error,
        currentSession: session('alice'),
        supabaseClient: {auth: {getSession: async () => ({data: {session: context.currentSession}})}},
        activeModalCatId: 'cat-one', modalRequestVersion: 1, loadedComments: [],
        CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options?.detail; } },
        document: {querySelectorAll: () => buttons},
        showToast: message => toasts.push(message),
        getCatLoginUrl: () => '/login?next=cat-one',
        fetch: async (url, options) => { calls.push({url, options}); return f.handler(url, options); },
        window: {
            location: {href: '/'},
            addEventListener(type, fn) { listeners.set(type, [...(listeners.get(type) || []), fn]); },
            dispatchEvent(event) { events.push(event); (listeners.get(event.type) || []).forEach(fn => fn(event)); },
        },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/comment-likes.js'), 'utf8'), context);
    Object.assign(f, {
        context,
        sync: ids => context.window.syncCommentLikes(ids || buttons.map(b => b.dataset.commentLikeId)),
        toggle: id => context.window.toggleCommentLike(id || 'one'),
        fire: async type => Promise.all((listeners.get(type) || []).map(fn => fn({type}))),
    });
    return f;
}

test('comment likes update only their own counts and use the server result', async () => {
    const f = fixture();
    f.context.loadedComments = [{id: 'one', likes_count: 4}];
    await f.sync();
    await f.toggle();
    assert.equal(f.buttons[0].attrs['aria-pressed'], 'true');
    assert.equal(f.buttons[0].count.textContent, '5');
    assert.equal(f.context.loadedComments[0].likes_count, 5);
    assert.equal(f.calls[1].options.method, 'PUT');
    assert.equal(f.calls[1].options.headers.Authorization, 'Bearer alice-token');
    assert.equal(f.buttons[0].disabled, false);
});

test('duplicate clicks are blocked before the session promise resolves', async () => {
    const f = fixture();
    const first = f.toggle();
    const second = f.toggle();
    await Promise.all([first, second]);
    assert.equal(f.calls.filter(call => call.options.method === 'PUT').length, 1);
    assert.equal(f.buttons[0].count.textContent, '5');
});

test('guests are sent to login without attempting a comment mutation', async () => {
    const f = fixture();
    f.context.currentSession = null;
    await f.fire('catrank_auth_changed');
    await f.toggle();
    assert.equal(f.calls.length, 0);
    assert.equal(f.context.window.location.href, '/login?next=cat-one');
    assert.equal(f.buttons[0].disabled, false);
});

test('all loaded comment IDs are fetched in batches of at most 100', async () => {
    const f = fixture(Array.from({length: 251}, (_, index) => String(index)));
    f.handler = async url => response({liked_comment_ids: new URL(url, 'https://cats.example').searchParams.get('ids').split(',')});
    await f.sync();
    assert.equal(f.calls.length, 3);
    assert.ok(f.calls.every(call => new URL(call.url, 'https://cats.example').searchParams.get('ids').split(',').length <= 100));
    assert.ok(f.buttons.every(button => button.attrs['aria-pressed'] === 'true'));
});

test('late personal-state responses cannot transfer likes to another account', async () => {
    const f = fixture();
    const old = deferred();
    f.handler = async (_url, options) => options.headers.Authorization === 'Bearer alice-token' ? old.promise : response({liked_comment_ids: []});
    const first = f.sync();
    await flush();
    f.context.currentSession = session('bob');
    await f.fire('catrank_auth_changed');
    await f.sync();
    old.resolve(response({liked_comment_ids: ['one']}));
    await first;
    assert.equal(f.buttons[0].attrs['aria-pressed'], 'false');
});

test('switching cats during JSON parsing discards the previous viewer response', async () => {
    const f = fixture();
    const body = deferred();
    f.handler = async () => ({ok: true, json: () => body.promise});
    const first = f.sync();
    await flush();
    f.context.activeModalCatId = 'cat-two';
    f.context.modalRequestVersion++;
    body.resolve({liked_comment_ids: ['one']});
    await first;
    assert.equal(f.buttons[0].attrs['aria-pressed'], 'false');
});

test('late old-account writes cannot paint or unlock a new-account write', async () => {
    const f = fixture();
    const old = deferred();
    const newer = deferred();
    await f.sync();
    f.handler = async (_url, options) => !options.method ? response({liked_comment_ids: []}) : options.headers.Authorization === 'Bearer alice-token' ? old.promise : newer.promise;
    const first = f.toggle();
    await flush();
    f.context.currentSession = session('bob');
    await f.fire('catrank_auth_changed');
    await f.sync();
    const second = f.toggle();
    await flush();
    old.resolve(response({liked: true, likes_count: 99}));
    await first;
    assert.equal(f.buttons[0].disabled, true);
    assert.equal(f.buttons[0].count.textContent, '5');
    newer.resolve(response({liked: true, likes_count: 6}));
    await second;
    assert.equal(f.buttons[0].count.textContent, '6');
    assert.equal(f.buttons[0].disabled, false);
    assert.equal(f.events.filter(event => event.type === 'catrank_comment_like_changed').length, 1);
});

test('a stale refresh cannot undo a completed optimistic mutation', async () => {
    const f = fixture();
    await f.sync();
    const old = deferred();
    f.handler = async (_url, options) => options.method ? response({liked: true, likes_count: 5}) : old.promise;
    const first = f.sync();
    await flush();
    await f.toggle();
    old.resolve(response({liked_comment_ids: []}));
    await first;
    assert.equal(f.buttons[0].attrs['aria-pressed'], 'true');
});

test('failed mutations roll back counts and allow a retry', async () => {
    const f = fixture();
    await f.sync();
    f.handler = async () => response({error: 'Please retry'}, false);
    await f.toggle();
    assert.equal(f.buttons[0].count.textContent, '4');
    assert.equal(f.buttons[0].attrs['aria-pressed'], 'false');
    assert.equal(f.buttons[0].disabled, false);
    assert.deepEqual(f.toasts, ['Please retry']);
});

test('an unknown previous like is read before choosing PUT or DELETE', async () => {
    const f = fixture();
    f.handler = async (_url, options) => response(options.method ? {liked: false, likes_count: 3} : {liked_comment_ids: ['one']});
    await f.toggle();
    assert.equal(f.calls[1].options.method, 'DELETE');
    assert.equal(f.buttons[0].count.textContent, '3');
    assert.equal(f.buttons[0].attrs['aria-pressed'], 'false');
});

test('unavailable initial state never guesses and sends the wrong mutation', async () => {
    const f = fixture();
    f.handler = async () => response({}, false);
    await f.toggle();
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].options.method, undefined);
    assert.equal(f.buttons[0].count.textContent, '4');
    assert.equal(f.buttons[0].disabled, false);
});
