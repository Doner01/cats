const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture({code='abc', intent, userId='one', bootstrapOK=true}={}) {
    const store=new Map();
    if(intent) store.set('catrank_oauth_intent',JSON.stringify(intent));
    const calls=[];
    const status={textContent:''};
    const back={classList:{remove(){calls.push('back-visible')}}};
    const session={access_token:'test-access',user:{id:userId}};
    const auth={
        getSession:async()=>({data:{session}}),
        signInWithOAuth:async params=>{calls.push(['oauth',params]);return {error:null}},
        linkIdentity:async params=>{calls.push(['link',params]);return {error:null}},
        exchangeCodeForSession:async code=>{calls.push(['exchange',code]);return {data:{session},error:null}},
        signOut:async options=>{calls.push(['signout',options]);return {error:null}},
    };
    const context=vm.createContext({URL,URLSearchParams,Date,JSON,console,Error,
        supabaseClient:{auth},
        sessionStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},
        history:{replaceState:(_a,_b,p)=>calls.push(['history',p])},
        document:{addEventListener(){},querySelectorAll:()=>[],getElementById:id=>id==='oauth-status'?status:id==='oauth-back'?back:null},
        window:{location:{search:code?'?code='+code:'',hash:'',origin:'https://cats.example',replace:p=>calls.push(['redirect',p])}},
        getLoginDestination:()=>'/profile?tab=favorites',
        showToast:message=>calls.push(['toast',message]),
        fetch:async(url,opts)=>{
            calls.push(['fetch',url,opts]);
            if(url==='/api/auth/options') return {ok:true,json:async()=>({google_enabled:true})};
            return {ok:bootstrapOK,json:async()=>bootstrapOK?{ready:true}:{error:'Profile unavailable'}};
        },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/account.js'),'utf8'),context);
    return {context,calls,store,status,run:code=>vm.runInContext(code,context)};
}

const intent=(next='/profile')=>({next,userId:null,started:Date.now()});

test('Google start stores only intent and uses fixed local callback',async()=>{
    const f=fixture();await f.run('startGoogleSignIn()');
    const c=f.calls.find(c=>c[0]==='oauth');
    assert.equal(c[1].provider,'google');
    assert.equal(c[1].options.redirectTo,'https://cats.example/auth/callback');
    assert.equal(JSON.parse(f.store.get('catrank_oauth_intent')).next,'/profile?tab=favorites');
    assert.ok(!f.store.get('catrank_oauth_intent').includes('test-access'));
});

test('connecting Google records the account that must be returned',async()=>{
    const f=fixture();await f.run('startGoogleSignIn(true)');
    assert.ok(f.calls.some(c=>c[0]==='link'));
    assert.equal(JSON.parse(f.store.get('catrank_oauth_intent')).userId,'one');
});

test('successful callback exchanges code and initializes verified profile before redirect',async()=>{
    const f=fixture({intent:intent()});await f.run('completeGoogleSignIn()');
    assert.equal(f.calls.filter(c=>c[0]==='exchange').length,1);
    assert.equal(f.calls.find(c=>c[0]==='fetch')[1],'/api/auth/bootstrap');
    assert.equal(f.calls.find(c=>c[0]==='redirect')[1],'/profile');
    assert.equal(f.store.has('catrank_oauth_intent'),false);
    assert.equal(f.calls[0][0],'history');
});

test('expired callback never exchanges a code',async()=>{
    const f=fixture({intent:{...intent(),started:Date.now()-700000}});await f.run('completeGoogleSignIn()');
    assert.ok(!f.calls.some(c=>c[0]==='exchange'));
    assert.match(f.status.textContent,/expired/);
});

test('a linking callback for another account is rejected and signed out locally',async()=>{
    const f=fixture({intent:{...intent(),userId:'original'},userId:'different'});await f.run('completeGoogleSignIn()');
    assert.equal(f.calls.find(c=>c[0]==='signout')[1].scope,'local');
    assert.ok(!f.calls.some(c=>c[0]==='redirect'));
});

test('external return destinations cannot redirect users away from CatRank',async()=>{
    const f=fixture({intent:intent('https://evil.invalid/steal')});await f.run('completeGoogleSignIn()');
    assert.equal(f.calls.find(c=>c[0]==='redirect')[1],'/');
});

test('failed profile initialization is shown instead of reporting login complete',async()=>{
    const f=fixture({intent:intent(),bootstrapOK:false});await f.run('completeGoogleSignIn()');
    assert.equal(f.status.textContent,'Profile unavailable');
    assert.ok(!f.calls.some(c=>c[0]==='redirect'));
});

test('cancelled Google consent is handled without code exchange',async()=>{
    const f=fixture({intent:intent()});f.context.window.location.search='?error=access_denied';
    await f.run('completeGoogleSignIn()');
    assert.ok(!f.calls.some(c=>c[0]==='exchange'));
    assert.match(f.status.textContent,/cancelled/);
});
