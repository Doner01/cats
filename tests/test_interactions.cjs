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
    },setAttribute(k,v){this.attributes[k]=v},appendChild(el){this.children.push(el)},addEventListener(){},querySelector(){return null}};
    elements.set(id,node); return node;
  }
  ['modal-like-count','modal-heart-icon','modal-cat-name','modal-cat-img','modal-cat-bio-box','modal-cat-bio-text','modal-comments-list','modal-comments-count','modal-comments-count-badge','modal-comment-input','cat-detail-modal'].forEach(id=>element(id,id==='modal-like-count'?'0':''));
  ['modal-prev-cat','modal-next-cat','cat-detail-scroll','modal-comment-submit-btn','custom-confirm-modal'].forEach(id=>element(id));
  ['cat-detail-modal','modal-prev-cat','modal-next-cat','custom-confirm-modal'].forEach(id=>elements.get(id).classList.add('hidden'));
  const context=vm.createContext({console,setTimeout:()=>0,URL,Map,Set,Date,
    document:{getElementById:id=>elements.get(id)||null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(name,callback){if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push(callback)},createElement:()=>element('created'),body:{style:{}}},
    window:{addEventListener(){}},fetch,showToast(){},supabaseClient:{auth:{getSession:async()=>({data:{session:{access_token:'test'}}})}},currentSession:{access_token:'test'}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/main.js'),'utf8'),context);
  return {context,element,elements,listeners,run:source=>vm.runInContext(source,context)};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

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
 assert.equal(f.elements.get('modal-comments-list').textContent,'Could not load comments. ');
 assert.equal(f.elements.get('modal-comments-list').children[0].textContent,'Try again');
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
 f.elements.get('modal-comments-list').innerHTML='Newest comments';
 resolve({ok:true,json:async()=>({comments:[]})});await pending;
 assert.equal(f.elements.get('modal-comments-list').innerHTML,'Newest comments');
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
