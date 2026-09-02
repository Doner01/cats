const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture(fetch) {
  const elements = new Map();
  const listeners = new Map();
  function element(id, text='') {
    const classes = new Set();
    const node={id,innerText:text,textContent:text,src:'',value:'',scrollTop:0,dataset:{},style:{},children:[],attributes:{},classList:{
      add(...names){names.forEach(name=>classes.add(name))},
      remove(...names){names.forEach(name=>classes.delete(name))},
      contains(name){return classes.has(name)},
      toggle(name,force){const value=force===undefined?!classes.has(name):force;value?classes.add(name):classes.delete(name);return value}
    },setAttribute(k,v){this.attributes[k]=v},appendChild(el){this.children.push(el)},addEventListener(){},querySelector(){return null},focus(){}};
    elements.set(id,node); return node;
  }
  ['modal-like-count','modal-heart-icon','modal-cat-name','modal-cat-img','modal-cat-bio-box','modal-cat-bio-text','modal-comments-list','modal-comments-count','modal-comments-count-badge','modal-comment-input','cat-detail-modal'].forEach(id=>element(id,id==='modal-like-count'?'0':''));
  ['modal-prev-cat','modal-next-cat','cat-detail-scroll','modal-comment-submit-btn','custom-confirm-modal'].forEach(id=>element(id));
  ['cat-detail-modal','modal-prev-cat','modal-next-cat','custom-confirm-modal'].forEach(id=>elements.get(id).classList.add('hidden'));
  element('modal-comments-items');
  const context=vm.createContext({console,setTimeout:()=>0,URL,URLSearchParams,Map,Set,Date,CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail}},
    document:{getElementById:id=>elements.get(id)||null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(name,callback){if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push(callback)},createElement:()=>element('created'),body:{style:{}}},
    window:{location:{href:'https://cats.example/',origin:'https://cats.example',search:''},addEventListener(name,callback){if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push(callback)},dispatchEvent(event){(listeners.get(event.type)||[]).forEach(fn=>fn(event))}},fetch,showToast(){},supabaseClient:{auth:{getSession:async()=>({data:{session:{access_token:'test',user:{id:'user-a'}}}})}},currentSession:{access_token:'test',user:{id:'user-a'}}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/main.js'),'utf8'),context);
  return {context,element,elements,listeners,run:source=>vm.runInContext(source,context)};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('bio expands inline safely without moving the comments scroll position',async()=>{
 const bio='  First paragraph.\n\nSecond <script>literal</script> paragraph.  ';
 const f=fixture(async url=>({ok:true,json:async()=>url.endsWith('/comments')?{comments:[]}:{cat:{name:'Cat',bio}}}));
 const button=f.element('modal-bio-more');
 const box=f.elements.get('modal-cat-bio-box');
 const preview=f.elements.get('modal-cat-bio-text');
 preview.scrollHeight=108;preview.clientHeight=36;
 await f.run("openCatModal('cat-a')");
 assert.equal(preview.textContent,'First paragraph. Second <script>literal</script> paragraph.');
 assert.equal(button.classList.contains('hidden'),false);
 assert.equal(button.attributes['aria-expanded'],'false');
 assert.equal(box.classList.contains('is-expanded'),false);
 f.elements.get('modal-comments-list').scrollTop=180;
 f.run('toggleCatBio()');
 assert.equal(preview.textContent,bio.trim());
 assert.equal(box.classList.contains('is-expanded'),true);
 assert.equal(button.attributes['aria-expanded'],'true');
 assert.equal(button.textContent,'Show less');
 assert.equal(preview.attributes.tabindex,'0');
 assert.equal(f.elements.get('modal-comments-list').scrollTop,180);
 f.run('toggleCatBio()');
 assert.equal(preview.textContent,'First paragraph. Second <script>literal</script> paragraph.');
 assert.equal(box.classList.contains('is-expanded'),false);
 assert.equal(button.attributes['aria-expanded'],'false');
 assert.equal(preview.attributes.tabindex,'-1');
 assert.equal(f.elements.get('modal-comments-list').scrollTop,180);
 preview.scrollHeight=18;preview.clientHeight=18;
 f.run('updateCatBioPreview()');
 assert.equal(button.classList.contains('hidden'),true);
 f.run('closeCatModal()');
 assert.equal(preview.textContent,'');
 assert.equal(f.run('activeModalBio'),'');
});

test('arrow keys still navigate after expanding and reset the next bio',async()=>{
 const f=fixture(async url=>({ok:true,json:async()=>url.endsWith('/comments')?{comments:[]}:{cat:{name:'Cat',bio:'Some bio'}}}));
 const button=f.element('modal-bio-more');
 const a=f.element('a');a.dataset.catModalId='cat-a';
 const b=f.element('b');b.dataset.catModalId='cat-b';
 f.context.document.querySelectorAll=selector=>selector==='[data-cat-modal-id]'?[a,b]:[];
 await f.run("openCatModal('cat-a')");f.run('toggleCatBio()');
 f.listeners.get('keydown').forEach(fn=>fn({key:'ArrowRight',target:{tagName:'BUTTON'},preventDefault(){}}));
 await tick();
 assert.equal(f.run('activeModalCatId'),'cat-b');
 assert.equal(f.elements.get('modal-cat-bio-box').classList.contains('is-expanded'),false);
 assert.equal(button.attributes['aria-expanded'],'false');
});

test('expanded bio retains its collapse control when text fits after resizing',async()=>{
 const f=fixture(async url=>({ok:true,json:async()=>url.endsWith('/comments')?{comments:[]}:{cat:{name:'Cat',bio:'Full bio'}}}));
 const button=f.element('modal-bio-more');
 const text=f.elements.get('modal-cat-bio-text');
 text.scrollHeight=100;text.clientHeight=36;
 await f.run("openCatModal('cat-a')");
 f.run('toggleCatBio()');
 text.scrollHeight=100;text.clientHeight=100;
 f.run('updateCatBioPreview()');
 assert.equal(button.classList.contains('hidden'),false);
 assert.equal(text.attributes.tabindex,'-1');
 f.run('toggleCatBio()');
 assert.equal(button.classList.contains('hidden'),true);
});

function favoriteFixture(fetch) {
 const f=fixture(fetch);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/favorites.js'),'utf8'),f.context);
 f.run("favoritesOwnerId='user-a';favoritesReady=true");
 return f;
}

test('favorites use PUT and DELETE without changing likes',async()=>{
 const methods=[];
 const f=favoriteFixture(async(url,options)=>{methods.push(options.method);return {ok:true,json:async()=>({saved:options.method==='PUT'})}});
 await f.run("toggleFavorite('cat-a')");
 assert.equal(f.run("userFavoriteCatIds.has('cat-a')"),true);
 assert.equal(f.run("userLikedCatIds.size"),0);
 await f.run("toggleFavorite('cat-a')");
 assert.deepEqual(methods,['PUT','DELETE']);
 assert.equal(f.run("userFavoriteCatIds.has('cat-a')"),false);
});

test('failed favorites roll back and rapid clicks cannot duplicate writes',async()=>{
 let resolve;let calls=0;
 const f=favoriteFixture(()=>{calls++;return new Promise(r=>resolve=r)});
 const pending=f.run("toggleFavorite('cat-a')");await tick();
 assert.equal(f.run("userFavoriteCatIds.has('cat-a')"),true);
 await f.run("toggleFavorite('cat-a')");assert.equal(calls,1);
 resolve({ok:false,json:async()=>({error:'offline'})});await pending;
 assert.equal(f.run("userFavoriteCatIds.has('cat-a')"),false);
 assert.equal(f.run('pendingFavorites.size'),0);
});

test('signing out discards late favorites responses even after signing back in',async()=>{
 let resolve;
 const f=favoriteFixture(()=>new Promise(r=>resolve=r));
 const pending=f.run("toggleFavorite('cat-a')");await tick();
 f.run("resetFavorites();favoritesOwnerId='user-a';favoritesReady=true");
 resolve({ok:true,json:async()=>({saved:true})});await pending;
 assert.equal(f.run('userFavoriteCatIds.size'),0);
});

test('saved IDs never transfer to another account',async()=>{
 let resolve;
 const f=favoriteFixture(()=>new Promise(r=>resolve=r));
 f.run('favoritesReady=false');
 const pending=f.run('syncUserFavorites()');
 f.run("resetFavorites();favoritesOwnerId='user-b'");
 resolve({ok:true,json:async()=>({favorite_cat_ids:['cat-a']})});
 assert.equal(await pending,false);
 assert.equal(f.run('userFavoriteCatIds.size'),0);
});

test('signed out viewers get a login prompt and return to the same cat',()=>{
 const f=fixture(async()=>({ok:true}));
 const form=f.element('modal-comment-form');
 const prompt=f.element('modal-login-prompt');
 const link=f.element('modal-login-link');
 f.context.currentSession=null;
 f.run("activeModalCatId='cat-a';updateModalAuth()");
 assert.equal(form.classList.contains('hidden'),true);
 assert.equal(prompt.classList.contains('hidden'),false);
 assert.equal(new URL(link.href,'https://cats.example').searchParams.get('next'),'/?cat=cat-a');
 f.context.currentSession={user:{id:'user-a'}};
 f.run('updateModalAuth()');
 assert.equal(form.classList.contains('hidden'),false);
 assert.equal(prompt.classList.contains('hidden'),true);
});

test('a double-click on an already liked photo does not remove the like',()=>{
 let calls=0;const f=fixture(()=>{calls++;return Promise.resolve({ok:true})});
 f.run("activeModalCatId='cat-a';userLikedCatIds.add('cat-a');likeModalPhoto()");
 assert.equal(calls,0);
});

test('login return destinations allow local pages but reject external redirects',()=>{
 const f=fixture(async()=>({ok:true}));
 f.context.supabaseClient.auth.onAuthStateChange=()=>{};
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/auth.js'),'utf8'),f.context);
 for (const next of ['https://evil.example','//evil.example','/\\evil.example','javascript:alert(1)','/login']) {
   f.context.window.location.search='?next='+encodeURIComponent(next);
   assert.equal(f.run('getLoginDestination()'),'/');
 }
 f.context.window.location.search='?next='+encodeURIComponent('/user/owner?cat=cat-a');
 assert.equal(f.run('getLoginDestination()'),'/user/owner?cat=cat-a');
});

test('switching profile tabs discards a late favorites response',async()=>{
 let resolve;
 const f=favoriteFixture(()=>new Promise(r=>resolve=r));
 ['profile-favorites-tab','profile-uploads-tab','favorites-private-note','favorites-pagination','user-cats-grid'].forEach(id=>f.element(id));
 f.context.t=key=>key;
 f.context.safeImageUrl=()=> 'https://images.example/cat.jpg';
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/profile-cats.js'),'utf8'),f.context);
 f.run('configureProfileCats([],true)');
 const pending=f.run("switchProfileCatsTab('favorites')");await tick();
 f.run("switchProfileCatsTab('uploads')");
 const uploads=f.elements.get('user-cats-grid').innerHTML;
 resolve({ok:true,json:async()=>({cats:[{id:'late',name:'Late favorite'}]})});await pending;
 assert.equal(f.elements.get('user-cats-grid').innerHTML,uploads);
 assert.equal(f.run('profileCatsState.tab'),'uploads');
});

test('profile tabs render escaped uploader links and keep favorites private',()=>{
 const f=favoriteFixture(async()=>({ok:true}));
 ['profile-favorites-tab','profile-uploads-tab','favorites-private-note','favorites-pagination','user-cats-grid'].forEach(id=>f.element(id));
 f.context.t=key=>key;
 f.context.safeImageUrl=()=> 'https://images.example/cat.jpg';
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/profile-cats.js'),'utf8'),f.context);
 f.run(`configureProfileCats([{id:'cat-a',user_id:'owner',name:'<script>bad</script>',user_name:'Owner',likes_count:2}], false)`);
 const html=f.elements.get('user-cats-grid').innerHTML;
 assert.ok(html.includes('/user/owner'));
 assert.ok(html.includes('&lt;script&gt;'));
 assert.ok(!html.includes('<script>'));
 assert.ok(!html.includes('deleteMyCat'));
 assert.equal(f.elements.get('profile-favorites-tab').classList.contains('hidden'),true);
 f.run("switchProfileCatsTab('favorites')");
 assert.equal(f.run('profileCatsState.tab'),'uploads');
});

test('feed votes use the feed count and roll back after a failed request',async()=>{
 let resolve;const f=fixture(()=>new Promise(r=>resolve=r));
 f.element('like-count-cat-a','42');f.element('heart-icon-cat-a','🤍');
 const pending=f.run("toggleLike('cat-a')");await tick();
 assert.equal(f.elements.get('like-count-cat-a').innerText,43);
 resolve({ok:false,json:async()=>({error:'offline'})});await pending;
 assert.equal(f.elements.get('like-count-cat-a').innerText,42);
 assert.equal(f.run("pendingLikes.size"),0);
});

test('rapid double clicks send only one vote request',async()=>{
 let resolve;let requests=0;const f=fixture(()=>{requests++;return new Promise(r=>resolve=r)});
 f.element('like-count-cat-a','42');f.element('heart-icon-cat-a','🤍');
 const a=f.run("toggleLike('cat-a')");await tick();await f.run("toggleLike('cat-a')");
 assert.equal(requests,1);resolve({ok:true,json:async()=>({status:'liked',likes_count:43})});await a;
 assert.equal(f.elements.get('like-count-cat-a').innerText,43);
});

test('a different open modal cannot change the feed vote count',async()=>{
 const f=fixture(async()=>({ok:true,json:async()=>({status:'liked',likes_count:43})}));
 f.element('like-count-cat-a','42');f.element('heart-icon-cat-a','🤍');
 f.elements.get('modal-like-count').innerText='999';f.elements.get('modal-heart-icon').innerText='❤️';
 f.run("activeModalCatId='cat-b'");await f.run("toggleLike('cat-a')");
 assert.equal(f.elements.get('modal-like-count').innerText,'999');
 assert.equal(f.elements.get('like-count-cat-a').innerText,43);
});

test('late cat details cannot overwrite a newer modal',async()=>{
 const pending={};const f=fixture(url=>{
 if(url.endsWith('/comments'))return Promise.resolve({ok:true,json:async()=>({comments:[]})});
 return new Promise(resolve=>pending[url]=resolve);
 });
 const a=f.run("openCatModal('cat-a')");const b=f.run("openCatModal('cat-b')");
 pending['/api/cats/cat-b']({ok:true,json:async()=>({cat:{name:'Second',likes_count:20}})});await b;
 pending['/api/cats/cat-a']({ok:true,json:async()=>({cat:{name:'First',likes_count:10}})});await a;
 assert.equal(f.elements.get('modal-cat-name').innerText,'Second');
});

test('a closed modal ignores pending responses',async()=>{
 let resolve;const f=fixture(()=>new Promise(r=>resolve=r));
 const pending=f.run("openCatModal('cat-a')");f.run('closeCatModal()');
 resolve({ok:true,json:async()=>({cat:{name:'Late'}})});await pending;
 assert.equal(f.elements.get('modal-cat-name').innerText,'');
});

test('comment failures show a retry instead of an empty discussion',async()=>{
 const f=fixture(async()=>({ok:false,json:async()=>({error:'offline'})}));
 f.run("activeModalCatId='cat-a'");await f.run("loadCatComments('cat-a')");
 assert.equal(f.elements.get('modal-comments-items').textContent,'Could not load comments. ');
 assert.equal(f.elements.get('modal-comments-items').children[0].textContent,'Try again');
});

test('modal arrows move through the visible cats and wrap around',async()=>{
 const f=fixture(async url=>({ok:true,json:async()=>url.endsWith('/comments')?{comments:[]}:{cat:{name:url.split('/').pop(),likes_count:0}}}));
 const first=f.element('first-card');first.dataset.catModalId='cat-a';
 const second=f.element('second-card');second.dataset.catModalId='cat-b';
 const third=f.element('third-card');third.dataset.catModalId='cat-c';
 f.context.document.querySelectorAll=selector=>selector==='[data-cat-modal-id]'?[first,second,third]:[];
 await f.run("openCatModal('cat-b')");
 await f.run('navigateCatModal(1)');
 assert.equal(f.run('activeModalCatId'),'cat-c');
 await f.run('navigateCatModal(1)');
 assert.equal(f.run('activeModalCatId'),'cat-a');
 await f.run('navigateCatModal(-1)');
 assert.equal(f.run('activeModalCatId'),'cat-c');
});

test('switching cats resets the comments scroll position',async()=>{
 const f=fixture(async url=>({ok:true,json:async()=>url.endsWith('/comments')?{comments:[]}:{cat:{name:'Cat'}}}));
 const content=f.elements.get('cat-detail-scroll');
 const comments=f.elements.get('modal-comments-list');
 content.scrollTop=450;
 comments.scrollTop=300;
 await f.run("openCatModal('cat-a')");
 assert.equal(content.scrollTop,0);
 assert.equal(comments.scrollTop,0);
 assert.equal(f.elements.get('cat-detail-modal').classList.contains('hidden'),false);
 f.run('closeCatModal()');
 assert.equal(f.elements.get('cat-detail-modal').classList.contains('hidden'),true);
});

test('arrows appear for multiple cats and repeated cards are deduplicated',async()=>{
 const f=fixture(async url=>({ok:true,json:async()=>url.endsWith('/comments')?{comments:[]}:{cat:{name:'Cat'}}}));
 const a=f.element('a');a.dataset.catModalId='cat-a';
 const b=f.element('b');b.dataset.catModalId='cat-b';
 f.context.document.querySelectorAll=selector=>selector==='[data-cat-modal-id]'?[a,b,a]:[];
 await f.run("openCatModal('cat-a')");
 assert.deepEqual(Array.from(f.run('getModalCatIds()')),['cat-a','cat-b']);
 assert.equal(f.elements.get('modal-prev-cat').classList.contains('hidden'),false);
 assert.equal(f.elements.get('modal-next-cat').classList.contains('hidden'),false);
 f.context.document.querySelectorAll=selector=>selector==='[data-cat-modal-id]'?[a]:[];
 f.run('updateModalNavigation()');
 assert.equal(f.elements.get('modal-next-cat').classList.contains('hidden'),true);
});

test('keyboard navigation ignores typing and confirmation dialogs',async()=>{
 const f=fixture(async url=>({ok:true,json:async()=>url.endsWith('/comments')?{comments:[]}:{cat:{name:'Cat'}}}));
 const a=f.element('a');a.dataset.catModalId='cat-a';
 const b=f.element('b');b.dataset.catModalId='cat-b';
 f.context.document.querySelectorAll=selector=>selector==='[data-cat-modal-id]'?[a,b]:[];
 await f.run("openCatModal('cat-a')");
 const press=target=>f.listeners.get('keydown').forEach(fn=>fn({key:'ArrowRight',target,preventDefault(){}}));
 press({tagName:'INPUT'});
 assert.equal(f.run('activeModalCatId'),'cat-a');
 f.elements.get('custom-confirm-modal').classList.remove('hidden');
 press({tagName:'BUTTON'});
 assert.equal(f.run('activeModalCatId'),'cat-a');
 f.elements.get('custom-confirm-modal').classList.add('hidden');
 press({tagName:'BUTTON'});
 assert.equal(f.run('activeModalCatId'),'cat-b');
 await tick();
});

test('comments from an earlier visit cannot replace a reopened cat',async()=>{
 let resolve;const f=fixture(()=>new Promise(r=>resolve=r));
 f.run("activeModalCatId='cat-a';modalRequestVersion=1");
 const pending=f.run("loadCatComments('cat-a')");
 f.run('modalRequestVersion=3');
 f.elements.get('modal-comments-items').innerHTML='Newest comments';
 resolve({ok:true,json:async()=>({comments:[]})});await pending;
 assert.equal(f.elements.get('modal-comments-items').innerHTML,'Newest comments');
});

test('switching during auth cannot submit the next cats draft',async()=>{
 let resolveSession;let posts=0;
 const f=fixture(async()=>{posts++;return {ok:true}});
 f.context.supabaseClient.auth.getSession=()=>new Promise(r=>resolveSession=r);
 f.run("activeModalCatId='cat-a'");
 f.elements.get('modal-comment-input').value='First draft';
 const pending=f.run('submitComment()');
 f.run("activeModalCatId='cat-b';modalRequestVersion++");
 f.elements.get('modal-comment-input').value='Second draft';
 resolveSession({data:{session:{access_token:'test'}}});await pending;
 assert.equal(posts,0);
 assert.equal(f.elements.get('modal-comment-input').value,'Second draft');
});

test('comment pagination appends and deduplicates repeated rows',async()=>{
 const root={id:'c1',user_id:'user-a',user_name:'A',comment:'first',created_at:'2026-09-01'};
 const second={...root,id:'c2',comment:'second'};
 const f=fixture(async url=>({ok:true,json:async()=>url.includes('cursor=')?{comments:[root,second],next_cursor:null,total:null}:{comments:[root],next_cursor:'page2',total:2}}));
 f.run("activeModalCatId='cat-a'");
 await f.run("loadCatComments('cat-a')");
 await f.run("loadCatComments('cat-a', true)");
 assert.equal(f.run('loadedComments.length'),2);
 assert.equal(f.run('commentsTotal'),2);
 assert.equal(f.run('nextCommentsCursor'),null);
});

test('newly posted comments remain visible outside the first page',async()=>{
 const f=fixture(async()=>({ok:true,json:async()=>({comments:[{id:'old',user_id:'user-a',comment:'old'}],total:250,next_cursor:'page2'})}));
 f.run("activeModalCatId='cat-a'");
 await f.run("loadCatComments('cat-a', false, {id:'new',user_id:'user-a',comment:'my new comment'})");
 assert.equal(f.run('loadedComments[0].id'),'new');
 assert.equal(f.run('commentsTotal'),250);
});

test('late page fetch cannot overwrite a fresh comments reload',async()=>{
 let resolvePage;
 const f=fixture(async url=>url.includes('cursor=')?new Promise(resolve=>{resolvePage=resolve}):({ok:true,json:async()=>({comments:[{id:'root',comment:'fresh'}],next_cursor:'page2',total:2})}));
 f.run("activeModalCatId='cat-a'");await f.run("loadCatComments('cat-a')");
 const oldPage=f.run("loadCatComments('cat-a',true)");
 await f.run("loadCatComments('cat-a')");
 resolvePage({ok:true,json:async()=>({comments:[{id:'stale',comment:'stale'}],next_cursor:null})});await oldPage;
 assert.equal(f.run("loadedComments.some(c=>c.id==='stale')"),false);
});
