const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const session = id => ({user: {id}, access_token: `token-${id}`});
const response = data => ({ok: true, json: async () => data});
const deferred = () => {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return {promise, resolve};
};
const flush = () => new Promise(resolve => setImmediate(resolve));

function element(id = '') {
    const classes = new Set();
    return {
        id, dataset: {}, attributes: {}, innerHTML: '', innerText: '', textContent: '',
        classList: {
            add: (...names) => names.forEach(name => classes.add(name)),
            remove: (...names) => names.forEach(name => classes.delete(name)),
            contains: name => classes.has(name),
            toggle(name, enabled) {
                const value = enabled === undefined ? !classes.has(name) : enabled;
                if (value) classes.add(name); else classes.delete(name);
            }
        },
        setAttribute(name, value) { this.attributes[name] = value; },
        querySelector() { return null; },
        addEventListener() {},
    };
}

function browser(commentIds = []) {
    const nodes = new Map(['notifications-list', 'notif-badge', 'notifications-unread-count']
        .map(id => [id, element(id)]));
    const buttons = commentIds.map(id => {
        const button = element();
        button.dataset = {commentLikeId: String(id), commentLikeCount: '0'};
        const icon = element();
        const count = element();
        count.textContent = '0';
        button.querySelector = selector => selector.includes('icon') ? icon : count;
        return button;
    });
    const listeners = new Map();
    const document = {
        getElementById: id => nodes.get(id) || null,
        querySelectorAll(selector) {
            if (selector === '[data-comment-like-id]') return buttons;
            const match = selector.match(/^\[data-comment-like-id="(.*)"\]$/);
            return match ? buttons.filter(button => button.dataset.commentLikeId === match[1]) : [];
        },
        querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
        addEventListener() {},
        body: {style: {}}
    };
    const context = vm.createContext({
        document, console, URL, URLSearchParams, Date, Set, Map,
        CSS: {escape: value => String(value).replace(/"/g, '\\"')},
        CustomEvent: class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } },
        setTimeout: () => 0, clearTimeout() {}, showToast() {},
        location: {origin: 'https://catrank.example', pathname: '/', search: '', href: 'https://catrank.example/'},
        __session: session('alice'),
        fetch: async () => { throw new Error('Unexpected request'); },
    });
    context.window = context;
    context.addEventListener = (type, listener) => {
        if (!listeners.has(type)) listeners.set(type, []);
        listeners.get(type).push(listener);
    };
    context.dispatchEvent = event => (listeners.get(event.type) || []).forEach(listener => listener(event));
    context.supabaseClient = {auth: {
        getSession: async () => ({data: {session: context.__session}}),
        onAuthStateChange: callback => { context.authCallback = callback; },
    }};
    const run = source => vm.runInContext(source, context);
    for (const file of ['auth.js', 'main.js', 'comment-likes.js']) {
        run(fs.readFileSync(path.join(root, 'static/js', file), 'utf8'));
    }
    context.setCurrentSession(context.__session);
    const changeAccount = id => {
        context.__session = id ? session(id) : null;
        context.authCallback(id ? 'SIGNED_IN' : 'SIGNED_OUT', context.__session);
    };
    return {context, nodes, buttons, run, changeAccount};
}

test('logout discards private notifications even when an old response body resolves later', async () => {
    const {context, nodes, run, changeAccount} = browser();
    const body = deferred();
    context.fetch = async () => ({ok: true, json: () => body.promise});
    const pending = context.fetchNotifications();
    await flush();
    changeAccount(null);
    body.resolve({notifications: [{id: 'secret', message: 'private activity'}], unread_count: 1});
    await pending;
    assert.equal(run('notificationsCache.length'), 0);
    assert.equal(run('notificationsUnreadCount'), 0);
    assert.ok(!nodes.get('notifications-list').innerHTML.includes('private activity'));
});

test('simultaneous notification loads share a request', async () => {
    const {context} = browser();
    const request = deferred();
    let requests = 0;
    context.fetch = () => { requests++; return request.promise; };
    const first = context.fetchNotifications();
    const second = context.fetchNotifications();
    request.resolve(response({notifications: [], unread_count: 0}));
    await Promise.all([first, second]);
    assert.equal(requests, 1);
});

test('old account vote snapshots cannot populate a new account', async () => {
    const {context, run, changeAccount} = browser();
    const body = deferred();
    context.fetch = async () => ({ok: true, json: () => body.promise});
    const pending = context.syncUserLikes();
    await flush();
    changeAccount('bob');
    body.resolve({liked_cat_ids: ['cat-1']});
    await pending;
    assert.equal(run('userLikedCatIds.size'), 0);
});

test('an in-flight vote cannot repopulate a logged-out account', async () => {
    const {context, run, changeAccount} = browser();
    const request = deferred();
    context.fetch = () => request.promise;
    const pending = context.toggleLike('cat-1');
    await flush();
    assert.equal(run('userLikedCatIds.has("cat-1")'), true);
    changeAccount(null);
    request.resolve(response({status: 'liked', likes_count: 1}));
    await pending;
    assert.equal(run('userLikedCatIds.size'), 0);
    assert.equal(run('pendingLikes.size'), 0);
});

test('a stale vote snapshot cannot roll back a successful mutation', async () => {
    const {context, run} = browser();
    const snapshot = deferred();
    context.fetch = url => url === '/api/user/liked-cats'
        ? snapshot.promise : Promise.resolve(response({status: 'liked', likes_count: 1}));
    const pending = context.syncUserLikes();
    await context.toggleLike('cat-1');
    snapshot.resolve(response({liked_cat_ids: []}));
    await pending;
    assert.equal(run('userLikedCatIds.has("cat-1")'), true);
});

test('comment likes cover every page in batches of at most 100 and reuse known ids', async () => {
    const ids = Array.from({length: 205}, (_, i) => `comment-${i}`);
    const {context, buttons} = browser(ids);
    const batchSizes = [];
    context.fetch = async url => {
        const batch = new URL(url, context.location.origin).searchParams.get('ids').split(',');
        batchSizes.push(batch.length);
        return response({liked_comment_ids: batch});
    };
    await context.syncCommentLikes(ids);
    assert.deepEqual(batchSizes, [100, 100, 5]);
    assert.ok(buttons.every(button => button.attributes['aria-pressed'] === 'true'));
    await context.syncCommentLikes(ids);
    assert.deepEqual(batchSizes, [100, 100, 5]);
});

test('a stale comment-like snapshot cannot undo a successful vote', async () => {
    const {context, buttons} = browser(['comment-1']);
    const snapshot = deferred();
    context.fetch = url => url.startsWith('/api/user/comment-likes')
        ? snapshot.promise : Promise.resolve(response({liked: true, likes_count: 1}));
    const pending = context.syncCommentLikes(['comment-1']);
    await flush();
    await context.toggleCommentLike('comment-1');
    snapshot.resolve(response({liked_comment_ids: []}));
    await pending;
    assert.equal(buttons[0].attributes['aria-pressed'], 'true');
    assert.equal(buttons[0].dataset.commentLikeCount, '1');
});

test('double-clicking a comment vote issues one mutation', async () => {
    const {context} = browser(['comment-1']);
    let mutations = 0;
    context.fetch = async () => { mutations++; return response({liked: true, likes_count: 1}); };
    await Promise.all([context.toggleCommentLike('comment-1'), context.toggleCommentLike('comment-1')]);
    assert.equal(mutations, 1);
});

test('logout clears comment likes and ignores old mutation responses', async () => {
    const {context, buttons, changeAccount} = browser(['comment-1']);
    const request = deferred();
    context.fetch = () => request.promise;
    const pending = context.toggleCommentLike('comment-1');
    await flush();
    changeAccount(null);
    request.resolve(response({liked: true, likes_count: 1}));
    await pending;
    await flush();
    assert.equal(buttons[0].attributes['aria-pressed'], 'false');
});

test('concurrent mark-read actions decrement unread count only once', async () => {
    const {context, run} = browser();
    run('notificationsCache = [{id: "one", is_read: false}, {id: "two", is_read: false}]; notificationsUnreadCount = 2;');
    context.fetch = async () => response({});
    await Promise.all([context.markNotificationRead('one'), context.markNotificationRead('one')]);
    assert.equal(run('notificationsUnreadCount'), 1);
});

test('an old account pending vote does not block or unlock the new account vote', async () => {
    const {context, run, changeAccount} = browser();
    const alice = deferred();
    const bob = deferred();
    let requests = 0;
    context.fetch = () => ++requests === 1 ? alice.promise : bob.promise;
    const first = context.toggleLike('cat-1');
    await flush();
    changeAccount('bob');
    const second = context.toggleLike('cat-1');
    await flush();
    assert.equal(requests, 2);
    alice.resolve(response({status: 'liked', likes_count: 1}));
    await first;
    assert.equal(run('pendingLikes.size'), 1);
    await context.toggleLike('cat-1');
    assert.equal(requests, 2);
    bob.resolve(response({status: 'liked', likes_count: 2}));
    await second;
    assert.equal(run('pendingLikes.size'), 0);
});

test('an old account pending comment vote does not block the next account', async () => {
    const {context, buttons, changeAccount} = browser(['comment-1']);
    const alice = deferred();
    const bob = deferred();
    let requests = 0;
    context.fetch = () => ++requests === 1 ? alice.promise : bob.promise;
    const first = context.toggleCommentLike('comment-1');
    await flush();
    changeAccount('bob');
    const second = context.toggleCommentLike('comment-1');
    await flush();
    assert.equal(requests, 2);
    alice.resolve(response({liked: true, likes_count: 1}));
    await first;
    await context.toggleCommentLike('comment-1');
    assert.equal(requests, 2);
    bob.resolve(response({liked: true, likes_count: 2}));
    await second;
    assert.equal(buttons[0].dataset.commentLikeCount, '2');
});

test('account switches hide and reload pages containing private profile or admin data', () => {
    for (const page of ['/profile', '/admin', '/upload', '/user/alice']) {
        const {context, changeAccount} = browser();
        context.location.pathname = page;
        let reloads = 0;
        context.location.reload = () => reloads++;
        changeAccount('bob');
        assert.equal(reloads, 1);
        assert.equal(context.document.body.style.visibility, 'hidden');
    }
});
