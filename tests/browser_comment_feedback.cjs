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
const output = process.env.CATRANK_BROWSER_OUTPUT || path.join(root, 'artifacts/comment-feedback');
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
    browser = await chromium.launch({executablePath: process.env.CATRANK_CHROME || '/usr/bin/google-chrome-stable', args:['--no-sandbox']});
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
    let postStatus = 201, postDelay = 0, postCalls = [], postsById = new Map();
    let comments = [], nextCursor = null, failComments = false, delayA = false, stallComments = false;
    await context.route('**/api/**', async route => {
        const req=route.request(), url=new URL(req.url()), p=url.pathname, method=req.method(); requests.push({p, method});
        let data = {};
        if(p.endsWith('/comments') && method==='GET') {
            if(stallComments) return;
            if(delayA && p.includes('/1/')) {await new Promise(r=>setTimeout(r,300)); data={comments:[comment('stale', {comment:'STALE CAT A'})],total:1};}
            else data={comments, total:comments.length, next_cursor:nextCursor, server_time:new Date().toISOString()};
            if(failComments) return route.fulfill({status:503,json:{error:'Temporarily unavailable'}});
        } else if(p.endsWith('/comments') && method==='POST') {
            const body=req.postDataJSON(); postCalls.push({body, headers:req.headers(), path:p, method});
            if (postDelay) await new Promise(resolve=>setTimeout(resolve, postDelay));
            if (postStatus === 'network') return route.abort('failed');
            if (postStatus !== 201) return route.fulfill({status:postStatus, json:{error:'PRIVATE SQL httpx traceback must not render'}});
            let c=postsById.get(body.submission_id);
            if (!c) { c=comment('new-'+postCalls.length, body); comments.push(c); postsById.set(body.submission_id,c); }
            data={comment:c};
        }
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
    const widths = process.env.CATRANK_BROWSER_WIDTHS === 'forms' ? [] : [320,360,375,390,412,430,1440,1536];
    const cases = [];
    const input = page.locator('#modal-comment-input'), send = page.locator('#modal-comment-submit-btn');
    const status = page.locator('#modal-comment-status');
    const rect = locator => locator.boundingBox();
    const overlap = (a,b) => a.x < b.x+b.width && a.x+a.width>b.x && a.y<b.y+b.height && a.y+a.height>b.y;
    async function layout(label) {
        await inspect(label);
        const [form, button, close] = await Promise.all([rect(input),rect(send),rect(page.locator('[data-modal-initial-focus]'))]);
        for (const box of [form, button, close]) assert(box && box.x>=0 && box.y>=0 && box.x+box.width<=page.viewportSize().width+1 && box.y+box.height<=900, label+' visible controls');
        const reachable=await page.locator('[data-modal-initial-focus]').evaluate(el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))});
        assert(reachable, label+' reachable close');
    }
    for (const width of widths) for (const lang of ['en','ru']) {
        console.log(`Checking ${width}px ${lang}`);
        comments=[]; postsById.clear(); postStatus=201; postDelay=150;
        await page.setViewportSize({width,height:900});
        await page.goto(base+'/');
        await page.evaluate(lang=>setLanguage(lang),lang);
        await page.evaluate(()=>openCatModal('1'));
        await page.waitForFunction(()=>!commentsLoading && currentSession);
        await layout(`${width} ${lang} initial`);
        const modalBefore=await rect(page.locator('#cat-detail-panel'));
        const start=postCalls.length;
        await input.fill(lang==='en'?'Normal comment':'Обычный комментарий');
        // Race both calls while getSession is still pending.
        await page.evaluate(()=>{submitComment();submitComment();});
        assert(await send.isDisabled());
        await page.waitForFunction(()=>!document.getElementById('modal-comment-submit-btn').disabled);
        assert.equal(postCalls.length-start,1,'one POST for double submit');
        assert.equal(postCalls.at(-1).method,'POST');
        assert.equal(postCalls.at(-1).headers.authorization,'Bearer fixture-token');
        assert.match(postCalls.at(-1).body.submission_id,/^[0-9a-f-]{36}$/);
        assert.equal(await input.inputValue(),'');
        assert.equal(await page.evaluate(()=>commentsTotal),1);
        assert.equal(await page.evaluate(()=>loadedComments.length),1);
        assert.equal(await status.isVisible(),false);
        const parent=comments[0].id;
        await page.evaluate(id=>{lastCommentTime=0;startReply(id,'Tester',id)},parent);
        await input.fill(lang==='en'?'Normal reply':'Обычный ответ');
        await send.click();
        await page.waitForFunction(()=>!document.getElementById('modal-comment-submit-btn').disabled);
        assert.equal(postCalls.at(-1).body.parent_id,parent);
        assert.equal(await page.evaluate(()=>commentsTotal),2);
        await layout(`${width} ${lang} reply`);
        cases.push(`${width}/${lang}: normal, reply, double-submit, count`);
        for (const failure of [401,403,429,503,'network',500]) {
            postStatus=failure;
            await page.evaluate(()=>{lastCommentTime=0;cancelReply()});
            const draft=lang==='en'?'Keep my draft':'Сохраните мой комментарий';
            await input.fill(draft);
            await send.click();
            await page.waitForFunction(()=>!document.getElementById('modal-comment-submit-btn').disabled);
            assert.equal(await input.inputValue(),draft);
            assert(await status.isVisible());
            const expected=await page.evaluate(f=>friendlyFormError(f,'comment'),failure);
            assert.equal(await status.innerText(),expected);
            assert.equal(await page.locator('#toast-container > *').count(),0,'inline failure has no toast');
            await layout(`${width} ${lang} ${failure}`);
            const bounds=await rect(page.locator('#cat-detail-panel'));
            if(modalBefore && bounds) assert(Math.abs(bounds.y-modalBefore.y)<2,'modal must not jump');
            if (failure===503 && [320,390,1440,1536].includes(width)) await page.screenshot({path:path.join(output,`inline-${width}-${lang}.png`)});
            const retryId=postCalls.at(-1).body.submission_id;
            postStatus=201;
            await send.click();
            await page.waitForFunction(()=>!document.getElementById('modal-comment-submit-btn').disabled);
            assert.equal(postCalls.at(-1).body.submission_id,retryId,'retry reuses submission UUID');
            assert.equal(await input.inputValue(),'');
            assert.equal(await status.isVisible(),false);
            cases.push(`${width}/${lang}: ${failure} draft + inline + retry`);
        }
        await page.evaluate(()=>showToast(currentLang==='ru'?'Профиль успешно обновлён.':'Profile updated successfully.','success'));
        await page.waitForTimeout(200);
        const toast=await rect(page.locator('.global-toast'));
        assert(toast.y>=0 && toast.y<150,'toast from top');
        assert(!overlap(toast,await rect(input)),'toast clear of composer');
        await layout(`${width} ${lang} toast`);
        assert.equal(await page.locator('.system-feedback-container').count(),0);
        if([320,390,1440,1536].includes(width)) await page.screenshot({path:path.join(output,`toast-${width}-${lang}.png`)});
        await page.evaluate(()=>showToast('A second global notice','info'));
        await layout(`${width} ${lang} stacked toast`);
        const boxes=await page.locator('.global-toast').evaluateAll(items=>items.map(el=>{const r=el.getBoundingClientRect();return {top:r.top,bottom:r.bottom}}));
        assert(boxes[1].top >= boxes[0].bottom,'toasts stack downward');
        await page.locator('.global-toast button').first().click();
        await page.locator('.global-toast button').first().click();
        assert.equal(await page.locator('.global-toast').count(),0);
        cases.push(`${width}/${lang}: toast position + dismiss + no bottom alert`);
    }
    await page.goto(base+'/');
    // Form errors use the shipped login/register/upload/profile markup too.
    for (const [url, action, host] of [
        ['/login',()=>handleLogin(),'#login-email-form'],
        ['/register',()=>handleSignUp(),'#register-email-form'],
        ['/upload',()=>handleFileSelect(new File(['bad'],'bad.txt',{type:'text/plain'})),'#upload-form'],
        ['/profile',()=>{openEditProfileModal();showInlineError('tab-content-basic',friendlyFormError(503));},'#tab-content-basic']
    ]) {
        await page.evaluate(signedOut=>localStorage.setItem("fixture-signed-out",signedOut ? "1" : "0"),["/login","/register"].includes(url));
        await page.goto(base+url);
        await page.evaluate(action);
        assert(await page.locator(host+' [data-inline-error]').isVisible(),url+' inline at '+page.url());
        assert.equal(await page.locator('#toast-container > *').count(),0);
        cases.push(url+': inline form error');
    }
    assert.deepEqual(errors,[],'No JavaScript errors');
    assert.deepEqual(overflows,[],'No horizontal overflow');
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:cases.length,failed:0,widths,languages:['en','ru'],cases,errors,overflows,mocked:'Auth, API and images; actual Flask templates and shipped modal JS/CSS'},null,2));
    fs.writeFileSync(path.join(output,'runtime.log'),serverLog);
    console.log(JSON.stringify({passed:cases.length,failed:0,errors,overflows,output}));
}
main().catch(error=>{console.error(error);process.exitCode=1}).finally(async()=>{await browser?.close();server?.kill();});
