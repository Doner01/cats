/* Render the real Flask page with fixture authentication and API responses. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require('puppeteer');
const root = path.resolve(__dirname, '..');
const base = 'http://127.0.0.1:5099';
const uid = '00000000-0000-4000-8000-000000000001';
const user = {id: uid, email: 'member@example.test', email_confirmed_at: '2026-01-01',
    app_metadata: {providers: ['email'], has_password: true},
    user_metadata: {display_name: 'Карина Миллер', bio: '', has_password: true},
    identities: [{provider: 'email', identity_data: {email: 'member@example.test'}}]};
const avatar = 'https://images.example.test/avatar.svg';
const cat = {id: '1', user_id: uid, user_name: user.user_metadata.display_name, name: 'Mochi',
    image_url: avatar, user_avatar: avatar, created_at: '2026-09-01', likes_count: 2, bio: 'A happy cat.'};
const output = '/tmp/catrank-profile-results';
let server, browser;

async function main() {
    fs.mkdirSync(output, {recursive: true});
    server = spawn(path.join(root, 'venv/bin/python'), ['-m', 'tests.browser_server'], {cwd: root, stdio: ['ignore', 'ignore', 'pipe']});
    let serverLog = '';
    server.stderr.on('data', chunk => { serverLog += chunk; });
    for (let i = 0; i < 100; i++) {
        try { if ((await fetch(base + '/livez')).ok) break; } catch {}
        if (i === 99) throw Error(serverLog);
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    browser = await puppeteer.launch({headless: true, args: ['--no-sandbox']});
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.evaluateOnNewDocument(user => {
        window.fixtureUser = user;
        localStorage.setItem('catrank_lang', 'ru');
    }, user);
    let cats = [], favoritesFail = false;
    await page.setRequestInterception(true);
    page.on('request', request => {
        const url = new URL(request.url()), p = url.pathname;
        const json = (data, status = 200) => request.respond({status, contentType: 'application/json', body: JSON.stringify(data)});
        if (p === '/static/vendor/supabase.js') return request.respond({contentType: 'application/javascript', body: `
            window.supabase = {createClient: () => ({auth: {
                getSession: async () => ({data: {session: {user: window.fixtureUser, access_token: 'fixture-token'}}}),
                getUser: async () => ({data: {user: window.fixtureUser}}),
                getUserIdentities: async () => ({data: {identities: window.fixtureUser.identities}}),
                onAuthStateChange: () => ({data: {subscription: {unsubscribe(){}}}}),
                refreshSession: async () => ({data: {session: {user: window.fixtureUser, access_token: 'fixture-token'}}})
            }})};`});
        if (url.origin !== base) {
            if (request.resourceType() === 'image') return request.respond({contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" rx="60" fill="#fb501c"/><text x="60" y="80" text-anchor="middle" fill="white" font-family="sans-serif" font-size="60">K</text></svg>'});
            return request.abort();
        }
        if (p.startsWith('/api/')) {
            if (p.endsWith('/profile')) return json({user_name: user.user_metadata.display_name, bio: user.user_metadata.bio, user_avatar: avatar, cats, total_likes: cats.length * 2});
            if (p.endsWith('/favorites')) return favoritesFail ? json({error: 'Temporary failure'}, 503) : json({cats: [], has_next: false});
            if (p.endsWith('/favorite-ids')) return json({favorite_cat_ids: []});
            if (p.endsWith('/liked-cats')) return json({liked_cat_ids: []});
            if (p === '/api/notifications') return json({notifications: [], unread_count: 0});
            if (p === '/api/auth/options') return json({google_enabled: true});
            if (p === '/api/cats/1' && request.method() === 'PUT') {
                Object.assign(cat, JSON.parse(request.postData()));
                return json({cat});
            }
            return json({});
        }
        return request.continue();
    });
    const loaded = async () => {
        await page.goto(base + '/profile');
        await page.waitForSelector('#profile-actions a');
        await page.waitForFunction(() => document.querySelector('#user-cats-grid .profile-grid-message, #user-cats-grid .cat-card'));
    };
    const noOverflow = async label => {
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), label + ': page overflow');
        assert(await page.$eval('.profile-header', el => el.scrollWidth <= el.clientWidth + 1), label + ': header overflow');
    };
    for (const width of [320, 390, 640, 768, 1024, 1440]) {
        await page.setViewport({width, height: 900});
        await loaded();
        await noOverflow(String(width));
        const layout = await page.evaluate(() => {
            const rect = selector => {const r = document.querySelector(selector).getBoundingClientRect(); return {x: r.x, y: r.y, right: r.right};};
            return {avatar: rect('.profile-avatar-wrap'), details: rect('.profile-details'), actions: rect('#profile-actions'), stats: rect('.profile-stats')};
        });
        if (width >= 640) {
            assert(layout.details.x >= layout.avatar.right, 'Desktop identity must sit beside avatar');
            assert(Math.abs(layout.details.y - layout.avatar.y) < 2, 'Desktop identity must align with avatar');
        } else assert(layout.details.y > layout.avatar.y, 'Mobile identity stacks beneath avatar');
        assert.equal(await page.$eval('#profile-bio', el => el.offsetHeight), 0, 'Empty bio must not leave a gap');
        assert.equal(await page.$eval('.profile-grid-message a', el => el.getAttribute('href')), '/upload');
        if ([390, 1440].includes(width)) await page.screenshot({path: path.join(output, `profile-${width}.png`), fullPage: true});
        await page.focus('#avatar-edit-overlay-btn');
        await page.keyboard.press('Enter');
        await page.waitForSelector('#edit-profile-modal:not(.hidden)');
        await page.keyboard.press('Escape');
        await page.waitForSelector('#edit-profile-modal.hidden');
        assert(await page.evaluate(() => !document.documentElement.classList.contains('overflow-hidden') && !document.body.classList.contains('overflow-hidden')), 'Escape restores scrolling');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'avatar-edit-overlay-btn', 'Closing restores focus');
        await page.click('#profile-actions button');
        await page.click('#tab-btn-security');
        await noOverflow(`${width} security`);
        const dialog = await page.$eval('#edit-profile-dialog', el => ({overflow: el.scrollWidth > el.clientWidth + 1, bottom: el.getBoundingClientRect().bottom}));
        assert(!dialog.overflow && dialog.bottom <= 900, 'Security dialog stays in viewport');
        await page.keyboard.press('Escape');
        console.log(`Profile and settings layout passed at ${width}px`);
    }
    user.user_metadata.bio = 'My custom biography must survive translation.';
    user.user_metadata.display_name = 'LongUnbrokenDisplayName'.repeat(3);
    await page.setViewport({width: 320, height: 900});
    await loaded();
    await noOverflow('long name');
    await page.evaluate(() => setLanguage('en'));
    assert.equal(await page.$eval('#profile-bio', el => el.textContent), user.user_metadata.bio);
    assert.equal(await page.$eval('#profile-actions button span', el => el.textContent), 'Edit Profile');
    await page.evaluate(() => setLanguage('ru'));
    assert.equal(await page.$eval('#profile-bio', el => el.textContent), user.user_metadata.bio);
    assert.equal(await page.$eval('#profile-actions button span', el => el.textContent), 'Редактировать');
    assert.equal(await page.$eval('[data-i18n="member_badge"]', el => el.textContent), 'Участник CatRank');
    favoritesFail = true;
    await page.click('#profile-favorites-tab');
    await page.waitForSelector('.profile-grid-message button');
    favoritesFail = false;
    await page.click('.profile-grid-message button');
    await page.waitForFunction(() => !document.querySelector('.profile-grid-message button'));
    assert.equal(await page.$('.profile-grid-message a'), null, 'Empty favorites must not show upload action');
    await page.click('#profile-uploads-tab');
    await page.waitForSelector('.profile-grid-message a');
    cats = [cat];
    await loaded();
    await page.click('.profile-cat-edit-button');
    await page.waitForFunction(() => document.activeElement.id === 'cat-edit-name-1');
    await page.$eval('#cat-edit-name-1', el => {el.value = 'Updated Mochi';});
    // Bring the action above the fixed mobile navigation before tapping it.
    await page.$eval('#cat-edit-save-1', el => el.scrollIntoView({block: 'center', behavior: 'instant'}));
    await page.click('#cat-edit-save-1');
    try {
        await page.waitForFunction(() => document.querySelector('.cat-title-row h3').textContent === 'Updated Mochi', {timeout: 5000});
    } catch (error) {
        await page.screenshot({path: path.join(output, 'edit-failure.png'), fullPage: true});
        console.error(await page.evaluate(() => ({text: document.body.innerText, session: Boolean(currentSession), save: document.querySelector('#cat-edit-save-1')?.outerHTML})), errors);
        throw error;
    }
    assert.equal(cat.name, 'Updated Mochi');
    await page.goto(base + '/user/00000000-0000-4000-8000-000000000009');
    await page.waitForSelector('.cat-card');
    assert.equal(await page.$eval('#profile-favorites-tab', el => getComputedStyle(el).display), 'none');
    assert.equal(await page.$eval('#avatar-edit-overlay', el => getComputedStyle(el).display), 'none');
    assert.equal(await page.$eval('#profile-actions', el => el.children.length), 0);
    assert.deepEqual(errors, []);
    console.log('Language switching, favorites retry, cat editing, public profile and keyboard checks passed.');
    console.log(`Screenshots: ${output}`);
}
main().catch(error => {console.error(error); process.exitCode = 1;}).finally(async () => {
    if (browser) await browser.close();
    if (server) server.kill();
});
