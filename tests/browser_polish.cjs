/* Optional real-browser check; all accounts, API replies and images are fixtures. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const base = 'http://127.0.0.1:5099';
const uid = '00000000-0000-4000-8000-000000000001';
const other = '00000000-0000-4000-8000-000000000009';
const user = {id: uid, email: 'a'.repeat(60) + '@example.test', email_confirmed_at: '2026-01-01', app_metadata: {providers: ['email'], has_password: true}, user_metadata: {display_name: 'LongUsername'.repeat(4), bio: 'LongBiography'.repeat(30), has_password: true}, identities: [{provider: 'email', identity_data: {email: 'a'.repeat(60) + '@example.test'}}]};
const cat = id => ({id, user_id: uid, user_name: user.user_metadata.display_name, name: 'Test Cat ' + id, image_url: 'https://images.example.test/cat.svg', user_avatar: 'https://images.example.test/avatar.svg', created_at: new Date().toISOString(), likes_count: 2, bio: 'A long story '.repeat(80)});
const comment = (id, extra={}) => ({id, cat_id: '1', user_id: uid, user_name: user.user_metadata.display_name, user_avatar: 'https://images.example.test/avatar.svg', comment: 'A friendly comment '.repeat(10), created_at: new Date().toISOString(), likes_count: 0, ...extra});
const errors = [], overflows = [], requests = [], consoleErrors = [];
const output = process.env.CATRANK_BROWSER_OUTPUT || '/tmp/catrank-browser-results';
fs.mkdirSync(output, {recursive: true});
let browser, server;
async function main() {
    server = spawn(path.join(root, 'venv/bin/python'), ['-m', 'tests.browser_server'], {cwd:root, stdio:['ignore','ignore','pipe']});
    let serverLog = '';
    server.stderr.on('data', value => {serverLog += value;});
    for(let i=0;i<60;i++) {
        try {if ((await fetch(base+'/livez')).ok) break;} catch {}
        if (i===59) throw Error(serverLog);
        await new Promise(r=>setTimeout(r,100));
    }
    browser = await chromium.launch();
    const context = await browser.newContext();
    await context.addInitScript(({user}) => { window.fixtureUser = user; window.fixtureSignedIn = localStorage.getItem('fixture-signed-out') !== '1'; }, {user});
    await context.route('**/static/vendor/supabase.js*', route => route.fulfill({contentType:'application/javascript', body:`
        window.supabase = {createClient: () => ({auth: {
            getSession: async () => ({data:{session: window.fixtureSignedIn ? {user:window.fixtureUser,access_token:'fixture-token'} : null}}),
            getUser: async () => ({data:{user:window.fixtureUser}}),
            getUserIdentities: async () => ({data:{identities:window.fixtureUser.identities}}),
            setSession: async () => {localStorage.removeItem('fixture-signed-out');window.fixtureSignedIn=true;return {data:{session:{user:window.fixtureUser,access_token:'fixture-token'},user:window.fixtureUser}}},
            onAuthStateChange: cb => {window.fixtureAuthCallback=cb;return {data:{subscription:{unsubscribe(){}}}}},
            signOut: async () => {localStorage.setItem('fixture-signed-out','1');window.fixtureSignedIn=false;window.fixtureAuthCallback?.('SIGNED_OUT',null);return {}},
            updateUser: async () => ({data:{user:window.fixtureUser}}),
            signInWithOAuth: async options => {window.fixtureOAuth=options;return {}},
            exchangeCodeForSession: async () => ({error:{message:'Invalid test code'}}),
            resetPasswordForEmail: async () => ({}),
        }})};` }));
    await context.route(/^https:\/\//, async route => {
        if (route.request().resourceType()==='image') return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400"><rect width="600" height="400" fill="#e9e2f5"/><text x="230" y="230" font-size="70">Cat</text></svg>'});
        return route.abort();
    });
    let comments = [], nextCursor = null, failComments = false, delayA = false, stallComments = false;
    await context.route('**/api/**', async route => {
        const req=route.request(), url=new URL(req.url()), p=url.pathname, method=req.method(); requests.push({p, method});
        let data = {};
        if(p.endsWith('/comments') && method==='GET') {
            if(stallComments) return;
            if(delayA && p.includes('/1/')) {await new Promise(r=>setTimeout(r,300)); data={comments:[comment('stale', {comment:'STALE CAT A'})],total:1};}
            else data={comments, total:comments.length, next_cursor:nextCursor, server_time:new Date().toISOString()};
            if(failComments) return route.fulfill({status:503,json:{error:'Temporarily unavailable'}});
        } else if(p.endsWith('/comments') && method==='POST') {const body=req.postDataJSON(); const c=comment('new-'+Date.now(),body); comments.push(c);data={comment:c};}
        else if(p.match(/\/comments\/[^/]+$/) && method==='PUT') {const c=comments.find(c=>c.id===p.split('/').at(-1)); if(c) Object.assign(c,req.postDataJSON());data={comment:c?.comment,updated_at:new Date().toISOString()};}
        else if(p.match(/\/comments\/[^/]+$/) && method==='DELETE') {comments=comments.filter(c=>c.id!==p.split('/').at(-1));data={status:'deleted'};}
        else if(p.endsWith('/like')) data={status:'liked',liked:true,likes_count:3};
        else if(p.endsWith('/favorite')) data={saved:method==='PUT'};
        else if(p==='/api/auth/options') data={google_enabled:true};
        else if(p==='/api/auth/login') data={access_token:'fixture-token',refresh_token:'fixture-refresh'};
        else if(p==='/api/auth/register') data={requires_email_confirmation:true};
        else if(p==='/api/notifications') data={notifications:[{id:'n1',actor_name:user.user_metadata.display_name,actor_avatar:cat('1').user_avatar,cat_id:'1',type:'comment',message:'A'.repeat(200),created_at:new Date().toISOString(),is_read:false}],unread_count:1};
        else if(p.endsWith('/profile')) data={user_name:user.user_metadata.display_name,bio:user.user_metadata.bio,user_avatar:cat('1').user_avatar,cats:[cat('1')],total_likes:2};
        else if(p.includes('comment-likes')) data={liked_comment_ids:[]};
        else if(p.endsWith('/liked-cats')) data={liked_cat_ids:[]};
        else if(p.endsWith('/favorite-ids')) data={favorite_cat_ids:[]};
        else if(p.endsWith('/favorites') || p.endsWith('/my-cats')) data={cats:[cat('1')],has_next:false};
        else if(p.startsWith('/api/cats/')) data={cat:cat(p.split('/')[3])};
        return route.fulfill({json:data});
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => {if(message.type()==='error') consoleErrors.push(message.text());});
    const inspect = async label => {
        const result=await page.evaluate(() => ({width:innerWidth,scroll:document.documentElement.scrollWidth, bad:[...document.querySelectorAll('body *')].filter(el=>{
            const r=el.getBoundingClientRect(),s=getComputedStyle(el);return r.width>0&&r.height>0&&s.position!=='fixed'&&(r.right>innerWidth+1||r.left < -1)&&!el.closest('.contact-honeypot')&&s.visibility!=='hidden';
        }).slice(0,10).map(el=>({tag:el.tagName,id:el.id,class:el.className}))}));
        if(result.scroll>result.width+1) overflows.push({label,...result});
    };
    const widths=process.env.CATRANK_BROWSER_WIDTHS ? process.env.CATRANK_BROWSER_WIDTHS.split(',').map(Number) : [320,360,375,390,412,430,768,1024,1440];
    const paths=['/','/leaderboard','/profile','/user/'+other,'/upload','/login','/register','/forgot-password','/reset-password','/set-password','/contact','/missing','/__test/error/403','/__test/error/429','/__test/error/500','/__test/error/503'];
    for(const width of widths) {
        await page.setViewportSize({width,height:850});
        for(const p of paths) {
            await page.goto(base+p); await page.waitForTimeout(70); await inspect(`${width} ${p}`);
            if(p==='/profile') {
                await page.evaluate(()=>openEditProfileModal()); await page.evaluate(()=>switchProfileModalTab('security')); await page.waitForTimeout(80);
                await inspect(`${width} security modal`);
                await page.evaluate(()=>openSecurityMethod('email')); await inspect(`${width} email settings`);
                const bounds = await page.locator('#edit-profile-dialog').boundingBox();
                assert(bounds.y >= 0 && bounds.y + bounds.height <= 850, 'Profile dialog must stay in viewport');
                if(width===320) await page.screenshot({path:path.join(output,'security-320.png')});
            }
            if(p==='/' || p==='/contact') {
                if(width===320||width===1440) await page.screenshot({path:path.join(output,`${p==='/'?'home':'contact'}-${width}.png`),fullPage:true});
            }
        }
        await page.goto(base+'/');
        await page.evaluate(()=>openCatModal('1'));
        await page.waitForFunction(()=>!commentsLoading);
        await inspect(`${width} cat modal`);
        assert.match(await page.locator('#modal-comments-items').innerText(),/No comments/);
        await page.evaluate(()=>closeCatModal());
        await page.evaluate(()=>toggleNotificationsDropdown());
        await inspect(`${width} notifications`);
    }
    await page.setViewportSize({width:390,height:850});
    await page.goto(base+'/');
    comments=[comment('c1'),comment('c2',{parent_id:'c1',reply_to_id:'c1',comment:'A reply'})];
    await page.evaluate(()=>openCatModal('1'));
    await page.waitForFunction(()=>!commentsLoading);
    assert.match(await page.locator('#modal-comments-items').innerText(),/A reply/);
    await page.waitForFunction(()=>document.getElementById('modal-cat-img').naturalWidth>0);
    await page.locator('#modal-comment-input').fill('New comment from browser');
    await page.locator('#modal-comment-submit-btn').click();
    await page.waitForFunction(()=>!commentsLoading && loadedComments.some(c=>c.comment==='New comment from browser'));
    await page.evaluate(()=>{lastCommentTime=0;startReply('c1','Cat Person','c1')});
    await page.locator('#modal-comment-input').fill('Browser reply');
    await page.locator('#modal-comment-submit-btn').click();
    await page.waitForFunction(()=>!commentsLoading && loadedComments.some(c=>c.comment==='Browser reply' && c.parent_id==='c1'));
    await page.locator('[data-edit-comment-id="c1"]').click();
    await page.locator('.comment-inline-editor__textarea').fill('Edited in browser');
    await page.locator('.comment-inline-editor__button--save').click();
    await page.waitForFunction(()=>!commentsLoading && loadedComments.some(c=>c.comment==='Edited in browser'));
    await page.locator('[data-comment-like-id="c1"]').click();
    await page.waitForFunction(()=>document.querySelector('[data-comment-like-id="c1"]').getAttribute('aria-pressed')==='true');
    nextCursor='page-two';
    await page.evaluate(()=>loadCatComments('1'));
    comments=[comment('c3',{comment:'Second page comment'})]; nextCursor=null;
    await page.getByRole('button',{name:'Load more comments'}).click();
    await page.waitForFunction(()=>!commentsLoading && loadedComments.some(c=>c.id==='c3'));
    assert(await page.locator('#modal-comments-items').innerText().then(text=>text.includes('Edited in browser')));
    await page.locator('[onclick*="deleteComment(\'c3\'"]').click();
    await page.locator('#custom-confirm-action-btn').click();
    await page.waitForFunction(()=>!commentsLoading && !loadedComments.some(c=>c.id==='c3'));
    comments=[comment('c1'),comment('c2',{parent_id:'c1',comment:'A reply'})];
    await page.evaluate(()=>loadCatComments('1'));
    await page.waitForTimeout(250);
    await page.screenshot({path:path.join(output,'comments-390.png')});
    await page.evaluate(()=>closeCatModal());
    failComments=true;
    await page.evaluate(()=>openCatModal('1'));
    await page.waitForFunction(()=>!commentsLoading);
    assert.match(await page.locator('#modal-comments-items').innerText(),/Try again/);
    failComments=false;
    await page.locator('#comments-retry').click();
    await page.waitForFunction(()=>!commentsLoading);
    assert.match(await page.locator('#modal-comments-items').innerText(),/A reply/);
    delayA=true;
    await page.evaluate(()=>{openCatModal('1');openCatModal('2')});
    await page.waitForTimeout(400);
    assert.doesNotMatch(await page.locator('#modal-comments-items').innerText(),/STALE CAT A/);
    await page.evaluate(()=>closeCatModal());
    delayA=false; stallComments=true;
    await page.evaluate(()=>{openCatModal('1')});
    await page.waitForFunction(()=>!commentsLoading, {timeout:20000});
    assert.match(await page.locator('#modal-comments-items').innerText(),/Try again/);
    stallComments=false;
    await page.evaluate(()=>closeCatModal());
    await page.evaluate(()=>openCatModal('1'));
    await page.waitForFunction(()=>!commentsLoading);
    assert.match(await page.locator('#modal-comments-items').innerText(),/A reply/);
    // Simulate the shorter viewport available while a mobile keyboard is open.
    await page.setViewportSize({width:320,height:420});
    await page.locator('#modal-comment-input').focus();
    await inspect('320 keyboard-height cat modal');
    const composer=await page.locator('#modal-comment-input').boundingBox();
    assert(composer.y>=0 && composer.y+composer.height<=420,'Composer must remain visible');
    await page.keyboard.press('Escape');
    assert(await page.locator('#cat-detail-modal').evaluate(el=>el.classList.contains('hidden')));
    await page.goto(base+'/contact');
    assert.equal(await page.locator('.contact-channel[target="_blank"]').count(),2);
    await page.getByLabel('Name',{exact:true}).fill('Browser Tester');
    await page.getByLabel('Email',{exact:true}).fill('browser@example.test');
    await page.getByLabel('Subject',{exact:true}).fill('Test contact');
    await page.getByLabel('Message',{exact:true}).fill('Test message');
    await page.waitForTimeout(2100);
    await page.getByRole('button',{name:'Send message'}).click();
    await page.waitForURL(base+'/contact');
    await page.getByRole('status').filter({hasText:'accepted by our email service'}).waitFor();
    await page.evaluate(()=>localStorage.setItem('fixture-signed-out','1'));
    for(const width of widths) {
        await page.setViewportSize({width,height:850});
        for(const p of ['/','/leaderboard','/user/'+other,'/upload','/login','/register','/forgot-password','/reset-password','/set-password','/contact','/auth/callback']) {
            await page.goto(base+p); await page.waitForTimeout(80); await inspect(`${width} logged out ${p}`);
        }
    }
    await page.goto(base+'/register');
    await page.locator('#reg-display-name').fill('Browser Cat');
    await page.locator('#reg-email').fill('new@example.test');
    await page.locator('#reg-password').fill('Test-password-123');
    await page.locator('#reg-confirm-password').fill('Test-password-123');
    await page.locator('#register-btn').click();
    await page.waitForFunction(()=>document.getElementById('register-alert-box').textContent.includes('new@example.test'));
    await page.goto(base+'/forgot-password');
    await page.locator('#forgot-email').fill('new@example.test');
    await page.locator('#forgot-btn').click();
    await page.waitForFunction(()=>!document.getElementById('forgot-btn').disabled);
    assert(requests.some(r=>r.p==='/api/auth/password-reset'&&r.method==='POST'));
    await page.goto(base+'/login');
    await page.evaluate(()=>startGoogleSignIn());
    assert.equal(await page.evaluate(()=>window.fixtureOAuth.provider),'google');
    await page.goto(base+'/login');
    await page.locator('#email').fill(user.email);
    await page.locator('#password').fill('Test-password-123');
    await page.locator('#login-btn').click();
    await page.waitForURL(base+'/');
    await page.goto(base+'/upload');
    await page.locator('#cat-name').fill('Browser Cat');
    const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=','base64');
    await page.locator('#cat-file').setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:png});
    await page.locator('#submit-btn').click();
    await page.waitForURL(base+'/');
    assert(requests.some(r=>r.p==='/api/cats/upload'&&r.method==='POST'));
    await page.evaluate(()=>openCatModal('1'));
    await page.locator('#modal-like-btn').click();
    await page.waitForFunction(()=>document.getElementById('modal-like-btn').getAttribute('aria-pressed')==='true');
    await page.locator('#modal-save-btn').click();
    await page.waitForFunction(()=>document.getElementById('modal-save-btn').getAttribute('aria-pressed')==='true');
    await page.evaluate(()=>closeCatModal());
    await page.evaluate(()=>handleLogout());
    await page.waitForFunction(()=>currentSession===null);
    const unexpectedConsoleErrors=[...new Set(consoleErrors)].filter(message=>!/^Failed to load resource: the server responded with a status of (400|403|404|429|500|503) /.test(message));
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({widths,paths,overflows,errors,unexpectedConsoleErrors,consoleErrors:[...new Set(consoleErrors)],requests:requests.length},null,2));
    assert.deepEqual(unexpectedConsoleErrors, [], 'Unexpected browser console errors');
    console.log(JSON.stringify({pages:widths.length*(paths.length+11),overflows,errors},null,2));
    assert.equal(overflows.length,0,'Horizontal overflow found');
    assert.deepEqual(errors,[],'Browser JavaScript errors');
}
main().catch(error=>{console.error(error);console.error(JSON.stringify({overflows,errors,consoleErrors:[...new Set(consoleErrors)]},null,2));process.exitCode=1}).finally(async()=>{await browser?.close();server?.kill();});
